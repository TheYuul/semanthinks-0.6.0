# Semanthinks 0.6.0

A Chromium-based browser extension (Manifest V3) plus a local FastAPI backend that helps a student stay on topic.
While the student is doing course work, it judges videos (YouTube), online articles and document/repository pages
against what they are studying (a program, a subject, or a keyword focus), and **hides**, **warns about** or **allows** each item.

Works in Chrome, Edge, Brave, Opera and other Chromium browsers (tested here on Chromium/Chrome only; see Limitations).

## How it works

1. The popup lets the student choose a program (CS / IT), optionally a subject, and optionally a keyword focus. This becomes the *context text*.
2. The content script collects each item's title, short description and, for videos, the thumbnail, and sends them to `http://localhost:8000`.
3. The backend embeds the text (frozen **EmbeddingGemma**, 256-d) and, when a thumbnail is available and image use is on, the image (frozen **MobileNetV2**, 1280-d).
4. Features: cosine similarity to the context, plus the text (and optional image) vectors, go into a small **Dense head** (ReLU, dropout, sigmoid) trained in pure NumPy, with a second multi-label **subject head** (K = 37).
5. Score: `C = alpha*S + (1-alpha)*(1-p)`, `S = (1-beta)*cos + beta*subject_score`, where `p` = probability the item is distracting.
   `C` below the **hide** threshold is hidden, at or above **hide + 0.30** is allowed, in between is shown with a warning (faded, dashed outline).
   alpha, beta and the thresholds are tuned on validation data under a false-positive-rate cap of 5%.
   Separate thresholds exist for keyword-focus contexts and for items with/without a thumbnail.

The pipeline's positive class is *distracting*. Dataset labels are `relevant` / `distracting`.

### Extension behavior
- Items being judged show an "Evaluating…" blur; if the backend is slow (6 s) they are hidden with "Still evaluating…", and released after 20 s if there is no answer.
- Article and document sites get a page-level notice. A blocked page has only a "Go back" button (no "Continue anyway"); a borderline page gets a dismissible warning banner. The student can still turn the extension or the filter off in the popup.
- **Distractions inside the page:** "related / recommended / trending" boxes, sidebars and share bars are handled link by link. Each link gets a *link-intent* check from its address (`extension/url-tools.js`: sponsored via `rel="sponsored"`, ad/affiliate networks, paid-campaign parameters or a "Sponsored" label; social-media links; share links) and, when it is none of those, the model judges the link text. Sponsored and social links are hidden by these fixed rules; off-topic ones by the model; on-topic ones and the article stay. Embedded social widgets (Facebook/Twitter plug-ins, AddThis-style share bars) are hidden. This is URL/link rules plus the model on short link text, not a trained link classifier, and it has no accuracy figure yet.
- **Ads inside YouTube videos:** while the player reports an ad, the extension presses Skip if it is offered; otherwise it mutes, speeds up and jumps to the end of the ad, then restores the student's own volume and speed. Banner and companion ads around the player are hidden. It depends on YouTube's current player markup, which YouTube changes, so it can stop working without warning, and it only runs on youtube.com pages (not YouTube players embedded elsewhere). It was tested on a mock player, not on live YouTube. Skipping ads may conflict with YouTube's terms of service; disclose that as a limitation.
- **Pop-up windows and forced redirects:** `extension/page-guard.js` runs inside the page (manifest `"world": "MAIN"`, Chrome 111+) and blocks `window.open()` to another site or a blank window, scripted new-tab clicks on other sites, and clicks on sponsored links. Sign-in pop-ups of the big account providers and ordinary links the student clicks still work. A script that changes `location.href` directly cannot be stopped this way. Banner ads (ad-network links, or standard banner sizes that open another site in a new tab) and invisible full-screen click-catchers are hidden. There is a popup switch for it. Tested on mock pages, not on live ad networks.
- Borderline (warn) items are faded, say "this video/result may be off-topic" on hover, and show a short notice when clicked. On a search page whose own search was judged off-topic, borderline results are hidden instead.
- Google Scholar results are judged (Google itself is not).
- Social media, games and streaming sites (Facebook, TikTok, Roblox, Twitch, Netflix, anime streaming sites...) are blocked by name by a domain rule (popup switch, on by default): Facebook, Instagram, TikTok, X/Twitter, Snapchat, Pinterest, Reddit and the entertainment sites listed in `extension/url-tools.js`. Messenger (messenger.com, m.me, facebook.com/messages) stays available. This is a rule, not a model decision, so it is not part of the accuracy numbers. Facebook groups are blocked too. Listing pages with 3+ article cards are judged card by card.
- Never judged: search engines, mail, Wikipedia, GitHub/GitLab/Stack Overflow, `.edu`/`.ac` sites, AI chat sites.
- Promotional pop-ups are judged by the model and kept only if allowed.
- Semantic search: the popup suggests subjects for what is typed (subject head, shown when p ≥ 0.15).
- Text-only mode: no thumbnails are sent. This is a precision-over-recall setting (see Evaluation).

