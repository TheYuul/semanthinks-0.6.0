"""
train_fusion.py - trains and evaluates the thesis Late Fusion classifier, then exports model_bundle.json.

    python train_fusion.py features.npz model_bundle.json --report report

features.npz comes from extract_features.py (or any file with the same arrays):
    text (N,256)  image (N,1280)  cosine (N,)  y (N,) 1 = distracting, 0 = relevant  has_image (N,) bool
  optional, enable the multi-task (subject) head:
    subjects (N,K) multi-hot  subject_known (N,) bool  ctx_subjects (N,K)  subject_ids (K,)
    heldout (N,) bool : rows (keyword-focus rows with a held-out keyword) never used for training/validation/early stopping;
                        every fold's model is evaluated on them as the "unseen keyword" test.

Evaluation
  --scheme kfold        5-fold stratified cross-validation. Each fold: test = 1/5 of the data, validation =
                        15% of the whole dataset (taken from the remaining 4/5), train = the rest (65%).
  --scheme holdout7015  5 repeated stratified 70/15/15 splits (train/validation/test), as written in the
                        thesis. NOTE: "5-fold" and "70/15/15" cannot both be true (5 folds give a 20% test set).
                        Pick one and make the paper say the same thing.
The validation split tunes the fusion weight alpha and the hide threshold (and early stopping). The test
split is only used for the reported numbers.
"""
import argparse, json
from collections import Counter
from pathlib import Path
import numpy as np
from sklearn.model_selection import GroupShuffleSplit, StratifiedGroupKFold, StratifiedKFold, train_test_split

from fusion_head import DenseHead, score_c, decide, allow_for, metrics, tune_decision, subject_score

TEXT_DIM, IMAGE_DIM = 256, 1280
IMAGE_SLICE = slice(TEXT_DIM, TEXT_DIM + IMAGE_DIM)


def build_X(text, image, cosine):
    return np.hstack([text, image, cosine[:, None]]).astype(np.float64)        # 256 + 1280 (=1536) + cosine


def fit_standardizer(X, has_image):
    ref = X[has_image] if has_image.any() else X
    mean, std = ref.mean(0), ref.std(0)
    return mean, np.where(std < 1e-8, 1.0, std)


def standardize(X, mean, std, has_image):
    Z = (X - mean) / std
    Z[~np.asarray(has_image, bool), IMAGE_SLICE] = 0.0       # no thumbnail -> neutral image block (same rule at serving time)
    return Z


def split_off(idx, frac, y, groups, seed):
    """Split idx into (rest, off) with `off` about frac of idx. Whole groups stay together when groups are given."""
    if groups is None:
        return train_test_split(idx, test_size=frac, stratify=y[idx], random_state=seed)
    rest, off = next(GroupShuffleSplit(1, test_size=frac, random_state=seed).split(idx, groups=groups[idx]))
    return idx[rest], idx[off]


def splits(y, scheme, folds, seed, groups=None):
    idx = np.arange(len(y))
    if scheme == "kfold":
        outer = StratifiedKFold(folds, shuffle=True, random_state=seed) if groups is None else StratifiedGroupKFold(folds, shuffle=True, random_state=seed)
        for tr_all, te in outer.split(idx, y, groups):
            tr, va = split_off(tr_all, 0.15 * len(y) / len(tr_all), y, groups, seed)
            yield tr, va, te
    else:
        for r in range(folds):
            tr_all, te = split_off(idx, 0.15, y, groups, seed + r)
            tr, va = split_off(tr_all, 0.15 / 0.85, y, groups, seed + r)
            yield tr, va, te


GRID = [(h, d) for h in (64, 128, 256) for d in (0.2, 0.3, 0.5)]      # hidden units x dropout


