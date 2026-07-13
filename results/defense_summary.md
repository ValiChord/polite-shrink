# Byzantine defenses

## Intent range-validation (V3, 10 forged names, attack from t=1500)

| run | true floor min (post) | mean level end | resizes | sync |
|---|---|---|---|---|
| clean | 5 | 0.85 | 3619 | 32891 |
| forged (no validation) | 6 | 2.34 | 5822 | 77204 |
| forged (range-validated) | 5 | 1.01 | 3623 | 34326 |

## Serve-audit (K=10 liars, 2 audits/agent-epoch, threshold 1, per-observer exclusion, no verdict gossip)

| run | seed | true-zero sectors end | true floor end | ring fully re-covered at |
|---|---|---|---|---|
| no audit | 42 | 357 | 0 | None |
| no audit | 7 | 352 | 0 | None |
| no audit | 99 | 348 | 0 | None |
| audit from t=1500 | 42 | 0 | 5 | 1769 |
| audit from t=1500 | 7 | 0 | 5 | 1798 |
| audit from t=1500 | 99 | 0 | 5 | 1828 |
