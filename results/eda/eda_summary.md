# Exploratory data analysis

Cleaned dataset: **21,370** rows (13,146 distracting, 8,224 relevant).

## Class balance by source

```
label       relevant  distracting  total  pct_distracting
source                                                   
article         1537         5366   6903            0.777
repository      4614         3378   7992            0.423
youtube         2073         4402   6475            0.680
```

## Text length (words)

```
                         count   mean    50%    max
source     label                                   
article    distracting  5366.0   22.6   18.0  211.0
           relevant     1537.0   24.3   23.0  206.0
repository distracting  3378.0  101.8  138.0  228.0
           relevant     4614.0  124.5  154.0  483.0
youtube    distracting  4402.0   24.6   27.0   53.0
           relevant     2073.0   26.1   27.0   49.0
```

## Language

```
label     relevant  distracting  total
language                              
english       7895        12704  20599
tagalog          0            1      1
taglish        329          441    770
```

Almost all items are English; Taglish and Tagalog are a small share, which limits any claim about Filipino-language performance.

## Top domains

```
                            n  pct_distracting
host                                          
youtube.com              6475            0.680
doi.org                  2602            0.313
dev.to                   2408            0.693
arxiv.org                2095            0.393
pubmed.ncbi.nlm.nih.gov  1401            0.529
semanticscholar.org       707            0.591
openalex.org              579            0.599
europepmc.org             395            0.400
manilatimes.net           283            0.883
philstar.com              190            0.953
zenodo.org                189            0.349
wired.com                 116            0.802
sciencedaily.com           92            0.946
theguardian.com            90            0.856
phys.org                   89            0.944
```

## Rows removed in cleaning

```
                                                                rows
reject_reason                                                       
exact duplicate text (first kept)                               5386
domain code non_csit but label relevant (contradiction)         2980
same text with different labels (see conflicts_for_review.csv)  1695
language_verified = exclude                                      678
text shorter than 15 characters                                   25
bad label (malformed row)                                          7
```

## Subject coverage (real items with a subject label)

34 subjects have at least one labeled real item; **21** have fewer than 30: database (28), platform (27), emerging-tech (20), info-management (18), spi (17), graphics (16), robotics (16), architecture (12), discrete (11), modeling (10), oop (10), systems-integration (10), programming-languages (9), integrative (7), complexity (6), thesis (6), multimedia (5), automata (4), internship (3), systems-admin (1), digital-logic (1).

Training-file rows by kind: base 21,044, subject_ctx 4,479, catalog 2,912, focus 1,776.
