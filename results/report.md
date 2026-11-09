# Evaluation (kfold, 5 folds, n=30211)

| Fold | Train/Val/Test | hidden/dropout | alpha/beta | hide < | Accuracy | Precision | Recall | F1 | FPR |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 20282/3909/5375 | 128/0.3 | 0.8/1.0 | 0.09 | 0.797 | 0.959 | 0.706 | 0.813 | 0.051 |
| 2 | 20386/3760/5420 | 128/0.3 | 0.8/1.0 | 0.08 | 0.790 | 0.955 | 0.696 | 0.805 | 0.055 |
| 3 | 19843/4349/5374 | 128/0.3 | 0.7/1.0 | 0.15 | 0.835 | 0.945 | 0.783 | 0.856 | 0.076 |
| 4 | 20066/4111/5389 | 128/0.3 | 0.0/0.0 | 0.32 | 0.829 | 0.960 | 0.758 | 0.847 | 0.053 |
| 5 | 20050/4148/5368 | 128/0.3 | 0.5/0.5 | 0.29 | 0.810 | 0.945 | 0.737 | 0.828 | 0.070 |
| **mean ± sd** | | | | | **0.812 ± 0.018** | **0.953 ± 0.006** | **0.736 ± 0.032** | **0.830 ± 0.019** | **0.061 ± 0.010** |

**subjects** (mean ± sd over folds): micro_f1 0.670 ± 0.028, top1 0.765 ± 0.043, macro_f1 0.630 ± 0.036

**video_youtube** (mean ± sd over folds): accuracy 0.851 ± 0.027, precision 0.972 ± 0.003, recall 0.804 ± 0.041, f1 0.879 ± 0.025, false_positive_rate 0.049 ± 0.004

**online_articles** (mean ± sd over folds): accuracy 0.810 ± 0.028, precision 0.970 ± 0.010, recall 0.784 ± 0.037, f1 0.867 ± 0.022, false_positive_rate 0.089 ± 0.024

**documents_repositories** (mean ± sd over folds): accuracy 0.783 ± 0.016, precision 0.886 ± 0.011, recall 0.576 ± 0.043, f1 0.697 ± 0.027, false_positive_rate 0.057 ± 0.011

**headline_single_decision_previous_method** (mean ± sd over folds): accuracy 0.813 ± 0.018, precision 0.953 ± 0.007, recall 0.737 ± 0.031, f1 0.831 ± 0.019, false_positive_rate 0.061 ± 0.011

**thumbnail_rows_scored_with_image** (mean ± sd over folds): accuracy 0.850 ± 0.028, precision 0.972 ± 0.003, recall 0.803 ± 0.042, f1 0.879 ± 0.026, false_positive_rate 0.050 ± 0.004

**thumbnail_rows_image_switched_off_text_only_mode** (mean ± sd over folds): accuracy 0.824 ± 0.031, precision 0.994 ± 0.002, recall 0.745 ± 0.052, f1 0.851 ± 0.034, false_positive_rate 0.010 ± 0.003

**subject_context_rows** (mean ± sd over folds): accuracy 0.678 ± 0.024, precision 0.994 ± 0.004, recall 0.602 ± 0.031, f1 0.749 ± 0.025, false_positive_rate 0.014 ± 0.010

**keyword_focus_rows_weak_labels** (mean ± sd over folds): accuracy 0.554 ± 0.064, precision 0.967 ± 0.015, recall 0.460 ± 0.085, f1 0.619 ± 0.086, false_positive_rate 0.061 ± 0.025

**heldout_keywords** (mean ± sd over folds): accuracy 0.579 ± 0.055, precision 0.992 ± 0.007, recall 0.413 ± 0.079, f1 0.578 ± 0.085, false_positive_rate 0.009 ± 0.008

HEADLINE numbers are on real items under the program context (kind = base), each scored with the decision for its input kind (thumbnail / text-only);
`headline_single_decision_previous_method` is the same rows with one decision for everything.
`thumbnail_rows_scored_with_image` vs `thumbnail_rows_image_switched_off_text_only_mode`: only items that have a thumbnail, scored with the image and with the image block switched off (what the popup's text-only mode does to this model).
`subject_context_rows` are the same items under a subject context
(augmented, easier). `keyword_focus_rows_weak_labels` use labels from text matches, so they are only indicative.
Positive class = distracting (hidden). FPR = share of relevant items that were wrongly hidden.
`subjects`: subject head on test rows with known subjects (micro-F1 at 0.5, top-1, macro-F1).
`heldout_keywords`: keyword-focus rows whose keyword was never used for training, validation or early stopping.
`video_youtube`, `online_articles`, `documents_repositories`: the headline rows split by where the item came from (the three categories of the study).
Confusion counts per fold are in the .json file.
