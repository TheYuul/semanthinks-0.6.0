# Model scored against the human audit labels

353 audited items, read blind by the group. These items and their augmented copies were removed from training. Positive class = distracting (hidden).

Human vs dataset label on these items: agreement 0.654 (95% CI 0.603-0.702), Cohen's kappa 0.322.

| Model | scored against | accuracy | precision | recall | F1 | FPR |
|---|---|---|---|---|---|---|
| text-only head (257-d) | HUMAN label | 0.816 | 0.796 | 0.667 | 0.726 | 0.098 |
| text-only head (257-d) | dataset label | 0.725 | 0.926 | 0.529 | 0.673 | 0.049 |
| text-only head (257-d) | (accuracy where human = dataset / where they differ, vs human) | 0.913 / 0.631 | | | | |

Read it like this: the HUMAN rows are the honest estimate of how well the model separates relevant from distracting content as a person would. The dataset-label rows show how closely it copies the dataset's own labels on the same items. A model that agrees with the dataset much more than with the humans has learned the dataset's quirks.
