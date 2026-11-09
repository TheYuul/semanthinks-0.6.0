# Model evaluation summary

5-fold cross-validation, headline = real items under the program context.

## By category (mean over folds)

| Category | F1 | Precision | Recall | FPR |
|---|---|---|---|---|
| Video (YouTube) | 0.879 | 0.972 | 0.804 | 0.049 |
| Online articles | 0.867 | 0.970 | 0.784 | 0.089 |
| Documents / repositories | 0.697 | 0.886 | 0.576 | 0.057 |
| All real items | 0.830 | 0.953 | 0.736 | 0.061 |

## Confusion matrix (sum over test folds)

TN 7,415 | FP 483 | FN 3,465 | TP 9,681

## Against the baselines

| Method | F1 | Recall | Precision | FPR |
|---|---|---|---|---|
| cosine-only | 0.481 | 0.329 | 0.915 | 0.059 |
| zero-shot (S - S_distract) | 0.517 | 0.359 | 0.923 | 0.055 |
| Late-fusion model | 0.830 | 0.736 | 0.953 | 0.061 |

F1 gain over the best baseline: **+0.313**.

## Subject head

Micro-F1 0.670, macro-F1 0.630, top-1 0.765. Macro-F1 is lower because subjects with very few labeled examples are weak.

## Thumbnail on vs off (items that have a thumbnail)

| Mode | F1 | Precision | Recall | FPR |
|---|---|---|---|---|
| With thumbnail | 0.879 | 0.972 | 0.803 | 0.050 |
| Thumbnail off (text-only mode) | 0.851 | 0.994 | 0.745 | 0.010 |

Text-only mode uses the text decision, which is more conservative: fewer relevant items hidden, fewer distractions caught. It is a different operating point, not a like-for-like F1 comparison.

## Per fold (headline rows)

| Fold | Accuracy | Precision | Recall | F1 | FPR |
|---|---|---|---|---|---|
| 1 | 0.797 | 0.959 | 0.706 | 0.813 | 0.051 |
| 2 | 0.790 | 0.955 | 0.696 | 0.805 | 0.055 |
| 3 | 0.835 | 0.945 | 0.783 | 0.856 | 0.076 |
| 4 | 0.829 | 0.960 | 0.758 | 0.847 | 0.053 |
| 5 | 0.810 | 0.945 | 0.737 | 0.828 | 0.070 |
| **mean ± sd** | 0.812 ± 0.018 | 0.953 ± 0.006 | 0.736 ± 0.032 | 0.830 ± 0.019 | 0.061 ± 0.010 |

FPR target on validation was 5%; on the test folds it exceeded that in fold(s) [1, 2, 3, 4, 5].
