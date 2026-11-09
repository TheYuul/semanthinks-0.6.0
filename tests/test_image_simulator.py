"""Checks tools/image_simulator.py end to end with fake embedders and a small made-up model file."""
import base64, io, json, sys, tempfile, threading, urllib.request, urllib.error
from pathlib import Path
import numpy as np
from PIL import Image

root = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(root / "tools"), str(root / "backend")]
import image_simulator as sim
from thesis_features import TEXT_DIM, IMAGE_DIM

rng = np.random.default_rng(0); n = TEXT_DIM + IMAGE_DIM + 1; K = 3
bundle = {"architecture": "thesis-late-fusion-v1", "input_layout": ["text_256", "image_1280", "cosine_1"],
          "dense": {"W1": (rng.normal(size=(n, 8)) * 0.05).tolist(), "b1": [0.0] * 8, "W2": rng.normal(size=8).tolist(), "b2": 0.0},
          "standardize": {"mean": [0.0] * n, "std": [1.0] * n},
          "decision": {"alpha": 0.5, "beta": 0.0, "hide_threshold": 0.4, "allow_threshold": 0.7},
          "decision_image": {"alpha": 0.5, "beta": 0.0, "hide_threshold": 0.2, "allow_threshold": 0.5},
          "decision_text": {"alpha": 0.5, "beta": 0.0, "hide_threshold": 0.4, "allow_threshold": 0.7},
          "decision_focus": {"alpha": 0.5, "beta": 0.0, "hide_threshold": 0.8, "allow_threshold": 0.95},
          "subjects": {"ids": ["programming", "database", "networks"], "W3": (rng.normal(size=(8, K))).tolist(), "b3": [0.0] * K}}
tmp = Path(tempfile.mkdtemp()); (tmp / "b.json").write_text(json.dumps(bundle))
eng, store = sim.make_engine(True, tmp / "b.json")
ctxs = sim.Contexts(); s = sim.Simulator(eng, store, ctxs)
assert len(s.meta()["subjects"]) >= 30
assert ctxs.build("", "") == ctxs.programs["Both"]; assert ctxs.build("programming", "c++").startswith("focus: c++ | ")
assert ctxs.build("programming", "").startswith("Computer Programming")
print("ok - contexts match the extension's format (program, subject, focus)")

def png(color):
    b = io.BytesIO(); Image.new("RGB", (64, 48), color).save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()

r = s.classify({"image": png("red"), "title": "Intro to SQL joins", "subject": "database", "focus": ""})
assert r["with_image"]["mode"] == "fused" and r["text_only"]["mode"] == "text" and r["with_image"]["action"] in ("hide", "warn", "allow")
print("ok - an uploaded image is scored in fused mode and the same card is also scored without it")
assert r["with_image"]["threshold"] == 0.2 and r["text_only"]["threshold"] == 0.4 and r["with_image"]["allow_threshold"] == 0.5
print("ok - a card with a thumbnail uses the thumbnail decision, a card without one uses the text decision")
assert "upload" not in store; print("ok - the upload is not kept")
r2 = s.classify({"image": None, "title": "Minecraft let's play", "subject": "", "focus": ""})
assert r2["with_image"] is None and r2["text_only"]["mode"] == "text"; print("ok - title-only works")
r3 = s.classify({"image": png("blue"), "title": "x", "subject": "", "focus": "c++"})
assert r3["focus_mode"] and r3["thresholds"]["hide"] == 0.8; print("ok - keyword focus uses the focus decision")
for bad in ({"image": "data:image/png;base64,AAAA", "title": "x"},):
    try: s.classify(bad); raise SystemExit("bad image accepted")
    except ValueError: pass
print("ok - a file that is not an image is rejected with a clear message")

# real HTTP round trip, bound to localhost
from http.server import ThreadingHTTPServer
srv = ThreadingHTTPServer(("127.0.0.1", 0), sim.make_handler(s)); port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
page = urllib.request.urlopen(f"http://127.0.0.1:{port}/").read().decode(); assert "Semanthinks image simulator" in page
req = urllib.request.Request(f"http://127.0.0.1:{port}/classify", data=json.dumps({"image": png("green"), "title": "Binary trees", "subject": "", "focus": ""}).encode(), headers={"Content-Type": "application/json"})
out = json.loads(urllib.request.urlopen(req).read()); assert "with_image" in out and "thresholds" in out
try: urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/classify", data=b'{"image":"data:image/png;base64,AAAA"}', headers={"Content-Type": "application/json"}))
except urllib.error.HTTPError as e: assert e.code == 400
print("ok - the page and the /classify endpoint work over HTTP")

try:
    from playwright.sync_api import sync_playwright
    png_path = tmp / "t.png"; Image.new("RGB", (120, 90), "orange").save(png_path)
    with sync_playwright() as p:
        br = p.chromium.launch(); pg = br.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://127.0.0.1:{port}/"); pg.wait_for_selector("#subject option:nth-child(5)", state="attached")
        pg.set_input_files("#file", str(png_path)); pg.wait_for_selector("#drop img")
        pg.fill("#title", "Intro to SQL joins"); pg.click("#go"); pg.wait_for_selector(".verdict")
        txt = pg.inner_text("#out"); assert "Image + title" in txt and "Title only" in txt and "Context used" in txt, txt
        pg.click("#clear"); pg.click("#go"); assert "Add an image" in pg.inner_text("#err")
        assert not errs, errs; br.close()
    print("ok - in the browser: choose an image, type a title, get a verdict with the with/without-image comparison")
except ImportError:
    print("skipped - browser check (playwright not installed)")
srv.shutdown()