def train_one(X, y, cos, has_img, tr, va, args, seed, hidden=None, dropout=None, aux=None, focus=None):
    """aux (optional): dict(S, known, ctx) for the subject head. focus (optional): bool mask of keyword-focus rows. The main decision
    (alpha, beta, hide threshold) is tuned on the non-focus validation rows; focus mode gets its own decision in main()."""
    mean, std = fit_standardizer(X[tr], has_img[tr])
    Z = standardize(X, mean, std, has_img)
    K = aux["S"].shape[1] if aux else 0
    net = DenseHead(X.shape[1], hidden=hidden or args.hidden, dropout=args.dropout if dropout is None else dropout, seed=seed, n_subjects=K)
    kw = dict(S=aux["S"][tr], known=aux["known"][tr], Sv=aux["S"][va], known_v=aux["known"][va], subject_weight=args.subject_weight) if aux else {}
    net.fit(Z[tr], y[tr], Z[va], y[va], epochs=args.epochs, lr=args.lr, image_dropout=args.image_dropout, seed=seed, **kw)
    vt = va if focus is None or (~focus[va]).sum() < 50 else va[~focus[va]]
    subj = subject_score(net.subject_probs(Z[vt]), aux["ctx"][vt]) if aux else None
    tuned = tune_decision(net.predict(Z[vt]), cos[vt], y[vt], max_fpr=args.max_fpr, subj=subj)
    return net, mean, std, Z, tuned


def tune_focus(net, Z, y, cos, aux, va_focus, max_fpr):
    """Own decision (alpha, beta, hide threshold) for keyword-focus mode, tuned on focus validation rows only. None if too few rows."""
    if len(va_focus) < 40 or len(np.unique(y[va_focus])) < 2: return None
    subj = subject_score(net.subject_probs(Z[va_focus]), aux["ctx"][va_focus]) if aux else None
    return tune_decision(net.predict(Z[va_focus]), cos[va_focus], y[va_focus], max_fpr=max_fpr, subj=subj)


def subject_metrics(q, S, known, min_pos=5):
    """Subject-head quality on rows with known subjects that have at least one subject: micro-F1 (threshold 0.5),
    top-1 (highest-probability subject is one of the true ones) and macro-F1 over subjects with >= min_pos test positives."""
    rel = known & (S.sum(1) > 0)
    if rel.sum() == 0: return None
    pr, tr_ = q[rel] > 0.5, S[rel] == 1
    f1 = lambda tp, p, t: 2 * tp / (p + t) if (p + t) else 0.0
    per = [f1((pr[:, k] & tr_[:, k]).sum(), pr[:, k].sum(), tr_[:, k].sum()) for k in range(S.shape[1]) if tr_[:, k].sum() >= min_pos]
    return {"n": int(rel.sum()), "micro_f1": float(f1((pr & tr_).sum(), pr.sum(), tr_.sum())),
            "top1": float(np.mean(tr_[np.arange(len(tr_)), q[rel].argmax(1)])), "macro_f1": float(np.mean(per)) if per else None,
            "subjects_scored": len(per)}


def eval_rows_modes(net, Z, y, cos, S, tuned, t_txt, t_img, idx, aux, band, has_img):
    """Like eval_rows, but rows with a thumbnail use the image-mode decision and rows without one use the text-mode decision
    (each falls back to `tuned` when that mode had too few validation rows)."""
    if len(idx) == 0: return None
    hidden = np.zeros(len(idx), bool); warn = np.zeros(len(idx), bool)
    for sel, t in ((has_img[idx], t_img or tuned), (~has_img[idx], t_txt or tuned)):
        sub = idx[sel]
        if len(sub) == 0: continue
        p = net.predict(Z[sub]); subj = subject_score(net.subject_probs(Z[sub]), aux["ctx"][sub]) if aux else None
        c = score_c(p, cos[sub], t["alpha"], subj, t.get("beta", 0.0))
        hidden[sel] = c < t["hide_threshold"]; warn[sel] = decide(c, t["hide_threshold"], allow_for(t["hide_threshold"], band)) == "warn"
    m = metrics(y[idx], hidden); m["warn_rate"] = float(warn.mean()); return m


