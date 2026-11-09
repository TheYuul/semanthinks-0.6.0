"""End-to-end check of train_fusion.py -> model_bundle.json -> ThesisEngine on SYNTHETIC features.
It proves the code path works and that serving reproduces training exactly. It says nothing about real accuracy.
Run: python tests/test_pipeline.py"""
import json, subprocess, sys, tempfile, pathlib
import numpy as np
root = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(root / "training")); sys.path.insert(0, str(root / "backend"))
from fusion_head import DenseHead, score_c, decide
from train_fusion import standardize
from thesis_engine import ThesisEngine

rng = np.random.default_rng(7)
N = 400
y = (rng.random(N) > 0.5).astype(int)
unit = lambda v: v / np.linalg.norm(v, axis=-1, keepdims=True)
ctx = unit(rng.normal(size=256))
topic = unit(rng.normal(size=256))
text = unit(0.12 * rng.normal(size=(N, 256)) + np.where(y[:, None] == 0, 1.0 * ctx, 1.0 * topic))
image = np.abs(rng.normal(size=(N, 1280)) + y[:, None] * 0.3)
has_image = rng.random(N) < 0.8
image[~has_image] = 0
cosine = text @ ctx
tmp = pathlib.Path(tempfile.mkdtemp())
np.savez(tmp / "f.npz", text=text, image=image, cosine=cosine, y=y, has_image=has_image)

