"""
extract_features.py - turns dataset.csv (+ thumbnails) into features.npz for train_fusion.py.

    python extract_features.py dataset.csv features.npz [--images-dir thumbnails/]

dataset.csv columns (see DATASET.md):
    id, text, image_path, label, language, source, context, group            (the original columns)
    subjects, ctx_subjects, kind, heldout                                     (optional, from tools/build_training_csv.py)
  label    : relevant | distracting   (or 0 | 1;  1 = distracting)
  context  : the subject text the annotator judged relevance against. Empty = the default CS/IT context.
  image_path may be empty (text-only article/document items).
  subjects : ids of the curriculum subjects the item belongs to, ';'-separated. 'none' = belongs to no subject (known).
             Empty = not labeled (the subject head ignores the row).
  ctx_subjects : subjects that `context` stands for ('' = all subjects). Used to score "is it one of the chosen subjects".
  kind     : base | subject_ctx | focus.   heldout : 1 = a keyword-focus row whose keyword is held out of training.
  group    : video id or channel/site. Rows with the same group are never split across train/validation/test
             (stops near-duplicates from leaking into the test set). Empty = each row is its own group.

Needs the packages from backend/requirements.txt and a Hugging Face login (hf auth login).
NOTE: this script needs the models downloaded, which was not possible where it was written, so it has not
been run. Run it on a machine with internet and check the printed shapes.
"""
import argparse, csv, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from thesis_features import FeatureExtractor, DEFAULT_CONTEXT, TEXT_DIM, IMAGE_DIM


def parse_label(v):
    v = str(v).strip().lower()
    if v in ("1", "distracting", "distraction", "irrelevant"): return 1
    if v in ("0", "relevant", "academic"): return 0
    raise ValueError(f"unknown label {v!r}")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("csv"); ap.add_argument("out"); ap.add_argument("--images-dir", default=".")
    ap.add_argument("--catalog", default=str(Path(__file__).resolve().parent.parent / "tools" / "Keywords.xlsx"), help="Keywords.xlsx; gives the subject id list")
    ap.add_argument("--distract-context", default="", help="optional text describing NON-CS/IT content; adds cosine_distract for the zero-shot baseline")
    args = ap.parse_args()
    rows = list(csv.DictReader(open(args.csv, encoding="utf-8")))
    fx = FeatureExtractor()
    # Text is embedded in batches (tens of thousands of rows). Identical texts (the same item under several contexts)
    # and identical images are embedded once.
    uniq_text = sorted({r["text"] for r in rows}); tmap = dict(zip(uniq_text, fx.embed_texts(uniq_text)))
    texts = [tmap[r["text"]] for r in rows]
    ctx_texts = [(r.get("context") or "").strip() or DEFAULT_CONTEXT for r in rows]
    unique = sorted(set(ctx_texts)); ctx_cache = dict(zip(unique, fx.embed_texts(unique)))
    dist_vec = fx.embed_texts([args.distract_context])[0] if args.distract_context else None
    cosine_d = []
    with_subjects = any(k in rows[0] for k in ("subjects", "ctx_subjects"))
    subject_ids = []
    if with_subjects:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
        from build_catalog import build_subjects
        subject_ids = [s["id"] for s in build_subjects(args.catalog)[0]]
    sidx = {sid: i for i, sid in enumerate(subject_ids)}

    def multi_hot(cell, row_id):
        v = np.zeros(len(subject_ids), np.float32)
        for tok in [t.strip() for t in (cell or "").split(";") if t.strip() and t.strip().lower() != "none"]:
            if tok not in sidx: raise ValueError(f"row {row_id}: unknown subject id {tok!r}")
            v[sidx[tok]] = 1.0
        return v

    ids, text, image, cosine, y, has_image, groups = [], [], [], [], [], [], []
    subj, subj_known, ctx_subj, kinds, heldout = [], [], [], [], []
    img_cache = {}
    for i, r in enumerate(rows):
        t, ctx_text = texts[i], ctx_texts[i]
        path = (r.get("image_path") or "").strip()
        v, ok = np.zeros(IMAGE_DIM), False
        if path:
            if path in img_cache: v, ok = img_cache[path]
            else:
                f = Path(args.images_dir) / path
                if f.exists():
                    try: v, ok = fx.embed_image(f.read_bytes()), True
                    except Exception as e: print(f"row {r.get('id', i)}: image unreadable ({e}); treated as no image")
                else: print(f"row {r.get('id', i)}: image {f} not found; treated as no image")
                img_cache[path] = (v, ok)
        rid = r.get("id", str(i))
        ids.append(rid); text.append(t); image.append(v.astype(np.float32)); has_image.append(ok)
        groups.append((r.get("group") or "").strip() or rid)
        if dist_vec is not None: cosine_d.append(float(t @ dist_vec))
        cosine.append(float(t @ ctx_cache[ctx_text])); y.append(parse_label(r["label"]))
        if with_subjects:
            cell = (r.get("subjects") or "").strip()
            subj.append(multi_hot(cell, rid)); subj_known.append(bool(cell))          # "none" counts as known (no subject)
            ctx_subj.append(multi_hot(r.get("ctx_subjects"), rid))
        kinds.append((r.get("kind") or "base").strip() or "base")
        heldout.append(str(r.get("heldout") or "0").strip() in ("1", "true", "True"))
        if (i + 1) % 500 == 0: print(f"{i + 1}/{len(rows)}")
    extra = {}
    if dist_vec is not None: extra["cosine_distract"] = np.array(cosine_d)
    if with_subjects:
        extra.update(subject_ids=np.array(subject_ids), subjects=np.array(subj, np.float32), subject_known=np.array(subj_known),
                     ctx_subjects=np.array(ctx_subj, np.float32))
    np.savez_compressed(args.out, ids=np.array(ids), text=np.array(text, dtype=np.float32), image=np.array(image, dtype=np.float32),
                        cosine=np.array(cosine), y=np.array(y), has_image=np.array(has_image), groups=np.array(groups),
                        kind=np.array(kinds), heldout=np.array(heldout), **extra)
    print(f"saved {args.out}: text {np.array(text).shape}, image {np.array(image).shape}, {sum(has_image)} with image, {sum(y)} distracting"
          + (f", {int(np.sum(subj_known))} rows with subject labels over {len(subject_ids)} subjects" if with_subjects else ""))


if __name__ == "__main__":
    main()
