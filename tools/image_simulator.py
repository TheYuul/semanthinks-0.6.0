"""
image_simulator.py - upload a thumbnail or image (plus an optional title) and see what Semanthinks would do with it.

  python tools/image_simulator.py                 (from the project root; opens http://127.0.0.1:8001)
  python tools/image_simulator.py --port 8002 --no-browser

It loads the same trained model (backend/model_bundle.json) and the same feature extractors as the extension's backend,
so the decision is the one the extension would make for a card with that image and title:
  BLOCK = hidden, WARN = shown faded with a dashed border, ALLOW = left alone.
The page also scores the same card WITHOUT the image, so you can see what the image changed.
Everything stays on this computer: the page is served on 127.0.0.1 only and uploads are not saved.

Needs the backend packages (torch, torchvision, sentence-transformers, pillow, numpy) and a Hugging Face login. No web framework needed.
Use --fake to try the page without the real models (random scores, for checking the page only).
"""
import argparse, base64, io, json, sys, threading, webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Semanthinks image simulator</title>
<style>
:root{--bg:#f5f7fb;--card:#fff;--ink:#17213a;--mute:#5d677d;--line:#d7deec;--brand:#3159a8;--ok:#1f7a54;--warn:#b7791f;--bad:#c0392b}
@media (prefers-color-scheme:dark){:root{--bg:#10151f;--card:#18202e;--ink:#e8edf7;--mute:#9aa7bf;--line:#2b3649;--brand:#7aa2f7;--ok:#4cc38a;--warn:#e0a93b;--bad:#ef6f5e}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 Arial,Helvetica,sans-serif}
main{max-width:980px;margin:0 auto;padding:22px 16px 48px}h1{margin:0 0 4px;font-size:24px;color:var(--brand)}p.sub{margin:0 0 18px;color:var(--mute)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}@media (max-width:760px){.grid{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
label{display:block;font-weight:600;margin:12px 0 5px;font-size:13px}
input[type=text],select{width:100%;padding:9px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink);font:inherit}
#drop{border:2px dashed var(--line);border-radius:12px;min-height:170px;display:flex;align-items:center;justify-content:center;text-align:center;color:var(--mute);cursor:pointer;padding:10px;overflow:hidden}
#drop.over{border-color:var(--brand);background:rgba(49,89,168,.08)}#drop img{max-width:100%;max-height:260px;border-radius:8px}
button{font:600 14px Arial;padding:10px 16px;border-radius:8px;border:0;background:var(--brand);color:#fff;cursor:pointer;margin-top:14px}button:disabled{opacity:.5;cursor:wait}
button.ghost{background:transparent;color:var(--brand);border:1px solid var(--line);margin-left:6px}
.verdict{display:inline-block;padding:5px 14px;border-radius:999px;color:#fff;font-weight:700;letter-spacing:.04em}
.BLOCK{background:var(--bad)}.WARN{background:var(--warn)}.ALLOW{background:var(--ok)}
table{width:100%;border-collapse:collapse;margin-top:10px;font-size:13.5px}td,th{padding:6px 4px;border-bottom:1px solid var(--line);text-align:left}th{color:var(--mute);font-weight:600}
.mock{border:1px solid var(--line);border-radius:10px;padding:10px;display:flex;gap:12px;align-items:flex-start;margin-top:10px;background:var(--bg)}
.mock img{width:150px;border-radius:8px;flex:none}.mock .t{font-weight:600;font-size:14px}
.mock.warn{opacity:.55;outline:2px dashed #c98a00;outline-offset:-2px}.mock.block{border-style:dashed;color:var(--mute);text-align:center;justify-content:center;padding:22px}
.note{font-size:12.5px;color:var(--mute);margin-top:10px}.err{color:var(--bad);margin-top:10px}
</style></head><body><main>
<h1>Semanthinks image simulator</h1>
<p class="sub">Drop a thumbnail or image, type its title, pick what you are studying, and see whether the extension would block it.</p>
<div class="grid">
 <div class="card">
  <div id="drop" tabindex="0">Drop an image here, click to choose one, or paste it (Ctrl+V)</div>
  <input id="file" type="file" accept="image/*" hidden>
  <label for="title">Title of the video or article (the model also reads this)</label>
  <input id="title" type="text" placeholder="e.g. Intro to SQL joins | Database Systems" maxlength="300">
  <label for="subject">What you are studying</label>
  <select id="subject"></select>
  <label for="focus">Keyword focus (optional, narrows the filter)</label>
  <input id="focus" type="text" placeholder="e.g. c++" maxlength="60">
  <button id="go">Check it</button><button id="clear" class="ghost" type="button">Clear</button>
  <div id="err" class="err"></div>
 </div>
 <div class="card" id="out"><div class="note">The result appears here.</div></div>
</div>
<p class="note">Same model and features as the extension's backend. Decision bands: hide when C is below the hide threshold, allow at or above the allow threshold, warn in between. Nothing is uploaded anywhere or saved.</p>
</main>
<script>
const $=(i)=>document.getElementById(i);let dataUrl=null,meta={};
fetch("/meta").then(r=>r.json()).then(m=>{meta=m;const s=$("subject");
 s.append(new Option("Program default (all CS/IT)",""));m.subjects.forEach(x=>s.append(new Option(x.label,x.id)));});
function show(file){if(!file||!file.type.startsWith("image/")){$("err").textContent="Please choose an image file.";return;}
 if(file.size>8*1024*1024){$("err").textContent="That image is over 8 MB.";return;}
 const r=new FileReader();r.onload=()=>{dataUrl=r.result;$("drop").innerHTML="";const i=new Image();i.src=dataUrl;$("drop").append(i);$("err").textContent="";};r.readAsDataURL(file);}
$("drop").onclick=()=>$("file").click();$("file").onchange=(e)=>show(e.target.files[0]);
["dragover","dragenter"].forEach(n=>$("drop").addEventListener(n,(e)=>{e.preventDefault();$("drop").classList.add("over");}));
["dragleave","drop"].forEach(n=>$("drop").addEventListener(n,(e)=>{e.preventDefault();$("drop").classList.remove("over");}));
$("drop").addEventListener("drop",(e)=>show(e.dataTransfer.files[0]));
document.addEventListener("paste",(e)=>{const f=[...(e.clipboardData?.files||[])][0];if(f)show(f);});
$("clear").onclick=()=>{dataUrl=null;$("drop").textContent="Drop an image here, click to choose one, or paste it (Ctrl+V)";$("title").value="";$("focus").value="";$("out").innerHTML='<div class="note">The result appears here.</div>';$("err").textContent="";};
const word={hide:"BLOCK",warn:"WARN",allow:"ALLOW"};
function row(n,r){return `<tr><td>${n}</td><td><span class="verdict ${word[r.action]}">${word[r.action]}</span></td><td>${r.score.toFixed(3)}</td><td>${r.p_distract.toFixed(3)}</td><td>${r.cosine.toFixed(3)}</td><td>${r.mode}</td></tr>`;}
function mock(r,img,title){const t=title||"(no title)";
 if(r.action==="hide")return `<div class="mock block">This card would be hidden. Semanthinks removes it from the page.</div>`;
 return `<div class="mock ${r.action==="warn"?"warn":""}">${img?`<img src="${img}" alt="">`:""}<div><div class="t">${t.replace(/[<>&]/g,"")}</div><div class="note">${r.action==="warn"?"Shown faded with a dashed border. Hover says it may be off-topic.":"Shown normally."}</div></div></div>`;}
$("go").onclick=async()=>{$("err").textContent="";
 if(!dataUrl&&!$("title").value.trim()){$("err").textContent="Add an image, a title, or both.";return;}
 $("go").disabled=true;$("go").textContent="Checking...";
 try{const r=await fetch("/classify",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({image:dataUrl,title:$("title").value.trim(),subject:$("subject").value,focus:$("focus").value.trim()})});
  const j=await r.json();if(!r.ok)throw new Error(j.detail||"Request failed");
  const a=j.with_image||j.text_only, thr=j.thresholds;
  $("out").innerHTML=`<div><span class="verdict ${word[a.action]}">${word[a.action]}</span> &nbsp;<b>C = ${a.score.toFixed(3)}</b></div>
   ${mock(a,dataUrl,$("title").value.trim())}
   <table><tr><th>Scored</th><th>Action</th><th>C</th><th>p(distracting)</th><th>cosine</th><th>input</th></tr>
   ${j.with_image?row("Image + title",j.with_image):""}${row("Title only (no image)",j.text_only)}</table>
   <p class="note">Context used: <i>${j.context}</i><br>Hide below C = ${a.threshold.toFixed(2)}, allow at or above ${a.allow_threshold.toFixed(2)}${j.focus_mode?" (keyword-focus decision)":""}${j.with_image&&Math.abs(j.with_image.threshold-j.text_only.threshold)>0.001?` &middot; title only uses ${j.text_only.threshold.toFixed(2)} / ${j.text_only.allow_threshold.toFixed(2)}`:""}.
   ${j.detected?`Closest subject: ${j.detected}.`:""}</p>
   ${j.with_image&&j.with_image.action!==j.text_only.action?`<p class="note"><b>The image changed the decision</b> (title only: ${word[j.text_only.action]}).</p>`:""}
   ${!dataUrl?`<p class="note">No image given, so only the title was scored.</p>`:""}
   ${dataUrl&&!$("title").value.trim()?`<p class="note">No title given: the text part is empty, so the result mostly reflects the context. Add the title for a realistic check.</p>`:""}`;
 }catch(e){$("err").textContent=String(e.message||e);}
 $("go").disabled=false;$("go").textContent="Check it";};
</script></body></html>"""


def load_catalog():
    js = (ROOT / "extension" / "subject-catalog.js").read_text(encoding="utf-8")
    def grab(name, closer):
        start = js.index(f"const {name} = ") + len(f"const {name} = ")
        return json.loads(js[start: js.index(closer, start) + len(closer) - 1])
    return grab("SUBJECTS", "\n];"), grab("PROGRAM_CONTEXTS", "\n};")


class Contexts:
    """Same strings the extension builds (subject-tools.js contextString / focus context)."""
    def __init__(self):
        self.subjects, self.programs = load_catalog()
        self.by_id = {s["id"]: s for s in self.subjects}

    def label(self, s): return s["labels"].get("Both") or next(iter(s["labels"].values()))

    def build(self, subject_id, focus):
        s = self.by_id.get(subject_id)
        if focus:
            return (f"focus: {focus}" + (f" | {self.label(s)}" if s else ""))[:400]
        if not s: return self.programs["Both"]
        return f"{self.label(s)}: {', '.join(list(dict.fromkeys(s['keywords']))[:40])}"[:400]


def make_engine(fake, bundle_path=None):
    from thesis_engine import ThesisEngine
    bundle = Path(bundle_path) if bundle_path else ROOT / "backend" / "model_bundle.json"
    if not bundle.exists(): sys.exit(f"{bundle} not found. Train the model first (python run_pipeline.py).")
    store = {}
    if fake:
        import hashlib, numpy as np
        from thesis_features import TEXT_DIM, IMAGE_DIM, l2_normalize
        def seeded(b, d): return np.random.default_rng(int(hashlib.md5(b).hexdigest()[:8], 16)).normal(size=d)
        et = lambda t: l2_normalize(seeded(t.encode(), TEXT_DIM)); ei = lambda b: np.abs(seeded(b, IMAGE_DIM))
    else:
        from thesis_features import FeatureExtractor
        fx = FeatureExtractor(); et, ei = fx.embed_text, fx.embed_image
    eng = ThesisEngine(bundle, et, ei, lambda key: store.get(key))
    return eng, store


class Simulator:
    def __init__(self, eng, store, ctxs):
        self.eng, self.store, self.ctxs = eng, store, ctxs; self.lock = threading.Lock()

    def meta(self):
        return {"subjects": sorted(({"id": s["id"], "label": self.ctxs.label(s)} for s in self.ctxs.subjects), key=lambda x: x["label"])}

    def classify(self, r):
        """r: dict(image=data URL or None, title, subject, focus). Raises ValueError with a message for the page."""
        from PIL import Image
        eng, ctxs = self.eng, self.ctxs
        title = (r.get("title") or "").strip()[:300]
        data = None
        if r.get("image"):
            try:
                data = base64.b64decode(r["image"].split(",", 1)[-1])
                if len(data) > 8 * 1024 * 1024: raise ValueError("too large")
                Image.open(io.BytesIO(data)).convert("RGB")          # make sure it really is an image
            except Exception:
                raise ValueError("That file could not be read as an image (use JPG, PNG or WebP).")
        subject, focus = r.get("subject") or "", (r.get("focus") or "").strip()
        context = ctxs.build(subject, focus)
        subjects = [subject] if subject else []
        with self.lock:
            text_only = eng.classify(title or " ", None, context, subjects)
            with_image = None
            if data is not None:
                self.store["upload"] = data
                try: with_image = eng.classify(title or " ", "upload", context, subjects)
                finally: self.store.pop("upload", None)
        ref = with_image or text_only
        fm = ref.get("focus_mode")
        top = ref.get("detected_subjects") or []
        detected = f"{ctxs.label(ctxs.by_id[top[0]['id']])} ({top[0]['p']:.0%})" if top and top[0]["p"] >= 0.4 and top[0]["id"] in ctxs.by_id else ""
        return {"with_image": with_image, "text_only": text_only, "context": context, "focus_mode": bool(fm),
                "thresholds": {"hide": ref["threshold"], "allow": ref["allow_threshold"]}, "detected": detected}


def make_handler(sim):
    from http.server import BaseHTTPRequestHandler

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _send(self, code, body, ctype="application/json"):
            b = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(code); self.send_header("Content-Type", ctype + "; charset=utf-8"); self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(b)
        def do_GET(self):
            if self.path in ("/", "/index.html"): self._send(200, PAGE, "text/html")
            elif self.path == "/meta": self._send(200, json.dumps(sim.meta()))
            else: self._send(404, json.dumps({"detail": "not found"}))
        def do_POST(self):
            if self.path != "/classify": return self._send(404, json.dumps({"detail": "not found"}))
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if n > 12 * 1024 * 1024: return self._send(413, json.dumps({"detail": "That image is too large."}))
                self._send(200, json.dumps(sim.classify(json.loads(self.rfile.read(n) or b"{}"))))
            except ValueError as e: self._send(400, json.dumps({"detail": str(e)}))
            except Exception as e: self._send(500, json.dumps({"detail": f"{type(e).__name__}: {e}"}))
    return H


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=8001); ap.add_argument("--no-browser", action="store_true"); ap.add_argument("--bundle", default=None, help="model file (default backend/model_bundle.json)")
    ap.add_argument("--fake", action="store_true", help="random embeddings, only to check the page works"); a = ap.parse_args()
    eng, store = make_engine(a.fake, a.bundle); sim = Simulator(eng, store, Contexts())
    from http.server import ThreadingHTTPServer
    server = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(sim))      # 127.0.0.1 only: not reachable from other computers
    url = f"http://127.0.0.1:{a.port}/"; print("Open", url, "(Ctrl+C to stop)")
    if not a.no_browser: threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try: server.serve_forever()
    except KeyboardInterrupt: print("stopped")


if __name__ == "__main__":
    main()
