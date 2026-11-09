"""
legacy_engine.py - the 0.2.x test models (CLIP image + EmbeddingGemma-768 text, logistic regressions).
Kept only as a fallback until model_bundle.json (the thesis architecture) exists. NOT the thesis architecture.
Unchanged from classify_service.py 0.2.0 except for where the weight files live (backend/legacy/).
"""
import io, json, math, os, threading
from pathlib import Path
from urllib.parse import urlparse
from typing import Callable, Optional

import httpx
import numpy as np

HERE = Path(__file__).parent / "legacy"
TEXT_CFG = json.loads((HERE / "classifier.json").read_text())
BUNDLE = json.loads((HERE / "model_weights.json").read_text())

# Each model returns P(related) = sigmoid(w.x + b). The card is BLOCKED when P(related) < threshold.
# Only the text threshold (0.175) comes from your files. The fused model borrows the same value
# so the first test follows your "block only when fairly sure" policy. It is NOT tuned for the
# fused model: change it without editing code, for example (Windows PowerShell):
#   $env:SEMANTHINKS_FUSED_THRESHOLD = "0.5" ; uvicorn classify_service:app --host 127.0.0.1 --port 8000
THRESHOLDS = {
    "text": float(os.getenv("SEMANTHINKS_TEXT_THRESHOLD", TEXT_CFG["threshold"])),
    "image": 0.5,
    "fused": float(os.getenv("SEMANTHINKS_FUSED_THRESHOLD", TEXT_CFG["threshold"])),
}

# The backend only downloads thumbnails from these hosts. This stops a web page, or anything else
# that can reach this port, from making the backend fetch arbitrary addresses.
ALLOWED_IMAGE_HOSTS = ("ytimg.com",)

# Preprocessing MUST match what you used when training.
# The fusion training script (train_fusion_classifier.py) L2-normalized the CLIP image embeddings
# (and the EmbeddingGemma text embeddings), so this must stay True for the fused / image models.
CLIP_NORMALIZE = True
CLIP_DIM = 512             # ViT-B/32 projected embedding size

def sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))

def finish_image_vector(v: np.ndarray) -> np.ndarray:
    """Turn whatever came out of CLIP into the flat, normalized (512,) vector the classifier expects."""
    v = np.asarray(v, dtype=np.float64).reshape(-1)
    if v.shape[0] != CLIP_DIM:
        raise ValueError(f"CLIP image embedding has {v.shape[0]} values, expected {CLIP_DIM}")
    return v / (np.linalg.norm(v) + 1e-12) if CLIP_NORMALIZE else v

class LinearHead:
    def __init__(self, weights, bias):
        self.w = np.asarray(weights, dtype=np.float64)
        self.b = float(bias)
    def p_related(self, x: np.ndarray) -> float:
        assert x.shape == self.w.shape, f"expected {self.w.shape}, got {x.shape}"
        return sigmoid(float(x @ self.w + self.b))

HEADS = {
    "text": LinearHead(TEXT_CFG["weights"], TEXT_CFG["bias"]),   # classifier.json
    "image": LinearHead(BUNDLE["models"]["image"]["weights"], BUNDLE["models"]["image"]["bias"]),
    "fused": LinearHead(BUNDLE["models"]["fused"]["weights"], BUNDLE["models"]["fused"]["bias"]),
}
assert BUNDLE["fused_layout"] == ["image_512", "text_768"]     # image part first, text part last

# ---------- real embedders (loaded lazily so the module can be imported for tests) ----------
def load_embedders():
    from sentence_transformers import SentenceTransformer
    import torch
    from transformers import CLIPModel, CLIPProcessor
    from PIL import Image

    text_model = SentenceTransformer(TEXT_CFG["model_id"])
    text_model.max_seq_length = TEXT_CFG["max_seq_length"]
    clip = CLIPModel.from_pretrained(BUNDLE["clip_model"]).eval()
    proc = CLIPProcessor.from_pretrained(BUNDLE["clip_model"])

    def embed_text(text: str) -> np.ndarray:
        v = text_model.encode(text, prompt=TEXT_CFG["prompt"], normalize_embeddings=TEXT_CFG["normalize"])
        return np.asarray(v, dtype=np.float64)                  # (768,)

    def embed_image(data: bytes) -> np.ndarray:
        img = Image.open(io.BytesIO(data)).convert("RGB")
        with torch.no_grad():
            out = clip.get_image_features(**proc(images=img, return_tensors="pt"))
            # Newer transformers return an output object (per-patch features first), not a tensor.
            # Taking out[0] gave the (1, 50, 768) array behind the 500 errors.
            if hasattr(out, "pooler_output"):
                out = out.pooler_output
            if out.shape[-1] != clip.config.projection_dim:     # got the unprojected pooled vector
                out = clip.visual_projection(out)
        return finish_image_vector(out.cpu().numpy())           # (512,)
    return embed_text, embed_image

class Classifier:
    def __init__(self, embed_text: Callable[[str], np.ndarray], embed_image: Callable[[bytes], np.ndarray],
                 fetch_image: Optional[Callable[[str], Optional[bytes]]] = None):
        self.embed_text, self.embed_image = embed_text, embed_image
        self.fetch_image = fetch_image or self._download
        self._lock = threading.Lock()   # one model call at a time, so parallel requests do not fight over the CPU

    @staticmethod
    def _host_allowed(url: str) -> bool:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        return parsed.scheme == "https" and any(host == h or host.endswith("." + h) for h in ALLOWED_IMAGE_HOSTS)

    @staticmethod
    def _download(url: str) -> Optional[bytes]:
        if not Classifier._host_allowed(url):
            return None
        try:
            r = httpx.get(url, timeout=5.0, follow_redirects=True)
            r.raise_for_status()
            if not Classifier._host_allowed(str(r.url)):   # a redirect must not leave the allowed hosts
                return None
            return r.content
        except Exception:
            return None

    def classify(self, text: str, image_url: Optional[str] = None) -> dict:
        data = self.fetch_image(image_url) if image_url else None
        with self._lock:
            t = self.embed_text(text)
            if data is not None:
                try:
                    x = np.concatenate([self.embed_image(data), t])  # image 512 first, then text 768
                    mode = "fused"
                except Exception as e:                               # unreadable image: do not fail the request
                    print(f"image skipped ({type(e).__name__}: {str(e)[:100]}), using text only")
                    x, mode = t, "text"
            else:
                x, mode = t, "text"                                  # no usable thumbnail: text-only model
        p = HEADS[mode].p_related(x)
        block = p < THRESHOLDS[mode]
        result = {"block": bool(block), "label": "unrelated" if block else "related",
                  "p_related": round(p, 4), "threshold": THRESHOLDS[mode], "mode": mode}
        print(f"[{mode:5s}] P(related)={p:.3f} -> {'HIDE' if block else 'keep'} | {text[:70]}")
        return result

