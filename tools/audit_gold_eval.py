"""
audit_gold_eval.py - score the model against the HUMAN labels of the blind audit (a small gold set), not only against the dataset labels.

    python tools/audit_gold_eval.py data/clean/features.npz data/audit/audit_sheet.csv data/audit/audit_key.csv --out results/audit_gold

Why: the audit showed the dataset labels agree with a blind human reader only about 63% of the time, so a score against the dataset
labels alone says how well the model copies those labels, not how well it judges relevance. Here every audited item (and every
augmented copy of it) is REMOVED from training, a text-only head (and with --vision a text+vision head) is trained on the rest
with the usual tuning (validation rows, FPR cap), and the audited items are then scored twice: against the human label and against the
dataset label. Rows the annotator marked "unsure" are skipped. Positive class = distracting (hidden).
"""
import argparse, json, sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "training")); sys.path.insert(0, str(ROOT / "tools"))
from fusion_head import metrics
from train_fusion import TEXT_DIM, IMAGE_DIM
from compare_models import fit_variant, score_variant
from score_audit import kappa, wilson


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("features"); ap.add_argument("sheet"); ap.add_argument("key"); ap.add_argument("--out", default="results/audit_gold")
    ap.add_argument("--hidden", type=int, default=128); ap.add_argument("--dropout", type=float, default=0.3); ap.add_argument("--epochs", type=int, default=200)
    ap.add_argument("--lr", type=float, default=1e-3); ap.add_argument("--max-fpr", type=float, default=0.05); ap.add_argument("--image-dropout", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=42); ap.add_argument("--vision", action="store_true", help="also train and score the text + vision head")
    a = ap.parse_args()

    d = np.load(a.features, allow_pickle=False)
    text, image, cos, y = d["text"], d["image"], d["cosine"].astype(float), d["y"].astype(int)
    has_img = d["has_image"].astype(bool); ids = np.array([str(i) for i in d["ids"]])
    kind = d["kind"].astype(str) if "kind" in d else np.array(["base"] * len(y))
    groups = d["groups"] if "groups" in d else None
    heldout = d["heldout"].astype(bool) if "heldout" in d else np.zeros(len(y), bool)

    sheet = pd.read_csv(a.sheet, dtype=str, keep_default_na=False); key = pd.read_csv(a.key, dtype=str, keep_default_na=False)
    gold = sheet.merge(key[["id", "label"]], on="id"); gold = gold[gold["annotator_label"].isin(["relevant", "distracting"])]
    pos = {i: k for k, i in enumerate(ids)}
    gold = gold[gold["id"].isin(pos)]
    if len(gold) < 20: sys.exit(f"only {len(gold)} audited rows found in the features file; check that the ids match")
    gidx = np.array([pos[i] for i in gold["id"]]); gidx = gidx[kind[gidx] == "base"] if (kind[gidx] == "base").any() else gidx
    gold = gold[gold["id"].isin(set(ids[gidx]))].reset_index(drop=True)
    gidx = np.array([pos[i] for i in gold["id"]])
    y_h = (gold["annotator_label"] == "distracting").astype(int).to_numpy(); y_d = y[gidx]

    # remove the audited items, and every row that shares a group with them (augmented copies), from training and validation
    excl = np.isin(groups, np.unique(groups[gidx])) if groups is not None and len(np.unique(groups)) < len(groups) else np.isin(ids, ids[gidx])
    pool = np.where(~excl & ~heldout)[0]; train_only = kind == "catalog"
    rng = np.random.default_rng(a.seed)
    base_pool = pool[(kind[pool] == "base") & ~train_only[pool]]
    ug = np.unique(groups[base_pool]) if groups is not None else base_pool
    val_groups = set(rng.choice(ug, size=max(1, int(0.15 * len(ug))), replace=False).tolist())
    va = base_pool[np.isin(groups[base_pool] if groups is not None else base_pool, list(val_groups))]
    tr = np.setdiff1d(pool, np.where(np.isin(groups, list(val_groups)))[0] if groups is not None else va)
    print(f"audited rows scored: {len(gold)} | removed from training: {int(excl.sum())} rows | train {len(tr)} | validation {len(va)}")

    X = np.hstack([text, image, cos[:, None]]).astype(np.float64)
    cols_text = np.r_[0:TEXT_DIM, TEXT_DIM + IMAGE_DIM]; cols_all = np.arange(X.shape[1])
    variants = {"text-only head (257-d)": (cols_text, None)}
    if a.vision: variants["text + vision head (1537-d)"] = (cols_all, a.image_dropout)
    args = SimpleNamespace(hidden=a.hidden, dropout=a.dropout, epochs=a.epochs, lr=a.lr, max_fpr=a.max_fpr)

    agree = float((y_h == y_d).mean()); lo, hi = wilson(int((y_h == y_d).sum()), len(gold))
    out = {"n": int(len(gold)), "human_vs_dataset": {"agreement": agree, "ci": [lo, hi], "kappa": float(kappa(list(y_h), list(y_d)))}, "models": {}}
    for name, (cols, imgdrop) in variants.items():
        v = fit_variant(X, y, cos, has_img, tr, va, cols, imgdrop, args, a.seed)
        p, c = score_variant(v, cos, gidx, y_h); hidden = c < v["tuned"]["hide_threshold"]
        agree_rows = y_h == y_d
        out["models"][name] = {"hide_threshold": v["tuned"]["hide_threshold"], "vs_human": metrics(y_h, hidden), "vs_dataset_label": metrics(y_d, hidden),
                               "accuracy_where_human_and_dataset_agree": float((hidden[agree_rows] == y_h[agree_rows]).mean()) if agree_rows.any() else None,
                               "accuracy_where_they_disagree_vs_human": float((hidden[~agree_rows] == y_h[~agree_rows]).mean()) if (~agree_rows).any() else None,
                               "agreement_with_human_kappa": float(kappa(list(y_h), list(hidden.astype(int))))}
    o = Path(a.out); o.mkdir(parents=True, exist_ok=True); (o / "audit_gold_eval.json").write_text(json.dumps(out, indent=1))
    f = lambda x: "n/a" if x is None else f"{x:.3f}"
    L = ["# Model scored against the human audit labels", "",
         f"{len(gold)} audited items, read blind by the group. These items and their augmented copies were removed from training. Positive class = distracting (hidden).", "",
         f"Human vs dataset label on these items: agreement {agree:.3f} (95% CI {lo:.3f}-{hi:.3f}), Cohen's kappa {out['human_vs_dataset']['kappa']:.3f}.", "",
         "| Model | scored against | accuracy | precision | recall | F1 | FPR |", "|---|---|---|---|---|---|---|"]
    for name, r in out["models"].items():
        for lab, m in (("HUMAN label", r["vs_human"]), ("dataset label", r["vs_dataset_label"])):
            L.append(f"| {name} | {lab} | {f(m['accuracy'])} | {f(m['precision'])} | {f(m['recall'])} | {f(m['f1'])} | {f(m['false_positive_rate'])} |")
        L.append(f"| {name} | (accuracy where human = dataset / where they differ, vs human) | {f(r['accuracy_where_human_and_dataset_agree'])} / {f(r['accuracy_where_they_disagree_vs_human'])} | | | | |")
    L += ["", "Read it like this: the HUMAN rows are the honest estimate of how well the model separates relevant from distracting content as a person would. "
          "The dataset-label rows show how closely it copies the dataset's own labels on the same items. A model that agrees with the dataset much more than with the humans has learned the dataset's quirks."]
    (o / "audit_gold_eval.md").write_text("\n".join(L) + "\n", encoding="utf-8"); print("\n".join(L))


if __name__ == "__main__":
    main()
