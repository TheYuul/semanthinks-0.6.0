"""
fusion_head.py - the thesis "Dense Linear Classifier", the decision rule and the metrics.

Input  x = [text_256 | image_1280 | cosine_1]   (1536 fused tensor + the cosine similarity, as in Chapter 3)
Model  Dense(H) -> ReLU -> Dropout -> Dense(1) -> Sigmoid  = p_distract
Score  C = alpha * S + (1 - alpha) * (1 - p_distract),  S = clip(cosine, 0, 1)
Rule   C >= allow_threshold          -> allow
       hide_threshold <= C < allow   -> warn   (soft warning, student may dismiss)
       C <  hide_threshold           -> hide

Positive class = DISTRACTING (label 1, to be hidden). A false positive is therefore a legitimate
academic item that was hidden, which is the error the panel asked us to track separately.

Pure NumPy, so it trains and tests without PyTorch.
"""
import numpy as np


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -60, 60)))


class DenseHead:
    """Shared Dense(H)+ReLU(+dropout) trunk with two outputs:
         p_distract  : sigmoid(1)                       (the thesis binary head)
         q_subject   : sigmoid(K), multi-label          (optional; which curriculum subjects the item belongs to)
    n_subjects = 0 gives the original single-output head."""

    def __init__(self, n_in, hidden=128, dropout=0.3, seed=0, n_subjects=0):
        rng = np.random.default_rng(seed)
        self.hidden, self.dropout, self.K = hidden, dropout, n_subjects
        self.W1 = rng.normal(0, np.sqrt(2.0 / n_in), (n_in, hidden))     # He init (ReLU)
        self.b1 = np.zeros(hidden)
        self.W2 = rng.normal(0, np.sqrt(1.0 / hidden), hidden)
        self.b2 = 0.0
        if n_subjects:
            self.W3 = rng.normal(0, np.sqrt(1.0 / hidden), (hidden, n_subjects))
            self.b3 = np.zeros(n_subjects)

    def _params(self):
        return ["W1", "b1", "W2", "b2"] + (["W3", "b3"] if self.K else [])

    def forward(self, X, train=False, rng=None):
        h = np.maximum(0.0, X @ self.W1 + self.b1)
        mask = None
        if train and self.dropout > 0:
            mask = (rng.random(h.shape) >= self.dropout) / (1.0 - self.dropout)   # inverted dropout
            h = h * mask
        return sigmoid(h @ self.W2 + self.b2), h, mask

    def predict(self, X):
        return self.forward(X)[0]

    def subject_probs(self, X):
        assert self.K, "model has no subject head"
        return sigmoid(np.maximum(0.0, X @ self.W1 + self.b1) @ self.W3 + self.b3)

    def fit(self, X, y, Xv, yv, epochs=200, batch=64, lr=1e-3, weight_decay=1e-4, patience=15,
            image_dropout=0.2, image_slice=slice(256, 1536), seed=0,
            S=None, known=None, Sv=None, known_v=None, subject_weight=0.5):
        """Adam + binary cross-entropy, early stopping on validation loss.
        image_dropout: share of training rows whose image block is zeroed, so the model also works when
        a card has no thumbnail (text-only articles, thumbnail not loaded yet).
        Subject head (when K > 0): S (n,K) multi-hot subject labels, known (n,) True where the row's subjects are
        labeled (distracting rows count as known: no subject). Unlabeled rows only train the binary output."""
        rng = np.random.default_rng(seed)
        params = self._params()
        use_s = bool(self.K) and S is not None
        m = {k: 0.0 for k in params}; v = {k: 0.0 for k in params}
        t = 0
        best = (np.inf, None); bad = 0
        pos_w = 0.5 * len(y) / max(1, y.sum()); neg_w = 0.5 * len(y) / max(1, len(y) - y.sum())   # balanced classes
        if use_s:
            kn = np.asarray(known, bool); pos = S[kn].sum(0); nk = max(1, kn.sum())
            sw_k = np.clip((nk - pos) / np.maximum(pos, 1), 1.0, 10.0)           # rare subjects count more (capped)
        history = []
        for epoch in range(epochs):
            order = rng.permutation(len(y))
            for s in range(0, len(y), batch):
                idx = order[s:s + batch]
                xb, yb = X[idx].copy(), y[idx]
                if image_dropout > 0:
                    drop = rng.random(len(idx)) < image_dropout
                    xb[drop, image_slice] = 0.0
                p, h, mask = self.forward(xb, train=True, rng=rng)
                w = np.where(yb == 1, pos_w, neg_w)
                dz = (p - yb) * w / len(idx)
                gW2 = h.T @ dz + weight_decay * self.W2
                gb2 = dz.sum()
                dh = np.outer(dz, self.W2)
                grads = {}
                if use_s:
                    q = sigmoid(h @ self.W3 + self.b3)
                    Sb = S[idx]
                    dz3 = (q - Sb) * np.where(Sb == 1, sw_k, 1.0) * kn[idx][:, None] * subject_weight / len(idx)
                    grads["W3"] = h.T @ dz3 + weight_decay * self.W3; grads["b3"] = dz3.sum(0)
                    dh = dh + dz3 @ self.W3.T
                if mask is not None: dh = dh * mask
                dh = dh * ((xb @ self.W1 + self.b1) > 0)          # ReLU derivative
                grads["W1"] = xb.T @ dh + weight_decay * self.W1; grads["b1"] = dh.sum(0); grads["W2"] = gW2; grads["b2"] = gb2
                t += 1
                for k in params:
                    g = grads[k]
                    m[k] = 0.9 * m[k] + 0.1 * g
                    v[k] = 0.999 * v[k] + 0.001 * g * g
                    step = lr * (m[k] / (1 - 0.9 ** t)) / (np.sqrt(v[k] / (1 - 0.999 ** t)) + 1e-8)
                    setattr(self, k, getattr(self, k) - step)
            pv = np.clip(self.predict(Xv), 1e-7, 1 - 1e-7)
            wv = np.where(yv == 1, pos_w, neg_w)
            loss = float(-(wv * (yv * np.log(pv) + (1 - yv) * np.log(1 - pv))).mean())
            if use_s and Sv is not None and np.asarray(known_v).any():
                kv = np.asarray(known_v, bool); qv = np.clip(self.subject_probs(Xv[kv]), 1e-7, 1 - 1e-7); sv = Sv[kv]
                loss += subject_weight * float(-(np.where(sv == 1, sw_k, 1.0) * (sv * np.log(qv) + (1 - sv) * np.log(1 - qv))).mean())
            history.append(loss)
            if loss < best[0] - 1e-5:
                best = (loss, {k: np.copy(getattr(self, k)) if k not in ("b2",) else float(self.b2) for k in params}); bad = 0
            else:
                bad += 1
                if bad >= patience: break
        for k, val in best[1].items(): setattr(self, k, val)
        return history


