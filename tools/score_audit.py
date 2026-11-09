"""
score_audit.py - compares the annotators' blind labels with the dataset labels.

    python tools/score_audit.py data/audit/audit_sheet.csv data/audit/audit_key.csv [--second other_annotator.csv]

Prints agreement with the dataset label (Wilson 95% CI), the estimated label-noise rate, Cohen's kappa, and the
per-label disagreement. With --second (another annotator's sheet), also prints inter-annotator kappa.
Label strings: relevant / distracting / unsure (unsure rows are skipped).
"""
import argparse, math
import pandas as pd


def wilson(k, n, z=1.96):
    if n == 0: return (0.0, 0.0)
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def kappa(a, b):
    a, b = list(a), list(b); n = len(a)
    if n == 0: return float("nan")
    po = sum(x == y for x, y in zip(a, b)) / n
    cats = set(a) | set(b)
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def score(sheet, key, second=None):
    m = sheet.merge(key, on="id")
    m = m[m["annotator_label"].isin(["relevant", "distracting"])]
    n = len(m); agree = int((m["annotator_label"] == m["label"]).sum())
    lo, hi = wilson(agree, n)
    res = {"n": n, "agreement": agree / n if n else float("nan"), "ci": (lo, hi), "noise_rate": 1 - agree / n if n else float("nan"),
           "kappa": kappa(m["annotator_label"], m["label"]),
           "disagree_by_label": m[m["annotator_label"] != m["label"]]["label"].value_counts().to_dict(),
           "disagree_by_domain": m[m["annotator_label"] != m["label"]]["domain"].value_counts().head(8).to_dict()}
    if second is not None:
        j = sheet.merge(second[["id", "annotator_label"]], on="id", suffixes=("", "_2"))
        j = j[j["annotator_label"].isin(["relevant", "distracting"]) & j["annotator_label_2"].isin(["relevant", "distracting"])]
        res["inter_annotator_kappa"] = kappa(j["annotator_label"], j["annotator_label_2"]); res["inter_n"] = len(j)
    return res


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("sheet"); ap.add_argument("key"); ap.add_argument("--second")
    a = ap.parse_args()
    r = score(pd.read_csv(a.sheet, dtype=str, keep_default_na=False), pd.read_csv(a.key, dtype=str, keep_default_na=False),
              pd.read_csv(a.second, dtype=str, keep_default_na=False) if a.second else None)
    print(f"scored rows: {r['n']}\nagreement with dataset label: {r['agreement']:.3f} (95% CI {r['ci'][0]:.3f}-{r['ci'][1]:.3f})\n"
          f"estimated label noise: {r['noise_rate']:.3f}\nCohen's kappa vs dataset: {r['kappa']:.3f}\n"
          f"disagreements by dataset label: {r['disagree_by_label']}\nby domain: {r['disagree_by_domain']}")
    if "inter_annotator_kappa" in r: print(f"inter-annotator kappa: {r['inter_annotator_kappa']:.3f} (n={r['inter_n']})")


if __name__ == "__main__":
    main()
