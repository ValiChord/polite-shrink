# Should a failure detector err toward paranoia?

Constraint 6 says the shrink wait must be sized against death-detection latency. This asks the question it leaves open: which *direction* should a detector be wrong in?

`p` = per-(viewer, peer) probability that a **live** peer is wrongly convicted and dropped from the viewer's coverage. Storm 50%, N=200, R=5, gossip lag [8,24], 48 seeds/cell.

**This is a deliberate stress regime.** Loss only occurs at slow detection (§11's 2-8x band); milder settings lose nothing at any `p` and cannot discriminate. Absolute rates here are not operating figures.

Environment: Python 3.14.6, numpy 2.5.1 — numpy matches the repo pin, Python does not (3.12.1). Re-run under the pins before publishing digits.

## pure V3 (f=1.0), death_lag = 96

| p | P(any loss) | E[loss] (sector-ticks) | exposure | eq. arc level | sync cost |
|---|---|---|---|---|---|
| 0.0 | 4/48 (8%) | 28,760 | 108 | 1.32 | 19,523 |
| 0.02 | 3/48 (6%) | 28,223 | 115 | 1.14 (-14%) | 15,041 |
| 0.05 | 3/48 (6%) | 44,275 | 108 | 1.29 (-3%) | 11,359 |
| 0.1 | 1/48 (2%) | 2,689 | 92 | 1.36 (+3%) | 8,751 |
| 0.2 | 0/48 (0%) | 0 | 62 | 1.51 (+14%) | 9,302 |
| 0.4 | 0/48 (0%) | 0 | 19 | 1.97 (+48%) | 31,249 |

## pure V3 (f=1.0), death_lag = 192

| p | P(any loss) | E[loss] (sector-ticks) | exposure | eq. arc level | sync cost |
|---|---|---|---|---|---|
| 0.0 | 19/48 (40%) | 148,240 | 199 | 1.39 | 20,401 |
| 0.02 | 12/48 (25%) | 91,677 | 204 | 1.17 (-16%) | 15,731 |
| 0.05 | 4/48 (8%) | 87,904 | 190 | 1.27 (-8%) | 11,642 |
| 0.1 | 1/48 (2%) | 5,693 | 164 | 1.32 (-5%) | 9,165 |
| 0.2 | 1/48 (2%) | 8,468 | 117 | 1.44 (+4%) | 9,906 |
| 0.4 | 5/48 (10%) | 23,146 | 83 | 2.11 (+52%) | 34,569 |

## f=0.1, death_lag = 96

| p | P(any loss) | E[loss] (sector-ticks) | exposure | eq. arc level | sync cost |
|---|---|---|---|---|---|
| 0.0 | 6/48 (12%) | 64,070 | 115 | 0.71 | 31,232 |
| 0.02 | 4/48 (8%) | 93,752 | 126 | 0.73 (+3%) | 35,187 |
| 0.05 | 1/48 (2%) | 10,972 | 124 | 0.72 (+1%) | 36,276 |
| 0.1 | 1/48 (2%) | 25,098 | 116 | 0.87 (+23%) | 38,724 |
| 0.2 | 0/48 (0%) | 0 | 81 | 1.02 (+44%) | 42,479 |
| 0.4 | 0/48 (0%) | 0 | 40 | 1.48 (+110%) | 69,382 |

## f=0.1, death_lag = 192

| p | P(any loss) | E[loss] (sector-ticks) | exposure | eq. arc level | sync cost |
|---|---|---|---|---|---|
| 0.0 | 7/48 (15%) | 170,819 | 201 | 0.71 | 31,703 |
| 0.02 | 7/48 (15%) | 203,137 | 209 | 0.75 (+6%) | 36,314 |
| 0.05 | 3/48 (6%) | 38,628 | 201 | 0.74 (+4%) | 35,845 |
| 0.1 | 7/48 (15%) | 97,212 | 196 | 0.86 (+22%) | 39,699 |
| 0.2 | 6/48 (12%) | 52,139 | 156 | 1.05 (+48%) | 46,203 |
| 0.4 | 10/48 (21%) | 73,892 | 109 | 1.47 (+107%) | 79,714 |


## Findings

**1. The asymmetry holds in the realistic range — the direction was right.**
In the strongest-signal cell (f=1.0, death_lag=192) `P(any loss)` falls from
**40% to 2%** as `p` goes 0 -> 0.10, with E[loss] falling 148,240 -> 5,693. The
f=1.0/death_lag=96 cell agrees (8% -> 0%), as does f=0.1/death_lag=96
(12% -> 0%). Convicting the living really is cheaper than missing the dead.

**2. But it is NOT monotonic, and the reason is error cancellation — not
conservatism.** Past `p` ~ 0.2 the benefit reverses: f=1.0/death_lag=192 goes
back up to **10% at p=0.40**, five times its own optimum.

`diag_detector_bias.py` measures the viewer's mean signed coverage error against
ground truth and explains the whole curve (storm 50%, death_lag=192, 8 seeds):

| p | view bias (post-storm) | held loss |
|---|---|---|
| 0.00 | **+0.50** (over-counts) | 3,996 |
| 0.02 | +0.25 | 243 |
| 0.05 | **+0.10** (~balanced) | **0** |
| 0.10 | -0.24 | 3,119 |
| 0.20 | -1.14 | 0 |
| 0.40 | **-3.67** (under-counts) | 0 |

Under slow detection a viewer **over-counts**, because dead peers are still in
its coverage. A false conviction **under-counts**. The two annul near p ~ 0.05,
and that is exactly where loss is minimised. So the mechanism is not "paranoia
makes you conservative" — it is **one error source cancelling another**. Past the
crossing the viewer is simply wrong in the other direction, and at p=0.40 it is
under-counting by nearly four copies, which is a broken view rather than a
cautious one.

The practical consequence is sharper than "tune it paranoid": **the optimum sits
where the detector's false-positive rate offsets its false-negative rate, so it
is a function of detection latency and must be tuned against it** — the same
quantity constraint 6 already identifies.

**2b. This also explains the storage anomaly, which is real.** The equilibrium
arc dips at p=0.02 (1.387 -> 1.168 at death_lag=192) and the dip survives
testing: z = +3.01 across 48 seeds (z = +2.33 at death_lag=96). Holding *less*
while losing *less* looked contradictory, and it is not. At p=0 the viewer
over-counts, so it over-shrinks, opens holes, and then has to repair-grow; that
churn settles the network at a higher and much noisier level (seed std 0.40).
Cancel the bias and the controller shrinks correctly the first time, so it needs
no repair growth — less storage and less loss together. Seed variance collapses
monotonically with `p` (std 0.43 -> 0.14 at death_lag=96), which is the same
story: a less biased view produces a more repeatable equilibrium.

**3. Calibrate what `p` means before reading the right-hand rows.** `p` here is
a false-positive rate *per look*. A real accrual detector runs orders of
magnitude below this — Akka's default threshold of phi=8 corresponds to roughly
1e-8. Even a deliberately twitchy setting is p ~ 0.1. So the operating range is
the **left end** of these tables; p=0.40 is not a detector setting, it is a
broken view, and it is included only to locate the turn-over.

**4. The cost is storage, not bandwidth — the opposite of what was assumed.**
Equilibrium arc level rises (up to +52%), but sync cost *falls* across most of
the range (20,401 -> 9,165 at f=1.0/death_lag=192). Same mechanism as
REPORT_agentinfo_encoding.md 4.3: less shrinking means less re-growing, and
re-growing is what sync cost measures. Bandwidth only turns bad at p >= 0.4,
where thrash dominates. For phone-hosted nodes this is a *better* trade than
expected.

## Caveats

- **f=0.1 / death_lag=192 is non-monotonic throughout and should not be
  read as a curve.** 7/48 -> 7/48 -> 3/48 -> 7/48 -> 6/48 -> 10/48 is consistent
  with binomial noise at these counts. It neither supports nor contradicts;
  it is underpowered.
- **The storage dip was flagged as unexplained in the first version of this
  report and is now explained** (finding 2b). It was neither an averaging
  artefact nor noise. Recorded here because the first reading was wrong.
- **Stress regime.** Storm 50% at 4-8x the gossip lag. Chosen because nothing
  loses data at milder settings, which makes them useless for discriminating.
  These are not operating rates.
- **The detector is memoryless.** Convictions are redrawn per view, so this
  measures the cost of a false positive in isolation, not any real detector's
  dynamics. Heterogeneous per-peer responsiveness and detector memory are steps
  2 and 3 of this line of work, and are what a phi accrual detector would need
  in order to be more than a fixed timeout.
- 48 seeds per cell; single-digit counts carry the usual uncertainty.
