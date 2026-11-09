"""
compare_models.py - three systems on the SAME data split, with validation, a held-out test, ROC-AUC, confusion matrices
and computational measurements.

  A  Rule-based baseline : the keyword rules (word lists copied from extension/content.js and the subject catalog), no learning
  B  Text-only model     : Dense head on [text_256 | cosine]            (257-d input)
  C  Text + Vision model : Dense head on [text_256 | image_1280 | cosine] (1537-d input, the thesis architecture)
  B-LR / C-LR : the same two feature sets with a plain logistic regression instead of the Dense head (the "plug-in" classifier question)

  python training/compare_models.py data/clean/features.npz --out results/compare            (from the project root)
  python training/compare_models.py features.npz --repeats 5 --time-extractors --images-dir thumbnails

Split: 70 / 15 / 15 (train / validation / held-out test), whole items kept together (group-aware). Validation rows tune the
head (early stopping, alpha and the hide threshold, FPR cap). The test rows are used ONCE per split, only to report.
Metrics are on real items (kind = base) with the program context. Positive class = distracting (hidden).
Models B and C use the binary head only, so the comparison isolates the effect of the image features; the deployed
model also has the subject head. --repeats N repeats the whole thing on N different splits and reports mean ± sd.
"""
import argparse, csv, json, re, subprocess, time
from pathlib import Path
import numpy as np
from sklearn.metrics import roc_auc_score, roc_curve
from sklearn.linear_model import LogisticRegression

import sys
sys.path.insert(0, str(Path(__file__).parent))
from fusion_head import DenseHead, score_c, metrics, tune_decision, allow_for, decide
from train_fusion import splits, fit_standardizer, standardize, TEXT_DIM, IMAGE_DIM, IMAGE_SLICE

ROOT = Path(__file__).resolve().parent.parent


# ---------- A: rule-based baseline ----------
def js_list(src, name):
    m = re.search(rf"const {name} = \[(.*?)\];", src, re.S)
    return re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1)) if m else []


def load_rules():
    js = (ROOT / "extension" / "content.js").read_text(encoding="utf-8")
    academic, distracting = js_list(js, "ACADEMIC_TERMS"), js_list(js, "DISTRACTING_TERMS")
    cat = (ROOT / "extension" / "subject-catalog.js").read_text(encoding="utf-8")
    body = cat[cat.index("const SUBJECTS = ") + len("const SUBJECTS = "):]
    subjects = json.loads(body[:body.index("\n];") + 2])
    catalog_kw = sorted({k.lower() for s in subjects for k in s["keywords"]})
    return academic, distracting, catalog_kw


def term_regex(terms):
    return re.compile(r"(?:^|[^a-z0-9])(?:" + "|".join(re.escape(t) for t in sorted(set(terms), key=len, reverse=True)) + r")(?:s|es)?(?:$|[^a-z0-9])", re.I)


def make_rules():
    academic, distracting, catalog_kw = load_rules()
    ac, di, kw = term_regex(academic), term_regex(distracting), term_regex(academic + catalog_kw)
    norm = lambda t: re.sub(r"\s+", " ", t.lower()).strip()
    # A1 = what the extension does without the model: hide only when a distracting word appears and no academic word does.
    a1 = lambda t: bool(di.search(norm(t))) and not ac.search(norm(t))
    # A2 = a plain keyword filter: hide anything that mentions no academic / CS-IT keyword at all.
    a2 = lambda t: not kw.search(norm(t))
    return {"A1 distracting-word rules (extension fallback)": a1, "A2 keyword-match filter (hide if no CS/IT keyword)": a2}