def eval_rows(net, Z, y, cos, S, tuned, idx, aux, band):
    """Decision metrics for rows `idx` with the tuned alpha/beta/threshold (None when there are no rows)."""
    if len(idx) == 0: return None
    p = net.predict(Z[idx])
    subj = subject_score(net.subject_probs(Z[idx]), aux["ctx"][idx]) if aux else None
    c = score_c(p, cos[idx], tuned["alpha"], subj, tuned.get("beta", 0.0))
    allow_t = allow_for(tuned["hide_threshold"], band)
    m = metrics(y[idx], c < tuned["hide_threshold"])
    m["warn_rate"] = float((decide(c, tuned["hide_threshold"], allow_t) == "warn").mean())
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("features"); ap.add_argument("out")
    ap.add_argument("--scheme", choices=["kfold", "holdout7015"], default="kfold")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--hidden", type=int, default=128)
    ap.add_argument("--dropout", type=float, default=0.3)
    ap.add_argument("--epochs", type=int, default=200)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--image-dropout", type=float, default=0.2)
    ap.add_argument("--tune", action="store_true", help="grid-search hidden units {64,128,256} x dropout {0.2,0.3,0.5} per fold on the validation split")
    ap.add_argument("--max-fpr", type=float, default=0.05, help="largest share of relevant items the system may hide (validation)")
    ap.add_argument("--band", type=float, default=0.30, help="width of the 'warn' band above the hide threshold")
    ap.add_argument("--subject-weight", type=float, default=0.5, help="weight of the subject loss relative to the binary loss")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--source-csv", default="data/clean/training.csv", help="gives each row's source (youtube / article / repository) for the per-category results")
    ap.add_argument("--report", default=None, help="writes <report>.json and <report>.md")
    args = ap.parse_args()

    d = np.load(args.features, allow_pickle=False)
    text, image, cos, y = d["text"], d["image"], d["cosine"].astype(float), d["y"].astype(int)
    has_img = d["has_image"].astype(bool) if "has_image" in d else np.ones(len(y), bool)
    assert text.shape[1] == TEXT_DIM and image.shape[1] == IMAGE_DIM, (text.shape, image.shape)
    assert set(np.unique(y)) <= {0, 1} and len(np.unique(y)) == 2, "labels must contain both classes (0 relevant, 1 distracting)"
    groups = d["groups"] if "groups" in d else None
    if groups is not None and len(np.unique(groups)) == len(groups): groups = None     # every row its own group = plain stratified
    X = build_X(text, image, cos)
    heldout = d["heldout"].astype(bool) if "heldout" in d else np.zeros(len(y), bool)
    kind = d["kind"].astype(str) if "kind" in d else np.array(["base"] * len(y))
    is_focus = (kind == "focus")
    source = np.array([""] * len(y), dtype=object)
    if Path(args.source_csv).exists() and "ids" in d:
        import csv
        with open(args.source_csv, encoding="utf-8", newline="") as fh: smap = {r["id"]: r.get("source", "") for r in csv.DictReader(fh)}
        source = np.array([smap.get(str(i), "") for i in d["ids"]], dtype=object)
    train_only = (kind == "catalog")   # syllabus-derived rows: train only, never val/test
    aux = None
    if "subjects" in d:
        aux = {"S": d["subjects"].astype(float), "known": d["subject_known"].astype(bool), "ctx": d["ctx_subjects"].astype(float)}
        subject_ids = [str(v) for v in d["subject_ids"]]
        print(f"subject head on: {len(subject_ids)} subjects, {int(aux['known'].sum())} rows with subject labels")
    print("group-aware splits:", f"{len(np.unique(groups))} groups" if groups is not None else "off (no shared groups in the data)")
    print(f"{len(y)} samples, {int(y.sum())} distracting, {int((1 - y).sum())} relevant, {int(has_img.sum())} with image"
          + (f", {int((heldout & ~train_only).sum())} held-out keyword rows (test only)" if (heldout & ~train_only).any() else "")
          + (f", {int(train_only.sum())} catalog rows (training only)" if train_only.any() else ""))
    ho_idx = np.where(heldout & ~train_only)[0]       # the unseen-keyword test uses real items only, not syllabus-derived rows

    folds = []
    for k, (tr, va, te) in enumerate(splits(y, args.scheme, args.folds, args.seed, groups)):
        tr, va, te = tr[~heldout[tr]], va[~heldout[va]], te[~heldout[te]]       # held-out keyword rows never train, tune or stop
        tr = np.concatenate([tr, va[train_only[va]], te[train_only[te]]]); va, te = va[~train_only[va]], te[~train_only[te]]
        if args.tune:
            # Hyperparameters are chosen on the VALIDATION split of this fold only; the test fold is never used.
            # Preference: meets the false-positive cap, then higher validation F1.
            trials = []
            for h, dr in GRID:
                out = train_one(X, y, cos, has_img, tr, va, args, args.seed + k, h, dr, aux, is_focus)
                v = out[4]["val_metrics"]; trials.append(((out[4]["met_fpr_target"], v["f1"]), h, dr, out))
            _, hid, drop, (net, mean, std, Z, tuned) = max(trials, key=lambda t: t[0])
            print(f"fold {k + 1}: tuning picked hidden={hid} dropout={drop} (validation F1 {tuned['val_metrics']['f1']:.3f})")
        else:
            hid, drop = args.hidden, args.dropout
            net, mean, std, Z, tuned = train_one(X, y, cos, has_img, tr, va, args, args.seed + k, aux=aux, focus=is_focus)
        S_ = aux["S"] if aux else None
        tuned_f = tune_focus(net, Z, y, cos, aux, va[is_focus[va]], args.max_fpr)
        tuned_i = tune_focus(net, Z, y, cos, aux, va[~is_focus[va] & has_img[va]], args.max_fpr)     # decision for items scored with a thumbnail
        tuned_t = tune_focus(net, Z, y, cos, aux, va[~is_focus[va] & ~has_img[va]], args.max_fpr)    # decision for text-only items
        te_base, te_ctx, te_foc = te[kind[te] == "base"], te[kind[te] == "subject_ctx"], te[is_focus[te]]
        if len(te_base) == 0: te_base = te                                    # files without a `kind` column
        m = eval_rows_modes(net, Z, y, cos, S_, tuned, tuned_t, tuned_i, te_base, aux, args.band, has_img)   # HEADLINE: real items, program context, decision per input mode
        m_single = eval_rows(net, Z, y, cos, S_, tuned, te_base, aux, args.band)                            # same rows with one decision for everything (previous method)
        fold = {"fold": k + 1, "hidden": hid, "dropout": drop, "sizes": [len(tr), len(va), len(te)], "alpha": tuned["alpha"], "beta": tuned.get("beta", 0.0),
                "hide_threshold": tuned["hide_threshold"], "met_fpr_target_on_validation": tuned["met_fpr_target"], "test": m,
                "test_single_decision": m_single,
                "decision_image": None if tuned_i is None else {"alpha": tuned_i["alpha"], "beta": tuned_i.get("beta", 0.0), "hide_threshold": tuned_i["hide_threshold"]},
                "decision_text": None if tuned_t is None else {"alpha": tuned_t["alpha"], "beta": tuned_t.get("beta", 0.0), "hide_threshold": tuned_t["hide_threshold"]},
                "test_subject_ctx": eval_rows(net, Z, y, cos, S_, tuned, te_ctx, aux, args.band),
                "focus_decision": None if tuned_f is None else {"alpha": tuned_f["alpha"], "beta": tuned_f.get("beta", 0.0), "hide_threshold": tuned_f["hide_threshold"]}}
        ft = tuned_f or tuned
        for cat in ("youtube", "article", "repository"):
            idx = te_base[source[te_base] == cat]
            if len(idx) >= 30 and len(np.unique(y[idx])) == 2: fold["test_" + cat] = eval_rows_modes(net, Z, y, cos, S_, tuned, tuned_t, tuned_i, idx, aux, args.band, has_img)
        # What text-only mode does to the deployed network: the same model with the image block switched off, on items that have a thumbnail.
        te_th = te_base[has_img[te_base]]
        if len(te_th) >= 30 and len(np.unique(y[te_th])) == 2:
            Zn = Z.copy(); Zn[:, IMAGE_SLICE] = 0.0; no_img = np.zeros(len(y), bool)
            fold["test_thumb_rows_with_image"] = eval_rows_modes(net, Z, y, cos, S_, tuned, tuned_t, tuned_i, te_th, aux, args.band, has_img)
            fold["test_thumb_rows_image_ignored"] = eval_rows_modes(net, Zn, y, cos, S_, tuned, tuned_t, tuned_i, te_th, aux, args.band, no_img)
        fold["test_focus_weak"] = eval_rows(net, Z, y, cos, S_, ft, te_foc, aux, args.band)
        if aux:
            fold["subjects"] = subject_metrics(net.subject_probs(Z[te_base]), aux["S"][te_base], aux["known"][te_base])
        if len(ho_idx):
            fold["heldout_keywords"] = eval_rows(net, Z, y, cos, S_, ft, ho_idx, aux, args.band)
        folds.append(fold)
        print(f"fold {k + 1}: alpha={tuned['alpha']:.1f} beta={tuned.get('beta', 0.0):.1f} hide<{tuned['hide_threshold']:.2f}  [base rows] acc={m['accuracy']:.3f} P={m['precision']:.3f} "
              f"R={m['recall']:.3f} F1={m['f1']:.3f} FPR={m['false_positive_rate']:.3f}"
              + (f" | subjects micro-F1={fold['subjects']['micro_f1']:.3f} top1={fold['subjects']['top1']:.3f}" if aux and fold["subjects"] else "")
              + (f" | focus mode alpha={ft['alpha']:.1f} beta={ft.get('beta', 0.0):.1f} hide<{ft['hide_threshold']:.2f}" if tuned_f else " | focus mode: too few validation rows, main decision used")
              + (f" | held-out keywords F1={fold['heldout_keywords']['f1']:.3f} FPR={fold['heldout_keywords']['false_positive_rate']:.3f}" if fold.get("heldout_keywords") else ""))

    keys = ["accuracy", "precision", "recall", "f1", "false_positive_rate", "warn_rate"]
    ms = lambda vals: {"mean": float(np.mean(vals)), "std": float(np.std(vals))}
    summary = {k: ms([f["test"][k] for f in folds]) for k in keys}
    extra_summary = {}
    if aux:
        sub = [f["subjects"] for f in folds if f.get("subjects")]
        if sub: extra_summary["subjects"] = {k: ms([x[k] for x in sub if x[k] is not None]) for k in ("micro_f1", "top1", "macro_f1") if any(x[k] is not None for x in sub)}
    for name, key_ in (("video_youtube", "test_youtube"), ("online_articles", "test_article"), ("documents_repositories", "test_repository"), ("headline_single_decision_previous_method", "test_single_decision"), ("thumbnail_rows_scored_with_image", "test_thumb_rows_with_image"), ("thumbnail_rows_image_switched_off_text_only_mode", "test_thumb_rows_image_ignored"), ("subject_context_rows", "test_subject_ctx"), ("keyword_focus_rows_weak_labels", "test_focus_weak"), ("heldout_keywords", "heldout_keywords")):
        got = [f[key_] for f in folds if f.get(key_)]
        if got: extra_summary[name] = {k: ms([x[k] for x in got]) for k in ("accuracy", "precision", "recall", "f1", "false_positive_rate")}
    fd = [f["focus_decision"] for f in folds if f.get("focus_decision")]
    focus_dec = None
    if fd:
        fb = float(Counter(x["beta"] for x in fd).most_common(1)[0][0]); fh = float(np.round(np.median([x["hide_threshold"] for x in fd]), 2))
        focus_dec = {"alpha": float(np.round(np.median([x["alpha"] for x in fd]), 1)), "beta": fb, "hide_threshold": fh, "allow_threshold": allow_for(fh, args.band)}
    def agg_dec(key):
        ds = [f[key] for f in folds if f.get(key)]
        if len(ds) < max(2, len(folds) // 2): return None                    # too few folds had enough validation rows for this mode
        b_ = float(Counter(x["beta"] for x in ds).most_common(1)[0][0]); h_ = float(np.round(np.median([x["hide_threshold"] for x in ds]), 2))
        return {"alpha": float(np.round(np.median([x["alpha"] for x in ds]), 1)), "beta": b_, "hide_threshold": h_, "allow_threshold": allow_for(h_, args.band)}
    dec_img, dec_txt = agg_dec("decision_image"), agg_dec("decision_text")
    alpha = float(np.round(np.median([f["alpha"] for f in folds]), 1))
    beta = float(Counter(f["beta"] for f in folds).most_common(1)[0][0]) if aux else 0.0
    hide_t = float(np.round(np.median([f["hide_threshold"] for f in folds]), 2))
    allow_t = allow_for(hide_t, args.band)
    print("CV mean:", {k: round(v["mean"], 3) for k, v in summary.items()}, f"| final alpha={alpha} beta={beta} hide<{hide_t} allow>={allow_t}")
    print("  decision with thumbnail:", dec_img, "| decision text-only:", dec_txt)
    for name, blk in extra_summary.items(): print(f"  {name}:", {k: round(v["mean"], 3) for k, v in blk.items()})

    # Final model: all non-held-out data, with a stratified 15% validation slice for early stopping only.
    keep = np.where(~heldout)[0]
    tr, va = split_off(keep, 0.15, y, groups, args.seed)
    tr, va = np.concatenate([tr, va[train_only[va]]]), va[~train_only[va]]
    if args.tune:   # the setting most folds agreed on (ties: the smaller network)
        votes = Counter((f["hidden"], f["dropout"]) for f in folds)
        args.hidden, args.dropout = sorted(votes, key=lambda hp: (-votes[hp], hp))[0]
        print(f"final model uses hidden={args.hidden} dropout={args.dropout} (chosen by {votes[(args.hidden, args.dropout)]} of {len(folds)} folds)")
    net, mean, std, _, _ = train_one(X, y, cos, has_img, tr, va, args, args.seed, aux=aux, focus=is_focus)

    bundle = {
        "architecture": "thesis-late-fusion-v1",
        "positive_class": "distracting",
        "text": {"model": "google/embeddinggemma-300m", "prompt": "task: classification | query: ", "mrl_dim": TEXT_DIM, "max_seq_length": 128},
        "image": {"model": "mobilenet_v2", "dim": IMAGE_DIM, "input_size": 224},
        "input_layout": ["text_256", "image_1280", "cosine_1"],
        "standardize": {"mean": np.round(mean, 6).tolist(), "std": np.round(std, 6).tolist(), "image_block_zero_when_missing": True},
        "dense": {"hidden": args.hidden, "activation": "relu", "dropout": args.dropout, "output": "sigmoid",
                  "W1": np.round(net.W1, 6).tolist(), "b1": np.round(net.b1, 6).tolist(), "W2": np.round(net.W2, 6).tolist(), "b2": round(float(net.b2), 6)},
        "decision": {"alpha": alpha, "beta": beta, "hide_threshold": hide_t, "allow_threshold": allow_t,
                     "rule": "S = (1-beta)*cosine + beta*subject_score; C = alpha*S + (1-alpha)*(1-p_distract); hide if C < hide_threshold; allow if C >= allow_threshold; else warn "
                             "(subject_score = max over the student's chosen subjects of the subject head's probability; beta = 0 without a subject head)"},
        "evaluation": {"scheme": args.scheme, "folds": args.folds, "n_samples": int(len(y)), "summary": summary, "max_fpr_target": args.max_fpr, **extra_summary},
    }
    if focus_dec:
        bundle["decision_focus"] = {**focus_dec, "rule": "same score formula, used when the student set a keyword focus (context starts with 'focus:'); tuned on keyword-focus validation rows"}
    for key_, dd, why in (("decision_image", dec_img, "items scored together with a thumbnail"), ("decision_text", dec_txt, "items scored from text alone")):
        if dd: bundle[key_] = {**dd, "rule": f"same score formula; used for {why}; tuned on validation rows of that kind"}
    if aux:
        bundle["subjects"] = {"ids": subject_ids, "output": "sigmoid (multi-label)", "W3": np.round(net.W3, 6).tolist(), "b3": np.round(net.b3, 6).tolist()}
    Path(args.out).write_text(json.dumps(bundle))
    print("wrote", args.out)

    if args.report:
        Path(args.report + ".json").write_text(json.dumps({"args": vars(args), "folds": folds, "summary": summary, **extra_summary}, indent=1))
        lines = [f"# Evaluation ({args.scheme}, {args.folds} folds, n={len(y)})", "",
                 "| Fold | Train/Val/Test | hidden/dropout | alpha/beta | hide < | Accuracy | Precision | Recall | F1 | FPR |", "|---|---|---|---|---|---|---|---|---|---|"]
        for f in folds:
            t = f["test"]; lines.append(f"| {f['fold']} | {'/'.join(map(str, f['sizes']))} | {f['hidden']}/{f['dropout']} | {f['alpha']:.1f}/{f['beta']:.1f} | {f['hide_threshold']:.2f} | {t['accuracy']:.3f} | {t['precision']:.3f} | {t['recall']:.3f} | {t['f1']:.3f} | {t['false_positive_rate']:.3f} |")
        lines.append("| **mean ± sd** | | | | | " + " | ".join(f"**{summary[k]['mean']:.3f} ± {summary[k]['std']:.3f}**" for k in ["accuracy", "precision", "recall", "f1", "false_positive_rate"]) + " |")
        for name, blk in extra_summary.items():
            lines += ["", f"**{name}** (mean ± sd over folds): " + ", ".join(f"{k} {v['mean']:.3f} ± {v['std']:.3f}" for k, v in blk.items())]
        lines += ["", "HEADLINE numbers are on real items under the program context (kind = base), each scored with the decision for its input kind (thumbnail / text-only);",
                  "`headline_single_decision_previous_method` is the same rows with one decision for everything.",
                  "`thumbnail_rows_scored_with_image` vs `thumbnail_rows_image_switched_off_text_only_mode`: only items that have a thumbnail, scored with the image and with the image block switched off (what the popup's text-only mode does to this model).",
                  "`subject_context_rows` are the same items under a subject context",
                  "(augmented, easier). `keyword_focus_rows_weak_labels` use labels from text matches, so they are only indicative.",
                  "Positive class = distracting (hidden). FPR = share of relevant items that were wrongly hidden.",
                  "`subjects`: subject head on test rows with known subjects (micro-F1 at 0.5, top-1, macro-F1).",
                  "`heldout_keywords`: keyword-focus rows whose keyword was never used for training, validation or early stopping.",
                  "`video_youtube`, `online_articles`, `documents_repositories`: the headline rows split by where the item came from (the three categories of the study).",
                  "Confusion counts per fold are in the .json file."]
        Path(args.report + ".md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
