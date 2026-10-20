# REJECTED candidate: the combined rule ('safe-or-lowest') at N = 200

Vacate if R remain even if every racing intender leaves, OR if I am the lowest
racer and R remain counting the higher ids as staying. Rejected because one
ordinary, instantly-detected death breaks it (REPORT_stale_views.md section 7);
kept here as evidence. Fresh seeds 920000+; exact 95% intervals; de-duplicated.

| part | scenario | rule | runs losing data | 95% CI | declared loss | eq. arc level | sync cost |
|---|---|---|---|---|---|---|---|
| A | activation | V3 | 0/48 | 0-7% | 0 | 0.88 | 21,189 |
| A | activation | V5 | 0/48 | 0-7% | 2,686 | 2.23 | 2,988 |
| A | activation | combined | 0/48 | 0-7% | 0 | 0.89 | 16,356 |
| A | churn | V3 | 0/48 | 0-7% | 0 | 0.83 | 21,531 |
| A | churn | V5 | 0/48 | 0-7% | 2,164 | 0.81 | 8,952 |
| A | churn | combined | 0/48 | 0-7% | 0 | 0.86 | 16,990 |
| A | flashcrowd | V3 | 0/48 | 0-7% | 0 | 0.57 | 21,745 |
| A | flashcrowd | V5 | 0/48 | 0-7% | 1,998 | 1.40 | 3,093 |
| A | flashcrowd | combined | 0/48 | 0-7% | 0 | 0.59 | 16,698 |
| A | storm | V3 | 0/48 | 0-7% | 0 | 1.05 | 19,879 |
| A | storm | V5 | 0/48 | 0-7% | 1,784 | 1.40 | 7,145 |
| A | storm | combined | 0/48 | 0-7% | 0 | 1.13 | 16,576 |
| B | storm30 | V3 | 0/100 | 0-4% | 0 | 1.01 | 19,333 |
| B | storm30 | V5 | 1/100 | 0-5% | 2,801 | 1.44 | 7,247 |
| B | storm30 | combined | 0/100 | 0-4% | 0 | 1.14 | 16,740 |
| B | storm40 | V3 | 0/100 | 0-4% | 0 | 1.08 | 18,651 |
| B | storm40 | V5 | 11/100 | 6-19% | 5,832 | 1.64 | 8,089 |
| B | storm40 | combined | 2/100 | 0-7% | 5,501 | 1.20 | 14,968 |
| C | stress50_dl192 | V3 | 26/72 | 25-48% | 125,059 | 1.37 | 19,671 |
| C | stress50_dl192 | V5 | 35/72 | 37-61% | 112,264 | 1.85 | 8,255 |
| C | stress50_dl192 | combined | 31/72 | 31-55% | 332,359 | 1.54 | 17,755 |
