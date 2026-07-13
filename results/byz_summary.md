# Byzantine study summary

## Forged intents (worst case: whole-ring claims, 10 lowest ids)

| run | true floor min (post-attack) | mean level end | resizes | sync cost |
|---|---|---|---|---|
| clean | 5 | 0.85 | 3619 | 32891 |
| forged intents | 6 | 2.34 | 5822 | 77204 |

## Full-arc liars (declared floor stays ≥ R in every run — the attack is invisible to declared coverage)

| run | declared floor end | true floor end | true-zero sectors end | fraction of ring |
|---|---|---|---|---|
| liar K=2 | 5 | 3 | 0 | 0.0% |
| liar K=4 | 5 | 1 | 0 | 0.0% |
| liar K=5 | 5 | 0 | 139 | 27.1% |
| liar K=10 | 10 | 0 | 357 | 69.7% |
| liar K=20 | 20 | 0 | 364 | 71.1% |

## Trojan exit (K = R-1) vs equal honest storm

| run | true floor min post-exit | true-zero sector-ticks post-exit |
|---|---|---|
| trojan exit | 1 | 0 |
| honest storm | 5 | 0 |