# ---------- decision rule ----------
def subject_score(q, ctx_mask=None):
    """How strongly the item belongs to the subjects of the student's context: max over the chosen subjects.
    q (n,K) subject probabilities; ctx_mask (n,K) 0/1, or None/all-zero rows = every subject."""
    q = np.asarray(q)
    if ctx_mask is None: return q.max(1)
    mk = np.asarray(ctx_mask, float)
    mk = np.where(mk.sum(1, keepdims=True) == 0, 1.0, mk)
    return (q * mk).max(1)


def score_c(p_distract, cosine, alpha, subj=None, beta=0.0):
    """C = alpha*S + (1-alpha)*(1-p). S is the cosine to the context; when a subject head exists, S mixes in the
    subject score: S = (1-beta)*cosine + beta*subject_score (beta = 0 is the original thesis formula)."""
    s = np.clip(cosine, 0.0, 1.0)
    if subj is not None and beta: s = (1.0 - beta) * s + beta * np.clip(subj, 0.0, 1.0)
    return alpha * s + (1.0 - alpha) * (1.0 - p_distract)


def decide(c, hide_threshold, allow_threshold):
    """Returns 'allow' / 'warn' / 'hide' for scalars or arrays."""
    c = np.asarray(c)
    return np.where(c < hide_threshold, "hide", np.where(c >= allow_threshold, "allow", "warn"))


def allow_for(hide_threshold, band=0.30):
    return min(1.0, round(hide_threshold + band, 4))      # thesis defaults: hide < 0.40, allow >= 0.70


# ---------- metrics ----------
def metrics(y_true, hidden):
    """y_true: 1 = distracting. hidden: bool, True if the system hid it."""
    y_true = np.asarray(y_true).astype(int); pred = np.asarray(hidden).astype(int)
    tp = int(((pred == 1) & (y_true == 1)).sum()); tn = int(((pred == 0) & (y_true == 0)).sum())
    fp = int(((pred == 1) & (y_true == 0)).sum()); fn = int(((pred == 0) & (y_true == 1)).sum())
    div = lambda a, b: float(a / b) if b else 0.0
    precision, recall = div(tp, tp + fp), div(tp, tp + fn)
    return {"accuracy": div(tp + tn, len(y_true)), "precision": precision, "recall": recall,
            "f1": div(2 * precision * recall, precision + recall), "false_positive_rate": div(fp, fp + tn),
            "tp": tp, "tn": tn, "fp": fp, "fn": fn}


def tune_decision(p, cosine, y, max_fpr=0.05, subj=None):
    """Pick alpha (fusion weight), beta (subject share of S; only when `subj` is given) and the hide threshold on the
    VALIDATION split. Best F1 among settings whose false-positive rate is at most max_fpr; if none qualifies, the lowest FPR."""
    best, fallback = None, None
    for beta in ((0.0, 0.5, 1.0) if subj is not None else (0.0,)):
        for alpha in np.round(np.arange(0.0, 1.01, 0.1), 2):
            c = score_c(p, cosine, alpha, subj, beta)
            for t in np.round(np.arange(0.05, 0.96, 0.01), 2):
                m = metrics(y, c < t)
                cand = (m["f1"], -m["false_positive_rate"], alpha, t, m, beta)
                if m["false_positive_rate"] <= max_fpr and (best is None or cand[:2] > best[:2]): best = cand
                if fallback is None or (m["false_positive_rate"], -m["f1"]) < (fallback[4]["false_positive_rate"], -fallback[4]["f1"]):
                    fallback = cand
    chosen = best or fallback
    return {"alpha": float(chosen[2]), "beta": float(chosen[5]), "hide_threshold": float(chosen[3]), "val_metrics": chosen[4], "met_fpr_target": best is not None}
