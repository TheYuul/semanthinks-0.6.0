"""
make_focus_pairs.py - (item, focus keyword) pairs for the keyword-focus filter.

    python tools/make_focus_pairs.py data/clean/dataset_clean.csv data/labeling/subject_labels.csv --out data/labeling

For items with confirmed subjects it builds, from the catalog keywords and syllabus topics:
  pos        a term of the item's subject that appears in the text   (suggested: yes)
  neg_same   a term of the SAME subject that does not appear         (hard negative; suggested: no, but the item may still cover it)
  neg_other  a term of ANOTHER subject that does not appear          (easy negative; suggested: no)
Outputs: focus_pairs_sheet.csv (id, text, focus, answer: yes/partly/no; for annotators, WITHOUT the suggestion) and
focus_pairs_key.csv (pair_id, item id, focus, focus_subject, kind, suggested, heldout). Humans verify a sample (~1000 pairs):
the suggested labels are weak and are only used for training with --use-suggested in build_training_csv.py.
heldout: a fixed share of focus TERMS (by hash) is held out of training so unseen-keyword generalisation can be tested.
"""
import argparse, hashlib, random, re
from pathlib import Path
import pandas as pd

import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_catalog import build_subjects
from clean_dataset import norm_text

GUIDE = """# Focus-pair guideline
Question: does this item actually teach or discuss the FOCUS topic (not just the general subject)?
- yes     : the focus topic is a main or clearly covered part of the item
- partly  : mentioned or touched on, but not the point of the item
- no      : not about the focus topic (even if it is about the same subject)
Judge the text shown only.
"""


def is_heldout(term, frac):
    return int(hashlib.md5(term.lower().encode()).hexdigest(), 16) % 100 < int(frac * 100)


def term_pool(subjects):
    """subject id -> clean list of focus terms (keywords + syllabus topic titles, 3-60 chars)."""
    pool = {}
    for s in subjects:
        terms = [t.strip() for t in s["keywords"] + [t[0] for t in s["topics"]]]
        pool[s["id"]] = list(dict.fromkeys(t for t in terms if 3 <= len(t) <= 60))
    return pool


def appears(term, ntext):
    nt = norm_text(term)
    return bool(nt) and re.search(rf"(^| ){re.escape(nt)}(s|es)?( |$)", ntext) is not None


def make_pairs(items, subjects, per_item=2, holdout_frac=0.2, seed=42):
    """items: DataFrame with id, text, subjects (';' ids). Returns a list of pair dicts."""
    rnd = random.Random(seed); pool = term_pool(subjects); ids = list(pool)
    pairs = []
    for _, r in items.iterrows():
        sids = [x for x in r["subjects"].split(";") if x in pool]
        if not sids: continue
        nt = norm_text(r["text"]); sid = sids[0]
        hits = [t for s_ in sids for t in pool[s_] if appears(t, nt)]
        misses_same = [t for s_ in sids for t in pool[s_] if not appears(t, nt)]
        others = [(o, t) for o in ids if o not in sids for t in pool[o] if not appears(t, nt)]
        made = []
        if hits: made.append(("pos", sid, max(hits, key=len), "yes"))
        if misses_same: made.append(("neg_same", sid, rnd.choice(misses_same), "no"))
        if others: o, t = rnd.choice(others); made.append(("neg_other", o, t, "no"))
        rnd.shuffle(made)
        for kind, fs, term, sug in made[:max(per_item, 1)]:
            pairs.append({"pair_id": f"{r['id']}~{len(pairs)}", "id": r["id"], "focus": term, "focus_subject": fs, "kind": kind, "suggested": sug,
                          "heldout": int(is_heldout(term, holdout_frac))})
    return pairs


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("clean"); ap.add_argument("labels"); ap.add_argument("--per-item", type=int, default=2)
    ap.add_argument("--holdout-frac", type=float, default=0.2); ap.add_argument("--sheet-n", type=int, default=1000, help="pairs put on the annotator sheet")
    ap.add_argument("--keywords", default=str(HERE / "Keywords.xlsx")); ap.add_argument("--out", default="data/labeling"); ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    subjects, _, _ = build_subjects(a.keywords)
    clean = pd.read_csv(a.clean, dtype=str, keep_default_na=False)
    lab = pd.read_csv(a.labels, dtype=str, keep_default_na=False)
    lab = lab[lab["status"].isin(["ok", "agreed", "adjudicated"]) & (lab["subjects"] != "")]
    items = clean.merge(lab[["id", "subjects"]], on="id")
    pairs = make_pairs(items, subjects, a.per_item, a.holdout_frac, a.seed)
    key = pd.DataFrame(pairs); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    key.to_csv(out / "focus_pairs_key.csv", index=False)
    text = dict(zip(items["id"], items["text"])); lang = dict(zip(items["id"], items["language"]))
    sheet = key.sample(min(a.sheet_n, len(key)), random_state=a.seed)
    pd.DataFrame({"pair_id": sheet["pair_id"], "text": [text[i][:700] for i in sheet["id"]], "language": [lang[i] for i in sheet["id"]],
                  "focus": sheet["focus"], "answer": "", "note": ""}).to_csv(out / "focus_pairs_sheet.csv", index=False, encoding="utf-8-sig")
    (out / "focus_guideline.md").write_text(GUIDE)
    print(f"{len(key)} pairs ({key['kind'].value_counts().to_dict()}), {int(key['heldout'].sum())} with held-out focus terms; sheet: {len(sheet)} rows")


if __name__ == "__main__":
    main()
