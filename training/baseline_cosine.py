"""
baseline_cosine.py - the no-training baselines the Dense head must beat (same splits as train_fusion.py).

    python baseline_cosine.py features.npz [--max-fpr 0.05]

1. cosine-only : EmbeddingGemma similarity to the student's context (= alpha 1 in the fusion rule). Hide if S < t.
2. zero-shot   : only if features.npz has `cosine_distract` (extract_features.py --distract-context "...");
                 score = S - cosine_distract, hide if score < t.
Thresholds are tuned on the validation split only (largest recall with false-positive rate <= max-fpr);
numbers are reported on the test split, as for the trained model.
"""
import argparse
import numpy as np
from train_fusion import splits
from fusion_head import metrics


def pick_threshold(score, y, max_fpr):
    """Hide if score < t. Positive class = distracting (y=1). Returns the t with best recall under the FPR cap."""
    best, best_r = float(score.min()) - 1e-9, -1.0
    for t in np.unique(np.quantile(score, np.linspace(0.01, 0.99, 197))):
        m = metrics(y, score < t)
        if m["false_positive_rate"] <= max_fpr and m["recall"] > best_r: best, best_r = float(t), m["recall"]
    return best


def evaluate(score, y, groups, scheme="kfold", folds=5, seed=42, max_fpr=0.05):
    rows = []
    for tr, va, te in splits(y, scheme, folds, seed, groups):
        t = pick_threshold(score[va], y[va], max_fpr)
        rows.append(metrics(y[te], score[te] < t))
    keys = ["accuracy", "precision", "recall", "f1", "false_positive_rate"]
    return {k: (float(np.mean([r[k] for r in rows])), float(np.std([r[k] for r in rows]))) for k in keys}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("features"); ap.add_argument("--max-fpr", type=float, default=0.05)
    ap.add_argument("--scheme", default="kfold"); ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    d = np.load(a.features, allow_pickle=False); y = d["y"].astype(int)
    groups = d["groups"] if "groups" in d else None
    if groups is not None and len(np.unique(groups)) == len(groups): groups = None
    out = {"cosine-only": d["cosine"].astype(float)}
    if "cosine_distract" in d: out["zero-shot (S - S_distract)"] = d["cosine"].astype(float) - d["cosine_distract"].astype(float)
    for name, sc in out.items():
        r = evaluate(sc, y, groups, a.scheme, 5, a.seed, a.max_fpr)
        print(f"{name:28s} " + "  ".join(f"{k}={m:.3f}±{s:.3f}" for k, (m, s) in r.items()))


if __name__ == "__main__":
    main()
