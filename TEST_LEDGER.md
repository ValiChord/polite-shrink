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
| **Partitions** | split the network, heal it, absorb the reconnection shrink storm | **no durability loss** in any of 3 geometries × 3 controllers (single seed; V1 and V2 also lose nothing, so this does not discriminate); V3's floor never left R. Flapping partitions defeat the damped controller, not this one ([REPORT_stage3 §1](REPORT_stage3.md)) |

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
| **8-node storm** (kitsune2 fork, in-memory transport) | shard down, kill 3 of 8 at once, recover to target | **no sector ever orphaned** ([REPORT_stage1 §5](REPORT_stage1.md)); repeated Oct 2026 under **V6** on [`feat/sharding-v6`](https://github.com/topeuph-ai/kitsune2/tree/feat/sharding-v6) — passes under V6 and V3 |
| **Forced simultaneous race** (kitsune2 fork, Oct 2026) | 8 agents, target 6, six agents deciding from one snapshot so their announcements truly race; no deaths; 12 runs per rule | **V6: never below target, never stalled, every waiter later left, settles in ≈ 2–3 s with 0 re-grows. V3: also safe, but median 34 announcements and 10 re-grows per run, up to ≈ 1 min to settle** ([results/rust_fork_v6.md](results/rust_fork_v6.md)) |
| **Stale views on a real network** (kitsune2 fork, Oct 2026) | every node acts on the network as it was 2 s ago; 6 nodes, target 4, no deaths; wait 1.5× the staleness; control arm with a wait of 0.5× | **V6 never below target, 0 re-grows (14 runs). Control fell below target in every run (to 0 twice), so the test can see a failure. V3 never below target either (14 runs) but re-grew 4–20 times per run; the model puts its failures in a narrow timing band, so not catching one is expected** ([results/rust_fork_v6.md §4](results/rust_fork_v6.md)) |
| **The staggered cascade, forced** (kitsune2 fork, Oct 2026) | 4 nodes sharing a half, target 1, 2 s old views, announcing in descending ID order 1 s apart, wait 4 s; delay before leavers grow back swept 0.5–8 s | **V3: the half reaches 0 declared copies in every run once growing back takes ≥ 2 s (12/12); masked when growing back is near instant. V6: never below 1 copy at any delay (18/18). V3 safe on fresh views (control)** ([§7](results/rust_fork_v6.md)) |
| **Where V3's re-growing comes from** (kitsune2 fork, Oct 2026) | label every grow decision: real shortage, or only announced departures? | **all 225 of V3's re-grows came from abandoned "leaving" notices still live at peers. Withdrawing them on backing off: V3 0 re-grows, settles in 2.3 s (was median 225 s, one run never settled in 5 min)** ([§5](results/rust_fork_v6.md)) |
| **Forged notice displacing a genuine one** (kitsune2 fork, Oct 2026) | a short-lived forged notice in a leaving node's name, from another peer | **was possible (unsafe direction, missed by the Stage 3 analysis); fixed by tracking each notice's sender, with unit tests for displacement, forged and out-of-order withdrawals** ([§6](results/rust_fork_v6.md)) |
| **Deaths noticed late** (Rust model, Oct 2026) | every schedule, 4 nodes, a death at any tick noticed 0–6 ticks later | **V6 safe while a death is noticed within less than its wait; 6.5% of schedules fail at a delay equal to the wait, 36% at 3×; always a little better than V3, which fails 4.6% even with instant detection** ([rust_fork_v6.md §8.1](results/rust_fork_v6.md)) |
| **Wait shorter than the staleness** (Rust model, Oct 2026) | every schedule, 4 nodes, wait from 1/3 to 2× the gossip lag | **V6 safe exactly from wait = lag (1.9% failing at 2/3, 20% at 1/3); V3 still fails 0.02% at twice the lag** ([§8.2](results/rust_fork_v6.md)) |
| **Liars and forged notices with V6** (simulation, Oct 2026) | Stage-3 Byzantine studies rerun for V3 and V6, 6 seeds | **same liar threshold (K = R) for both; no rule can see a false declaration, so the defence is still verified coverage. Forged notices: no loss under either; V6 keeps arcs wide but does not churn** ([§8.3](results/rust_fork_v6.md)) |
| **Storm over a real network stack** (kitsune2 iroh transport, Oct 2026) | 8–32 nodes on one machine, shard down, kill a quarter at once | **never an orphaned sector; sharded to ~10% of full replication at 32 nodes; back to target within ~2.5 s** ([§8.4](results/rust_fork_v6.md)) |
| **Stale views in TLA+** (Oct 2026) | `spec/StaleShrink.tla`, the timed stale-view model restated in TLA+ and checked by TLC; no deaths | **TLC finds V3's staggered cascade on its own; V6 safe and live at waits of 1x and 2x the lag; a too-short-wait control fails as it must. Every verdict matches the Python checker** ([spec/README.md](spec/README.md#stale-views-in-tla)) |
| **Stale-view model check on the Rust code** (Oct 2026) | `spec/timed_check.py` ported to Rust, driving the controller's own re-check functions; exhaustive over announce times, lags and a death at any tick | **V3 failure counts identical to the Python checker; V6 safe in every schedule, extended to six nodes overnight: 0 failures and 0 stalls in 3 × 16.8 million schedules, and 0 failures in 906 million with a death at any tick** ([results/rust_fork_v6.md](results/rust_fork_v6.md)) |
| **Wind Tunnel** (real iroh transport, live churn) | 33% of the network killed simultaneously; and a timed storm landing on pending intents | **zero orphaned sectors** in both. The brake cancelled all 9 pending intents in the timed storm (the simultaneous one had none pending), where op-level reachability found 0 of 23,673 ops lost ([Wind Tunnel report](wind_tunnel/results/REPORT_stage2_wind_tunnel.md)) |
| **Liveness under real transport** | (found by doing the above) | a broadcast head-of-line bug only a real transport could surface — found and fixed on the fork; plus an upstream mem-transport contract bug, fix offered ([PR #572](https://github.com/holochain/kitsune2/pull/572), closed by maintainers 2026-09-29: the transport is test-only) |

## Deployment realism — does it survive a *messy* rollout?

| Test | What it does | Result |
|---|---|---|
| **Rolling upgrade** | a network that's only *partly* upgraded — mixed new and old nodes | **safe from ~10% adoption — no flag day.** A small polite minority forms a backbone the old majority free-rides on ([rolling-upgrade report](REPORT_rolling_upgrade.md)) |
| **Rollout on the Rust fork** (V6, Oct 2026) | V6 nodes alongside nodes without dynamic sharding (full arc, never shrink); six such nodes replaced by V6 nodes one at a time; V6 nodes with two different timing configurations | **safe in every run** (3 repeats each): never below target with no deaths, no part of the DHT ever without a holder during the rollout, back at target once only V6 remains; no V6 agent left able to shrink ([results/rust_fork_v6.md](results/rust_fork_v6.md) §10) |
| **Decoupled clocks** | death-detection running on a *separate, slower* clock than gossip | at storm 30% the residual race is **≤ 2/312 runs** up to a detection latency of 2.7× the maximum gossip lag — governed by detection latency (at storm 50% and 4–8× the lag it is not small: 15–35% of V3 runs lose data), and it says to size the shrink wait against unresponsive-marking speed, not gossip ([REPORT_stage3 §11](REPORT_stage3.md)) |
| **Lossy gossip** | drop up to 90% of messages, so each node's view is incomplete *and* inconsistent | **data-loss rate stays flat** across 6,000 runs — no loss attributable to the drops. The re-check never needs a complete view ([REPORT_stage3 §12](REPORT_stage3.md)) |
| **Sparse-network deadlock** | (found by pushing V3 to its limit) | a real deadlock exists in sparse networks; the V4 expanding-ring repair rule fixes it — **120/120 recovery** while still sharding ([REPORT_stage3 §4](REPORT_stage3.md)) |

## Can the tests fail? (2026-10-21)

| | | |
|---|---|---|
| **Mutation testing** on the Rust fork | 18 hand-written realistic bugs, each planted alone, against the unit, model-check, race, cascade, stale-view and storm tests | **Round 1: 11/18 caught**, including every bug that breaks safety. The 7 survivors were glue code and defaults (wait wiring, withdrawal sending, announce-time yield, default settings, edge cases). Tests added for each: **18/18 caught** ([results/rust_fork_v6.md](results/rust_fork_v6.md) §9) |

## Formal proof — not tested, *proven*

| | | |
|---|---|---|
| **TLA+ / TLC model check** | "a sector never drops below R", every reachable state, five configurations (N = 6–8) | **no violation — but every node reads the true holder set instantly**, so the tie-break is never exercised (delete it and it still passes) and the naive rule's failure isolates nothing ([spec/](spec/)) |
| **Hybrid search** (Oct 2026) — safety *and* progress, every node retrying until it leaves | exhaustive, 8 configurations, plus deaths at any tick | V5 **stalls** in 35–87% of schedules (identical nodes cancel forever). Four hybrids tried: ID-ordered retries (stall), + yield-on-announce (stall), strict TCAS yield (safe, live, but only one node may leave at a time — useless at N = 200), safe-or-lowest (one ordinary death breaks it). **V6 "patient lowest" passes everything**: safe at a 1× wait, safe with prompt death detection, always progresses ([REPORT_stale_views.md](REPORT_stale_views.md) §7) |
| **V6 vs V3 vs V5 at N = 200** (fresh seeds) | standard scenarios ×48, storm 30/40% ×100, slow-detection stress ×72 | V6: arcs close to V3's, ≈ 3× less sync, cancel rate as low as V3's, **2–8× less time below R than V3** (4–20× less than V5); storm 40% losses V5 11/100, V3 0, V6 0. One V6 loss in 100 storm-30% worlds, starting at the storm tick (mass death, no shrink involved). Slow detection (192 ticks late) defeats all three equally ([results/v6_summary.md](results/v6_summary.md)) |
| **Stale-view check** (Oct 2026) | every announce schedule × per-node lag, N ≤ 5, with and without deaths | bare re-check: **fails everywhere**. ID tie-break (V3): safe for small N with a wait > 2× lag, **fails** a staggered cascade (R = 1) and one-death schedules (R = 2). Discount-every-announcer (V5): **safe in all**, at a 1× wait, with a proof for any N ([REPORT_stale_views.md](REPORT_stale_views.md)) |

---

## The same battery, re-run under the AgentInfo-only encoding (2026-07-25)

Announcement carried on the gossiped arc claim, no dedicated message. Full detail and the
trade-off analysis: [REPORT_agentinfo_encoding.md](REPORT_agentinfo_encoding.md).

| What was tested | Result |
|---|---|
| Formal safety of the encoding (TLA+/TLC, five configurations, N = 6–8) | **Safe** without a tie-break; the optimistic reading is **falsified** by a sequential drain, and the age-gated guess is **falsified** by a single misclassification |
| Stage-1 four scenarios | Durability held at the tested seeds; declared-coverage dips appear (phantom holes — bytes on disk, unreachable) |
| Partitions (netsplit + heal, 3 geometries) | Held floor stays at exactly R; zero data loss; availability recovers fully post-heal |
| Scale to N = 5,000 | Zero data loss; the reachability cost grows sharply with N (activation: 44 sector-ticks at N=200 → 14,718 at N=5,000; storm at N=5,000: 38,394) |
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
argument, not a measurement. Four studies test that claim, amend it, and then ask what a
policy author should do about the detection clock it turns on. Full detail:
[REPORT_mz_decomposition.md](REPORT_mz_decomposition.md), constraint 6b in
[REPORT_stage3.md](REPORT_stage3.md).

| What was tested | Result |
|---|---|
| Can a node see the race coming from its **own observation history**? (Mori–Zwanzig decomposition, 72 seeds, ~166k gate decisions) | **No.** Detection latency drives the failure mode up **29×** while the memory term stays flat (+0.0145 → +0.0150). A positive control detects memory ~8× more strongly where it exists, so this is the physics, not a weak estimator |
| Which local observables carry the information? (exact Shapley, 2^7 = 128 coalition fits) | **They are substitutes, and this narrows our own null.** Any one of six observables alone scores ≈0.89 against 0.92 for all seven — so the study above tested roughly *one* dimension of observable space sampled seven ways, not seven. Recorded as a limitation the follow-up discovered |
| Which **direction** should a failure detector err in? (false-conviction sweep, 48 seeds) | **Toward convicting the living — up to a ceiling.** `P(any loss)` falls **40% → 2%** as `p` goes 0 → 0.10, then rises to 10% at p = 0.40. **Replicated on fresh seeds** (150/point): 36% → 2.7% at p = 0.10 → 15.3% at p = 0.40, non-overlapping 95% intervals ([RELATED_WORK.md §5](RELATED_WORK.md)) |
| Why does the curve turn over? | **Open.** The first reading was error cancellation (over-count from slow detection annulled by false conviction, the bias crossing zero near p ≈ 0.05). The replication puts the loss minimum nearer p ≈ 0.10, and at p = 0.40 nodes hold *more* data yet lose more — consistent with thrashing as much as with cancellation |
| What does paranoia cost? | **Storage, not bandwidth.** Equilibrium arc up to +52%, but sync cost *falls* across most of the range — less shrinking means less re-growing. Bandwidth only degrades at p ≥ 0.4, where the view is broken rather than cautious |
| Bug found and fixed in the existing model | `DecoupledSim` never stamped `death_lag` on agents joining mid-run, so join-bearing scenarios raised `AttributeError`. The published §11 sweep is storm-only and never reached the path; `validate_decoupled.py` still passes and prior output is byte-identical |
| Is a **single** detector threshold good enough for a network whose peers detect at different speeds? (5×5 grid over the two classes' rates) | **No effect detectable.** The best per-class setting beats the best uniform one by 4 pp — but a selection-bias null test (all cells given the same true rate) reproduces a gap that large in 11% of grids, so it is what taking the best of 25 cells manufactures. Read as "not resolvable at 24 seeds", not "no effect" |
| What *is* worth having, then? | **Getting the threshold roughly right: 42% → 4%**, a 38 pp first-order effect. Per-peer calibration is bounded above by ~4 pp on top of that. Self-calibration (phi accrual and relatives) is therefore second-order here, and justifying it needs ~10× the seeds |
| Does mixing detection speeds help or hurt? | **Heterogeneity helps.** Replicated on fresh seeds (72 each): homogeneous dl=192 loses data in 35% of runs, homogeneous dl=96 in 15%, a 50/50 mix in **18%**. (The earlier "0/24" came from an uncommitted probe and did not replicate.) Safety tracks the *fastest* class, not the slowest — the same backbone effect §10 found for a polite minority in a naive majority |
| A grid that had to be thrown away | The first attempt set the fast class *faster than gossip*, which §11 had already shown drives its race to zero; that class then rescued the whole network, the baseline lost nothing, and all 25 cells were noise around zero. The summariser now reports the baseline first and refuses to be read as a null when there is no headroom |

*Not* claimed: none of this ran on real transport. Detection latency and conviction rate
are **per-agent** (that is what the last four rows measure), but there is still no
heartbeat timing, no arrival-time distribution and no detector memory — so this measures
whether the optimum *moves*, not any real detector's ability to track it. Two latency
classes at a 2:1 ratio is not a continuum. And `p` is a false-positive rate *per look*:
real accrual detectors run orders of magnitude lower, so only the left end of those sweeps
is an operating regime.

## What we don't claim

These are simulation and kitsune2-substrate measurements on one machine — not a
Holochain-conductor deployment, and not a WAN. The verified-coverage and audit defences
against liars exist in simulation only, not yet on the fork. And the policy constants
above are evidenced, not proven — the [seven constraints on any policy](README.md) say
what the runs establish that a real sizing policy has to respect, while leaving the policy
itself, and the choice of R, to whoever knows what these networks carry.
