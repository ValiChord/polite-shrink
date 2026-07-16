# §6.1 race vs death-detection latency (storm, decoupled clock)

Seeds: 312. Gossip/view lag = [8,24]. `death_lag` = uniform death-detection latency; `coupled` = base single-clock model (death clock = own gossip lag).

Race = a shrink executed after the death tick on a view still counting not-yet-detected deaths. Death-only = orphaned at t=1500 (mass death, detection-independent).


## upgraded fraction f = 0.1

| death_lag | §6.1 races | pure-death losses | any-loss rate |
|---|---|---|---|
| coupled | 1/312 | 2/312 | 1.0% |
| 4 | 0/312 | 2/312 | 0.6% |
| 8 | 0/312 | 2/312 | 0.6% |
| 12 | 0/312 | 2/312 | 0.6% |
| 16 | 1/312 | 2/312 | 1.0% |
| 24 | 1/312 | 2/312 | 1.0% |
| 32 | 1/312 | 2/312 | 1.0% |
| 48 | 2/312 | 2/312 | 1.3% |
| 64 | 2/312 | 2/312 | 1.3% |

## upgraded fraction f = 0.3

| death_lag | §6.1 races | pure-death losses | any-loss rate |
|---|---|---|---|
| coupled | 0/312 | 0/312 | 0.0% |
| 4 | 0/312 | 0/312 | 0.0% |
| 8 | 0/312 | 0/312 | 0.0% |
| 12 | 0/312 | 0/312 | 0.0% |
| 16 | 0/312 | 0/312 | 0.0% |
| 24 | 0/312 | 0/312 | 0.0% |
| 32 | 0/312 | 0/312 | 0.0% |
| 48 | 0/312 | 0/312 | 0.0% |
| 64 | 0/312 | 0/312 | 0.0% |

## upgraded fraction f = 0.5

| death_lag | §6.1 races | pure-death losses | any-loss rate |
|---|---|---|---|
| coupled | 0/312 | 0/312 | 0.0% |
| 4 | 0/312 | 0/312 | 0.0% |
| 8 | 0/312 | 0/312 | 0.0% |
| 12 | 0/312 | 0/312 | 0.0% |
| 16 | 0/312 | 0/312 | 0.0% |
| 24 | 0/312 | 0/312 | 0.0% |
| 32 | 0/312 | 0/312 | 0.0% |
| 48 | 0/312 | 0/312 | 0.0% |
| 64 | 1/312 | 0/312 | 0.3% |

## upgraded fraction f = 1.0

| death_lag | §6.1 races | pure-death losses | any-loss rate |
|---|---|---|---|
| coupled | 0/312 | 0/312 | 0.0% |
| 4 | 0/312 | 0/312 | 0.0% |
| 8 | 0/312 | 0/312 | 0.0% |
| 12 | 0/312 | 0/312 | 0.0% |
| 16 | 0/312 | 0/312 | 0.0% |
| 24 | 0/312 | 0/312 | 0.0% |
| 32 | 0/312 | 0/312 | 0.0% |
| 48 | 0/312 | 0/312 | 0.0% |
| 64 | 1/312 | 0/312 | 0.3% |
