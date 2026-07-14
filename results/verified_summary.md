# Verified coverage — proof-gated shrink sensor

A declared peer counts toward coverage only while a fresh proof-of-serve (successful audit within `proof_ttl`) backs it. Liars never earn a proof, so they never count.

## Safety vs K full-arc liars (R=5, seeds [42, 7, 99], tail-mean of true coverage)

| policy | K | true floor | true-zero sectors | ring 0-copy | mean level end | sync |
|---|---|---|---|---|---|---|
| declared | 0 | 5.7 | 0 | 0.0% | 0.89 | 24628 |
| declared | 4 | 1.0 | 0 | 0.0% | 1.24 | 660 |
| declared | 5 | 0.0 | 130 | 25.4% | 0.90 | 0 |
| declared | 10 | 0.0 | 352 | 68.8% | 0.45 | 0 |
| declared | 15 | 0.0 | 356 | 69.5% | 0.68 | 0 |
| reactive-exclusion | 0 | 5.7 | 0 | 0.0% | 0.89 | 24628 |
| reactive-exclusion | 4 | 5.0 | 0 | 0.0% | 1.16 | 17030 |
| reactive-exclusion | 5 | 5.3 | 0 | 0.0% | 1.16 | 14760 |
| reactive-exclusion | 10 | 5.3 | 0 | 0.0% | 1.14 | 13286 |
| reactive-exclusion | 15 | 5.0 | 0 | 0.0% | 1.59 | 18778 |
| verified | 0 | 6.5 | 0 | 0.0% | 0.94 | 28067 |
| verified | 4 | 6.5 | 0 | 0.0% | 1.22 | 31271 |
| verified | 5 | 6.4 | 0 | 0.0% | 1.11 | 30313 |
| verified | 10 | 6.4 | 0 | 0.0% | 1.34 | 27014 |
| verified | 15 | 6.6 | 0 | 0.0% | 1.58 | 27229 |

## Cost of pessimism — honest network, K=0 (mean arc level: lower = more sharding)

| policy | audits/epoch | proof TTL | mean level end | sync | mean proven peers |
|---|---|---|---|---|---|
| declared | None | None | 0.94 | 27362 | nan |
| verified | 2 | 300 | 3.78 | 205691 | 78.5 |
| verified | 2 | 600 | 1.86 | 90470 | 126.0 |
| verified | 4 | 300 | 1.79 | 81456 | 125.6 |
| verified | 4 | 600 | 1.34 | 39292 | 171.9 |
| verified | 6 | 300 | 1.41 | 50494 | 155.6 |
| verified | 6 | 600 | 0.96 | 31699 | 189.4 |
| verified | 10 | 300 | 1.51 | 24358 | 182.8 |
| verified | 10 | 600 | 0.93 | 30971 | 197.6 |
