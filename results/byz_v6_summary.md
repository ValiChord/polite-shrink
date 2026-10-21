# Byzantine studies: V3 against V6

Same scenarios as byzantine_sim.py, 6 seeds each (930000+), N = 200, R = 5, 512 sectors.

## Forged leaving-notices (whole ring, 10 lowest-ID names, from t = 1500)

| rule | run | true floor min after attack (worst seed) | mean arc level at end | sync cost (mean) |
|---|---|---|---|---|
| V3 | clean | 5 | 0.94 | 21,458 |
| V3 | forged intents | 5 | 2.11 | 80,155 |
| V6 | clean | 5 | 0.86 | 8,966 |
| V6 | forged intents | 5 | 3.00 | 9,925 |

## Full-arc liars (declared coverage looks fine in every run)

| rule | liars K | true floor at end (worst seed) | sectors with no real copy at end (mean) |
|---|---|---|---|
| V3 | 2 | 3 | 0.0 |
| V3 | 4 | 1 | 0.0 |
| V3 | 5 | 0 | 120.0 |
| V3 | 10 | 0 | 352.0 |
| V3 | 20 | 0 | 359.2 |
| V6 | 2 | 3 | 0.0 |
| V6 | 4 | 1 | 0.0 |
| V6 | 5 | 0 | 93.3 |
| V6 | 10 | 0 | 328.8 |
| V6 | 20 | 0 | 335.7 |

## Trojan exit (K = R-1 = 4) against an honest storm of the same size

| rule | run | true floor min after exit (worst seed) | sector-ticks with no real copy (mean) |
|---|---|---|---|
| V3 | trojan exit | 1 | 0.0 |
| V3 | honest storm | 5 | 0.0 |
| V6 | trojan exit | 1 | 0.0 |
| V6 | honest storm | 5 | 0.0 |