# ---------- models B, C ----------
def fit_variant(X, y, cos, has_img, tr, va, cols, image_dropout, args, seed):
    Xs = X[:, cols]
    t0 = time.time()
    mean, std = fit_standardizer(Xs[tr], has_img[tr])
    Z = (Xs - mean) / std
    if image_dropout is not None:                                   # vision model: neutral image block where there is no thumbnail
        sl = slice(TEXT_DIM, TEXT_DIM + IMAGE_DIM); Z[~has_img, sl] = 0.0
    net = DenseHead(Xs.shape[1], hidden=args.hidden, dropout=args.dropout, seed=seed)
    hist = net.fit(Z[tr], y[tr], Z[va], y[va], epochs=args.epochs, lr=args.lr, image_dropout=image_dropout or 0.0, image_slice=slice(TEXT_DIM, TEXT_DIM + IMAGE_DIM), seed=seed)
    tuned = tune_decision(net.predict(Z[va]), cos[va], y[va], max_fpr=args.max_fpr)
    return {"net": net, "Z": Z, "tuned": tuned, "train_s": time.time() - t0, "epochs": len(hist), "mean": mean, "std": std}


class _LRHead:
    """Wraps a fitted logistic regression so it can be scored like the Dense head (probability of distracting)."""
    def __init__(self, lr): self.lr = lr
    def predict(self, Z): return self.lr.predict_proba(Z)[:, 1]


def fit_lr(X, y, cos, has_img, tr, va, cols, vision, args):
    Xs = X[:, cols]; t0 = time.time()
    mean, std = fit_standardizer(Xs[tr], has_img[tr]); Z = (Xs - mean) / std
    if vision: Z[~has_img, TEXT_DIM:TEXT_DIM + IMAGE_DIM] = 0.0
    lr = LogisticRegression(C=args.lr_c, max_iter=2000); lr.fit(Z[tr], y[tr])
    net = _LRHead(lr)
    tuned = tune_decision(net.predict(Z[va]), cos[va], y[va], max_fpr=args.max_fpr)
    return {"net": net, "Z": Z, "tuned": tuned, "train_s": time.time() - t0, "epochs": int(np.max(lr.n_iter_)), "mean": mean, "std": std, "coef": lr.coef_[0], "bias": float(lr.intercept_[0])}


def lr_latency(v, repeats=2000):
    x = np.random.default_rng(0).normal(size=len(v["coef"]))
    t = time.perf_counter()
    for _ in range(repeats): 1.0 / (1.0 + np.exp(-(((x - v["mean"]) / v["std"]) @ v["coef"] + v["bias"])))
    return (time.perf_counter() - t) / repeats * 1e6


def score_variant(v, cos, idx, y):
    p = v["net"].predict(v["Z"][idx])
    c = score_c(p, cos[idx], v["tuned"]["alpha"])
    return p, c


def block(y_true, hidden, dist_score=None):
    m = metrics(y_true, hidden)
    m["roc_auc"] = float(roc_auc_score(y_true, dist_score)) if dist_score is not None and len(np.unique(y_true)) == 2 else None
    return m


def ms(vals):
    a = np.array(vals, float); return {"mean": float(a.mean()), "std": float(a.std(ddof=1)) if len(a) > 1 else 0.0}


def head_latency(net, mean, std, n_in, repeats=2000):
    x = np.random.default_rng(0).normal(size=n_in); net_p = net
    t = time.perf_counter()
    for _ in range(repeats):
        z = (x - mean) / std; h = np.maximum(0.0, z @ net_p.W1 + net_p.b1); 1.0 / (1.0 + np.exp(-(h @ net_p.W2 + net_p.b2)))
    return (time.perf_counter() - t) / repeats * 1e6          # microseconds per item, numpy, batch of 1 (as the backend does it)


