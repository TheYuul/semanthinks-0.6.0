"""
LEGACY: superseded by run_pipeline.py (use that one). Kept only for reference.

final_run.py - the whole pipeline in one command, on a machine with internet + a Hugging Face login (hf auth login).

    python final_run.py                 # all stages
    python final_run.py --from extract  # resume from a stage
    python final_run.py --dry-run       # only print the commands
    python final_run.py --tune          # hyperparameter search in the final training (slower, roughly 40-60 min)

Stages: clean, labels, training_csv, thumbnails, extract, baseline, train, install
Inputs (already in the project): data/export_merged_labeled.csv, data/labeling/ai_labels_claude.csv (+ human-checked files if you add them),
data/labeling/focus_pairs_key.csv and focus_pairs_answers.csv.
Output: backend/model_bundle.json. Restart the backend and the extension uses the trained thesis model.
"""
import argparse, shutil, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable
L = ROOT / "data" / "labeling"; C = ROOT / "data" / "clean"
DISTRACT = "entertainment, gaming, music videos, sports, celebrities, cooking, vlogs, pranks, stock market, politics"


def stages(a):
    labels = [str(p) for p in [L / "ai_labels_claude.csv", *sorted(L.glob("human_*filled*.csv"))] if p.exists()]
    pairs = []
    if (L / "focus_pairs_key.csv").exists():
        pairs = ["--pairs-key", str(L / "focus_pairs_key.csv")]
        pairs += ["--pairs-answers", str(L / "focus_pairs_answers.csv")] if (L / "focus_pairs_answers.csv").exists() else ["--use-suggested"]
    return [
        ("clean", [PY, str(ROOT / "tools/clean_dataset.py"), str(ROOT / "data/export_merged_labeled.csv"), "--out", str(C)]),
        ("labels", [PY, str(ROOT / "tools/merge_labels.py"), *labels, "--out", str(L)]),
        ("training_csv", [PY, str(ROOT / "tools/build_training_csv.py"), "--clean", str(C / "dataset_clean.csv"), "--labels", str(L / "subject_labels.csv"), *pairs, "--out", str(C / "training.csv")]),
        ("thumbnails", [PY, str(ROOT / "tools/download_thumbnails.py"), str(C / "training.csv"), "--urls-from", str(C / "dataset_clean.csv"), "--out", str(ROOT / "thumbnails")]),
        ("extract", [PY, str(ROOT / "training/extract_features.py"), str(C / "training.csv"), str(ROOT / "features.npz"), "--images-dir", str(ROOT / "thumbnails"), "--distract-context", DISTRACT]),
        ("baseline", [PY, str(ROOT / "training/baseline_cosine.py"), str(ROOT / "features.npz")]),
        ("train", [PY, str(ROOT / "training/train_fusion.py"), str(ROOT / "features.npz"), str(ROOT / "model_bundle.json"), "--report", str(ROOT / "report")] + (["--tune"] if a.tune else [])),
        ("install", None),
    ]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--from", dest="start", default="clean"); ap.add_argument("--only"); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--tune", action="store_true")
    a = ap.parse_args()
    plan = stages(a); names = [n for n, _ in plan]
    assert a.start in names, names
    for name, cmd in plan[names.index(a.start):]:
        if a.only and name != a.only: continue
        print(f"\n=== {name} ===")
        if cmd is None:
            print("copy model_bundle.json -> backend/model_bundle.json")
            if not a.dry_run:
                if not (ROOT / "model_bundle.json").exists(): sys.exit("model_bundle.json not found: the train stage did not finish")
                shutil.copy(ROOT / "model_bundle.json", ROOT / "backend" / "model_bundle.json")
            continue
        print(" ".join(f'"{c}"' if " " in c else c for c in cmd))
        if a.dry_run: continue
        t = time.time(); r = subprocess.run(cmd, cwd=ROOT)
        if r.returncode: sys.exit(f"stage '{name}' failed (exit {r.returncode}). Fix it, then resume with: python final_run.py --from {name}")
        print(f"[{name} done in {time.time() - t:.0f}s]")
    if not a.dry_run: print("\nDone. Start the backend:  cd backend && python -m uvicorn classify_service:app --host 127.0.0.1 --port 8000")


if __name__ == "__main__":
    main()
