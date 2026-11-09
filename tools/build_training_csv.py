"""
build_training_csv.py - the CSV for training/extract_features.py with three context levels.

    python tools/build_training_csv.py --clean data/clean/dataset_clean.csv --labels data/labeling/subject_labels.csv \
        --pairs-key data/labeling/focus_pairs_key.csv --pairs-answers data/labeling/focus_pairs_sheet_filled.csv --out data/clean/training.csv

Rows (column `kind`):
  base         every cleaned item under the program-level context. subjects: "none" for distracting rows (known: no subject),
               the confirmed subject ids for labeled relevant rows, empty (unknown) for the rest.
  subject_ctx  context-swap augmentation for items with confirmed subjects: the item under ITS OWN subject context (relevant) and
               under a context of a subject it does not belong to (distracting for that context). Some distracting items are also
               paired with a random subject context (always distracting).
  catalog      (with --add-catalog) syllabus topics and keywords of the 37 subjects as short texts. TRAINING ONLY: never used for validation/test.
  focus        verified (item, keyword) pairs: context = focus_context([term], [subject]); yes -> relevant, no -> distracting.
               'partly' and unanswered pairs are skipped unless --use-suggested (weak labels, marked in the id).
`group` is the item's group, so all rows derived from one item stay in the same train/validation/test split.
`heldout` = 1 for focus rows whose keyword was held out; train_fusion.py never trains on them.
The context strings are built by subject_context.py, identical to what the extension sends.
"""
import argparse, random
from pathlib import Path
import pandas as pd

import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_catalog import build_subjects
from subject_context import Contexts
from make_focus_pairs import is_heldout


def read_any(p):
    return (pd.read_excel(p, dtype=str) if str(p).endswith(".xlsx") else pd.read_csv(p, dtype=str)).fillna("")


def catalog_rows(subjects, ctx, all_ids, rnd, include_drafts=True, holdout_frac=0.2):
    """Training-only rows made from the catalog: every syllabus topic ('title. detail') and keyword is a short relevant text for its subject.
    Per text: program context (relevant, subject known), another subject's context (distracting for that context) and a keyword-focus
    context built from the topic title (relevant) plus the same text under another subject's focus term (distracting).
    kind = catalog: train_fusion.py never uses these rows for validation or testing. Topic titles whose hash falls in the held-out
    share are marked heldout so they are not trained on either (same rule as make_focus_pairs.py)."""
    rows, n = [], 0
    for s in subjects:
        if s["id"] not in all_ids: continue
        items = [(f"{t[0]}. {t[1]}".strip(". ") if t[1] else t[0], t[0]) for t in s["topics"] if include_drafts or len(t) == 2]
        items += [(k, k) for k in s["keywords"] if len(k) >= 3]
        for text, term in dict.fromkeys(items):
            n += 1; rid = f"cat{n:05d}"
            base = {"id": rid, "text": text[:400], "image_path": "", "label": "relevant", "language": "english", "source": "catalog", "context": ctx.program_text,
                    "group": rid, "subjects": s["id"], "ctx_subjects": "", "kind": "catalog", "heldout": 0}
            other = rnd.choice([o for o in all_ids if o != s["id"]])
            ho = int(is_heldout(term, holdout_frac))
            rows += [base,
                     {**base, "id": rid + "#n", "label": "distracting", "context": ctx.subject_context([other]), "ctx_subjects": other},
                     {**base, "id": rid + "#f", "context": ctx.focus_context([term], [s["id"]]), "ctx_subjects": s["id"], "heldout": ho},
                     {**base, "id": rid + "#g", "label": "distracting", "context": ctx.focus_context([rnd.choice(rnd.choice([x for x in subjects if x["id"] == other])["keywords"] or [other])], [other]),
                      "ctx_subjects": other, "heldout": ho}]
    return rows


