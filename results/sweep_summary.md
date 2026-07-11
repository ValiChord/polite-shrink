# Robustness sweep — 8 (scenario,seed) cells, 32 simulations

## Pooled across all four scenarios

| variant | runs | runs with data loss | loss rate | 95% upper bound | worst floor | mean exposure |
|---|---|---|---|---|---|---|
| V0 naive | 8 | 8 | 100.00% | < 100.00% | 0 | 261791 |
| V1 damped | 8 | 3 | 37.50% | < 71.05% | 0 | 21786 |
| V2 damped+jitter | 8 | 1 | 12.50% | < 35.42% | 0 | 22671 |
| V3 full (polite shrink) | 8 | 0 | 0.00% | < 37.50% | 3 | 3851 |

## Per scenario (runs with data loss / runs)

| scenario | V0 naive | V1 damped | V2 damped+jitter | V3 full (polite shrink) |
|---|---|---|---|---|
| activation | 2/2 | 1/2 | 0/2 | 0/2 |
| storm | 2/2 | 0/2 | 0/2 | 0/2 |
| flashcrowd | 2/2 | 1/2 | 0/2 | 0/2 |
| churn | 2/2 | 1/2 | 1/2 | 0/2 |
