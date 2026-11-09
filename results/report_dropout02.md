# Evaluation (kfold, 5 folds, n=30211)

| Fold | Train/Val/Test | hidden/dropout | alpha/beta | hide < | Accuracy | Precision | Recall | F1 | FPR |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 20282/3909/5375 | 128/0.3 | 0.6/0.5 | 0.30 | 0.792 | 0.958 | 0.698 | 0.807 | 0.052 |
| 2 | 20386/3760/5420 | 128/0.3 | 0.8/1.0 | 0.08 | 0.784 | 0.949 | 0.693 | 0.801 | 0.062 |
| 3 | 19843/4349/5374 | 128/0.3 | 0.3/1.0 | 0.31 | 0.831 | 0.942 | 0.779 | 0.853 | 0.081 |
| 4 | 20066/4111/5389 | 128/0.3 | 0.5/0.5 | 0.31 | 0.820 | 0.964 | 0.739 | 0.837 | 0.046 |
| 5 | 20050/4148/5368 | 128/0.3 | 0.4/0.0 | 0.37 | 0.811 | 0.948 | 0.736 | 0.829 | 0.066 |
| **mean ± sd** | | | | | **0.808 ± 0.017** | **0.952 ± 0.008** | **0.729 ± 0.031** | **0.825 ± 0.019** | **0.061 ± 0.012** |

**subjects** (mean ± sd over folds): micro_f1 0.659 ± 0.033, top1 0.763 ± 0.032, macro_f1 0.606 ± 0.043

**video_youtube** (mean ± sd over folds): accuracy 0.842 ± 0.028, precision 0.971 ± 0.008, recall 0.792 ± 0.042, f1 0.872 ± 0.026, false_positive_rate 0.050 ± 0.010

**online_articles** (mean ± sd over folds): accuracy 0.807 ± 0.030, precision 0.968 ± 0.011, recall 0.782 ± 0.041, f1 0.864 ± 0.024, false_positive_rate 0.095 ± 0.027

**documents_repositories** (mean ± sd over folds): accuracy 0.782 ± 0.021, precision 0.889 ± 0.012, recall 0.569 ± 0.051, f1 0.692 ± 0.034, false_positive_rate 0.055 ± 0.012

**headline_single_decision_previous_method** (mean ± sd over folds): accuracy 0.812 ± 0.016, precision 0.952 ± 0.007, recall 0.737 ± 0.028, f1 0.830 ± 0.017, false_positive_rate 0.063 ± 0.012

**subject_context_rows** (mean ± sd over folds): accuracy 0.661 ± 0.020, precision 0.995 ± 0.002, recall 0.580 ± 0.027, f1 0.732 ± 0.022, false_positive_rate 0.012 ± 0.003

**keyword_focus_rows_weak_labels** (mean ± sd over folds): accuracy 0.559 ± 0.056, precision 0.964 ± 0.011, recall 0.469 ± 0.078, f1 0.627 ± 0.076, false_positive_rate 0.073 ± 0.027

**heldout_keywords** (mean ± sd over folds): accuracy 0.580 ± 0.056, precision 0.990 ± 0.006, recall 0.416 ± 0.081, f1 0.580 ± 0.086, false_positive_rate 0.011 ± 0.007

HEADLINE numbers are on real items under the program context (kind = base), each scored with the decision for its input kind (thumbnail / text-only);
`headline_single_decision_previous_method` is the same rows with one decision for everything.
`subject_context_rows` are the same items under a subject context
(augmented, easier). `keyword_focus_rows_weak_labels` use labels from text matches, so they are only indicative.
Positive class = distracting (hidden). FPR = share of relevant items that were wrongly hidden.
`subjects`: subject head on test rows with known subjects (micro-F1 at 0.5, top-1, macro-F1).
`heldout_keywords`: keyword-focus rows whose keyword was never used for training, validation or early stopping.
`video_youtube`, `online_articles`, `documents_repositories`: the headline rows split by where the item came from (the three categories of the study).
Confusion counts per fold are in the .json file.
