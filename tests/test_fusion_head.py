"""Gradient check + learning check for the NumPy Dense head. Run: python tests/test_fusion_head.py"""
import sys, pathlib
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "training"))
from fusion_head import DenseHead, sigmoid, metrics, decide, score_c, tune_decision

# 1) analytic gradient (the code path used in fit, dropout off) vs numerical gradient
rng = np.random.default_rng(1)
X = rng.normal(size=(12, 7)); y = (rng.random(12) > 0.5).astype(float)
net = DenseHead(7, hidden=5, dropout=0.0, seed=2)
def loss():
    p = net.predict(X); return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())
p, h, _ = net.forward(X, train=True, rng=rng)
dz = (p - y) / len(y)
dh = np.outer(dz, net.W2) * ((X @ net.W1 + net.b1) > 0)
analytic = {"W1": X.T @ dh, "W2": h.T @ dz}
for name in ("W1", "W2"):
    W = getattr(net, name); num = np.zeros_like(W)
    for i in np.ndindex(W.shape):
        old = W[i]; W[i] = old + 1e-6; up = loss(); W[i] = old - 1e-6; dn = loss(); W[i] = old
        num[i] = (up - dn) / 2e-6
    err = np.abs(num - analytic[name]).max()
    assert err < 1e-6, (name, err)
print("ok - analytic gradients match numerical gradients")

# 2) it learns a separable problem and the decision/metrics helpers behave
n = 600; yy = (rng.random(n) > 0.5).astype(float)
XX = rng.normal(size=(n, 40)) + yy[:, None] * 0.9
net = DenseHead(40, hidden=16, dropout=0.3, seed=3)
net.fit(XX[:400], yy[:400], XX[400:500], yy[400:500], epochs=60, image_dropout=0.0)
acc = ((net.predict(XX[500:]) > 0.5) == yy[500:]).mean(); assert acc > 0.85, acc
print(f"ok - learns a separable problem (held-out accuracy {acc:.2f})")
m = metrics([1, 1, 0, 0], [True, False, True, False]); assert (m["tp"], m["fn"], m["fp"], m["tn"]) == (1, 1, 1, 1) and m["false_positive_rate"] == 0.5
assert list(decide(np.array([0.2, 0.5, 0.9]), 0.4, 0.7)) == ["hide", "warn", "allow"]
pv = net.predict(XX[400:500]); t = tune_decision(pv, np.zeros(100), yy[400:500], max_fpr=0.1)
assert t["val_metrics"]["false_positive_rate"] <= 0.1 and t["met_fpr_target"]
print("ok - metrics, decision bands and threshold tuning")

# 3) multi-task head: learns multi-label subjects, ignores rows whose subjects are unknown, and the score helpers work
from fusion_head import subject_score
K = 4; n = 900
Sg = (rng.random((n, K)) < 0.25).astype(float)
Xs = rng.normal(size=(n, 30)); Xs[:, :K] += 5.0 * Sg
ys = (Sg.sum(1) == 0).astype(float)                         # no subject = distracting
net = DenseHead(30, hidden=24, dropout=0.2, seed=4, n_subjects=K)
net.fit(Xs[:600], ys[:600], Xs[600:750], ys[600:750], epochs=80, image_dropout=0.0, S=Sg[:600], known=np.ones(600, bool), Sv=Sg[600:750], known_v=np.ones(150, bool))
q = net.subject_probs(Xs[750:]); pr = q > 0.5; tr_ = Sg[750:] == 1
tp_ = (pr & tr_).sum(); acc = 2 * tp_ / (pr.sum() + tr_.sum()); assert acc > 0.85, acc      # micro-F1 (rare positives are weighted up, so plain accuracy is not the right check)
assert ((net.predict(Xs[750:]) > 0.5) == (ys[750:] == 1)).mean() > 0.85
W3_before = DenseHead(30, hidden=24, dropout=0.2, seed=4, n_subjects=K).W3.copy()
net2 = DenseHead(30, hidden=24, dropout=0.0, seed=4, n_subjects=K)
net2.fit(Xs[:200], ys[:200], Xs[200:260], ys[200:260], epochs=2, weight_decay=0.0, image_dropout=0.0, S=Sg[:200], known=np.zeros(200, bool), Sv=Sg[200:260], known_v=np.zeros(60, bool))
assert np.abs(net2.W3 - W3_before).max() < 1e-3, "unlabeled rows must not train the subject output"
assert np.allclose(subject_score(np.array([[.9, .2, .1]]), np.array([[0, 1, 0]])), [.2]) and np.allclose(subject_score(np.array([[.9, .2, .1]]), np.array([[0, 0, 0]])), [.9])
c = score_c(np.array([0.1]), np.array([0.3]), 0.5, subj=np.array([0.9]), beta=1.0); assert np.allclose(c, 0.5 * 0.9 + 0.5 * 0.9)
t = tune_decision(net.predict(Xs[600:750]), np.full(150, .3), ys[600:750], max_fpr=0.1, subj=subject_score(net.subject_probs(Xs[600:750])))
assert "beta" in t and t["val_metrics"]["false_positive_rate"] <= 0.1
print(f"ok - multi-task head (subject micro-F1 {acc:.2f}), unlabeled rows ignored, subject score blends into C")
