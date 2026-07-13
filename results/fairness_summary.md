# Rotating tie-break (V3F) — safety and fairness

## Safety sweep

| variant | scenario | runs with loss | loss sector-ticks | worst floor | mean exposure |
|---|---|---|---|---|---|
| V3 | storm | 0/48 | 0 | 1 | 7310 |
| V3 | churn | 0/48 | 0 | 3 | 11269 |
| V3F P=200 | storm | 0/48 | 0 | 2 | 8006 |
| V3F P=200 | churn | 0/48 | 0 | 2 | 10865 |
| V3F P=50 | storm | 0/48 | 0 | 1 | 7678 |
| V3F P=50 | churn | 0/48 | 0 | 2 | 10623 |

## Fairness at equilibrium (no disruption, t=2600)

| variant | corr(aid, level) | level std | top-decile storage share |
|---|---|---|---|
| V3 | +0.077 | 1.97 | 91.1% |
| V3F P=200 | +0.011 | 1.89 | 93.1% |
| V3F P=50 | +0.014 | 1.89 | 93.0% |
