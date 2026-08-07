# What polite shrink has been tested against

A single page listing every test the controller has been put through, and what happened.
It's a summary — each row links to the write-up with the method, the exact numbers, and
how to reproduce it. Every result here is one-command reproducible; see
[REPRODUCE.md](REPRODUCE.md).

Two things worth stating up front:

- **The safety property is one sentence:** no sector ever holds fewer than R real copies.
  Every test below is a different way of trying to break it.
- **What's *proven* is the gate** — the pre-drop re-check (discount your own stale view,
  treat every lower-id intender as gone, proceed only if R remain). The controller's
  *policy* (target, hysteresis constants, growth rule, clamp) is not proven; it's
  engineering judgement, and it's what these tests measure. Detail:
  [REPORT_stage1.md §2.2](REPORT_stage1.md).

Throughout, **V3 / polite shrink** is the controller being tested; **V0 naive**, **V1
damped**, **V2 jittered** are the weaker variants it's compared against. **V5** is the
same gate with the announcement carried on the already-gossiped `AgentInfo` arc claim
instead of a dedicated message — the section at the end lists what happened when the
whole battery was re-run against it.

---

## Simulation — does it hold, and at what scale?

| Test | What it does | Result |
|---|---|---|
| **Robustness sweep** | 4 disruption scenarios × 312 seeds × 4 controllers = 4,992 paired runs | polite shrink lost **0 sectors in 1,248 runs**; the naive controller lost data in **95.9%** ([REPORT_stage1](REPORT_stage1.md)) |
| **Ablation** | add one ingredient at a time — hysteresis, jitter, two-phase shrink | hysteresis alone: 95.9% → 24%. Jitter: no help (24.3%). The **two-phase handshake** is what reaches zero ([REPORT_stage1](REPORT_stage1.md)) |
| **Scale** | grow the network to 5,000 agents on rings up to 16,384 sectors | polite shrink held the floor at R with **zero loss at every N**; the damped controller starts losing data at N ≥ 2,000 ([REPORT_stage3 §3](REPORT_stage3.md)) |
| **Partitions** | split the network, heal it, absorb the reconnection shrink storm | **no durability loss in 9 runs**; the floor never left R. Flapping partitions defeat the damped controller, not this one ([REPORT_stage3 §1](REPORT_stage3.md)) |

## Adversarial — can something *trying* to break it succeed?

| Test | What it does | Result |
|---|---|---|
| **Evolutionary adversary** | 20 generations searching for the worst possible schedule of node kills, free choice of who and when | broke the damped and jittered controllers; **could not make polite shrink lose a single sector** ([REPORT_stage1 §4](REPORT_stage1.md)) |
| **Forged shrink-intents** | a liar announces bogus intent to vacate, in the highest-priority names, over the whole ring | **fail-safe: zero data loss.** It's only a *cost* attack (more sync, wider arcs); range-validation cuts it to ~4% and is implemented on the fork ([REPORT_stage3 §2](REPORT_stage3.md)) |
| **False coverage (the honest gap)** | nodes *lie* about what they store | this is the one thing a coverage-trusting controller can't survive — past K = R liars, data is lost invisibly. It's a **sensor problem, not a control problem** ([REPORT_stage3 §2b](REPORT_stage3.md)) |
| **Verified coverage** | count a peer only while a fresh proof-of-serve backs it | removes the liar ceiling entirely — **zero dead sectors from K = 0 all the way to 3R**, at a bandwidth cost the operator sets (~13–16%) ([REPORT_stage3 §7](REPORT_stage3.md)) |
| **Partial liars** | store a strategic fraction, serve just enough challenges to pass | **zero data loss at every fraction**; a margin dip in the middle that a higher audit sample-count restores ([REPORT_stage3 §8](REPORT_stage3.md)) |

## Real network — does it survive a real transport?

