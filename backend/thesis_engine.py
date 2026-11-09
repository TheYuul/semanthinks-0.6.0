"""
thesis_engine.py - serving side of the thesis Late Fusion model (NumPy only; no PyTorch needed for the head).

Loads model_bundle.json written by training/train_fusion.py. The feature extractor is injected, so the
engine can be tested with fake embedders; classify_service.py passes the real ones.
"""
import json, math, threading
from collections import OrderedDict
from typing import Callable, Optional
import numpy as np

from thesis_features import DEFAULT_CONTEXT, TEXT_DIM, IMAGE_DIM


class ThesisEngine:
    architecture = "thesis-late-fusion-v1"

    def __init__(self, bundle_path, embed_text: Callable, embed_image: Callable, fetch_image: Callable):
        b = json.loads(open(bundle_path, encoding="utf-8").read())
        assert b["architecture"] == self.architecture and b["input_layout"] == ["text_256", "image_1280", "cosine_1"], "unexpected bundle layout"
        d = b["dense"]
        self.W1, self.b1 = np.asarray(d["W1"]), np.asarray(d["b1"])
        self.W2, self.b2 = np.asarray(d["W2"]), float(d["b2"])
        self.mean, self.std = np.asarray(b["standardize"]["mean"]), np.asarray(b["standardize"]["std"])
        dec = b["decision"]
        self.alpha, self.hide_t, self.allow_t = float(dec["alpha"]), float(dec["hide_threshold"]), float(dec["allow_threshold"])
        self.beta = float(dec.get("beta", 0.0))
        df = b.get("decision_focus")              # optional separate decision for keyword-focus mode
        self.dec_focus = {k: float(df[k]) for k in ("alpha", "beta", "hide_threshold", "allow_threshold")} if df else None
        self.dec_image, self.dec_text = (self._dec(b.get(k)) for k in ("decision_image", "decision_text"))   # optional, per input kind
        sj = b.get("subjects")                      # optional subject head (multi-task bundle)
        self.subject_ids = list(sj["ids"]) if sj else []
        self.W3, self.b3 = (np.asarray(sj["W3"]), np.asarray(sj["b3"])) if sj else (None, None)
        self.info = {"architecture": self.architecture, "evaluation": b.get("evaluation", {}).get("summary")}
        self.embed_text, self.embed_image, self.fetch_image = embed_text, embed_image, fetch_image
        self._ctx = OrderedDict()
        self._txt = OrderedDict()                 # recent title embeddings (YouTube re-asks about the same cards)
        self._lock = threading.Lock()

    @staticmethod
    def _dec(d):
        return {k: float(d[k]) for k in ("alpha", "beta", "hide_threshold", "allow_threshold")} if d else None

    def decision_for(self, focus: bool, has_image: bool) -> dict:
        """Keyword-focus decision first, then the one for this input kind (thumbnail or text-only), then the general one."""
        if focus and self.dec_focus: return self.dec_focus
        d = self.dec_image if has_image else self.dec_text
        return d or {"alpha": self.alpha, "beta": self.beta, "hide_threshold": self.hide_t, "allow_threshold": self.allow_t}

    def _context_vector(self, context: Optional[str]):
        key = (context or "").strip() or DEFAULT_CONTEXT
        if key not in self._ctx:
            self._ctx[key] = self.embed_text(key)
            if len(self._ctx) > 64: self._ctx.popitem(last=False)
        return self._ctx[key]

    def _text_vector(self, text: str):
        if text not in self._txt:
            self._txt[text] = self.embed_text(text)
            if len(self._txt) > 512: self._txt.popitem(last=False)
        return self._txt[text]

    def suggest_subjects(self, text: str, top: int = 5) -> list:
        """Which curriculum subjects a typed phrase is about, by meaning (the trained subject head on the text alone)."""
        if self.W3 is None: return []
        with self._lock:
            t = self._text_vector(text)
            cos = float(t @ self._context_vector(None))
        _, q = self.head_all(np.concatenate([t, np.zeros(IMAGE_DIM), [cos]]), False)
        return [{"id": self.subject_ids[i], "p": round(float(q[i]), 4)} for i in np.argsort(-q)[:top]]

    def head_all(self, x_raw: np.ndarray, has_image: bool):
        """(p_distract, subject probabilities or None) for one raw feature row [text_256 | image_1280 | cosine]."""
        z = (x_raw - self.mean) / self.std
        if not has_image: z[TEXT_DIM:TEXT_DIM + IMAGE_DIM] = 0.0
        h = np.maximum(0.0, z @ self.W1 + self.b1)
        p = 1.0 / (1.0 + math.exp(-float(h @ self.W2 + self.b2)))
        q = None if self.W3 is None else 1.0 / (1.0 + np.exp(-np.clip(h @ self.W3 + self.b3, -60, 60)))
        return p, q

    def head(self, x_raw: np.ndarray, has_image: bool) -> float:
        return self.head_all(x_raw, has_image)[0]

    def subject_score(self, q, chosen):
        """max probability over the chosen subject ids; no (known) chosen subject = every subject."""
        if q is None: return None
        idx = [self.subject_ids.index(i) for i in (chosen or []) if i in self.subject_ids]
        return float(q[idx].max()) if idx else float(q.max())

    def decide(self, p_distract: float, cosine: float, subj: Optional[float] = None, focus: bool = False, has_image: bool = False):
        d = self.decision_for(focus, has_image)
        s = min(1.0, max(0.0, cosine))
        if subj is not None and d["beta"]: s = (1.0 - d["beta"]) * s + d["beta"] * min(1.0, max(0.0, subj))
        c = d["alpha"] * s + (1.0 - d["alpha"]) * (1.0 - p_distract)
        action = "hide" if c < d["hide_threshold"] else ("allow" if c >= d["allow_threshold"] else "warn")
        return c, action

    def classify(self, text: str, image_url: Optional[str] = None, context: Optional[str] = None, subjects: Optional[list] = None) -> dict:
        data = self.fetch_image(image_url) if image_url else None
        with self._lock:
            t = self._text_vector(text)
            cos = float(t @ self._context_vector(context))
            img, has_image = np.zeros(IMAGE_DIM), False
            if data is not None:
                try: img, has_image = self.embed_image(data), True
                except Exception as e: print(f"image skipped ({type(e).__name__}: {str(e)[:100]}), using text only")
        p, q = self.head_all(np.concatenate([t, img, [cos]]), has_image)
        subj = self.subject_score(q, subjects)
        focus = (context or "").lstrip().lower().startswith("focus:")
        c, action = self.decide(p, cos, subj, focus, has_image)
        used = self.decision_for(focus, has_image)
        top = [] if q is None else [{"id": self.subject_ids[i], "p": round(float(q[i]), 4)} for i in np.argsort(-q)[:3]]
        return {"subject_score": None if subj is None else round(subj, 4), "detected_subjects": top,
                "block": action == "hide", "action": action, "label": "distracting" if action == "hide" else "relevant",
                "score": round(c, 4), "p_distract": round(p, 4), "cosine": round(cos, 4), "p_related": round(1 - p, 4),
                "threshold": used["hide_threshold"], "allow_threshold": used["allow_threshold"], "focus_mode": focus, "mode": "fused" if has_image else "text", "architecture": self.architecture}