def size_kb(net, n_in):
    return len(json.dumps({"W1": np.round(net.W1, 6).tolist(), "b1": np.round(net.b1, 6).tolist(), "W2": np.round(net.W2, 6).tolist()})) / 1024


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("features"); ap.add_argument("--out", default="results/compare")
    ap.add_argument("--source-csv", default="data/clean/training.csv", help="gives raw text (for the rule baseline) and source per row")
    ap.add_argument("--repeats", type=int, default=1, help="number of different 70/15/15 splits (1 = a single held-out test)")
    ap.add_argument("--hidden", type=int, default=128); ap.add_argument("--dropout", type=float, default=0.3)
    ap.add_argument("--epochs", type=int, default=200); ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--lr-c", type=float, default=1.0, help="inverse regularisation strength of the logistic-regression baselines"); ap.add_argument("--image-dropout", type=float, default=0.2); ap.add_argument("--max-fpr", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--time-extractors", action="store_true", help="also time EmbeddingGemma and MobileNetV2 (needs the backend packages and, for images, --images-dir)")
    ap.add_argument("--images-dir", default="thumbnails")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)

    d = np.load(a.features, allow_pickle=False)
    text, image, cos, y = d["text"], d["image"], d["cosine"].astype(float), d["y"].astype(int)
    has_img = d["has_image"].astype(bool); ids = [str(i) for i in d["ids"]]
    groups = d["groups"] if "groups" in d else None
    if groups is not None and len(np.unique(groups)) == len(groups): groups = None
    kind = d["kind"].astype(str) if "kind" in d else np.array(["base"] * len(y))
    heldout = d["heldout"].astype(bool) if "heldout" in d else np.zeros(len(y), bool)
    train_only = kind == "catalog"
    with open(a.source_csv, encoding="utf-8", newline="") as fh: rows = {r["id"]: r for r in csv.DictReader(fh)}
    raw = [rows.get(i, {}).get("text", "") for i in ids]; source = np.array([rows.get(i, {}).get("source", "") for i in ids], dtype=object)
    X = np.hstack([text, image, cos[:, None]]).astype(np.float64)
    cols_text = np.r_[0:TEXT_DIM, TEXT_DIM + IMAGE_DIM]; cols_all = np.arange(X.shape[1])
    rules = make_rules()
    variants = {"B Text-only (257-d)": (cols_text, None), "C Text + Vision (1537-d)": (cols_all, a.image_dropout)}
    lr_variants = {"B-LR Logistic regression, text-only (257-d)": (cols_text, False), "C-LR Logistic regression, text + vision (1537-d)": (cols_all, True)}
    names = list(rules) + list(variants) + list(lr_variants)

    runs = []
    for rep in range(a.repeats):
        tr, va, te = next(iter(splits(y, "holdout7015", 1, a.seed + rep, groups)))
        tr, va, te = tr[~heldout[tr]], va[~heldout[va]], te[~heldout[te]]
        tr = np.concatenate([tr, va[train_only[va]], te[train_only[te]]]); va, te = va[~train_only[va]], te[~train_only[te]]
        keep_base = lambda idx: idx[kind[idx] == "base"] if (kind[idx] == "base").any() else idx
        vb, tb = keep_base(va), keep_base(te)
        tb_img = tb[has_img[tb]]
        res = {"sizes": {"train": int(len(tr)), "validation": int(len(vb)), "test": int(len(tb)), "test_with_thumbnail": int(len(tb_img))}, "models": {}}
        print(f"split {rep + 1}/{a.repeats}: train {len(tr)}, validation {len(vb)}, held-out test {len(tb)} ({len(tb_img)} with thumbnails)")
        for n, f in rules.items():
            h = lambda idx: np.array([f(raw[i]) for i in idx])
            res["models"][n] = {"validation": block(y[vb], h(vb)), "test": block(y[tb], h(tb)), "test_thumbnail_rows": block(y[tb_img], h(tb_img)) if len(tb_img) else None}
        for n, (cols, imgdrop) in variants.items():
            v = fit_variant(X, y, cos, has_img, tr, va, cols, imgdrop, a, a.seed + rep)
            r = {"tuned": {"alpha": v["tuned"]["alpha"], "hide_threshold": v["tuned"]["hide_threshold"]}, "epochs": v["epochs"], "train_seconds": v["train_s"]}
            for key, idx in (("validation", vb), ("test", tb), ("test_thumbnail_rows", tb_img)):
                if not len(idx): r[key] = None; continue
                p, c = score_variant(v, cos, idx, y[idx])
                r[key] = block(y[idx], c < v["tuned"]["hide_threshold"], 1 - c)
                r[key]["roc_auc_p_only"] = float(roc_auc_score(y[idx], p)) if len(np.unique(y[idx])) == 2 else None
                if key == "test": r["_curve"] = [x.tolist() for x in roc_curve(y[idx], 1 - c)[:2]]
            n_in = len(cols); net = v["net"]
            r["compute"] = {"input_dim": int(n_in), "parameters": int(net.W1.size + net.b1.size + net.W2.size + 1), "head_size_kb": size_kb(net, n_in),
                            "head_latency_us": head_latency(net, v["mean"], v["std"], n_in), "flops_per_item": int(2 * n_in * a.hidden + 2 * a.hidden)}
            res["models"][n] = r
        for n, (cols, vision) in lr_variants.items():
            v = fit_lr(X, y, cos, has_img, tr, va, cols, vision, a)
            r = {"tuned": {"alpha": v["tuned"]["alpha"], "hide_threshold": v["tuned"]["hide_threshold"]}, "epochs": v["epochs"], "train_seconds": v["train_s"]}
            for key, idx in (("validation", vb), ("test", tb), ("test_thumbnail_rows", tb_img)):
                if not len(idx): r[key] = None; continue
                p, c = score_variant(v, cos, idx, y[idx])
                r[key] = block(y[idx], c < v["tuned"]["hide_threshold"], 1 - c)
                r[key]["roc_auc_p_only"] = float(roc_auc_score(y[idx], p)) if len(np.unique(y[idx])) == 2 else None
            n_in = len(cols)
            r["compute"] = {"input_dim": int(n_in), "parameters": int(n_in + 1), "head_size_kb": len(json.dumps(np.round(v["coef"], 6).tolist())) / 1024,
                            "head_latency_us": lr_latency(v), "flops_per_item": int(2 * n_in)}
            res["models"][n] = r
        runs.append(res)

    # rule latency
    sample = [t for t in raw[:2000] if t]; comp_rules = {}
    for n, f in rules.items():
        t = time.perf_counter(); [f(s) for s in sample]; comp_rules[n] = (time.perf_counter() - t) / len(sample) * 1e6

    extractor = None
    if a.time_extractors:
        try:
            sys.path.insert(0, str(ROOT / "backend")); from thesis_features import FeatureExtractor
            fx = FeatureExtractor(); fx.embed_text("warm up"); titles = [t for t in raw[:60] if t]
            tt = []
            for s in titles: t0 = time.perf_counter(); fx.embed_text(s); tt.append((time.perf_counter() - t0) * 1000)
            extractor = {"embed_text_ms_median": float(np.median(tt)), "embed_text_ms_p90": float(np.percentile(tt, 90))}
            imgs = [p for p in Path(a.images_dir).glob("*.jpg")][:30]
            if imgs:
                data = [p.read_bytes() for p in imgs]; fx.embed_image(data[0]); ti = []
                for b in data: t0 = time.perf_counter(); fx.embed_image(b); ti.append((time.perf_counter() - t0) * 1000)
                extractor["embed_image_ms_median"] = float(np.median(ti)); extractor["embed_image_ms_p90"] = float(np.percentile(ti, 90))
            extractor["note"] = "measured on this machine, CPU; EmbeddingGemma has about 300M parameters, MobileNetV2 about 3.4M"
        except Exception as e:
            extractor = {"error": f"{type(e).__name__}: {e}"}

    # ---------- aggregate ----------
    keys = ["accuracy", "precision", "recall", "f1", "false_positive_rate", "roc_auc"]
    summary = {}
    for n in names:
        summary[n] = {}
        for split in ("validation", "test", "test_thumbnail_rows"):
            blk = [r["models"][n][split] for r in runs if r["models"][n][split]]
            if not blk: continue
            s = {k: ms([b[k] for b in blk]) for k in keys if all(b.get(k) is not None for b in blk)}
            s.update({c: int(round(np.mean([b[c] for b in blk]))) for c in ("tp", "tn", "fp", "fn")}); summary[n][split] = s
    compute = {n: ({k: runs[0]["models"][n]["compute"][k] for k in runs[0]["models"][n]["compute"]} | {"train_seconds": float(np.mean([r["models"][n]["train_seconds"] for r in runs])), "epochs": float(np.mean([r["models"][n]["epochs"] for r in runs]))}
                   if (n in variants or n in lr_variants) else {"head_latency_us": comp_rules[n], "parameters": 0, "input_dim": 0}) for n in names}
    for r in runs:
        for m in r["models"].values(): m.pop("_curve", None) if False else None
    (out / "model_comparison.json").write_text(json.dumps({"args": vars(a), "runs": [{**r, "models": {n: {k: v for k, v in m.items() if k != "_curve"} for n, m in r["models"].items()}} for r in runs],
                                                          "summary": summary, "compute": compute, "extractors": extractor}, indent=1))
    curves = {n: runs[0]["models"][n]["_curve"] for n in variants}
    np.savez(out / "roc_curves.npz", **{n.split()[0]: np.array(c) for n, c in curves.items()})
    write_report(out, a, runs, summary, compute, extractor, names, keys)
    base_names = [n for n in names if n not in lr_variants]
    make_figures(out, summary, compute, curves, base_names, keys, extractor)
    make_classifier_figure(out, summary, [n for n in names if n in variants or n in lr_variants])