## Repository layout

| Path | Purpose |
|---|---|
| `extension/` | MV3 extension (content script, popup, background, icons) |
| `backend/` | FastAPI service, thesis engine, thumbnail fetcher, `model_bundle.json` (trained model) |
| `training/` | Dense head, feature extraction, training, baselines, model comparison |
| `tools/` | Dataset cleaning, labeling, syllabus parsing, EDA, evaluation figures, simulators |
| `data/` | Raw export, cleaned data, labels, training file |
| `results/` | `report.md` and other evaluation outputs from the last run |
| `tests/` | Python and browser tests |
| `run_pipeline.py` | One-command data → training pipeline |
| `run_tests.py` | One-command test runner |
| `final_run.py` | **Legacy**, superseded by `run_pipeline.py` |

`UPDATE_NOTES.md` lists what changed in 0.6.0 and which files to copy from an older folder.

## Setup

```
pip install -r requirements-dev.txt        # backend + training + evaluation + tests
npm install                                # Playwright for the browser tests (needs Node.js)
npx playwright install chromium
```
Running only the backend needs just `pip install -r backend/requirements.txt`.
The embedding model is gated on Hugging Face: run `hf auth login` once on the machine that runs the backend or feature extraction.

## Run the system

```
cd backend
uvicorn classify_service:app --host 127.0.0.1 --port 8000
```
Then in Chrome/Edge: `chrome://extensions` → Developer mode → Load unpacked → select `extension/`.
The backend loads the trained model from `backend/model_bundle.json`; make sure that file is present (copy it from the trained folder) before starting.

## Tests

One command:
```
python run_tests.py
```
It runs 9 suites (head/decision rule, training pipeline, dataset tools, labeling tools and JS/Python parity, image simulator, subject catalog, popup in a browser, content script in a browser) and prints PASS / FAIL / SKIP per suite.
A suite whose dependency is missing is reported as SKIP with the install command, and `python run_tests.py --strict` turns skips into failures.
The browser tests need Node.js, Playwright and Chromium (setup above). The backend's FastAPI layer needs `requirements-dev.txt` installed to be exercised.

## Retrain

```
python run_pipeline.py                 # clean → labels → training file → thumbnails → features → baseline → train
python run_pipeline.py --smoke         # quick check on a small subset
python run_pipeline.py --redo-step train --image-dropout 0.5
```
Outputs `backend/model_bundle.json` and `results/report.md`. After any retrain, refresh the figures with
`python tools/eda.py`, `python tools/evaluate_model.py`, `python training/compare_models.py`, and update the numbers below.

## Data

- Raw export 32,141 rows → 21,370 after cleaning (13,146 distracting, 8,224 relevant; articles 6,903, repositories 7,992, YouTube 6,475).
  Removed: duplicates 5,386, contradictory non-CS/IT-but-relevant 2,980, same-text label conflicts 1,695, excluded language 678, too short 25, malformed 7.
- Training file 30,211 rows: 21,044 base, 4,479 subject-context rows, 2,912 catalog rows (training only), 1,776 keyword-focus rows.
- Language is about 96% English; Taglish/Tagalog is minimal (771 rows).
- 35 subjects across CS and IT (the IT list has 24; Practical Data Science is in both programs). 21 of 35 have fewer than 30 labeled real items.

## Evaluation

All numbers are from `results/report.md` of the latest run (5-fold cross-validation, real items under program context, positive = distracting; ± is standard deviation across folds).

| Metric | Value |
|---|---|
| Accuracy | 0.812 ± 0.018 |
| Precision | 0.953 |
| Recall | 0.736 |
| F1 | 0.830 ± 0.019 |
| False-positive rate | **0.061 ± 0.010** |

**The false-positive rate (6.1%) is above the 5% design target.** Per-fold test FPR was 0.051, 0.055, 0.076, 0.053 and 0.070, so every fold was above 5% (folds 3 and 5 by the most). The 5% cap was applied on validation data and did not carry over to the held-out test folds.

By category:

| Category | F1 | Precision | Recall | FPR |
|---|---|---|---|---|
| Video | 0.879 | 0.972 | 0.804 | 0.049 |
| Articles | 0.867 | 0.970 | 0.784 | 0.089 |
| Documents/repositories | 0.697 | 0.886 | 0.576 | 0.057 |

