# Dataset specification (thesis Chapter 3)

Target: at least 10,000 samples (adviser requirement); about 30,000 collected. Bilingual (English / Tagalog / Taglish),
from YouTube, academic article sites and document repositories. Social media and entertainment sites are excluded.
Chapter 3 still says 1,500 manually annotated samples: update every mention (objectives, instruments, data gathering,
cross-validation) and state exactly how the labels were produced.

One row per item in `dataset.csv` (see `dataset_template.csv`):

| column | meaning |
|---|---|
| `id` | unique id |
| `text` | what the system sees: the video title, or the paragraph / card text (the same text the extension sends) |
| `image_path` | thumbnail file relative to `--images-dir`. Empty for text-only items |
| `label` | `relevant` (keep) or `distracting` (hide). Judged **against `context`** |
| `language` | `en`, `tl` or `taglish` (for the per-language breakdown in the paper) |
| `source` | `youtube`, `article` or `document` |
| `context` | the subject(s) the annotator judged against, written the way the popup sends them, e.g. `Database Management Systems`. Empty = default CS/IT context |
| `group` | video id, or channel / site. All rows with the same group stay on the same side of every train / validation / test split, so near-duplicates cannot leak into the test set. Strongly recommended at this dataset size |

Guidance
* The same video can be relevant for one subject and distracting for another, so label against a context and
  record it. Include both kinds in the data, otherwise the cosine feature learns nothing.
* Keep the classes reasonably balanced and include hard negatives (entertainment with technical words in the title,
  academic videos with clickbait titles). Hard negatives are what decide the false-positive rate the panel asked about.
* Remove exact and near-duplicate rows (same video collected twice, reposted titles) before training, and fill `group`.
  With 30k scraped rows this is the biggest threat to honest numbers: leaked duplicates make every metric look better than it is.
* If part of the 30k was labelled automatically (keyword rules, another model), say so in the paper and keep a manually
  labelled test subset. A model trained on rule-made labels only learns the rules.
* Real thumbnails only. Do not generate or invent samples, and keep annotation notes (who labelled, how disagreements
  were resolved) for the paper.
* Collect a separate small set per language so you can report F1 for English and Tagalog separately.

Pipeline
```
python training/extract_features.py dataset.csv features.npz --images-dir thumbs/    # embeds in batches; run once, reuse features.npz
python training/train_fusion.py features.npz backend/model_bundle.json --report report
```
`report.md` has the per-fold table (accuracy, precision, recall, F1, false-positive rate) for the paper.

## Building the dataset from the merged export (0.3.1)

```
python tools/clean_dataset.py data/export_merged_labeled.csv --out data/clean     # dataset_clean.csv, rejects.csv, conflicts_for_review.csv, cleaning_report.md
python tools/build_reference.py --out data/subject_reference.csv                  # subject x program: courses, year/term, keywords, topics
python tools/make_audit_sample.py data/clean/dataset_clean.csv --n 400 --out data/audit
#   give annotators audit_sheet.csv + annotation_guideline.md ONLY (blind); then:
python tools/score_audit.py data/audit/audit_sheet_filled.csv data/audit/audit_key.csv [--second other.csv]
python training/extract_features.py data/clean/dataset_clean.csv features.npz --images-dir thumbnails/ --distract-context "entertainment, gaming, music, sports, celebrities, cooking, vlogs"
python training/baseline_cosine.py features.npz          # cosine-only and zero-shot baselines
python training/train_fusion.py features.npz model_bundle.json --tune --report report
```

* **Label direction:** the export has 1 = relevant; the cleaner flips it (pipeline 1 = distracting). Confirm with the audit.
* **Frozen extractors:** EmbeddingGemma and MobileNetV2 use pretrained weights and are never trained here. Only the Dense head is trained.
* **Curriculum columns** (`domain_subjects`, `keyword_subjects`, `matched_keywords`, `curriculum_basis`) are automatic reference columns, not ground truth. The `domain -> subjects` mapping is in `clean_dataset.py` and needs team review.
* `context` is the same program-level text for every row, so cosine similarity cannot leak the label.
* Thumbnails: `image_path` is `<youtube_id>.jpg`; download them from `image_url` (only i.ytimg.com URLs) into `--images-dir`.

## Subject labels, keyword focus and the multi-task model (0.4.0)

The model now has two outputs on one shared Dense layer: `p_distract` (the thesis binary head) and a multi-label **subject head**
(which of the 37 curriculum subjects the item belongs to). The decision score is
`S = (1-beta)*cosine + beta*subject_score`, `C = alpha*S + (1-alpha)*(1-p_distract)`, with `subject_score` = the highest probability among
the student's chosen subjects (or the focus term's subjects). `beta = 0` gives the original thesis formula; alpha, beta and the thresholds
are tuned on the validation split only.

Three context levels (the `context` column, built by `tools/subject_context.py`, identical to the extension's text):
1. program: `Computer Science and Information Technology: ...`
2. subject: `Database Management Systems: database, sql, ...`
3. keyword focus: `focus: c++ | Computer Programming 1 & 2`

### Labeling workflow
```
python tools/make_label_sheet.py data/clean/dataset_clean.csv --n 1500 --overlap 150 --prefill --out data/labeling
#   annotator A fills subject_sheet_A.xlsx, annotator B fills subject_sheet_B.xlsx (blind: no suggestions, same 150 rows as A's blind rows)
python tools/merge_labels.py data/labeling/subject_sheet_A.xlsx data/labeling/subject_sheet_B.xlsx      # subject_labels.csv, conflicts, flags, coverage + kappa
python tools/make_focus_pairs.py data/clean/dataset_clean.csv data/labeling/subject_labels.csv --out data/labeling
#   annotators answer yes / partly / no in focus_pairs_sheet.csv (~1000 pairs)
python tools/build_training_csv.py --clean data/clean/dataset_clean.csv --labels data/labeling/subject_labels.csv \
    --pairs-key data/labeling/focus_pairs_key.csv --pairs-answers data/labeling/focus_pairs_sheet_filled.csv --out data/clean/training.csv
python training/extract_features.py data/clean/training.csv features.npz --images-dir thumbnails/
python training/train_fusion.py features.npz model_bundle.json --tune --report report
```
* Distracting rows get subject `none` automatically: they need no subject labeling.
* `not_csit = Y` in a sheet means the annotator thinks the item is not CS/IT. Those rows are listed in `label_flags.csv` and dropped from
  training until the binary label is reviewed.
* Prefilled suggestions come from domain codes and keyword matches. They are NOT ground truth, and prefilling can anchor annotators.
  The 150 overlap rows are never prefilled, so the A/B kappa is honest. Unlabeled relevant rows stay `subjects = ""` and are ignored by the subject head.
* `subject_ctx` rows are context-swap augmentation: the same item under its own subject (relevant) and under another subject (distracting).
  `focus` rows come only from human-answered pairs ('partly' and blank are skipped) unless `--use-suggested`, which marks them `~weak`.
* A fixed share of focus **keywords** (by hash) is `heldout`: never used for training, validation or early stopping. train_fusion.py reports
  the `heldout_keywords` result per fold. That is the evidence that the model handles focus terms that are not in any list. The *items*
  behind those pairs can still appear in training under other contexts, so say "unseen keyword", not "unseen item".
* Every row derived from one item shares its `group`, so the item never lands in two splits.
