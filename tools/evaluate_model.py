"""
evaluate_model.py - figures and a summary table for the model evaluation.

  python tools/evaluate_model.py                     (from the project root, after run_pipeline.py has finished)
  python tools/evaluate_model.py --report results/report.json --baseline results/baseline.txt --out results/figures

Reads results/report.json (written by training/train_fusion.py) and, if present, results/baseline.txt.
Everything plotted is a measured value from the cross-validated test folds; nothing is simulated.
Positive class = distracting (hidden). FPR = share of RELEVANT items that were wrongly hidden.
"""
import argparse, json, re
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

C = {"precision": "#2563eb", "recall": "#0d9488", "f1": "#7c3aed", "false_positive_rate": "#c2410c", "accuracy": "#64748b"}
NAMES = {"accuracy": "Accuracy", "precision": "Precision", "recall": "Recall", "f1": "F1", "false_positive_rate": "FPR"}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False})


def save(fig, out, name):
    fig.tight_layout(); fig.savefig(out / name, dpi=160); plt.close(fig); print("wrote", out / name)


def parse_baseline(path):
    """Lines like: `cosine-only   accuracy=0.544±0.027  precision=0.915±0.023 ...`; tolerant of how ± was encoded."""
    rows = {}
    if not Path(path).exists(): return rows
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^\s*(.+?)\s{2,}(accuracy=.*)$", line)
        if not m: continue
        vals = {k: (float(v), float(sd) if sd else 0.0) for k, v, sd in re.findall(r"(\w+)=([0-9.]+)(?:\D{1,3}([0-9.]+))?", m.group(2))}
        if "f1" in vals: rows[m.group(1).strip()] = vals
    return rows


