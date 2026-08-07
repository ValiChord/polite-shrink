# Is one detector threshold good enough for a mixed network?

The question that decides whether adaptive, self-calibrating failure detection is worth building. Half the agents detect deaths fast (latency 192), half slowly (384); the two classes' false-conviction rates are swept independently.

Storm 50%, N=200, R=5, 24 seeds/cell. Stress regime — milder settings lose nothing at any setting and cannot discriminate; these are not operating rates.

Environment: Python 3.14.6, numpy 2.5.1 — numpy matches the repo pin, Python does not (3.12.1).

## Baseline check — is there anything here to measure?

At p = 0 for both classes the network loses data in **42%** of runs. That is the headroom every cell below is competing against.

## P(any loss), by class setting

Rows = `p_slow` (the slow-detecting half), columns = `p_fast`. The **diagonal** is what a single global threshold can reach; everything off it needs per-peer calibration.

| p_slow \ p_fast | 0.0 | 0.02 | 0.05 | 0.1 | 0.2 |
|---|---|---|---|---|---|
| **0.0** | *42%* | 33% | 21% | 4% | 8% |
| **0.02** | 38% | *29%* | 12% | 12% | 4% |
| **0.05** | 25% | 8% | *8%* | **0%** | 4% |
| **0.1** | 8% | 4% | 12% | *4%* | 8% |
| **0.2** | 12% | 17% | 12% | 8% | *4%* |

*italic* = diagonal (uniform threshold); **bold** = grid optimum.

## What per-peer calibration buys

| | setting | P(any loss) | E[loss] |
|---|---|---|---|
| best **uniform** | p = 0.1 for both | 4% (1/24 runs) | 5,925 |
| best **per-class** | fast 0.1, slow 0.05 | 0% (0/24 runs) | 0 |
| apparent gap | | +4 pp | -5,925 |

**Selection-bias check.** If every cell in the grid had the *same* true rate (4%), simply taking the best of 25 cells rather than the best of 5 would produce a gap this large or larger in **11%** of grids (20,000 simulated).

**No evidence that per-peer calibration helps.** The apparent 4 pp advantage is what the search procedure manufactures on its own — it is 1 losing run(s) versus 0 out of 24, and vanishes under the null. Read as **'no effect detectable at this sample size'**, not 'no effect'.

**What the grid does show, and it is the larger number.** Going from no paranoia at all to the best single global threshold takes `P(any loss)` from **42% to 4%** — a 38 pp first-order effect. Whatever per-peer calibration is worth on top, it is bounded above by roughly 4 pp and is not resolvable here. **Getting the threshold roughly right matters enormously; getting it right *per peer* does not measurably.**

For phi accrual and relatives that is the answer: their value is self-calibration, and self-calibration is second-order against an effect this size. Justifying that machinery needs a regime where the first-order effect is already captured and the residual per-peer term is resolvable — which would take on the order of 10x the 24 seeds used here.

## Storage, split by who pays it

| p_fast | p_slow | arc (fast class) | arc (slow class) | sync |
|---|---|---|---|---|
| 0.0 | 0.0 | 2.32 | 0.54 | 21,869 |
| 0.02 | 0.02 | 1.79 | 0.48 | 17,126 |
| 0.05 | 0.05 | 1.99 | 0.56 | 12,171 |
| 0.1 | 0.1 | 2.04 | 0.43 | 9,763 |
| 0.2 | 0.2 | 2.26 | 0.51 | 12,595 |

## Caveats

- Two latency classes at a 4:1 ratio and a 50/50 split. A real network has a continuum, and the answer could differ for a long-tailed distribution.
- `p` is a false-positive rate *per look*; real accrual detectors run orders of magnitude lower, so the interesting region is the top-left of the grid.
- No heartbeat timing, no detector memory. This measures whether the *optimum moves*, which is the precondition for adaptivity being useful — not any detector's ability to track it.
- 24 seeds per cell; grid minima of noisy quantities are biased low, so treat the gap as an upper bound on what adaptivity could buy.

