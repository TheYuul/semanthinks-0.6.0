"""
subject_audit.py - human check of the AI-assisted subject labels (blind), in two steps.

  1) make sheets (random sample of the AI-labeled items, split between members; subjects are NOT shown):
       python tools/subject_audit.py make --n 200 --parts 4
     -> data/audit_subjects/subject_audit_1.xlsx ... _4.xlsx   (give one to each member)
        data/audit_subjects/subject_audit_key.csv              (the AI labels; do NOT share with annotators)
  2) score the filled sheets:
       python tools/subject_audit.py score data/audit_subjects/subject_audit_1_filled.xlsx ... [--out data/labeling]
     -> prints agreement with the AI labels and writes data/labeling/human_subject_labels.csv (the humans' answers),
        which you pass to the pipeline:  python run_pipeline.py --redo ... --extra-labels data/labeling/human_subject_labels.csv

Sheet columns: id, text, language, subject_1..3 (dropdown), not_csit (Y = not about CS/IT at all), note.
"""
import argparse, random, sys
from pathlib import Path
import pandas as pd
import openpyxl
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.styles import Alignment, Font

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_catalog import build_subjects
from score_audit import wilson, kappa

GUIDE = ("Blind check. For each item pick up to 3 subjects it is mainly useful for (subject_1 = best fit) from the dropdown (see the 'subjects' sheet). "
         "If it is NOT about CS/IT at all, type Y in not_csit and leave the subjects empty. Judge the text only; do not look up or ask what the AI said.")


def write_book(path, rows, subjects):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "label"
    ws.append(["id", "text", "language", "subject_1", "subject_2", "subject_3", "not_csit", "note"])
    for c in ws[1]: c.font = Font(bold=True)
    for _, r in rows.iterrows(): ws.append([r["id"], str(r["text"])[:700], r["language"], "", "", "", "", ""])
    ref = wb.create_sheet("subjects"); ref.append(["id", "CS label", "IT label", "keywords (first 8)"])
    for s in subjects: ref.append([s["id"], s["labels"]["CS"] or "", s["labels"]["IT"] or "", ", ".join(s["keywords"][:8])])
    dv = DataValidation(type="list", formula1=f"=subjects!$A$2:$A${len(subjects) + 1}", allow_blank=True, showErrorMessage=True)
    ws.add_data_validation(dv); dv.add(f"D2:F{len(rows) + 1}")
    dv2 = DataValidation(type="list", formula1='"Y"', allow_blank=True); ws.add_data_validation(dv2); dv2.add(f"G2:G{len(rows) + 1}")
    for col, w in zip("ABCDEFGH", (12, 90, 10, 22, 22, 22, 10, 30)): ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=2): row[1].alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "C2"; wb.create_sheet("guide").append([GUIDE]); wb.save(path)


def cmd_make(a):
    subjects, _, _ = build_subjects(a.keywords)
    ai = pd.read_csv(a.ai, dtype=str).fillna(""); data = pd.read_csv(a.data, dtype=str).fillna("")
    m = ai.merge(data[["id", "text", "language"]], on="id")
    m = m.sample(n=min(a.n, len(m)), random_state=a.seed).reset_index(drop=True)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    key = m[["id", "subject_1", "subject_2", "subject_3", "not_csit"]]; key.to_csv(out / "subject_audit_key.csv", index=False)
    for p in range(a.parts):
        write_book(out / f"subject_audit_{p + 1}.xlsx", m.iloc[p::a.parts], subjects)
    print(f"{len(m)} items -> {a.parts} sheets in {out}/ ({key['not_csit'].str.upper().eq('Y').sum()} were flagged not-CS/IT by the AI). Keep subject_audit_key.csv away from annotators.")


def ids_of(r):
    return [r.get(c, "").strip() for c in ("subject_1", "subject_2", "subject_3") if r.get(c, "").strip()]


def cmd_score(a):
    h = pd.concat([pd.read_excel(p, sheet_name="label", dtype=str).fillna("") if str(p).endswith(".xlsx") else pd.read_csv(p, dtype=str).fillna("") for p in a.sheets])
    h = h[(h[["subject_1", "subject_2", "subject_3"]].ne("").any(axis=1)) | (h["not_csit"].str.upper() == "Y")]
    key = pd.read_csv(a.key, dtype=str).fillna("")
    m = h.merge(key, on="id", suffixes=("", "_ai"))
    n = len(m)
    if not n: sys.exit("no filled rows found")
    hn = m["not_csit"].str.upper().eq("Y"); an = m["not_csit"+"_ai"].str.upper().eq("Y")
    flag_agree = (hn == an).mean()
    both = m[~hn & ~an & m["subject_1"].ne("") & m["subject_1_ai"].ne("")]
    same1 = (both["subject_1"] == both["subject_1_ai"]); lo, hi = wilson(int(same1.sum()), len(both))
    overlap = [bool(set(ids_of(r)) & set(ids_of({k[:-3]: v for k, v in r.items() if k.endswith("_ai")}))) for _, r in both.iterrows()]
    jac = []
    for _, r in both.iterrows():
        x = set(ids_of(r)); y = set(ids_of({k[:-3]: v for k, v in r.items() if k.endswith("_ai")}))
        jac.append(len(x & y) / len(x | y))
    lines = [f"human-checked items: {n}",
             f"CS/IT-vs-not flag agreement: {flag_agree:.3f}  (human says not CS/IT: {int(hn.sum())}, AI says not CS/IT: {int(an.sum())})",
             f"items both call CS/IT: {len(both)}",
             f"  main subject identical (subject_1): {same1.mean():.3f}  (95% CI {lo:.3f}-{hi:.3f})",
             f"  any shared subject: {sum(overlap) / max(1, len(overlap)):.3f}",
             f"  mean Jaccard of subject sets: {sum(jac) / max(1, len(jac)):.3f}",
             f"  Cohen's kappa on subject_1: {kappa(both['subject_1'], both['subject_1_ai']):.3f}"]
    print("\n".join(lines))
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    keep = h[["id", "subject_1", "subject_2", "subject_3", "not_csit"]].copy(); keep["note"] = ""
    keep.to_csv(out / "human_subject_labels.csv", index=False)
    (out / "subject_audit_report.md").write_text("# Subject-label human audit\n\n" + "\n".join(f"- {l.strip()}" for l in lines) + "\n")
    print(f"wrote {out / 'human_subject_labels.csv'} and subject_audit_report.md")


def main():
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    m = sp.add_parser("make"); m.add_argument("--n", type=int, default=200); m.add_argument("--parts", type=int, default=4); m.add_argument("--seed", type=int, default=7)
    m.add_argument("--ai", default="data/labeling/ai_labels_claude.csv"); m.add_argument("--data", default="data/clean/dataset_clean.csv")
    m.add_argument("--keywords", default=str(HERE / "Keywords.xlsx")); m.add_argument("--out", default="data/audit_subjects")
    s = sp.add_parser("score"); s.add_argument("sheets", nargs="+"); s.add_argument("--key", default="data/audit_subjects/subject_audit_key.csv"); s.add_argument("--out", default="data/labeling")
    a = ap.parse_args()
    {"make": cmd_make, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    main()
