"""
make_label_sheet.py - subject-labeling workbook for RELEVANT rows (distracting rows need no subject: they get "none").

    python tools/make_label_sheet.py data/clean/dataset_clean.csv --n 1500 --overlap 150 --out data/labeling

Writes subject_sheet_A.xlsx (everyone's main sheet) and, with --overlap, subject_sheet_B.xlsx (the same N overlap rows for a
SECOND annotator, to measure agreement). Overlap rows are never pre-filled in either sheet, so the agreement is not inflated.
Each sheet: id, text, language, suggested, subject_1..3 (dropdown of catalog ids), not_csit (Y = this is not CS/IT at all), note.
Suggestions come from the cleaner's domain code and keyword matches. They are NOT ground truth. --prefill copies the top
suggestion into subject_1 for speed (anchoring risk: annotators may accept it too readily; overlap rows stay blind).
The sample is spread across subjects so rare subjects are represented.
"""
import argparse, random
from collections import defaultdict
from pathlib import Path
import pandas as pd
import openpyxl
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.styles import Alignment, Font

import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_catalog import build_subjects

GUIDE = ("Pick up to 3 curriculum subjects the item is mainly useful for (subject_1 = best fit). Use the dropdown ids (see the 'subjects' sheet). "
         "Judge the text only. If the item is NOT about CS/IT, type Y in not_csit and leave the subjects empty (this flags a wrong relevant/distracting label).")


def suggest(row, order):
    """Ranked subject ids: keyword-matched subjects score 2, domain-mapped subjects 1."""
    score = defaultdict(int)
    for sid in [x for x in str(row.get("keyword_subjects", "")).split(";") if x]: score[sid] += 2
    for sid in [x for x in str(row.get("domain_subjects", "")).split(";") if x]: score[sid] += 1
    return sorted(score, key=lambda sid: (-score[sid], order[sid]))[:3]


def sample_rows(df, n, order, seed):
    rnd = random.Random(seed)
    df = df.assign(_top=[(suggest(r, order) or ["_none"])[0] for _, r in df.iterrows()])
    groups = {k: g.index.tolist() for k, g in df.groupby("_top")}
    for g in groups.values(): rnd.shuffle(g)
    quota = max(1, -(-n // len(groups)))
    picked = [i for g in groups.values() for i in g[:quota]]
    rest = [i for g in groups.values() for i in g[quota:]]
    rnd.shuffle(rest); picked += rest[:max(0, n - len(picked))]
    rnd.shuffle(picked)
    return df.loc[picked[:n]]


def write_book(path, rows, subjects, prefill_ids, order, prefill):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "label"
    ws.append(["id", "text", "language", "suggested", "subject_1", "subject_2", "subject_3", "not_csit", "note"])
    for c in ws[1]: c.font = Font(bold=True)
    for _, r in rows.iterrows():
        sug = suggest(r, order)
        pre = sug[0] if (prefill and r["id"] not in prefill_ids and sug) else ""
        ws.append([r["id"], r["text"][:700], r["language"], "; ".join(sug), pre, "", "", "", ""])
    ref = wb.create_sheet("subjects")
    ref.append(["id", "CS label", "IT label", "keywords (first 8)"])
    for s in subjects: ref.append([s["id"], s["labels"]["CS"] or "", s["labels"]["IT"] or "", ", ".join(s["keywords"][:8])])
    dv = DataValidation(type="list", formula1=f"=subjects!$A$2:$A${len(subjects) + 1}", allow_blank=True, showErrorMessage=True)
    ws.add_data_validation(dv); dv.add(f"E2:G{len(rows) + 1}")
    dv2 = DataValidation(type="list", formula1='"Y"', allow_blank=True); ws.add_data_validation(dv2); dv2.add(f"H2:H{len(rows) + 1}")
    for col, w in zip("ABCDEFGHI", (12, 90, 10, 28, 22, 22, 22, 10, 30)): ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=2):
        row[1].alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "C2"
    g = wb.create_sheet("guide"); g.append([GUIDE])
    wb.save(path)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("csv"); ap.add_argument("--n", type=int, default=1500)
    ap.add_argument("--overlap", type=int, default=0); ap.add_argument("--prefill", action="store_true")
    ap.add_argument("--exclude", default=None, help="subject_labels.csv; ids already labeled are skipped")
    ap.add_argument("--keywords", default=str(HERE / "Keywords.xlsx")); ap.add_argument("--out", default="data/labeling"); ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    subjects, _, _ = build_subjects(a.keywords); order = {s["id"]: i for i, s in enumerate(subjects)}
    df = pd.read_csv(a.csv, dtype=str, keep_default_na=False)
    df = df[df["label"] == "relevant"]
    if a.exclude and Path(a.exclude).exists():
        df = df[~df["id"].isin(set(pd.read_csv(a.exclude, dtype=str)["id"]))]
    rows = sample_rows(df.reset_index(drop=True), a.n, order, a.seed)
    overlap_ids = set(rows["id"].head(a.overlap))
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    write_book(out / "subject_sheet_A.xlsx", rows, subjects, overlap_ids, order, a.prefill)
    if a.overlap: write_book(out / "subject_sheet_B.xlsx", rows[rows["id"].isin(overlap_ids)], subjects, overlap_ids, order, False)
    print(f"wrote {len(rows)} rows to {out}/subject_sheet_A.xlsx" + (f" and {len(overlap_ids)} blind overlap rows to subject_sheet_B.xlsx" if a.overlap else ""))


if __name__ == "__main__":
    main()