for scheme in ("kfold", "holdout7015"):
    out = tmp / f"{scheme}_bundle.json"
    r = subprocess.run([sys.executable, str(root / "training" / "train_fusion.py"), str(tmp / "f.npz"), str(out), "--scheme", scheme,
                        "--epochs", "25", "--hidden", "32", "--report", str(tmp / f"{scheme}_report")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
    report = json.loads((tmp / f"{scheme}_report.json").read_text())
    sizes = report["folds"][0]["sizes"]
    assert len(report["folds"]) == 5 and abs(sum(sizes) - N) <= 1, sizes
    if scheme == "kfold": assert abs(sizes[2] / N - 0.2) < 0.02 and abs(sizes[1] / N - 0.15) < 0.02, sizes
    else: assert abs(sizes[2] / N - 0.15) < 0.02 and abs(sizes[1] / N - 0.15) < 0.02 and abs(sizes[0] / N - 0.70) < 0.02, sizes
    f1 = report["summary"]["f1"]["mean"]; assert f1 > 0.8, f1
    print(f"ok - {scheme}: sizes train/val/test = {sizes}, mean F1 {f1:.2f}, mean FPR {report['summary']['false_positive_rate']['mean']:.3f}")
assert (tmp / "kfold_report.md").read_text().startswith("# Evaluation")
r = subprocess.run([sys.executable, str(root / "training" / "train_fusion.py"), str(tmp / "f.npz"), str(tmp / "tuned_bundle.json"), "--epochs", "10", "--tune", "--report", str(tmp / "tuned_report")], capture_output=True, text=True)
assert r.returncode == 0, r.stderr[-800:]
assert r.stdout.count("tuning picked") == 5 and "final model uses hidden=" in r.stdout
tb = json.loads((tmp / "tuned_bundle.json").read_text()); assert len(tb["dense"]["W1"][0]) in (64, 128, 256)
assert "hidden/dropout" in (tmp / "tuned_report.md").read_text()
print("ok - --tune: per-fold grid search on validation only, final model uses the majority choice, report lists hyperparameters")

bundle = json.loads((tmp / "kfold_bundle.json").read_text())
assert len(bundle["standardize"]["mean"]) == 1537 and len(bundle["dense"]["W1"]) == 1537 and len(bundle["dense"]["W1"][0]) == 32
print("ok - bundle layout: 256 text + 1280 image + 1 cosine = 1537 inputs")

# Serving must reproduce training: same standardization, same weights -> same probability.
net = DenseHead(1537, hidden=32, dropout=0.3)
net.W1, net.b1, net.W2, net.b2 = np.array(bundle["dense"]["W1"]), np.array(bundle["dense"]["b1"]), np.array(bundle["dense"]["W2"]), bundle["dense"]["b2"]
mean, std = np.array(bundle["standardize"]["mean"]), np.array(bundle["standardize"]["std"])
X = np.hstack([text, image, cosine[:, None]])
Z = standardize(X, mean, std, has_image)
ref = net.predict(Z)
eng = ThesisEngine.__new__(ThesisEngine)
eng.W1, eng.b1, eng.W2, eng.b2, eng.mean, eng.std = net.W1, net.b1, net.W2, net.b2, mean, std
eng.W3 = eng.b3 = None; eng.subject_ids = []; eng.beta = 0.0
mine = np.array([eng.head(X[i].copy(), bool(has_image[i])) for i in range(N)])
assert np.abs(ref - mine).max() < 1e-9, np.abs(ref - mine).max()
print(f"ok - serving matches training (max difference {np.abs(ref - mine).max():.1e}, rows with and without image)")

# Full engine with fake embedders: image missing -> neutral image block; actions follow the bands.
lookup = {f"t{i}": text[i] for i in range(N)}
fake_ctx = ctx
def embed_text(s): return lookup.get(s, fake_ctx)
engine = ThesisEngine(tmp / "kfold_bundle.json", embed_text, lambda b: image[int(b.decode())], lambda url: str(int(url)).encode() if url else None)
actions = {"hide": 0, "warn": 0, "allow": 0}
for i in range(N):
    res = engine.classify(f"t{i}", str(i) if has_image[i] else None, "anything")
    actions[res["action"]] += 1
    assert res["block"] == (res["action"] == "hide") and 0 <= res["score"] <= 1 and res["mode"] == ("fused" if has_image[i] else "text")
    c, a = engine.decide(res["p_distract"], res["cosine"]); assert a == res["action"]
dec = bundle["decision"]
assert dec["allow_threshold"] >= dec["hide_threshold"]
print("ok - engine actions:", actions, "| alpha", dec["alpha"], "hide <", dec["hide_threshold"], "allow >=", dec["allow_threshold"])

# ---- group-aware splits: items of one group (same video/channel) must never be split across train/val/test ----
from train_fusion import splits
G = 300; groups = np.array([f"g{i % G}" for i in range(N)])        # ~1.3 rows per group; many groups hold both classes
yy = (np.array([i % G for i in range(N)]) % 2).astype(int)         # label constant within a group so stratification is possible
for scheme in ("kfold", "holdout7015"):
    n_folds = 0
    for tr, va, te in splits(yy, scheme, 5, 3, groups):
        n_folds += 1
        assert not (set(groups[tr]) & set(groups[te])) and not (set(groups[tr]) & set(groups[va])) and not (set(groups[va]) & set(groups[te])), "group leaked across splits"
        assert len(set(tr) | set(va) | set(te)) == len(tr) + len(va) + len(te)
        assert 0.1 < len(va) / N < 0.2
    assert n_folds == 5
print("ok - group-aware splits: no group appears in more than one of train/validation/test (both schemes)")
r = subprocess.run([sys.executable, str(root / "training" / "train_fusion.py"), str(tmp / "g.npz"), str(tmp / "g_bundle.json"), "--epochs", "5"], capture_output=True, text=True) if np.savez(tmp / "g.npz", text=text, image=image, cosine=cosine, y=y, has_image=has_image, groups=np.array([f"g{i // 2}" for i in range(N)])) is None else None
assert r.returncode == 0 and "group-aware splits: 200 groups" in r.stdout, (r.stdout[-300:], r.stderr[-500:])
print("ok - train_fusion.py uses the groups stored in features.npz")

# ---- extract_features.py logic with a fake extractor (no models needed) ----
import csv, runpy, thesis_features
class Fake:
    def embed_texts(self, texts, batch_size=64):
        out = []
        for t in texts:
            v = np.random.default_rng(abs(hash(t)) % (2**32)).normal(size=256); out.append(v / np.linalg.norm(v))
        return np.array(out)
    def embed_image(self, data): return np.full(1280, 0.5)
thesis_features.FeatureExtractor = Fake
d = tmp / "ds"; (d / "thumbs").mkdir(parents=True); (d / "thumbs" / "a.jpg").write_bytes(b"x")
with open(d / "dataset.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["id", "text", "image_path", "label", "language", "source", "context", "group"])
    w.writerow(["1", "Finite automata", "thumbs/a.jpg", "relevant", "en", "youtube", "Automata", "chanA"])
    w.writerow(["2", "Prank video", "thumbs/missing.jpg", "distracting", "en", "youtube", "", "chanA"])
    w.writerow(["3", "Sponsored: buy now", "", "1", "en", "article", "", ""])
sys.argv = ["extract_features.py", str(d / "dataset.csv"), str(d / "f.npz"), "--images-dir", str(d)]
runpy.run_path(str(root / "training" / "extract_features.py"), run_name="__main__")
z = np.load(d / "f.npz")
assert z["text"].shape == (3, 256) and z["image"].shape == (3, 1280) and z["text"].dtype == np.float32
assert list(z["has_image"]) == [True, False, False] and list(z["y"]) == [0, 1, 1] and list(z["groups"]) == ["chanA", "chanA", "3"]
assert np.all(z["image"][1:] == 0) and -1 <= z["cosine"].min() and z["cosine"].max() <= 1
print("ok - extract_features.py: labels, missing images, groups and shapes (with a fake extractor)")


# ---- multi-task: subject head + held-out keyword rows, trained through the CLI and served by the engine ----
K = 4; ids_k = ["database", "networks", "programming", "automata"]
sub_of = rng.integers(0, K, N)                                  # each relevant row belongs to one subject, distracting rows to none
protos = unit(rng.normal(size=(K, 256)))
yk = (rng.random(N) > 0.45).astype(int)
tk = unit(0.15 * rng.normal(size=(N, 256)) + np.where(yk[:, None] == 0, protos[sub_of], topic))
S = np.zeros((N, K), np.float32); S[np.arange(N)[yk == 0], sub_of[yk == 0]] = 1
imgk = np.abs(rng.normal(size=(N, 1280)) + yk[:, None] * 0.2)
ctxm = np.zeros((N, K), np.float32); ctxm[np.arange(N), sub_of] = 1                  # context = the item's own subject
held = np.zeros(N, bool); held[rng.choice(N, 40, replace=False)] = True
np.savez(tmp / "mt.npz", text=tk, image=imgk, cosine=np.sum(tk * protos[sub_of], 1), y=yk, has_image=np.ones(N, bool), subjects=S,
         subject_known=np.ones(N, bool), ctx_subjects=ctxm, subject_ids=np.array(ids_k), heldout=held)
r = subprocess.run([sys.executable, str(root / "training" / "train_fusion.py"), str(tmp / "mt.npz"), str(tmp / "mt_bundle.json"), "--epochs", "40", "--hidden", "32",
                    "--report", str(tmp / "mt_report")], capture_output=True, text=True)
assert r.returncode == 0, r.stderr[-900:]
rep = json.loads((tmp / "mt_report.json").read_text())
assert "subject head on: 4 subjects" in r.stdout and "40 held-out keyword rows" in r.stdout
assert rep["subjects"]["micro_f1"]["mean"] > 0.7 and rep["heldout_keywords"]["f1"]["mean"] > 0.7, (rep["subjects"], rep["heldout_keywords"])
assert all(sum(f["sizes"]) + 0 <= N - 40 + 5 for f in rep["folds"]), "held-out rows must not be in train/val/test"
mb = json.loads((tmp / "mt_bundle.json").read_text())
assert mb["subjects"]["ids"] == ids_k and len(mb["subjects"]["W3"]) == 32 and len(mb["subjects"]["W3"][0]) == K and mb["decision"]["beta"] in (0.0, 0.5, 1.0)
print(f"ok - multi-task training: subject micro-F1 {rep['subjects']['micro_f1']['mean']:.2f}, held-out keyword F1 {rep['heldout_keywords']['f1']['mean']:.2f}, bundle has the subject head")
lk = {f"t{i}": tk[i] for i in range(N)}
eng2 = ThesisEngine(tmp / "mt_bundle.json", lambda s_: lk.get(s_, protos[0]), lambda b: imgk[int(b.decode())], lambda url: str(int(url)).encode() if url else None)
net2 = DenseHead(1537, hidden=32); d3 = mb["dense"]
net2.W1, net2.b1, net2.W2, net2.b2 = np.array(d3["W1"]), np.array(d3["b1"]), np.array(d3["W2"]), d3["b2"]
net2.K = K; net2.W3, net2.b3 = np.array(mb["subjects"]["W3"]), np.array(mb["subjects"]["b3"])
Xk = np.hstack([tk, imgk, np.sum(tk * protos[0], 1)[:, None]]); Zk = standardize(Xk, np.array(mb["standardize"]["mean"]), np.array(mb["standardize"]["std"]), np.ones(N, bool))
qref = net2.subject_probs(Zk)
for i in range(0, N, 40):
    res = eng2.classify(f"t{i}", str(i), "ctx", ["networks"])
    assert abs(res["detected_subjects"][0]["p"] - qref[i].max()) < 1e-3 and res["detected_subjects"][0]["id"] == ids_k[int(qref[i].argmax())]
    assert abs(res["subject_score"] - qref[i][1]) < 1e-3                                    # chosen = networks only
    assert abs(eng2.classify(f"t{i}", str(i), "ctx", [])["subject_score"] - qref[i].max()) < 1e-3   # nothing chosen = any subject
print("ok - engine reproduces the subject head and scores against only the chosen subjects")


# ---- catalog (syllabus-derived) rows are training only: never in validation or test ----
kind = np.array(["catalog" if i % 5 == 0 else "base" for i in range(N)])
np.savez(tmp / "cat.npz", text=tk, image=imgk, cosine=np.sum(tk * protos[sub_of], 1), y=yk, has_image=np.ones(N, bool), subjects=S, subject_known=np.ones(N, bool),
         ctx_subjects=ctxm, subject_ids=np.array(ids_k), kind=kind, heldout=np.zeros(N, bool))
r = subprocess.run([sys.executable, str(root / "training" / "train_fusion.py"), str(tmp / "cat.npz"), str(tmp / "cat_bundle.json"), "--epochs", "10", "--hidden", "16", "--report", str(tmp / "cat_report")],
                   capture_output=True, text=True)
assert r.returncode == 0 and f"{int((kind == 'catalog').sum())} catalog rows (training only)" in r.stdout, (r.stdout[-400:], r.stderr[-400:])
rep = json.loads((tmp / "cat_report.json").read_text()); n_real = int((kind != "catalog").sum())
assert all(f["sizes"][1] + f["sizes"][2] <= n_real * 0.4 for f in rep["folds"]), "validation/test must contain no catalog rows"
assert all(f["sizes"][2] <= 0.25 * n_real for f in rep["folds"]) and all(f["sizes"][0] > 0.6 * N for f in rep["folds"]), [f["sizes"] for f in rep["folds"]]
print("ok - catalog rows go to training only; validation and test hold real rows")
