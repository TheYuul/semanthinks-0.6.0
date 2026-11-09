"""
make_audit_sample.py - stratified random sample for a BLIND relabeling audit.

    python tools/make_audit_sample.py data/clean/dataset_clean.csv --n 400 --out data/audit

Writes audit_sheet.csv (id, text, language; NO label, domain or curriculum columns, so annotators are blind) and
audit_key.csv (id + original label + domain + curriculum_basis). Give annotators only audit_sheet.csv and
annotation_guideline.md, then run score_audit.py. Sample is stratified by label x domain-group so rare classes show up.
"""
import argparse
from pathlib import Path
import pandas as pd

GUIDE = """# Annotation guideline (blind audit)

For each row decide whether the item is relevant to studying Computer Science / Information Technology
(programming, algorithms, databases, networks, security, software engineering, AI/ML, systems, web, etc.).

Fill the `annotator_label` column with one of:
- relevant      : mainly useful for learning CS/IT topics
- distracting   : entertainment, news, other fields, or only incidentally mentions tech
- unsure        : cannot decide from the text (use sparingly; these are excluded from scoring)

Judge the text shown, not what you guess the original label was. Do not look the item up on other sheets.
Tagalog/Taglish is fine; judge the meaning. Add a short `note` when a row is odd (spam, broken text, wrong language).
"""


def sample(df, n, seed=42):
    df = df.copy()
    df["_stratum"] = df["label"] + "|" + df["domain"].where(df["domain"].isin(df["domain"].value_counts().head(6).index), "rest")
    k = max(1, n // df["_stratum"].nunique())
    parts = [g.sample(min(len(g), k), random_state=seed) for _, g in df.groupby("_stratum")]
    got = pd.concat(parts)
    if len(got) < n:
        rest = df.drop(got.index)
        got = pd.concat([got, rest.sample(min(len(rest), n - len(got)), random_state=seed)])
    return got.sample(frac=1, random_state=seed).head(n)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("csv"); ap.add_argument("--n", type=int, default=400)
    ap.add_argument("--out", default="data/audit"); ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    s = sample(pd.read_csv(a.csv, dtype=str, keep_default_na=False), a.n, a.seed)
    o = Path(a.out); o.mkdir(parents=True, exist_ok=True)
    sheet = s[["id", "text", "language"]].copy(); sheet["annotator_label"] = ""; sheet["note"] = ""
    sheet.to_csv(o / "audit_sheet.csv", index=False, encoding="utf-8-sig")
    s[["id", "label", "domain", "curriculum_basis"]].to_csv(o / "audit_key.csv", index=False)
    (o / "annotation_guideline.md").write_text(GUIDE)
    print(f"wrote {len(s)} rows to {o}")


if __name__ == "__main__":
    main()
