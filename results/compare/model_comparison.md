# Comparison of the rule-based baseline, the text-only model and the text + vision model

Split 70/15/15, whole items kept together, 5 split(s). First split: train 21,706, validation 2,965, held-out test 3,199 real items (1,008 with a thumbnail).
Validation rows are used to tune the head (early stopping, alpha, hide threshold, FPR cap of 5%); the test rows are used once, only to report. Positive class = distracting (hidden). ROC-AUC uses the continuous score 1 - C; the rule baselines are yes/no, so they have no ROC-AUC.

## Held-out test

| Model | Accuracy | Precision | Recall | F1 | FPR | ROC-AUC | TN | FP | FN | TP |
|---|---|---|---|---|---|---|---|---|---|---|
| A1 distracting-word rules (extension fallback) | 0.399 ± 0.033 | 0.832 ± 0.030 | 0.064 ± 0.005 | 0.119 ± 0.009 | 0.023 ± 0.005 | n/a | 1139 | 26 | 1882 | 129 |
| A2 keyword-match filter (hide if no CS/IT keyword) | 0.773 ± 0.021 | 0.946 ± 0.005 | 0.679 ± 0.045 | 0.790 ± 0.032 | 0.067 ± 0.009 | n/a | 1087 | 77 | 642 | 1369 |
| B Text-only (257-d) | 0.838 ± 0.014 | 0.952 ± 0.007 | 0.782 ± 0.037 | 0.858 ± 0.024 | 0.069 ± 0.012 | 0.941 ± 0.007 | 1085 | 80 | 436 | 1575 |
| C Text + Vision (1537-d) | 0.815 ± 0.016 | 0.951 ± 0.009 | 0.745 ± 0.039 | 0.835 ± 0.028 | 0.066 ± 0.008 | 0.924 ± 0.009 | 1088 | 77 | 510 | 1501 |
| B-LR Logistic regression, text-only (257-d) | 0.806 ± 0.013 | 0.954 ± 0.010 | 0.727 ± 0.034 | 0.825 ± 0.024 | 0.060 ± 0.014 | 0.924 ± 0.009 | 1095 | 70 | 546 | 1465 |
| C-LR Logistic regression, text + vision (1537-d) | 0.742 ± 0.012 | 0.945 ± 0.010 | 0.627 ± 0.044 | 0.753 ± 0.032 | 0.065 ± 0.017 | 0.882 ± 0.012 | 1090 | 75 | 746 | 1265 |

## Validation (the rows used for tuning, so optimistic)

| Model | Accuracy | Precision | Recall | F1 | FPR | ROC-AUC | TN | FP | FN | TP |
|---|---|---|---|---|---|---|---|---|---|---|
| A1 distracting-word rules (extension fallback) | 0.404 ± 0.019 | 0.799 ± 0.036 | 0.068 ± 0.007 | 0.126 ± 0.012 | 0.029 ± 0.004 | n/a | 1123 | 33 | 1821 | 133 |
| A2 keyword-match filter (hide if no CS/IT keyword) | 0.786 ± 0.013 | 0.954 ± 0.007 | 0.692 ± 0.027 | 0.802 ± 0.017 | 0.057 ± 0.012 | n/a | 1091 | 66 | 599 | 1355 |
| B Text-only (257-d) | 0.851 ± 0.006 | 0.960 ± 0.003 | 0.795 ± 0.010 | 0.870 ± 0.007 | 0.056 ± 0.001 | 0.947 ± 0.005 | 1092 | 65 | 399 | 1555 |
| C Text + Vision (1537-d) | 0.825 ± 0.008 | 0.958 ± 0.004 | 0.754 ± 0.011 | 0.844 ± 0.008 | 0.056 ± 0.001 | 0.934 ± 0.004 | 1093 | 64 | 481 | 1474 |
| B-LR Logistic regression, text-only (257-d) | 0.819 ± 0.016 | 0.958 ± 0.004 | 0.744 ± 0.023 | 0.837 ± 0.015 | 0.055 ± 0.002 | 0.933 ± 0.007 | 1094 | 63 | 500 | 1454 |
| C-LR Logistic regression, text + vision (1537-d) | 0.754 ± 0.014 | 0.953 ± 0.006 | 0.640 ± 0.021 | 0.765 ± 0.016 | 0.053 ± 0.003 | 0.894 ± 0.010 | 1095 | 62 | 702 | 1252 |

