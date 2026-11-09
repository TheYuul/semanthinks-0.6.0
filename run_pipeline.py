"""
run_pipeline.py - one command from the cleaned data to a trained model in backend/.

    python run_pipeline.py --smoke          # ~10 minute check that models, download and training work on this machine
    python run_pipeline.py                  # the real run
    python run_pipeline.py --tune           # also grid-search hidden units / dropout (much slower)

Steps (each prints what it does; a finished step is skipped when its output exists unless --redo):
  1 clean      tools/clean_dataset.py            -> data/clean/dataset_clean.csv
  2 labels     tools/merge_labels.py             -> data/labeling/subject_labels.csv   (AI-assisted subject labels; see DATASET.md)
  3 training   tools/build_training_csv.py       -> data/clean/training.csv   (program / subject / keyword-focus contexts; the keyword-focus
                                                   rows are WEAK labels from text matches, see --no-weak-pairs)
  4 thumbnails tools/download_thumbnails.py      -> thumbnails/
  5 features   training/extract_features.py      -> features.npz   (needs the models: hf auth login, torch, sentence-transformers)
  6 baseline   training/baseline_cosine.py       -> printed + results/baseline.txt
  7 train      training/train_fusion.py          -> backend/model_bundle.json + results/report.md
Needs: pip install -r backend/requirements.txt pandas openpyxl scikit-learn   and a Hugging Face login (google/embeddinggemma-300m is gated).
--stop-after <step> stops early (for example `training` to only build the CSV).
"""
import argparse, shutil, subprocess, sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent
PY = sys.executable
STEPS = ["clean", "labels", "training", "thumbnails", "features", "baseline", "train"]


def run(cmd, log=None):
    print("\n$", " ".join(str(c) for c in cmd), flush=True)
    r = subprocess.run([str(c) for c in cmd], cwd=ROOT, capture_output=bool(log), text=True)
    if log:
        text = (r.stdout or "") + (r.stderr or ""); print(text); Path(log).parent.mkdir(parents=True, exist_ok=True); Path(log).write_text(text)
    if r.returncode: sys.exit(f"step failed (exit {r.returncode}). Fix the error above and run again; finished steps are skipped.")


def smoke_subset(src, dst, n_groups, seed=1):
    """A small training CSV that keeps whole groups, both classes and some subject rows (for the smoke test)."""
    df = pd.read_csv(src, dtype=str, keep_default_na=False)
    g = df.groupby("group").agg(rel=("label", lambda s: (s == "relevant").any()), subj=("subjects", lambda s: (~s.isin(["", "none"])).any()))
    pick = pd.concat([g[g.subj].sample(min(len(g[g.subj]), n_groups // 3), random_state=seed), g[~g.subj].sample(min(len(g[~g.subj]), n_groups), random_state=seed)]).index
    sub = df[df["group"].isin(pick)]
    sub.to_csv(dst, index=False); return len(sub)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="data/export_merged_labeled.csv"); ap.add_argument("--ai-labels", default="data/labeling/ai_labels_claude.csv")
    ap.add_argument("--extra-labels", nargs="*", default=[], help="more filled label sheets (for example from groupmates)")
    ap.add_argument("--smoke", action="store_true"); ap.add_argument("--tune", action="store_true"); ap.add_argument("--redo", action="store_true"); ap.add_argument("--redo-step", choices=STEPS, help="redo only this step (for example `train`), keeping the others")
    ap.add_argument("--skip-thumbnails", action="store_true"); ap.add_argument("--no-catalog", action="store_true", help="do not add syllabus topics/keywords as training-only rows"); ap.add_argument("--no-weak-pairs", action="store_true", help="do not add the text-match keyword-focus rows (weak labels)"); ap.add_argument("--stop-after", choices=STEPS)
    ap.add_argument("--images-dir", default="thumbnails"); ap.add_argument("--epochs", type=int, default=200)
    ap.add_argument("--image-dropout", type=float, default=0.2, help="share of training rows whose image block is zeroed (higher = the model leans less on thumbnails)")
    a = ap.parse_args()
    smoke = a.smoke
    res = ROOT / ("results_smoke" if smoke else "results"); res.mkdir(exist_ok=True)
    train_csv = ROOT / "data/clean" / ("training_smoke.csv" if smoke else "training.csv")
    feats = ROOT / ("features_smoke.npz" if smoke else "features.npz")
    bundle = ROOT / ("results_smoke/model_bundle.json" if smoke else "backend/model_bundle.json")

    def todo(name, out):
        if a.stop_after and STEPS.index(name) > STEPS.index(a.stop_after): return False
        if Path(out).exists() and not a.redo and a.redo_step != name: print(f"[{name}] skipped, {Path(out).name} exists (use --redo)"); return False
        print(f"\n===== step: {name} ====="); return True

    clean_csv = ROOT / "data/clean/dataset_clean.csv"
    if todo("clean", clean_csv): run([PY, "tools/clean_dataset.py", a.raw, "--out", "data/clean"])
    labels_csv = ROOT / "data/labeling/subject_labels.csv"
    if todo("labels", labels_csv): run([PY, "tools/merge_labels.py", a.ai_labels, *a.extra_labels, "--out", "data/labeling"])
    full_csv = ROOT / "data/clean/training.csv"
    if todo("training", full_csv if not smoke else train_csv):
        pairs = [] if a.no_weak_pairs else ["--pairs-key", "data/labeling/focus_pairs_key.csv", "--use-suggested"]
        if pairs:
            run([PY, "tools/make_focus_pairs.py", "data/clean/dataset_clean.csv", "data/labeling/subject_labels.csv", "--out", "data/labeling"])
        run([PY, "tools/build_training_csv.py", "--clean", "data/clean/dataset_clean.csv", "--labels", "data/labeling/subject_labels.csv", "--out", "data/clean/training.csv", *pairs, *([] if a.no_catalog else ["--add-catalog"])])
    if smoke and (a.redo or not train_csv.exists()):
        print("smoke subset:", smoke_subset(full_csv, train_csv, 450), "rows ->", train_csv.name)
    if a.stop_after == "training": return
    if todo("thumbnails", ROOT / a.images_dir / ".done") and not a.skip_thumbnails:
        run([PY, "tools/download_thumbnails.py", train_csv.relative_to(ROOT), "--out", a.images_dir]); (ROOT / a.images_dir / ".done").write_text("ok")
    if todo("features", feats):
        run([PY, "training/extract_features.py", train_csv.relative_to(ROOT), feats.relative_to(ROOT), "--images-dir", a.images_dir,
             "--distract-context", "entertainment, gaming, music, sports, celebrities, cooking, vlogs, news, shopping"])
    if todo("baseline", res / "baseline.txt"): run([PY, "training/baseline_cosine.py", feats.relative_to(ROOT)], log=res / "baseline.txt")
    if todo("train", bundle):
        run([PY, "training/train_fusion.py", feats.relative_to(ROOT), bundle.relative_to(ROOT), "--report", str((res / "report").relative_to(ROOT)),
             "--epochs", "30" if smoke else str(a.epochs), "--image-dropout", str(a.image_dropout), *(["--tune"] if a.tune else [])])
    print("\nFinished. " + (f"Smoke test OK: models, download and training work. Now run without --smoke." if smoke else
          f"Model written to backend/model_bundle.json. Report: {res}/report.md. Start the backend: cd backend && uvicorn classify_service:app --port 8000"))


if __name__ == "__main__":
    main()
