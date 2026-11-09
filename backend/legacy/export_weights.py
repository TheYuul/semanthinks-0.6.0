"""
export_weights.py

Converts fusion_model.joblib into a plain JSON file of weights.

Why: a .joblib file is a pickle. Loading a pickle can run code and it only loads
reliably with the same scikit-learn version that saved it. The three models inside
are logistic regressions, so they are just a weight vector and a bias. In JSON
they load anywhere (Python, JavaScript) with no scikit-learn at all.

Usage:  python export_weights.py fusion_model.joblib model_weights.json
Needs:  pip install scikit-learn joblib numpy
"""
import json, pickle, sys, warnings
import numpy as np
import sklearn
from joblib.numpy_pickle import NumpyUnpickler

warnings.filterwarnings("ignore")
ALLOWED_PREFIXES = ("sklearn.", "numpy", "joblib.numpy_pickle", "scipy.")
ALLOWED_BUILTINS = {("builtins", "dict"), ("builtins", "list"), ("builtins", "tuple"),
                    ("builtins", "set"), ("collections", "OrderedDict")}

class RestrictedUnpickler(NumpyUnpickler):
    """Refuses to load any class outside scikit-learn and numpy."""
    def find_class(self, module, name):
        if module.startswith(ALLOWED_PREFIXES) or (module, name) in ALLOWED_BUILTINS:
            return super().find_class(module, name)
        raise pickle.UnpicklingError(f"blocked: {module}.{name}")

def main(src, dst):
    with open(src, "rb") as f:
        bundle = RestrictedUnpickler(src, f, None).load()

    out = {
        "exported_with_sklearn": sklearn.__version__,
        "clip_model": bundle["clip_model"],
        "text_model": bundle["text_model"],
        "class_names": bundle["class_names"],          # index 0 = not related, index 1 = related
        # Inferred from the coefficients (the fused text weights match the text model with
        # cosine 0.98 when text is the LAST 768 values). Confirm against your training notebook.
        "fused_layout": ["image_512", "text_768"],
        "models": {},
    }
    for key in ("image", "text", "fused"):
        m = bundle[key]
        out["models"][key] = {
            "n_features": int(m.n_features_in_),
            "bias": float(m.intercept_[0]),
            "weights": [float(x) for x in m.coef_[0]],
            "p_is_related": "sigmoid(weights . x + bias)",
        }
    with open(dst, "w") as f:
        json.dump(out, f)

    # Check: the JSON math must reproduce scikit-learn exactly.
    rng = np.random.default_rng(0)
    for key in ("image", "text", "fused"):
        m = bundle[key]
        x = rng.normal(size=(200, m.n_features_in_))
        ref = m.predict_proba(x)[:, 1]
        w = np.array(out["models"][key]["weights"]); b = out["models"][key]["bias"]
        mine = 1 / (1 + np.exp(-(x @ w + b)))
        assert np.allclose(ref, mine, atol=1e-9), key
        print(f"{key:6s} {m.n_features_in_:5d} features: JSON output matches scikit-learn")
    print("wrote", dst)

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