def fmt(s, k):
    return f"{s[k]['mean']:.3f}" + (f" ± {s[k]['std']:.3f}" if s[k]["std"] else "") if k in s else "n/a"


def write_report(out, a, runs, summary, compute, extractor, names, keys):
    sz = runs[0]["sizes"]
    L = ["# Comparison of the rule-based baseline, the text-only model and the text + vision model", "",
         f"Split 70/15/15, whole items kept together, {a.repeats} split(s). First split: train {sz['train']:,}, validation {sz['validation']:,}, held-out test {sz['test']:,} real items ({sz['test_with_thumbnail']:,} with a thumbnail).",
         "Validation rows are used to tune the head (early stopping, alpha, hide threshold, FPR cap of "
         f"{a.max_fpr:.0%}); the test rows are used once, only to report. Positive class = distracting (hidden). ROC-AUC uses the continuous score 1 - C; the rule baselines are yes/no, so they have no ROC-AUC.", ""]
    for split, title in (("test", "Held-out test"), ("validation", "Validation (the rows used for tuning, so optimistic)"), ("test_thumbnail_rows", "Held-out test, only items that have a thumbnail (where vision can help)")):
        L += [f"## {title}", "", "| Model | Accuracy | Precision | Recall | F1 | FPR | ROC-AUC | TN | FP | FN | TP |", "|---|---|---|---|---|---|---|---|---|---|---|"]
        for n in names:
            s = summary[n].get(split)
            if s: L.append(f"| {n} | " + " | ".join(fmt(s, k) for k in keys) + f" | {s['tn']} | {s['fp']} | {s['fn']} | {s['tp']} |")
        L.append("")
    L += ["## Computational measurements", "", "| Model | Input dim | Parameters | Head size (KB) | Head latency (µs/item) | FLOPs/item | Training time (s) | Epochs |", "|---|---|---|---|---|---|---|---|"]
    for n in names:
        c = compute[n]
        L.append(f"| {n} | {c.get('input_dim', 0) or '-'} | {c.get('parameters', 0):,} | {c['head_size_kb']:.0f} |" if "head_size_kb" in c else f"| {n} | - | 0 | 0 |")
        L[-1] += f" {c['head_latency_us']:.1f} | {c.get('flops_per_item', 0):,} | " + (f"{c['train_seconds']:.1f} | {c['epochs']:.0f} |" if "train_seconds" in c else "- | - |")
    if extractor:
        L += ["", "Feature extractors (the real cost of the learned models; measured here on CPU):", "", "```", json.dumps(extractor, indent=1), "```"]
    else:
        L += ["", "Feature extractors were not timed. Run again with `--time-extractors` (and `--images-dir thumbnails`) on the machine that has the backend packages. EmbeddingGemma has about 300M parameters and MobileNetV2 about 3.4M, so extraction, not the Dense head, dominates the cost of models B and C. Model B needs no image download or MobileNetV2 pass."]
    L += ["", "B-LR and C-LR use the same features and the same validation tuning (alpha, hide threshold, FPR cap) with a logistic regression in place of the Dense head, to answer whether the extra capacity of the Dense head is needed. "
          "Notes: models B and C use the binary head only so that the comparison isolates the image features; the deployed model also carries the subject head. "
          "The deployed rule fallback (A1) was designed as a safety net, not as a competitor; A2 is the usual keyword filter."]
    (out / "model_comparison.md").write_text("\n".join(L) + "\n", encoding="utf-8"); print("wrote", out / "model_comparison.md")