def build(clean, labels, subjects, pairs_key=None, answers=None, aug_per_item=1, aug_distracting=0.2, use_suggested=False, program="Both", seed=42, drop_flagged=True,
          add_catalog=False, catalog_drafts=True):
    rnd = random.Random(seed); ctx = Contexts(subjects, program)
    all_ids = [s["id"] for s in subjects if program == "Both" or program in s["programs"]]
    lab = {r["id"]: r for _, r in labels.iterrows()} if labels is not None else {}
    flagged = {i for i, r in lab.items() if r["status"] == "not_csit"}
    usable = {i: r["subjects"] for i, r in lab.items() if r["status"] in ("ok", "agreed", "adjudicated", "human_override") and r["subjects"]}
    cols = ["id", "text", "image_path", "label", "language", "source", "context", "group", "subjects", "ctx_subjects", "kind", "heldout"]
    rows, base = [], {}
    for _, r in clean.iterrows():
        if drop_flagged and r["id"] in flagged: continue
        subj = "none" if r["label"] == "distracting" else usable.get(r["id"], "")
        row = {"id": r["id"], "text": r["text"], "image_path": r["image_path"], "label": r["label"], "language": r["language"], "source": r["source"],
               "context": ctx.program_text, "group": r["group"], "subjects": subj, "ctx_subjects": "", "kind": "base", "heldout": 0}
        rows.append(row); base[r["id"]] = row
    n_aug = 0
    for rid, row in list(base.items()):
        mine = [s for s in row["subjects"].split(";") if s and s != "none"]
        if mine:
            for j in range(aug_per_item):
                s_in = rnd.choice(mine); others = [s for s in all_ids if s not in mine]
                rows.append({**row, "id": f"{rid}#p{j}", "label": "relevant", "context": ctx.subject_context([s_in]), "ctx_subjects": s_in, "kind": "subject_ctx"})
                if others:
                    s_out = rnd.choice(others)
                    rows.append({**row, "id": f"{rid}#n{j}", "label": "distracting", "context": ctx.subject_context([s_out]), "ctx_subjects": s_out, "kind": "subject_ctx"}); n_aug += 2
        elif row["subjects"] == "none" and rnd.random() < aug_distracting:
            s_out = rnd.choice(all_ids)
            rows.append({**row, "id": f"{rid}#d", "context": ctx.subject_context([s_out]), "ctx_subjects": s_out, "kind": "subject_ctx"}); n_aug += 1
    n_focus = skipped = 0
    if pairs_key is not None:
        ans = {}
        if answers is not None:
            ans = {r["pair_id"]: r["answer"].strip().lower() for _, r in answers.iterrows() if r["answer"].strip()}
        for _, p in pairs_key.iterrows():
            a = ans.get(p["pair_id"]) or (p["suggested"] if use_suggested else "")
            if a not in ("yes", "no") or p["id"] not in base or base[p["id"]]["subjects"] in ("", "none"): skipped += 1; continue
            b = base[p["id"]]
            rows.append({**b, "id": p["pair_id"] + ("" if p["pair_id"] in ans else "~weak"), "label": "relevant" if a == "yes" else "distracting",
                         "context": ctx.focus_context([p["focus"]], [p["focus_subject"]]), "ctx_subjects": p["focus_subject"], "kind": "focus", "heldout": int(p["heldout"])}); n_focus += 1
    n_cat = 0
    if add_catalog:
        cat = catalog_rows(subjects, ctx, all_ids, rnd, catalog_drafts); rows += cat; n_cat = len(cat)
    out = pd.DataFrame(rows)[cols]
    return out, {"catalog": n_cat, "base": len(base), "subject_ctx": n_aug, "focus": n_focus, "focus_skipped": skipped, "labeled_relevant": len(usable), "dropped_flagged": len(flagged) if drop_flagged else 0}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--clean", required=True); ap.add_argument("--labels"); ap.add_argument("--pairs-key"); ap.add_argument("--pairs-answers")
    ap.add_argument("--aug-per-item", type=int, default=1); ap.add_argument("--aug-distracting", type=float, default=0.2); ap.add_argument("--use-suggested", action="store_true")
    ap.add_argument("--add-catalog", action="store_true", help="add syllabus topics and keywords as training-only rows"); ap.add_argument("--no-catalog-drafts", action="store_true")
    ap.add_argument("--program", default="Both", choices=["CS", "IT", "Both"]); ap.add_argument("--keywords", default=str(HERE / "Keywords.xlsx"))
    ap.add_argument("--out", default="data/clean/training.csv"); ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    subjects, _, _ = build_subjects(a.keywords)
    out, st = build(read_any(a.clean), read_any(a.labels) if a.labels else None, subjects, read_any(a.pairs_key) if a.pairs_key else None,
                    read_any(a.pairs_answers) if a.pairs_answers else None, a.aug_per_item, a.aug_distracting, a.use_suggested, a.program, a.seed,
                    add_catalog=a.add_catalog, catalog_drafts=not a.no_catalog_drafts)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True); out.to_csv(a.out, index=False); print(st, "->", a.out, f"({len(out)} rows)")


if __name__ == "__main__":
    main()
