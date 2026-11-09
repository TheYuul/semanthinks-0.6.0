"""
build_reference.py - subject reference table: one row per subject x program with the official curriculum
course(s) (code, year, term), the keywords, and the syllabus topics (official or draft).

    python tools/build_reference.py --out data/subject_reference.csv
"""
import argparse, csv, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_catalog import build_subjects

COLS = ["subject_id", "program", "subject_label", "curriculum_courses", "year_term", "keywords", "official_topics", "draft_topics", "topic_source"]


def rows(xlsx):
    subjects, _, courses = build_subjects(xlsx)
    for s in subjects:
        cs = courses.get(s["id"], [])
        official = [t[0] for t in s["topics"] if len(t) == 2]
        draft = [t[0] for t in s["topics"] if len(t) > 2]
        for p in s["programs"]:
            mine = [c for c in cs if c["program"] == p]
            yield {"subject_id": s["id"], "program": p, "subject_label": s["labels"][p],
                   "curriculum_courses": "; ".join(f"{c['code']} {c['title']}" for c in mine) or "(no official syllabus provided)",
                   "year_term": "; ".join(f"Y{c['year']} T{c['term']}" for c in mine),
                   "keywords": "; ".join(s["keywords"]), "official_topics": "; ".join(official), "draft_topics": "; ".join(draft),
                   "topic_source": "official+draft" if official and draft else "official" if official else "draft (team must review)"}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--keywords", default=str(HERE / "Keywords.xlsx")); ap.add_argument("--out", default="data/subject_reference.csv")
    a = ap.parse_args()
    data = list(rows(a.keywords))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, COLS); w.writeheader(); w.writerows(data)
    print(f"wrote {a.out}: {len(data)} rows")


if __name__ == "__main__":
    main()