def make_classifier_figure(out, summary, learned):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    order = sorted(learned, key=lambda n: (n.startswith("C"), n.startswith(("B-LR", "C-LR"))))
    fig, ax = plt.subplots(figsize=(8.4, 3.8)); x = np.arange(len(order)); w = 0.27
    for i, (k, c, lab) in enumerate((("f1", "#7c3aed", "F1"), ("recall", "#0d9488", "Recall"), ("false_positive_rate", "#c2410c", "FPR"))):
        v = [summary[n]["test"][k]["mean"] for n in order]; e = [summary[n]["test"][k]["std"] for n in order]
        b = ax.bar(x + (i - 1) * w, v, w, yerr=e if any(e) else None, capsize=2, color=c, label=lab)
        for bb, vv in zip(b, v): ax.text(bb.get_x() + bb.get_width() / 2, vv + 0.01, f"{vv:.2f}", ha="center", fontsize=7.5)
    ax.set_xticks(x); ax.set_xticklabels([n.replace(" Logistic regression,", "\nLogistic regression,").replace(" Text-only", "\nDense head, text-only").replace(" Text + Vision", "\nDense head, text + vision") for n in order], fontsize=8)
    ax.set_ylim(0, 1.1); ax.set_title("Classifier choice on the same features: Dense head vs logistic regression (held-out test)"); ax.legend(frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.25))
    fig.tight_layout(); fig.savefig(out / "05_classifier_choice.png", dpi=160); plt.close(fig)


