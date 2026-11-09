"""
classify_service.py  (Semanthinks local backend, 0.6.0)

Run:   uvicorn classify_service:app --host 127.0.0.1 --port 8000
Needs: pip install -r requirements.txt   and a Hugging Face login (google/embeddinggemma-300m is gated): hf auth login

Engines (chosen at startup):
  model_bundle.json present  -> THESIS architecture: EmbeddingGemma 256-d (MRL) + MobileNetV2 1280-d, late fusion,
                                Dense(ReLU, dropout, sigmoid), score C and allow / warn / hide bands.
                                Made by training/train_fusion.py.
  otherwise                  -> LEGACY test models (CLIP + EmbeddingGemma-768 logistic regressions), so the
                                extension keeps working until the thesis model is trained. /health reports which one.

Everything runs on this machine. The only network use is downloading the models once and fetching
a YouTube thumbnail from ytimg.com.
"""
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI
from pydantic import BaseModel

HERE = Path(__file__).parent
BUNDLE_PATH = HERE / "model_bundle.json"

class ClassifyRequest(BaseModel):
    text: str
    image_url: Optional[str] = None
    context: Optional[str] = None      # the student's selected subjects / keyword focus (the "session context")
    subjects: Optional[List[str]] = None   # ids of the chosen subjects (and of the focus keywords' subjects)

app = FastAPI(title="Semanthinks local classifier")
# No CORS middleware on purpose: the extension calls this from its background worker, which does not
# need it, and leaving it off stops ordinary web pages from calling your local classifier.
_engine = None
_kind = None

@app.on_event("startup")
def startup():
    global _engine, _kind
    if BUNDLE_PATH.exists():
        from thesis_features import FeatureExtractor
        from thesis_engine import ThesisEngine
        from thumbnails import download
        fx = FeatureExtractor()
        _engine, _kind = ThesisEngine(BUNDLE_PATH, fx.embed_text, fx.embed_image, download), "thesis"
    else:
        from legacy_engine import load_embedders, Classifier
        embed_text, embed_image = load_embedders()
        _engine, _kind = Classifier(embed_text, embed_image), "legacy"
    print(f"engine: {_kind}")

@app.get("/health")
def health():
    return {"status": "ok", "loaded": _engine is not None, "engine": _kind,
            "architecture": getattr(_engine, "architecture", "legacy-clip-logreg" if _engine else None)}

class SubjectsRequest(BaseModel):
    text: str

@app.post("/api/subjects")
def subjects_for(req: SubjectsRequest):
    """Search-bar helper: subjects a typed phrase is semantically related to (thesis engine only)."""
    if _kind != "thesis": return {"subjects": []}
    return {"subjects": _engine.suggest_subjects(req.text.strip()[:200])}

@app.post("/api/classify")
def classify(req: ClassifyRequest):
    text = req.text.strip()[:500]
    if _kind == "thesis":
        result = _engine.classify(text, req.image_url, (req.context or "")[:400], (req.subjects or [])[:40])
        print(f"[{result['mode']:5s}] C={result['score']:.3f} p_distract={result['p_distract']:.3f} cos={result['cosine']:.3f} -> {result['action']} | {text[:70]}")
        return result
    result = _engine.classify(text, req.image_url)                 # legacy engine ignores the context
    result["action"] = "hide" if result["block"] else "allow"
    result["score"] = result["p_related"]
    return result