Articles are the weakest on false positives (8.9%) and documents on recall (0.58).

### Model comparison (`training/compare_models.py`, 5 random 70/15/15 splits, held-out test)

The script now also fits a **logistic regression** on the same two feature sets (B-LR text-only, C-LR text + vision) with the same tuning, to answer whether the Dense head is needed. The table below predates that change; re-run `python training/compare_models.py <features.npz> --repeats 5` and add the B-LR and C-LR rows before presenting. Only EmbeddingGemma was evaluated as the text embedder; no other embedding model was compared.

| Model | F1 | ROC-AUC |
|---|---|---|
| A1 Distracting-word rules | 0.119 | n/a |
| A2 Keyword filter | 0.790 | n/a |
| **B Text-only head** | **0.858 ± 0.024** | 0.941 |
| C Text + vision head | 0.835 ± 0.028 | 0.924 |

- **The vision (CNN) branch did not improve results on this dataset.** Text-only scored higher than text + vision (0.858 vs 0.835), the difference is about one standard deviation, and the vision model has about 6x the parameters (196,993 vs 33,153) and slower head inference (about 31.5 vs 9.5 µs; text embedding about 94 ms, image embedding about 15 ms). We do not claim the image features add accuracy.
- The thumbnail setting is a trade-off, not a gain: on thumbnail rows, with the image F1 is 0.879 (precision 0.972, recall 0.803, FPR 0.050); with images off (text-only mode) F1 is 0.851 (precision 0.994, recall 0.745, FPR 0.010). Text-only mode gives far fewer false positives at the cost of recall; these F1 values are not like-for-like operating points.
- The keyword filter (A2) is strong (0.790) partly because the dataset was collected around those same keywords, so it is an optimistic baseline for that method.
- Earlier-run reference baselines: cosine-only F1 0.481, zero-shot 0.517.
- The per-kind decision thresholds did not improve the headline (F1 0.831 with a single decision rule vs 0.830).
- 5-fold CV (report.md) and 70/15/15 splits (comparison) are different protocols; their numbers should not be mixed in one table without saying so.

### Subjects and keyword focus
- Subject head: micro-F1 0.670, top-1 0.765, macro-F1 0.630. Thin subjects (physics, digital logic, calculus, automata) are weak.
- Held-out keyword focus: F1 0.578, precision 0.992, recall 0.413, FPR 0.009. Keyword-focus rows built from weak labels: F1 0.619. Focus mode is the least reliable feature and is conservative: it misses many relevant-to-focus items.

## Label audits (human checks)

- **Relevant/distracting labels:** `data/audit/audit_sheet.csv` (400 random items, blind) → fill `annotator_label` → `python tools/score_audit.py data/audit/audit_sheet.csv data/audit/audit_key.csv`.
- **AI-assisted subject labels:** `python tools/subject_audit.py make --n 200 --parts 4`, each member fills one workbook, then
  `python tools/subject_audit.py score data/audit_subjects/subject_audit_*_filled.xlsx`. The humans' answers are written to
  `data/labeling/human_subject_labels.csv`; pass it to `python run_pipeline.py ... --extra-labels data/labeling/human_subject_labels.csv`
  (a file name containing "human" makes the human answer override the AI one) and retrain.
- **Pop-ups and ads:** start the backend, then `node tools/evaluate_popups.js` (add `NODE_PATH=$(npm root -g)` if Playwright is global).
  It shows 51 labeled pop-ups (on-topic ads, off-topic ads, sign-up prompts, cookie notices, log-in forms, neutral notices) to the real content script and the real model, and writes `results/popup_eval.md`. The set is written by the team, not scraped from real sites; `--fake` uses a keyword stub and only checks the plumbing.
Report the agreement numbers in the paper; they are not in this README until the audits are done.

## Limitations (please read before relying on the system)

- Subject labels are AI-assisted (1,500 labels), not human-verified. Keyword-focus pair labels are weak labels. Some syllabus topics are drafts.
- False-positive rate is above target (6.1% overall, about 9% on articles). Document/repository recall is low (0.58).
- Very little Taglish/Tagalog data; performance on those is unmeasured.
- Page-level checks use the title and a short description, not the full page text.
- Only Chromium/Chrome was tested. Edge, Brave and Opera share the engine and the MV3 APIs used, but were not tested.
- The backend must be running locally; the extension does not work offline from it.
- This is not a security control: a student can disable the extension.

## Future work
URL pre-filtering before page load, judging paragraphs with the model, an ONNX/in-browser model so no backend is needed, human verification of the subject labels, and a larger labeled set for thin subjects.
