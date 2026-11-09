"""
eda.py - exploratory data analysis of the Semanthinks dataset, with figures.

  python tools/eda.py                      (from the project root)
  python tools/eda.py --clean data/clean/dataset_clean.csv --training data/clean/training.csv --out results/eda

Writes PNG figures and eda_summary.md into --out. Needs pandas, numpy, matplotlib. Labels: relevant / distracting.
Counts come straight from the CSVs; nothing here is estimated.
"""
import argparse, re
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REL, DIS = "#2a7f62", "#c2410c"          # relevant / distracting (consistent across figures)
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 110})


def save(fig, out, name):
    fig.tight_layout(); fig.savefig(out / name, dpi=160); plt.close(fig); print("wrote", out / name)


def tbl(df):
    try: return df.to_markdown()
    except ImportError: return "```\n" + df.to_string() + "\n```"     # tabulate is not installed


def host(url):
    m = re.match(r"https?://([^/]+)/?", url or "")
    return m.group(1).replace("www.", "") if m else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", default="data/clean/dataset_clean.csv"); ap.add_argument("--training", default="data/clean/training.csv")
    ap.add_argument("--rejects", default="data/clean/rejects.csv"); ap.add_argument("--out", default="results/eda")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    d = pd.read_csv(a.clean, dtype=str, keep_default_na=False)
    d["words"] = d["text"].str.split().str.len()
    d["host"] = d["source_url"].map(host)
    md = ["# Exploratory data analysis", "", f"Cleaned dataset: **{len(d):,}** rows ({(d.label == 'distracting').sum():,} distracting, {(d.label == 'relevant').sum():,} relevant).", ""]

    # 1. class balance by source (the three study categories)
    ct = pd.crosstab(d["source"], d["label"]).reindex(columns=["relevant", "distracting"], fill_value=0)
    fig, ax = plt.subplots(figsize=(6.2, 3.8))
    ct.plot.bar(stacked=True, ax=ax, color=[REL, DIS], width=0.6, rot=0)
    for i, (idx, row) in enumerate(ct.iterrows()):
        ax.text(i, row.sum() + ct.values.sum() * 0.005, f"{row.sum():,}\n({row['distracting'] / row.sum():.0%} distracting)", ha="center", va="bottom", fontsize=9)
    ax.set_ylim(0, ct.sum(axis=1).max() * 1.3); ax.set_xlabel(""); ax.set_ylabel("rows"); ax.set_title("Rows and class balance by source"); ax.legend(title="label", frameon=False, loc="upper left", ncol=2)
    save(fig, out, "01_class_balance_by_source.png")
    md += ["## Class balance by source", "", tbl(ct.assign(total=ct.sum(axis=1), pct_distracting=(ct["distracting"] / ct.sum(axis=1)).round(3))), ""]

    # 2. text length by label and source
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.6), sharey=True)
    for ax, (src, g) in zip(axes, d.groupby("source")):
        cap = g["words"].quantile(0.99)
        for lab, col in (("relevant", REL), ("distracting", DIS)):
            ax.hist(g.loc[g.label == lab, "words"].clip(upper=cap), bins=40, alpha=0.6, color=col, label=lab, density=True)
        ax.set_title(f"{src} (median {g['words'].median():.0f} words)"); ax.set_xlabel("words per item (99th pct cap)")
    axes[0].set_ylabel("density"); axes[0].legend(frameon=False)
    save(fig, out, "02_text_length.png")
    md += ["## Text length (words)", "", tbl(d.groupby(["source", "label"])["words"].describe()[["count", "mean", "50%", "max"]].round(1)), ""]

    # 3. language
    lg = pd.crosstab(d["language"], d["label"]).reindex(columns=["relevant", "distracting"], fill_value=0)
    fig, ax = plt.subplots(figsize=(5.6, 3.4))
    lg.plot.barh(stacked=True, ax=ax, color=[REL, DIS]); ax.set_xlabel("rows"); ax.set_ylabel(""); ax.set_title("Language of the items"); ax.legend(frameon=False)
    for i, v in enumerate(lg.sum(axis=1)): ax.text(v, i, f" {v:,}", va="center", fontsize=9)
    ax.set_xlim(0, lg.sum(axis=1).max() * 1.18)
    save(fig, out, "03_language.png")
    md += ["## Language", "", tbl(lg.assign(total=lg.sum(axis=1))), "", "Almost all items are English; Taglish and Tagalog are a small share, which limits any claim about Filipino-language performance.", ""]

    # 4. top domains
    top = d[d.host != ""].groupby("host").agg(n=("id", "size"), dist=("label", lambda s: (s == "distracting").mean())).sort_values("n", ascending=False).head(15)
    fig, ax = plt.subplots(figsize=(7, 4.6))
    ax.barh(top.index[::-1], top["n"][::-1], color="#475569")
    for i, (n, p) in enumerate(zip(top["n"][::-1], top["dist"][::-1])): ax.text(n, i, f" {n:,} ({p:.0%} dist.)", va="center", fontsize=8.5)
    ax.set_xlim(0, top["n"].max() * 1.3); ax.set_xlabel("rows"); ax.set_title("Top 15 source domains")
    save(fig, out, "04_top_domains.png")
    md += ["## Top domains", "", tbl(top.assign(pct_distracting=top["dist"].round(3))[["n", "pct_distracting"]]), ""]

    # 5. curriculum domain tags (classes of topic assigned during cleaning)
    dom = pd.crosstab(d["domain"], d["label"]).reindex(columns=["relevant", "distracting"], fill_value=0)
    dom = dom.loc[dom.sum(axis=1).sort_values().index]
    fig, ax = plt.subplots(figsize=(6.4, 0.32 * len(dom) + 1.2))
    dom.plot.barh(stacked=True, ax=ax, color=[REL, DIS]); ax.set_xlabel("rows"); ax.set_ylabel(""); ax.set_title("Topic domain tag (non_csit = outside CS/IT)"); ax.legend(frameon=False)
    save(fig, out, "05_domain_tags.png")

    # 6. cleaning funnel / rejects
    if Path(a.rejects).exists():
        r = pd.read_csv(a.rejects, dtype=str, keep_default_na=False)
        rc = r["reject_reason"].replace("", "unspecified").value_counts().head(10)
        if len(rc):
            fig, ax = plt.subplots(figsize=(7, 3.8))
            ax.barh(rc.index[::-1], rc.values[::-1], color="#64748b")
            for i, v in enumerate(rc.values[::-1]): ax.text(v, i, f" {v:,}", va="center", fontsize=9)
            ax.set_xlim(0, rc.max() * 1.15); ax.set_xlabel("rows removed"); ax.set_title(f"Why rows were removed in cleaning ({len(r):,} total)")
            save(fig, out, "06_cleaning_rejects.png")
            md += ["## Rows removed in cleaning", "", tbl(rc.to_frame("rows")), ""]

    # 7. training-set composition and subject coverage
    if Path(a.training).exists():
        t = pd.read_csv(a.training, dtype=str, keep_default_na=False)
        kinds = t["kind"].value_counts()
        fig, ax = plt.subplots(figsize=(5.8, 3.4))
        ax.bar(kinds.index, kinds.values, color="#475569")
        for i, v in enumerate(kinds.values): ax.text(i, v, f"{v:,}", ha="center", va="bottom", fontsize=9)
        ax.set_ylim(0, kinds.max() * 1.12); ax.set_title("Training-file rows by kind"); ax.set_ylabel("rows")
        save(fig, out, "07_training_kinds.png")
        base = t[(t.kind == "base") & (t.subjects != "")]
        sub = base["subjects"].str.split(";").explode().replace("", np.nan).dropna()
        sub = sub[sub != "none"]                       # "none" = distracting rows (no subject); it would dwarf the real subjects
        sc = sub.value_counts()
        fig, ax = plt.subplots(figsize=(7.2, 0.24 * len(sc) + 1.3))
        cols = ["#c2410c" if v < 30 else "#475569" for v in sc.values[::-1]]
        ax.barh(sc.index[::-1], sc.values[::-1], color=cols)
        for i, v in enumerate(sc.values[::-1]): ax.text(v, i, f" {v}", va="center", fontsize=8)
        ax.set_xscale("symlog"); ax.set_xlabel("labeled real items (log scale)"); ax.set_title("Labeled real items per subject (orange: fewer than 30)", fontsize=10)
        save(fig, out, "08_subject_coverage.png")
        thin = sc[sc < 30]
        md += ["## Subject coverage (real items with a subject label)", "", f"{len(sc)} subjects have at least one labeled real item; **{len(thin)}** have fewer than 30: " + (", ".join(f"{k} ({v})" for k, v in thin.items()) or "none") + ".", "",
               "Training-file rows by kind: " + ", ".join(f"{k} {v:,}" for k, v in kinds.items()) + ".", ""]
    (out / "eda_summary.md").write_text("\n".join(md), encoding="utf-8"); print("wrote", out / "eda_summary.md")


if __name__ == "__main__":
    main()