def grouped(ax, labels, series, keys, errs=None, cap=None):
    x = np.arange(len(labels)); w = 0.8 / len(keys)
    for i, k in enumerate(keys):
        vals = [s[k] for s in series]; e = None if errs is None else [er[k] for er in errs]
        bars = ax.bar(x + (i - (len(keys) - 1) / 2) * w, vals, w, yerr=e, capsize=2.5, color=C[k], label=NAMES[k], error_kw={"lw": 0.9})
        for b, v in zip(bars, vals): ax.text(b.get_x() + b.get_width() / 2, v + 0.012 + (0 if e is None else 0.02), f"{v:.2f}", ha="center", va="bottom", fontsize=7.5)
    ax.set_xticks(x); ax.set_xticklabels(labels); ax.set_ylim(0, 1.12); ax.set_ylabel("score")
    if cap is not None: ax.axhline(cap, color=C["false_positive_rate"], ls="--", lw=0.9, label=f"FPR target {cap:.0%}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default="results/report.json"); ap.add_argument("--baseline", default="results/baseline.txt")
    ap.add_argument("--out", default="results/figures")
    a = ap.parse_args()
    r = json.loads(Path(a.report).read_text(encoding="utf-8")); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    folds, summ = r["folds"], r["summary"]; cap = r.get("args", {}).get("max_fpr", 0.05)
    keys = ["precision", "recall", "f1", "false_positive_rate"]
    md = ["# Model evaluation summary", "", f"{len(folds)}-fold cross-validation, headline = real items under the program context.", ""]

    # 1. headline, mean ± sd over folds
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    grouped(ax, ["Headline (all real items)"], [{k: summ[k]["mean"] for k in NAMES}], ["accuracy"] + keys, [{k: summ[k]["std"] for k in NAMES}], cap)
    ax.set_title(f"Mean ± sd over {len(folds)} folds"); ax.legend(frameon=False, ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.08))
    save(fig, out, "01_headline_metrics.png")

    # 2. per fold
    fig, ax = plt.subplots(figsize=(8, 4))
    grouped(ax, [f"Fold {f['fold']}" for f in folds], [f["test"] for f in folds], keys, None, cap)
    ax.set_title("Metrics per test fold"); ax.legend(frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.1))
    save(fig, out, "02_per_fold.png")

    # 3. per category (the three categories of the study)
    cats = [("video_youtube", "Video (YouTube)"), ("online_articles", "Online articles"), ("documents_repositories", "Documents / repositories")]
    have = [(k, n) for k, n in cats if k in r]
    if have:
        fig, ax = plt.subplots(figsize=(8, 4))
        ser = [{m: r[k][m]["mean"] for m in NAMES} for k, _ in have] + [{m: summ[m]["mean"] for m in NAMES}]
        err = [{m: r[k][m]["std"] for m in NAMES} for k, _ in have] + [{m: summ[m]["std"] for m in NAMES}]
        grouped(ax, [n for _, n in have] + ["All real items"], ser, keys, err, cap)
        ax.set_title("Results by content category (mean ± sd over folds)"); ax.legend(frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.1))
        save(fig, out, "03_by_category.png")
        md += ["## By category (mean over folds)", "", "| Category | F1 | Precision | Recall | FPR |", "|---|---|---|---|---|"]
        md += [f"| {n} | " + " | ".join(f"{s[m]:.3f}" for m in ["f1", "precision", "recall", "false_positive_rate"]) + " |" for (_, n), s in zip(have + [(0, "All real items")], ser)] + [""]

    # 4. confusion matrix summed over folds (headline rows)
    tp, tn, fp, fn = (sum(f["test"][k] for f in folds) for k in ("tp", "tn", "fp", "fn"))
    cm = np.array([[tn, fp], [fn, tp]], float); norm = cm / cm.sum(axis=1, keepdims=True)
    fig, ax = plt.subplots(figsize=(4.8, 4.2))
    ax.imshow(norm, cmap="Blues", vmin=0, vmax=1)
    for i in range(2):
        for j in range(2): ax.text(j, i, f"{int(cm[i, j]):,}\n{norm[i, j]:.1%}", ha="center", va="center", color="white" if norm[i, j] > 0.5 else "#0f172a", fontsize=11)
    ax.set_xticks([0, 1]); ax.set_xticklabels(["kept", "hidden"]); ax.set_yticks([0, 1]); ax.set_yticklabels(["relevant", "distracting"])
    ax.set_xlabel("system action"); ax.set_ylabel("true label"); ax.set_title("Confusion matrix (all test folds, row-normalised)", fontsize=10)
    for s in ax.spines.values(): s.set_visible(False)
    save(fig, out, "04_confusion_matrix.png")
    md += ["## Confusion matrix (sum over test folds)", "", f"TN {int(tn):,} | FP {int(fp):,} | FN {int(fn):,} | TP {int(tp):,}", ""]

    # 5. model vs baselines
    base = parse_baseline(a.baseline)
    if base:
        names = list(base) + ["Late-fusion model"]
        ser = [{m: v[m][0] for m in NAMES if m in v} for v in base.values()] + [{m: summ[m]["mean"] for m in NAMES}]
        err = [{m: v[m][1] for m in NAMES if m in v} for v in base.values()] + [{m: summ[m]["std"] for m in NAMES}]
        fig, ax = plt.subplots(figsize=(8, 4))
        grouped(ax, names, ser, keys, err, cap)
        ax.set_title("Trained model vs. baselines (mean ± sd over folds)"); ax.legend(frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.1))
        save(fig, out, "05_vs_baselines.png")
        gain = ser[-1]["f1"] - max(s["f1"] for s in ser[:-1])
        md += ["## Against the baselines", "", "| Method | F1 | Recall | Precision | FPR |", "|---|---|---|---|---|"]
        md += [f"| {n} | " + " | ".join(f"{s[m]:.3f}" for m in ["f1", "recall", "precision", "false_positive_rate"]) + " |" for n, s in zip(names, ser)]
        md += ["", f"F1 gain over the best baseline: **{gain:+.3f}**.", ""]

    # 6. other test sets: how much easier / weaker each is than the headline
    sets = [("heldout_keywords", "Held-out keywords"), ("keyword_focus_rows_weak_labels", "Keyword focus\n(weak labels)"), ("subject_context_rows", "Subject context\n(augmented)")]
    sets = [(k, n) for k, n in sets if k in r]
    if sets:
        fig, ax = plt.subplots(figsize=(7.4, 3.9))
        ser = [{m: summ[m]["mean"] for m in NAMES}] + [{m: r[k][m]["mean"] for m in NAMES} for k, _ in sets]
        err = [{m: summ[m]["std"] for m in NAMES}] + [{m: r[k][m]["std"] for m in NAMES} for k, _ in sets]
        grouped(ax, ["Headline"] + [n for _, n in sets], ser, keys, err, cap)
        ax.set_title("Other test sets (read with care: some use weak labels)"); ax.legend(frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.14))
        save(fig, out, "06_other_test_sets.png")

    # 7. subject head
    if "subjects" in r:
        s = r["subjects"]; ks = [("micro_f1", "Micro-F1"), ("macro_f1", "Macro-F1"), ("top1", "Top-1 accuracy")]
        fig, ax = plt.subplots(figsize=(5.4, 3.6))
        v = [s[k]["mean"] for k, _ in ks]; e = [s[k]["std"] for k, _ in ks]
        ax.bar([n for _, n in ks], v, yerr=e, capsize=3, color="#475569", width=0.55)
        for i, x in enumerate(v): ax.text(i, x + e[i] + 0.015, f"{x:.2f}", ha="center", fontsize=9)
        ax.set_ylim(0, 1.05); ax.set_title("Subject head (mean ± sd over folds)"); ax.set_ylabel("score")
        save(fig, out, "07_subject_head.png")
        md += ["## Subject head", "", f"Micro-F1 {s['micro_f1']['mean']:.3f}, macro-F1 {s['macro_f1']['mean']:.3f}, top-1 {s['top1']['mean']:.3f}. Macro-F1 is lower because subjects with very few labeled examples are weak.", ""]

    # 8. tuned decision settings per fold
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.2))
    for ax, (k, t) in zip(axes, [("alpha", "alpha (weight of cosine S)"), ("beta", "beta (subject share of S)"), ("hide_threshold", "hide threshold")]):
        ax.bar([f"F{f['fold']}" for f in folds], [f[k] for f in folds], color="#475569")
        ax.set_title(t, fontsize=10); ax.set_ylim(0, 1.05)
    fig.suptitle("Decision settings chosen on each fold's validation split", fontsize=10)
    save(fig, out, "08_tuned_settings.png")

    # 9. thumbnail rows: image on vs image switched off (text-only mode), and per-kind vs single decision
    k_on, k_off, k_single = "thumbnail_rows_scored_with_image", "thumbnail_rows_image_switched_off_text_only_mode", "headline_single_decision_previous_method"
    if k_on in r and k_off in r:
        fig, axes = plt.subplots(1, 2 if k_single in r else 1, figsize=(10.5 if k_single in r else 6, 4), squeeze=False); axes = axes[0]
        def pair(ax, labels, blocks, title):
            ser = [{m: b[m]["mean"] for m in NAMES} for b in blocks]; err = [{m: b[m]["std"] for m in NAMES} for b in blocks]
            grouped(ax, labels, ser, keys, err, cap); ax.set_title(title, fontsize=10); return ser
        s_ = pair(axes[0], ["With thumbnail", "Thumbnail off\n(text-only mode)"], [r[k_on], r[k_off]], "Items that have a thumbnail")
        if k_single in r: pair(axes[1], ["One decision\n(previous)", "Decision per input kind\n(current)"], [r[k_single], {m: summ[m] for m in NAMES}], "Headline: single vs per-kind decision")
        h_, l_ = axes[0].get_legend_handles_labels(); fig.legend(h_, l_, frameon=False, ncol=5, loc="lower center")
        fig.tight_layout(rect=(0, 0.07, 1, 1)); fig.savefig(out / "09_image_vs_text_only.png", dpi=160); plt.close(fig); print("wrote", out / "09_image_vs_text_only.png")
        md += ["## Thumbnail on vs off (items that have a thumbnail)", "", "| Mode | F1 | Precision | Recall | FPR |", "|---|---|---|---|---|"]
        md += [f"| {n} | " + " | ".join(f"{b[m]['mean']:.3f}" for m in ["f1", "precision", "recall", "false_positive_rate"]) + " |" for n, b in (("With thumbnail", r[k_on]), ("Thumbnail off (text-only mode)", r[k_off]))]
        md += ["", "Text-only mode uses the text decision, which is more conservative: fewer relevant items hidden, fewer distractions caught. It is a different operating point, not a like-for-like F1 comparison.", ""]

    md += ["## Per fold (headline rows)", "", "| Fold | Accuracy | Precision | Recall | F1 | FPR |", "|---|---|---|---|---|---|"]
    md += [f"| {f['fold']} | " + " | ".join(f"{f['test'][m]:.3f}" for m in ["accuracy", "precision", "recall", "f1", "false_positive_rate"]) + " |" for f in folds]
    md += ["| **mean ± sd** | " + " | ".join(f"{summ[m]['mean']:.3f} ± {summ[m]['std']:.3f}" for m in ["accuracy", "precision", "recall", "f1", "false_positive_rate"]) + " |", ""]
    over = [f["fold"] for f in folds if f["test"]["false_positive_rate"] > cap]
    md += [f"FPR target on validation was {cap:.0%}; on the test folds it exceeded that in fold(s) {over}." if over else f"FPR stayed within {cap:.0%} on every test fold.", ""]
    (out / "evaluation_summary.md").write_text("\n".join(md), encoding="utf-8"); print("wrote", out / "evaluation_summary.md")


if __name__ == "__main__":
    main()