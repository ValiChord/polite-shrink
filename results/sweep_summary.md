# Robustness sweep — 1248 (scenario,seed) cells, 4992 simulations

## Pooled across all four scenarios

| variant | runs | runs with data loss | loss rate | 95% upper bound | worst floor | mean exposure |
|---|---|---|---|---|---|---|
| V0 naive | 1248 | 1197 | 95.91% | < 97.01% | 0 | 250879 |
| V1 damped | 1248 | 300 | 24.04% | < 26.41% | 0 | 25302 |
| V2 damped+jitter | 1248 | 303 | 24.28% | < 26.66% | 0 | 25032 |
| V3 full (polite shrink) | 1248 | 0 | 0.00% | < 0.24% | 1 | 4666 |

## Per scenario (runs with data loss / runs)

| scenario | V0 naive | V1 damped | V2 damped+jitter | V3 full (polite shrink) |
|---|---|---|---|---|
| activation | 312/312 | 96/312 | 112/312 | 0/312 |
| storm | 297/312 | 74/312 | 55/312 | 0/312 |
| flashcrowd | 281/312 | 29/312 | 33/312 | 0/312 |
| churn | 307/312 | 101/312 | 103/312 | 0/312 |
