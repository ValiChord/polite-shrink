# Partition study summary

dur_* = durability (live copies anywhere; zero = data gone). avail_* = availability (copies reachable within each side; zero-ticks = sector-ticks unreachable on some side — the unavoidable partition cost, shown so recovery speed can be compared). heal_settle = ticks after final heal until the resize rate stays < 1/tick for 300 ticks.

| scenario | variant | dur_floor_min | dur_loss_ticks | dur_floor_min_held | dur_loss_ticks_held | avail_floor_min_split | avail_zero_ticks_split | avail_zero_ticks_postheal | heal_settle | resizes | sync_cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| split5050 | V1 damped | 2 | 0 | 2 | 0 | 1 | 0 | 0 | never | 5142 | 63089 |
| split5050 | V2 damped+jitter | 2 | 0 | 2 | 0 | 2 | 0 | 0 | 0 | 5284 | 39225 |
| split5050 | V3 full (polite shrink) | 5 | 0 | 5 | 0 | 2 | 0 | 0 | 0 | 3793 | 28476 |
| split5050 | V5 polite (AgentInfo-only) | 4 | 0 | 5 | 0 | 0 | 240 | 0 | 236 | 2774 | 17295 |
| split9010 | V1 damped | 2 | 0 | 2 | 0 | 1 | 0 | 0 | never | 4890 | 60064 |
| split9010 | V2 damped+jitter | 2 | 0 | 2 | 0 | 1 | 0 | 0 | never | 4827 | 41098 |
| split9010 | V3 full (polite shrink) | 5 | 0 | 5 | 0 | 1 | 0 | 0 | 0 | 3894 | 41836 |
| split9010 | V5 polite (AgentInfo-only) | 4 | 0 | 5 | 0 | 0 | 5627 | 0 | 0 | 2355 | 17386 |
| flapping | V1 damped | 2 | 0 | 2 | 0 | 0 | 1007 | 0 | 190 | 5020 | 37507 |
| flapping | V2 damped+jitter | 4 | 0 | 4 | 0 | 2 | 0 | 0 | 142 | 5185 | 30150 |
| flapping | V3 full (polite shrink) | 5 | 0 | 5 | 0 | 2 | 0 | 0 | 354 | 4366 | 32530 |
| flapping | V5 polite (AgentInfo-only) | 3 | 0 | 5 | 0 | 0 | 401 | 0 | 255 | 3344 | 26808 |