def make_figures(out, summary, compute, curves, names, keys, extractor):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9.5, "axes.spines.top": False, "axes.spines.right": False})
    col = {"accuracy": "#64748b", "precision": "#2563eb", "recall": "#0d9488", "f1": "#7c3aed", "false_positive_rate": "#c2410c"}
    short = [n.split(" ")[0] + "\n" + " ".join(n.split(" ")[1:3]) for n in names]
    mk = ["precision", "recall", "f1", "false_positive_rate"]
    fig, ax = plt.subplots(figsize=(10, 4.2)); x = np.arange(len(names)); w = 0.8 / len(mk)
    for i, k in enumerate(mk):
        v = [summary[n]["test"][k]["mean"] for n in names]; e = [summary[n]["test"][k]["std"] for n in names]
        b = ax.bar(x + (i - 1.5) * w, v, w, yerr=e if any(e) else None, capsize=2, color=col[k], label={"false_positive_rate": "FPR"}.get(k, k.capitalize()))
        for bb, vv in zip(b, v): ax.text(bb.get_x() + bb.get_width() / 2, vv + 0.01, f"{vv:.2f}", ha="center", fontsize=7.5)
    ax.set_xticks(x); ax.set_xticklabels(short); ax.set_ylim(0, 1.1); ax.set_title("Held-out test: rule-based vs text-only vs text + vision"); ax.legend(frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.17))
    fig.tight_layout(); fig.savefig(out / "01_test_metrics.png", dpi=160); plt.close(fig)

    vn = [n for n in names if n in curves]
    fig, ax = plt.subplots(figsize=(4.8, 4.4))
    for n, c in zip(vn, ["#0d9488", "#7c3aed"]):
        fpr, tpr = curves[n]; ax.plot(fpr, tpr, color=c, label=f"{n.split(' (')[0]} (AUC {summary[n]['test']['roc_auc']['mean']:.3f})")
    ax.plot([0, 1], [0, 1], color="#94a3b8", ls="--", lw=0.8); ax.set_xlabel("false-positive rate"); ax.set_ylabel("true-positive rate"); ax.set_title("ROC on the held-out test (first split)"); ax.legend(frameon=False, loc="lower right")
    fig.tight_layout(); fig.savefig(out / "02_roc.png", dpi=160); plt.close(fig)

    fig, axes = plt.subplots(1, len(names), figsize=(3.2 * len(names), 3.4))
    for ax, n in zip(axes, names):
        s = summary[n]["test"]; cm = np.array([[s["tn"], s["fp"]], [s["fn"], s["tp"]]], float); nm = cm / cm.sum(axis=1, keepdims=True)
        ax.imshow(nm, cmap="Blues", vmin=0, vmax=1)
        for i in range(2):
            for j in range(2): ax.text(j, i, f"{int(cm[i, j]):,}\n{nm[i, j]:.0%}", ha="center", va="center", color="white" if nm[i, j] > 0.5 else "#0f172a", fontsize=9)
        ax.set_xticks([0, 1]); ax.set_xticklabels(["kept", "hidden"]); ax.set_yticks([0, 1]); ax.set_yticklabels(["relevant", "distracting"]); ax.set_title(n.split(" (")[0].replace(" ", "\n", 1) if len(n) > 22 else n, fontsize=8.5)
        for sp in ax.spines.values(): sp.set_visible(False)
    fig.suptitle("Confusion matrices on the held-out test (rows normalised)", fontsize=10); fig.tight_layout(); fig.savefig(out / "03_confusion_matrices.png", dpi=160); plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.4)); learned = [n for n in names if "parameters" in compute[n] and compute[n]["parameters"]]
    axes[0].bar([n.split(" ")[0] for n in names], [compute[n]["head_latency_us"] for n in names], color="#475569"); axes[0].set_yscale("log"); axes[0].set_title("Decision latency (µs per item, log)")
    for i, n in enumerate(names): axes[0].text(i, compute[n]["head_latency_us"], f"{compute[n]['head_latency_us']:.1f}", ha="center", va="bottom", fontsize=8)
    axes[1].bar([n.split(" ")[0] for n in learned], [compute[n]["parameters"] for n in learned], color="#475569"); axes[1].set_title("Trainable parameters")
    for i, n in enumerate(learned): axes[1].text(i, compute[n]["parameters"], f"{compute[n]['parameters']:,}", ha="center", va="bottom", fontsize=8)
    axes[2].bar([n.split(" ")[0] for n in learned], [compute[n].get("train_seconds", 0) for n in learned], color="#475569"); axes[2].set_title("Training time (s)")
    fig.tight_layout(); fig.savefig(out / "04_compute.png", dpi=160); plt.close(fig)
    print("wrote figures to", out)


if __name__ == "__main__":
    main()