## Held-out test, only items that have a thumbnail (where vision can help)

| Model | Accuracy | Precision | Recall | F1 | FPR | ROC-AUC | TN | FP | FN | TP |
|---|---|---|---|---|---|---|---|---|---|---|
| A1 distracting-word rules (extension fallback) | 0.398 ± 0.050 | 0.950 ± 0.035 | 0.132 ± 0.011 | 0.232 ± 0.018 | 0.015 ± 0.013 | n/a | 308 | 5 | 585 | 89 |
| A2 keyword-match filter (hide if no CS/IT keyword) | 0.759 ± 0.031 | 0.979 ± 0.009 | 0.661 ± 0.054 | 0.788 ± 0.041 | 0.030 ± 0.007 | n/a | 303 | 9 | 231 | 443 |
| B Text-only (257-d) | 0.853 ± 0.030 | 0.982 ± 0.005 | 0.798 ± 0.052 | 0.880 ± 0.033 | 0.033 ± 0.011 | 0.957 ± 0.011 | 303 | 10 | 137 | 537 |
| C Text + Vision (1537-d) | 0.813 ± 0.029 | 0.971 ± 0.016 | 0.748 ± 0.052 | 0.844 ± 0.038 | 0.046 ± 0.010 | 0.916 ± 0.015 | 298 | 15 | 172 | 502 |
| B-LR Logistic regression, text-only (257-d) | 0.808 ± 0.034 | 0.984 ± 0.010 | 0.730 ± 0.056 | 0.837 ± 0.039 | 0.027 ± 0.018 | 0.926 ± 0.020 | 304 | 8 | 184 | 490 |
| C-LR Logistic regression, text + vision (1537-d) | 0.719 ± 0.022 | 0.965 ± 0.031 | 0.612 ± 0.033 | 0.748 ± 0.028 | 0.050 ± 0.049 | 0.847 ± 0.031 | 297 | 16 | 263 | 411 |

## Computational measurements

| Model | Input dim | Parameters | Head size (KB) | Head latency (µs/item) | FLOPs/item | Training time (s) | Epochs |
|---|---|---|---|---|---|---|---|
| A1 distracting-word rules (extension fallback) | - | 0 | 0 | 15.5 | 0 | - | - |
| A2 keyword-match filter (hide if no CS/IT keyword) | - | 0 | 0 | 57.2 | 0 | - | - |
| B Text-only (257-d) | 257 | 33,153 | 337 | 9.4 | 66,048 | 5.2 | 20 |
| C Text + Vision (1537-d) | 1537 | 196,993 | 1999 | 30.5 | 393,728 | 53.3 | 18 |
| B-LR Logistic regression, text-only (257-d) | 257 | 258 | 3 | 3.2 | 514 | 0.7 | 61 |
| C-LR Logistic regression, text + vision (1537-d) | 1537 | 1,538 | 16 | 4.2 | 3,074 | 8.4 | 166 |

Feature extractors were not timed. Run again with `--time-extractors` (and `--images-dir thumbnails`) on the machine that has the backend packages. EmbeddingGemma has about 300M parameters and MobileNetV2 about 3.4M, so extraction, not the Dense head, dominates the cost of models B and C. Model B needs no image download or MobileNetV2 pass.

B-LR and C-LR use the same features and the same validation tuning (alpha, hide threshold, FPR cap) with a logistic regression in place of the Dense head, to answer whether the extra capacity of the Dense head is needed. Notes: models B and C use the binary head only so that the comparison isolates the image features; the deployed model also carries the subject head. The deployed rule fallback (A1) was designed as a safety net, not as a competitor; A2 is the usual keyword filter.
