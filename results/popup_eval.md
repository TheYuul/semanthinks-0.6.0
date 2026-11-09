# Pop-up and ad evaluation (real backend)

Study subjects: programming, database. 51 labeled pop-ups from `tools/popup_eval_set.csv`. Positive class = filter (hide).

| Overall | n | accuracy | precision | recall | F1 | FPR |
|---|---|---|---|---|---|---|
| all | 51 | 0.961 | 0.962 | 0.962 | 0.962 | 0.040 |

| Kind | n | expected | correct | wrongly hidden | wrongly kept | sent to model |
|---|---|---|---|---|---|---|
| ad_on_topic | 12 | keep | 11/12 | 1 | 0 | 12 |
| ad_off_topic | 14 | filter | 13/14 | 0 | 1 | 14 |
| signup_prompt | 12 | filter | 12/12 | 0 | 0 | 0 |
| cookie_notice | 4 | keep | 4/4 | 0 | 0 | 0 |
| login_form | 3 | keep | 3/3 | 0 | 0 | 0 |
| neutral_notice | 6 | keep | 6/6 | 0 | 0 | 0 |

## Mistakes (2)
- [ad_on_topic] expected keep, got filter: Limited offer: networking and CCNA practice exams at a discount.
- [ad_off_topic] expected filter, got keep: Advertisement: Cryptocurrency trading signals, sign up now for a promo code bonus.

Notes: the pop-up set was written by the project team/assistant, not scraped from real sites, so treat the numbers as a functional check of the decision logic. Sign-up/newsletter/app prompts are handled by rules (hidden regardless of topic); pop-ups with promotional wording are judged by the model against the student's subjects; pop-ups with neither kind of wording are left alone.
