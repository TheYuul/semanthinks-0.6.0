"""
merge_labels.py - turns filled subject sheets (xlsx or csv, one per annotator) into data/labeling/subject_labels.csv.

    python tools/merge_labels.py data/labeling/subject_sheet_A_filled.xlsx data/labeling/subject_sheet_B_filled.xlsx [--adjudicated adj.csv]

Per item: status ok (one annotator), agreed (same subject set), conflict (annotators differ: listed in
conflicts_for_adjudication.csv; supply the final answer with --adjudicated id,subjects), not_csit (flagged: the relevant label is
doubtful, listed in label_flags.csv), empty (nothing filled; skipped). Report: coverage per subject against --target and agreement
(Cohen's kappa on subject_1, mean Jaccard) on items labeled by two annotators.
"""
import argparse
from pathlib import Path
import pandas as pd

import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_catalog import build_subjects
from score_audit import kappa


def read_sheet(path):
    df = pd.read_excel(path, sheet_name="label", dtype=str) if str(path).endswith(".xlsx") else pd.read_csv(path, dtype=str)
    return df.fillna("")


def parse(df, valid, name, problems):
    out = {}
    for _, r in df.iterrows():
        ids = [r.get(c, "").strip() for c in ("subject_1", "subject_2", "subject_3") if r.get(c, "").strip()]
        bad = [i for i in ids if i not in valid]
        if bad: problems.append((name, r["id"], f"unknown subject id(s) {bad}")); ids = [i for i in ids if i in valid]
        flagged = r.get("not_csit", "").strip().upper() == "Y"
        if ids or flagged: out[r["id"]] = {"subjects": list(dict.fromkeys(ids)), "not_csit": flagged}
    return out


def merge(sheets, valid, adjudicated=None):
    """sheets: {annotator: parsed dict}. Returns (rows, conflicts, flags, problems-free stats)."""
    rows, conflicts, flags = [], [], []
    adjudicated = adjudicated or {}
    for rid in sorted({i for s in sheets.values() for i in s}):
        votes = {a: s[rid] for a, s in sheets.items() if rid in s}
        hum = [a for a in votes if "human" in a.lower()]
        if hum:   # a human check decides, whatever the AI said
            hv = votes[hum[0]]; others = [v for a, v in votes.items() if a != hum[0]]
            if hv["not_csit"]:
                flags.append({"id": rid, "annotators": hum[0], "note": "human says not CS/IT: review the relevant/distracting label"})
                rows.append({"id": rid, "subjects": "", "status": "not_csit", "annotators": ";".join(votes)}); continue
            same = all(not o["not_csit"] and tuple(sorted(o["subjects"])) == tuple(sorted(hv["subjects"])) for o in others)
            rows.append({"id": rid, "subjects": ";".join(hv["subjects"]), "status": "agreed" if same and others else ("human_override" if others else "ok"), "annotators": ";".join(votes)}); continue
        if any(v["not_csit"] for v in votes.values()):
            flags.append({"id": rid, "annotators": ";".join(a for a, v in votes.items() if v["not_csit"]), "note": "annotator says not CS/IT: review the relevant/distracting label"})
            rows.append({"id": rid, "subjects": "", "status": "not_csit", "annotators": ";".join(votes)}); continue
        sets = {a: tuple(sorted(v["subjects"])) for a, v in votes.items()}
        if len(set(sets.values())) == 1:
            rows.append({"id": rid, "subjects": ";".join(next(iter(votes.values()))["subjects"]), "status": "agreed" if len(votes) > 1 else "ok", "annotators": ";".join(votes)})
        elif rid in adjudicated:
            rows.append({"id": rid, "subjects": adjudicated[rid], "status": "adjudicated", "annotators": ";".join(votes)})
        else:
            conflicts.append({"id": rid, **{a: ";".join(v["subjects"]) for a, v in votes.items()}})
            rows.append({"id": rid, "subjects": "", "status": "conflict", "annotators": ";".join(votes)})
    return rows, conflicts, flags


def agreement(sheets):
    names = list(sheets)
    if len(names) < 2: return None
    a, b = sheets[names[0]], sheets[names[1]]
    shared = [i for i in a if i in b and not a[i]["not_csit"] and not b[i]["not_csit"] and a[i]["subjects"] and b[i]["subjects"]]
    if not shared: return None
    jac = [len(set(a[i]["subjects"]) & set(b[i]["subjects"])) / len(set(a[i]["subjects"]) | set(b[i]["subjects"])) for i in shared]
    return {"n": len(shared), "kappa_subject_1": kappa([a[i]["subjects"][0] for i in shared], [b[i]["subjects"][0] for i in shared]),
            "mean_jaccard": sum(jac) / len(jac), "annotators": names[:2]}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("sheets", nargs="+"); ap.add_argument("--adjudicated"); ap.add_argument("--target", type=int, default=60)
    ap.add_argument("--keywords", default=str(HERE / "Keywords.xlsx")); ap.add_argument("--out", default="data/labeling")
    a = ap.parse_args()
    subjects, _, _ = build_subjects(a.keywords); valid = {s["id"] for s in subjects}
    problems, parsed = [], {}
    for p in a.sheets: parsed[Path(p).stem] = parse(read_sheet(p), valid, Path(p).stem, problems)
    adj = dict(pd.read_csv(a.adjudicated, dtype=str).fillna("")[["id", "subjects"]].values) if a.adjudicated else {}
    rows, conflicts, flags = merge(parsed, valid, adj)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out / "subject_labels.csv", index=False)
    pd.DataFrame(conflicts).to_csv(out / "conflicts_for_adjudication.csv", index=False); pd.DataFrame(flags).to_csv(out / "label_flags.csv", index=False)
    good = [r for r in rows if r["status"] in ("ok", "agreed", "adjudicated", "human_override") and r["subjects"]]
    counts = {s["id"]: sum(1 for r in good if s["id"] in r["subjects"].split(";")) for s in subjects}
    ag = agreement(parsed)
    lines = ["# Subject labeling report", "", f"- usable labels: {len(good)}  |  conflicts: {len(conflicts)}  |  flagged not CS/IT: {len(flags)}  |  problems: {len(problems)}"]
    if ag: lines.append(f"- agreement ({ag['annotators'][0]} vs {ag['annotators'][1]}, {ag['n']} shared items): kappa on subject_1 = {ag['kappa_subject_1']:.3f}, mean Jaccard = {ag['mean_jaccard']:.3f}")
    lines += ["", f"## Coverage (target {a.target} per subject)"] + [f"- {k}: {v}{'  <-- below target' if v < a.target else ''}" for k, v in sorted(counts.items(), key=lambda kv: kv[1])]
    if problems: lines += ["", "## Problems"] + [f"- {n} / {i}: {m}" for n, i, m in problems[:50]]
    (out / "subject_label_report.md").write_text("\n".join(lines) + "\n"); print("\n".join(lines))


if __name__ == "__main__":
    main()
