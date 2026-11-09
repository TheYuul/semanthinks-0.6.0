"""Tests for clean_dataset, build_reference, audit sampling/scoring and the cosine baseline on synthetic data.
Run: python tests/test_dataset_tools.py"""
import sys, pathlib, tempfile, subprocess
import numpy as np, pandas as pd
root = pathlib.Path(__file__).parent.parent
for d in ("tools", "training"): sys.path.insert(0, str(root / d))
import clean_dataset as cd, build_reference as br, make_audit_sample as mk, score_audit as sa, baseline_cosine as bc
from build_catalog import build_subjects, program_contexts

subjects, _, courses = build_subjects(str(root / "tools" / "Keywords.xlsx"))
ctx = program_contexts(subjects)["Both"]

def row(i, title, desc, label, lang="english", domain="prg", group=None, vid=None, img=None):
    return dict(id=f"r{i}", platform="youtube", source_url="", source_type="x", title_text=title, description_text=desc,
                language_heuristic=lang, language_verified=lang, domain=domain, label=label, annotation_notes="", qc_status="retained",
                group_id=group or f"g{i}", source_query="", image_url=img or "", youtube_video_id=vid or "")

raw = pd.DataFrame([
    row(1, "Python programming tutorial for beginners", "Learn variables and loops in Python programming", "1", vid="abc", img="https://i.ytimg.com/vi/abc/hqdefault.jpg"),
    row(2, "Python programming tutorial for beginners", "Learn variables and loops in Python programming", "1"),              # exact duplicate
    row(3, "Funny cat compilation", "Cats doing silly things all day long", "0", domain="non_csit"),
    row(4, "Mixed up item", "Same text different labels here", "1"), row(5, "Mixed up item", "Same text different labels here", "0"),   # conflict
    row(6, "Pano mag-aral ng SQL database", "Tutorial sa database indexing at query optimization", "1", lang="taglish", domain="db"),
    row(7, "Excluded language item", "This one was marked exclude by annotators", "0", lang="exclude"),
    row(8, "Hi", "", "0"),                                                             # too short
    row(9, "Broken row", "shifted columns", "german"),
    row(10, "Stock market outlook for the quarter", "Analysts expect strong earnings across sectors", "1", domain="non_csit"),   # contradiction                                 # malformed label
])
out, rej, conf, st = cd.clean(raw, subjects, ctx)
assert list(out["id"]) == ["r1", "r3", "r6"], list(out["id"])
assert dict(zip(out["id"], out["label"])) == {"r1": "relevant", "r3": "distracting", "r6": "relevant"}     # export 1 = relevant
assert out.set_index("id").loc["r1", "image_path"] == "abc.jpg" and out.set_index("id").loc["r3", "image_path"] == ""
assert set(out["context"]) == {ctx}                                                    # label-independent
assert len(conf) == 2 and st["conflict_texts"] == 1
reasons = set(st["reject_reasons"])
assert any("contradiction" in r for r in reasons) and any("exclude" in r for r in reasons) and any("duplicate" in r for r in reasons) and any("shorter" in r for r in reasons) and any("malformed" in r for r in reasons)
o = out.set_index("id")
assert "database" in o.loc["r6", "domain_subjects"] and o.loc["r6", "curriculum_basis"] == "both" and "indexing" in o.loc["r6", "matched_keywords"]
assert o.loc["r3", "curriculum_basis"] == "none" and o.loc["r1", "domain_subjects"].startswith("programming")

ref = list(br.rows(str(root / "tools" / "Keywords.xlsx")))
assert len(ref) == sum(len(s["programs"]) for s in subjects) and all(r["keywords"] is not None for r in ref)
assert any(r["topic_source"].startswith("draft") for r in ref) and any(r["topic_source"].startswith("official") for r in ref)

big = pd.DataFrame({"id": [f"i{i}" for i in range(600)], "text": ["t"] * 600, "language": ["english"] * 600,
                    "label": np.where(np.arange(600) % 3 == 0, "relevant", "distracting"),
                    "domain": np.random.default_rng(0).choice(["prg", "ai", "non_csit", "db"], 600), "curriculum_basis": "none"})
s = mk.sample(big, 120)
assert len(s) == 120 and s["id"].is_unique and set(s["label"]) == {"relevant", "distracting"}
sheet = s[["id", "text", "language"]].copy(); assert "label" not in sheet and "domain" not in sheet
sheet["annotator_label"] = np.where(np.arange(120) < 12, np.where(s["label"] == "relevant", "distracting", "relevant"), s["label"])
r = sa.score(sheet, s[["id", "label", "domain", "curriculum_basis"]])
assert r["n"] == 120 and abs(r["noise_rate"] - 0.1) < 1e-9 and r["ci"][0] < 0.9 < r["ci"][1] and 0.7 < r["kappa"] < 0.9
assert abs(sa.kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]) - 1.0) < 1e-9

rng = np.random.default_rng(3); n = 500; y = (rng.random(n) > 0.5).astype(int)
cos = np.clip(0.6 - 0.25 * y + 0.12 * rng.normal(size=n), 0, 1)
res = bc.evaluate(cos, y, None, max_fpr=0.1)
assert res["false_positive_rate"][0] <= 0.2 and res["recall"][0] > 0.4 and res["accuracy"][0] > 0.65
print("dataset tool tests passed")

# ---- thumbnail downloader against a local test server, and the pipeline runner's smoke subset ----
import threading, http.server, socketserver, os, tempfile as _tf
sys.path.insert(0, str(root))
import download_thumbnails as dl, run_pipeline as rp
srv_dir = pathlib.Path(_tf.mkdtemp()); (srv_dir / "a.jpg").write_bytes(b"\xff\xd8\xff" + b"x" * 900)
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=str(srv_dir), **k)
    def log_message(self, *a): pass
httpd = socketserver.TCPServer(("127.0.0.1", 0), H); port = httpd.server_address[1]; threading.Thread(target=httpd.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{port}/"
out_dir = pathlib.Path(_tf.mkdtemp())
frame = pd.DataFrame({"image_path": ["a.jpg", "a.jpg", "b.jpg", "evil.jpg", ""], "image_url": [base + "a.jpg", base + "a.jpg", base + "missing.jpg", "https://evil.example/x.jpg", ""]})
todo = dl.jobs(frame, out_dir, allowed=base)
assert [d.name for _, d in todo] == ["a.jpg", "b.jpg"], "duplicates and non-allowlisted hosts are skipped"
assert dl.jobs(frame, out_dir, allowed="https://i.ytimg.com/") == [], "only i.ytimg.com is fetched by default"
assert dl.fetch(*todo[0]) is None and (out_dir / "a.jpg").exists() and dl.fetch(*todo[1]) is not None
assert [d.name for _, d in dl.jobs(frame, out_dir, allowed=base)] == ["b.jpg"], "downloaded files are skipped on re-run"
httpd.shutdown()
tdf = pd.DataFrame({"id": [f"i{n}" for n in range(60)], "group": [f"g{n % 30}" for n in range(60)], "label": ["relevant" if n % 2 else "distracting" for n in range(60)],
                    "subjects": ["database" if n % 6 == 1 else "none" for n in range(60)]})
tdf.to_csv(out_dir / "t.csv", index=False)
n_rows = rp.smoke_subset(out_dir / "t.csv", out_dir / "s.csv", 6); sub = pd.read_csv(out_dir / "s.csv", dtype=str)
assert 0 < n_rows < 60 and set(sub["label"]) == {"relevant", "distracting"} and sub.groupby("group")["id"].count().min() == 2
print("ok - thumbnail downloader (allowlist, dedupe, resume) and smoke subset")
