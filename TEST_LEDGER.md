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
damped**, **V2 jittered** are the weaker variants it's compared against.

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

## What we don't claim

These are simulation and kitsune2-substrate measurements on one machine — not a
Holochain-conductor deployment, and not a WAN. The verified-coverage and audit defences
against liars exist in simulation only, not yet on the fork. And the policy constants
above are evidenced, not proven — the [seven constraints on any policy](README.md) say
what the runs establish that a real sizing policy has to respect, while leaving the policy
itself, and the choice of R, to whoever knows what these networks carry.
