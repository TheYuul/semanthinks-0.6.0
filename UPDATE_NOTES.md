# Semanthinks 0.6.0

New in this version
- Per-input-kind decision (thumbnail vs text-only) learned in training and used by the backend and the simulator.
- Text-only mode: popup checkbox "Also score video thumbnails".
- Image simulator: `python tools/image_simulator.py`
- Articles, documents and pop-up relevance; semantic search suggestions; "Evaluating..." overlay; faster backend.
- Evaluation scripts: `tools/eda.py`, `tools/evaluate_model.py`, `training/compare_models.py`. Logo icons.

Bring these from your previous project folder (they are not in the zip)
- `backend/model_bundle.json`   (only needed until you retrain; retraining overwrites it)
- `features.npz` (data/clean/features.npz or wherever your pipeline wrote it), the `thumbnails/` folder, and `results/`
  Keep the same relative locations as before.

Retrain on the existing features, then check
1. `python run_pipeline.py --redo-step train`
   (optional, separate run to compare: `python run_pipeline.py --redo-step train --image-dropout 0.5`)
2. Read `results/report.md`: compare the headline with `headline_single_decision_previous_method`.
3. `cd backend && uvicorn classify_service:app --port 8000`, then `python tools/image_simulator.py`.
4. In chrome://extensions remove the old Semanthinks and load the new `extension` folder.
