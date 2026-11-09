# Cleaning report

- Input rows: 32141
- Kept: 21370
- Rejected: 10771

## Rejected by reason
- exact duplicate text (first kept): 5386
- domain code non_csit but label relevant (contradiction): 2980
- same text with different labels (see conflicts_for_review.csv): 1695
- language_verified = exclude: 678
- text shorter than 15 characters: 25
- bad label (malformed row): 7

Label counts (pipeline: distracting = export label 0): {'distracting': 13146, 'relevant': 8224}
Languages: {'english': 20599, 'taglish': 770, 'tagalog': 1}
Rows with a thumbnail URL: 6475  |  groups: 13431
Curriculum basis: {'none': 10549, 'both': 6967, 'domain': 2097, 'keyword': 1757}

Curriculum columns are automatic reference columns, not ground truth.