| Test | What it does | Result |
|---|---|---|
| **8-node storm** (kitsune2 fork, in-memory transport) | shard down, kill 3 of 8 at once, recover to target | **no sector ever orphaned** ([REPORT_stage1 §5](REPORT_stage1.md)) |
| **Wind Tunnel** (real iroh transport, live churn) | 33% of the network killed simultaneously at the worst moment | **zero orphaned sectors, zero of 23k+ published ops lost**; the storm brake cancelled all 9 stale-view shrink intents at detection ([Wind Tunnel report](wind_tunnel/results/REPORT_stage2_wind_tunnel.md)) |
| **Liveness under real transport** | (found by doing the above) | a broadcast head-of-line bug only a real transport could surface — found and fixed on the fork; plus an upstream mem-transport contract bug, fix offered ([PR #572](https://github.com/holochain/kitsune2/pull/572), open) |

## Deployment realism — does it survive a *messy* rollout?

| Test | What it does | Result |
|---|---|---|
| **Rolling upgrade** | a network that's only *partly* upgraded — mixed new and old nodes | **safe from ~10% adoption — no flag day.** A small polite minority forms a backbone the old majority free-rides on ([rolling-upgrade report](REPORT_rolling_upgrade.md)) |
| **Decoupled clocks** | death-detection running on a *separate, slower* clock than gossip | the residual race is **bounded and small** — governed by detection latency, and it says to size the shrink wait against unresponsive-marking speed, not gossip ([REPORT_stage3 §11](REPORT_stage3.md)) |
| **Lossy gossip** | drop up to 90% of messages, so each node's view is incomplete *and* inconsistent | **data-loss rate stays flat** across 6,000 runs — no loss attributable to the drops. The re-check never needs a complete view ([REPORT_stage3 §12](REPORT_stage3.md)) |
| **Sparse-network deadlock** | (found by pushing V3 to its limit) | a real deadlock exists in sparse networks; the V4 expanding-ring repair rule fixes it — **120/120 recovery** while still sharding ([REPORT_stage3 §4](REPORT_stage3.md)) |

## Formal proof — not tested, *proven*

| | | |
|---|---|---|
| **TLA+ / TLC model check** | "a sector never drops below R", checked over **every reachable state** (N ≤ 8, R from 1 to 7) | **no violation.** The naive rule fails the same check with a counterexample — which isolates the two-phase tie-break as the thing that buys safety ([spec/](spec/), [REPORT_stage3 §9](REPORT_stage3.md)) |

---

## The same battery, re-run under the AgentInfo-only encoding (2026-07-25)

Announcement carried on the gossiped arc claim, no dedicated message. Full detail and the
trade-off analysis: [REPORT_agentinfo_encoding.md](REPORT_agentinfo_encoding.md).

| What was tested | Result |
|---|---|
| Formal safety of the encoding (TLA+/TLC, N ≤ 8, R 1–7) | **Safe** without a tie-break; the optimistic reading is **falsified** by a sequential drain, and the age-gated guess is **falsified** by a single misclassification |
| Stage-1 four scenarios | Durability held at the tested seeds; declared-coverage dips appear (phantom holes — bytes on disk, unreachable) |
| Partitions (netsplit + heal, 3 geometries) | Held floor stays at exactly R; zero data loss; availability recovers fully post-heal |
| Scale to N = 5,000 | Zero data loss; the reachability cost grows sharply with N (44 sector-ticks at N=200 → 38,394 at N=5,000) |
| §6.1 shrink-race grid (1,680 runs) | **5 shrink-caused holes vs V3's 1,732** — 0.0002% of real holes against 0.0759% |
| Lossy gossip to 90% drop | Zero data loss — and this closes §12's own caveat, since here the dropped channel *is* the announcement channel |
| V4 expanding-ring repair, clamp = 0 | 12/12 recovery, nothing stuck, ~4× fewer repair grows |
| False-coverage liars | Threshold unchanged: both collapse at K = R |
| Verified coverage / partial liars | Both defences hold; zero true loss to K = 3R and at every held-fraction |
| Storage fairness | Top-decile share **92.4% → 43.4%**, which the rotating-key fix (92.7%) did not achieve |
| Decoupled death-clock | §11's shape holds; V5 carries a consistent small offset |
| Wind Tunnel, real iroh transport (5 runs) | All verdicts PASS both arms; 0 of 21,657 and 0 of 23,526 ops lost. Indistinguishable from the control **at this scale** — the harness runs 12–18 agents, and the sim predicts zero effect there, so this validates the simulation rather than clearing the encoding |
| **Mass-death frequency, 100 seeds** | **The correction.** Real loss in 6–9% of V5 storm runs vs 1% for V3 — more often, though less than half the total volume. Earlier "zero loss" readings rested on ≤4 seeds |

## The detection side, probed directly (2026-08-07)

§11 concluded that the slow-detection residual is "irreducible by any local rule" — as an
argument, not a measurement. These three studies test that, and amend it. Full detail:
[REPORT_mz_decomposition.md](REPORT_mz_decomposition.md), constraint 6b in
[REPORT_stage3.md](REPORT_stage3.md).

| What was tested | Result |
|---|---|
| Can a node see the race coming from its **own observation history**? (Mori–Zwanzig decomposition, 72 seeds, ~166k gate decisions) | **No.** Detection latency drives the failure mode up **29×** while the memory term stays flat (+0.0145 → +0.0150). A positive control detects memory ~8× more strongly where it exists, so this is the physics, not a weak estimator |
| Which local observables carry the information? (exact Shapley, 2^7 = 128 coalition fits) | **They are substitutes, and this narrows our own null.** Any one of six observables alone scores ≈0.89 against 0.92 for all seven — so the study above tested roughly *one* dimension of observable space sampled seven ways, not seven. Recorded as a limitation the follow-up discovered |
| Which **direction** should a failure detector err in? (false-conviction sweep, 48 seeds) | **Toward convicting the living — up to a ceiling.** `P(any loss)` falls **40% → 2%** as `p` goes 0 → 0.10, then rises to 10% at p = 0.40 |
| Why does the curve turn over? | **Error cancellation, not conservatism.** Slow detection makes a viewer over-count; false conviction under-counts; they annul near p ≈ 0.05 — exactly where loss is minimised. So the optimum is set by detection latency |
| What does paranoia cost? | **Storage, not bandwidth.** Equilibrium arc up to +52%, but sync cost *falls* across most of the range — less shrinking means less re-growing. Bandwidth only degrades at p ≥ 0.4, where the view is broken rather than cautious |
| Bug found and fixed in the existing model | `DecoupledSim` never stamped `death_lag` on agents joining mid-run, so join-bearing scenarios raised `AttributeError`. The published §11 sweep is storm-only and never reached the path; `validate_decoupled.py` still passes and prior output is byte-identical |
| Is a **single** detector threshold good enough for a network whose peers detect at different speeds? (5×5 grid over the two classes' rates) | **No effect detectable.** The best per-class setting beats the best uniform one by 4 pp — but a selection-bias null test (all cells given the same true rate) reproduces a gap that large in 11% of grids, so it is what taking the best of 25 cells manufactures. Read as "not resolvable at 24 seeds", not "no effect" |
| What *is* worth having, then? | **Getting the threshold roughly right: 42% → 4%**, a 38 pp first-order effect. Per-peer calibration is bounded above by ~4 pp on top of that. Self-calibration (phi accrual and relatives) is therefore second-order here, and justifying it needs ~10× the seeds |
| Does mixing detection speeds help or hurt? | **Heterogeneity is protective.** A homogeneous slow network (dl=192) loses data in 40% of runs; mixing in an equal half at dl=96 takes it to **0/24**. Safety tracks the *fastest* class, not the slowest — the same backbone effect §10 found for a polite minority in a naive majority |
| A grid that had to be thrown away | The first attempt set the fast class *faster than gossip*, which §11 had already shown drives its race to zero; that class then rescued the whole network, the baseline lost nothing, and all 25 cells were noise around zero. The summariser now reports the baseline first and refuses to be read as a null when there is no headroom |

*Not* claimed: none of this ran on real transport, the model has no heartbeat timing or
per-peer heterogeneity, and `p` is a false-positive rate *per look* — real accrual detectors
run orders of magnitude lower, so only the left end of that sweep is an operating regime.

## What we don't claim

These are simulation and kitsune2-substrate measurements on one machine — not a
Holochain-conductor deployment, and not a WAN. The verified-coverage and audit defences
against liars exist in simulation only, not yet on the fork. And the policy constants
above are evidenced, not proven — the [seven constraints on any policy](README.md) say
what the runs establish that a real sizing policy has to respect, while leaving the policy
itself, and the choice of R, to whoever knows what these networks carry.
