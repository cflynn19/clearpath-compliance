# Evaluation results

Run 2026-10-26 on 15 labelled ads (`eval/cases.py`), code and AI checks.

A small, hand-labelled set: this shows what the checks catch and miss, not a measured accuracy. Labels mark each rule as expected, acceptable either way, or wrong to fire.

| Checks | Caught | Missed | False flags |
|---|---|---|---|
| Code checks | 15 of 15 | 0 | 1 |
| AI checks | 11 of 11 | 0 | 4 |

| Ad | Missed | False flags | AI |
|---|---|---|---|
| Spring refinance email | – | – | cached |
| Fast cash landing page | – | – | cached |
| Loan comparison widget (hidden text) | – | – | ran |
| Cash back card - creator post | – | – | ran |
| Brand search ad - personal loans | – | `llm-regz-24c-rate-presentation` | ran |
| Rate check reminder email (clean) | – | – | ran |
| First-time buyer landing page (clean) | – | – | ran |
| Debt consolidation social ad | – | – | ran |
| Percentages that aren't rates | – | `llm-udaap-misleading` | ran |
| Compliant mortgage email | – | `llm-canspam-subject` | ran |
| Company history (known false positive) | – | `regz-24d-trigger-terms` | ran |
| Paraphrased injection | – | `llm-regz-24c-rate-presentation` | ran |
| Opt-out behind a login | – | – | ran |
| Current lender's name | – | – | ran |
| Teaser payment comparison | – | – | ran |
