# Dynamic DHT Storage-Arc Sizing: Controller Design, Robustness Evidence, and a Reference Implementation for Kitsune2

**Author:** Ceri John ([topeuph-ai](https://github.com/topeuph-ai)), with AI assistance (Claude, Anthropic) — roles in §9 Provenance; citation record in [`CITATION.cff`](CITATION.cff)
**Study period:** 2026-07-11 → 2026-07-12
**Status:** complete (Stages 1, 1c, 2); design note published on [holochain/kitsune2#160](https://github.com/holochain/kitsune2/issues/160#issuecomment-4949241059)
**Reference implementation:** [`topeuph-ai/kitsune2`, branch `feat/sharding-module-v3`](https://github.com/topeuph-ai/kitsune2/tree/feat/sharding-module-v3)

---

## Abstract

Holochain's DHT layer (kitsune2) supports per-agent *storage arcs* — the contiguous range of DHT locations an agent claims authority over — but has run all agents at full arcs since dynamic arc sizing was disabled in 2021 due to control-loop oscillation ("hallway dancing") that caused data loss. Kitsune2 issue #160 asks for the missing *sharding module*: a controller that recommends a target arc from observed redundancy.

We (1) built a discrete-time simulator of the arc control problem and evaluated four controller variants of increasing coordination sophistication across four disruption scenarios × 312 random world-realisations each (4,992 paired simulations); (2) subjected the surviving variants to an evolutionary adversarial search over disruption schedules; and (3) ported the winning controller into kitsune2 itself behind its existing `sharding` feature flag, validating it with unit tests and a multi-node in-process storm test.

The naive controller reproduces the 2021 oscillation (data loss in 95.9% of runs). Damping alone leaves a ~24% loss rate; decision-epoch jitter — the textbook desynchronisation remedy — provides no additional safety. A **two-phase "polite shrink"** (announce intent → wait a multiple of measured staleness → re-check with a deterministic lowest-id tie-break) lost **zero sectors in all 1,248 runs** (95% upper bound on the per-run loss rate: 0.24%) and could not be defeated by the adversarial search. Porting the controller into the real codebase surfaced three constraints invisible to the simulation, most notably that **death visibility and view staleness run on independent clocks**, which bounds the safety of any locally-decided shrink. The port, an upstream bug fix, and all findings were contributed to the kitsune2 issue tracker.

---

## 1. Background and problem statement

In kitsune2, shared data is assigned to locations on a 32-bit ring divided into 512 sectors (`SECTOR_SIZE = 2^23`). Each agent declares a storage arc; the network is healthy when every sector is covered by at least R agents (the redundancy target). Today every agent stores everything (`DhtArc::FULL`), which cannot scale.

Dynamic sizing requires each agent to independently decide, from a *stale* view of peers' declared arcs (gossip propagation delay), when to grow and when to shrink. The historical failure mode is oscillatory: agents react to each other's reactions, and shrink decisions taken on stale views orphan sectors. The design question is: **which local decision rule holds a redundancy target without global coordination, under disruption, with stale information?**

Kitsune2 already contains the safe half of the machinery behind its dormant `sharding` feature flag: an agent's *current* arc grows toward its *target* arc only as sectors verifiably sync (`crates/gossip/src/storage_arc.rs`). The missing piece — issue #160 — is the target-arc controller, and above all safe *shrinking*, which is where all the risk is concentrated: growth claims only what has been verified; shrinking abandons authority.

## 2. Stage 1 — simulation methodology

### 2.1 Model

Discrete-time simulator (`polite_shrink.py`, Python 3.12.1, numpy 2.5.1, byte-deterministic; see `REPRODUCE.md`):

- **Ring:** S = 512 sectors (= 2^9, matching kitsune2's sector count exactly).
- **Agents:** N = 200 (initial population), each with a fixed uniformly random *home sector* and a fixed per-viewer gossip staleness ("lag") drawn uniformly from [8, 24] ticks. An agent's view of the world at time *t* is the true declared state at *t − lag*.
- **Arcs are quantised:** an agent claims an *aligned power-of-two block* of sectors containing its home sector. The controller's only state is the block *level* L (block of 2^L sectors; L = 9 is the full ring). Growing doubles the block (into the *sibling half* of the parent block), shrinking halves it (dropping the *vacate half* not containing home).
- **Sync cost:** growing into k sectors takes ⌈0.05·k⌉ ticks before the new declaration takes effect; decisions are suspended while syncing. Shrinks take effect immediately.
- **Decision epochs:** agents evaluate every E = 6 ticks.
- **Redundancy target:** R = 5.

### 2.2 Controller variants

Each variant adds one ingredient, isolating its contribution:

| | hysteresis | jitter | two-phase shrink |
|---|---|---|---|
| **V0 naive** | – | – | – |
| **V1 damped** | ✓ | – | – |
| **V2 damped + jitter** | ✓ | ✓ | – |
| **V3 polite shrink** | ✓ | ✓ | ✓ |

Common conditions (evaluated on the agent's stale view):
- **Grow condition:** the sibling half's minimum declared coverage < R.
- **Shrink condition:** the vacate half's minimum coverage, excluding the agent's own declaration, ≥ R + 1 (i.e. strictly above target without us).

Variant-specific rules:
- **V0:** act immediately when a condition holds; all agents share decision phase 0 (synchronised epochs).
- **V1 (+hysteresis):** a condition must persist for ⌈1.0 × own lag⌉ ticks before growing and ⌈4.0 × own lag⌉ ticks before shrinking — grow readily, shrink reluctantly, dwell times scaled to the agent's *own measured staleness*.
- **V2 (+jitter):** each agent's decision epoch is offset by a uniform random phase in [0, E).
- **V3 (+two-phase shrink):**
  1. When the shrink condition matures, the agent *announces* an intent to vacate (visible to all agents after their lag) and freezes its own decisions.
  2. After `intent_delay` = 50 ticks (> 2 × max lag), it *re-checks* on its then-current stale view: effective coverage of the vacate half = declared coverage − own declaration − the vacated ranges of **announced intenders with lower agent id**. If min ≥ R it shrinks; otherwise it cancels and resets its dwell counter.
  3. Tie-break asymmetry: lower-id intenders are counted as gone; higher-id intenders are ignored (they will count *us* and defer). The lowest conflicting id therefore proceeds; symmetric deference was tried first and livelocks the network (no agent can ever shrink). The scheme is modelled on TCAS, aviation's collision-avoidance system (C. John's insight): conflicting parties announce, then resolve *asymmetrically* by a deterministic rank both sides compute independently — complementary resolution advisories, never mirrored ones. This ingredient, not damping or jitter, is what separates the zero-loss variant from the rest (§3, §4).
  4. Growers subtract announced vacates from coverage (move before the hole opens); starting a grow cancels any pending intent (safety first).
  5. Small-network clamp: below 25 visible peers, hold/grow to full arc, never shrink.

### 2.3 Scenarios

Worlds (homes, lags, deaths, joins) are pre-generated per seed and **identical across variants** (paired design; differences in outcome are attributable to the controller alone).

| scenario | ticks | disruption |
|---|---|---|
| activation | 2,200 | none — cold start from all-full arcs; measures shard-down stability |
| storm | 3,000 | 30% of agents die simultaneously at t = 1,500 |
| flashcrowd | 3,000 | 60% population influx at t = 1,500 (joiners start at level 0) |
| churn | 3,000 | from t = 1,200, each agent dies w.p. 4×10⁻⁴/tick; Poisson-matched joins |

### 2.4 Metrics

Measured per tick from the disruption onset (t = 0 for activation):

- **Sector loss:** number of sectors with zero declared copies. Run-level failure = any tick with any zero-coverage sector (`any_loss`). This is the primary safety metric.
- **Floor:** minimum per-sector coverage.
- **Exposure:** Σ over ticks of sectors below R (sector-ticks of under-replication) — a graded fragility measure.

### 2.5 Statistical treatment

312 seeds per scenario (seeds 100000…100311), 4 scenarios, 4 variants = 4,992 simulations. Run-level loss rates are reported with 95% upper confidence bounds: the rule of three (3/n) for zero observed failures, normal approximation otherwise. The sweep is resumable via per-cell checkpointing; the simulator is byte-deterministic across runs and interpreters (`check_determinism.py`; set-iteration order pinned).

## 3. Stage 1 — results

Pooled over all four scenarios (1,248 runs per variant):

| variant | runs with sector loss | loss rate | 95% upper bound | worst floor | mean exposure |
|---|---|---|---|---|---|
| V0 naive | 1,197 / 1,248 | 95.91% | < 97.01% | 0 | 250,879 |
| V1 damped | 300 / 1,248 | 24.04% | < 26.41% | 0 | 25,302 |
| V2 damped + jitter | 303 / 1,248 | 24.28% | < 26.66% | 0 | 25,032 |
| **V3 polite shrink** | **0 / 1,248** | **0.00%** | **< 0.24%** | **1** | **4,666** |

Per scenario (runs with loss / runs):

| scenario | V0 | V1 | V2 | V3 |
|---|---|---|---|---|
| activation | 312/312 | 96/312 | 112/312 | 0/312 |
| storm | 297/312 | 74/312 | 55/312 | 0/312 |
| flashcrowd | 281/312 | 29/312 | 33/312 | 0/312 |
| churn | 307/312 | 101/312 | 103/312 | 0/312 |

Observations:

1. **V0 reproduces the historical failure** — persistent oscillation and near-certain loss — validating the model against the 2021 experience.
2. **Hysteresis does most of the stabilising** (95.9% → 24.0%) but cannot close the shrink race: agents acting on stale views still occasionally abandon the same sectors simultaneously.
3. **Jitter provides no safety benefit** (V2 ≈ V1, 303 vs 300; per-scenario differences are noise-level in both directions). This is a useful negative result: desynchronising decision epochs is the standard first response to control-loop oscillation, and it does not address this failure mode — staggered unilateral shrinks erode coverage invisibly instead of collapsing it visibly.
4. **The two-phase handshake closes the race**: zero losses across all scenarios and seeds, never touching floor 0 (worst observed floor = 1), with ~5× lower under-replication exposure than the damped variants.

## 4. Stage 1c — adversarial falsification

### 4.1 Threat model and method

Multi-seed sweeps sample *random* disruptions; a controller may still have a small adversarially-reachable failure region. We therefore searched for one directly (`adversary.py`): the attacker has the storm scenario's budget — kill 60 of 200 agents (30%) — but freely chooses **which** agents die and **when**, across a 400-tick window opening at equilibrium (1,500 warm-up ticks; 700 ticks of post-attack observation). Schedules were optimised by an evolutionary search (population 16, 20 generations, elitism 4; fitness = sector-tick loss, then exposure), against each controller independently, with a 40-schedule random-search baseline. This is black-box adversarial falsification: learning-as-search over the disruption space.

### 4.2 Results

| variant | uniform storm loss | best random schedule | evolved attack | distinct sectors lost (evolved) |
|---|---|---|---|---|
| V1 damped | 391 | 0 | 5,994 | 134 |
| V2 damped + jitter | 0 | 128 | 2,938 | 23 |
| **V3 polite shrink** | **0** | **0** | **0** | **0** |

(Loss in sector-ticks: Σ over ticks of zero-coverage sectors.)

The search found and exploited qualitatively distinct weaknesses: against V1, concentrated simultaneous removal of a sector-neighbourhood's holders; against V2, a slow drip of targeted kills that rides the jittered epochs — independently rediscovering the erosion mechanism identified in Stage 1. Against V3 the search's best-of-generation loss stayed at zero for all 20 generations (a flat learning curve at the floor); the only quantity the adversary could degrade was transient exposure (7,559 → 27,872 sector-ticks), never coverage collapse. The best evolved anti-V3 schedule converged to a spatially and temporally spread pattern statistically similar to random — evidence that no concentrated strategy the search could represent does better.

## 5. Stage 2 — reference implementation in kitsune2

### 5.1 Approach

V3's decision rules were ported one-to-one into a `sharding` module inside kitsune2's gossip crate (`crates/gossip/src/sharding/`), behind the pre-existing `sharding` feature flag, with **no changes to `kitsune2_api`**. Design mapping and rationale: `kitsune2_port_design.md`. Key correspondences:

| sim concept | kitsune2 realisation |
|---|---|
| 512-sector ring | `SECTOR_SIZE = 2^23` — identical granularity (2^32 / 2^23 = 512) |
| declared arcs | `AgentInfoSigned.storage_arc` from the peer store |
| per-viewer lag | p90 of `now − last_gossip_timestamp(peer)` over responsive peers, clamped to configured bounds |
| intent announcement | `ShrinkIntent` protobuf on a new `"k2sharding"` transport module channel |
| death visibility | peers marked *unresponsive* are excluded from coverage |
| grow execution | existing verified-sync machinery (`storage_arc.rs`) raises the current arc toward the target hint; decisions gate on `cur_arc == block(target_level)` |
| tick / epoch | controller task interval; hysteresis accumulates wall-clock time against lag-scaled thresholds |

Configuration exposes the sim's constants (`target_redundancy`, `clamp_min_peers`, grow/shrink persistence factors 1.0/4.0, intent wait factor, lag clamps) via kitsune2's module-config system.

### 5.2 Verification

- **13 unit tests**, including deterministic regression tests for the tie-break semantics: the contested-range case (lowest id proceeds, higher id defers — the anti-livelock asymmetry), the rich-range case (concurrent shrinks are permitted when safe, i.e. the handshake does not serialise the network), partial-overlap blocking, and self-intent non-double-counting.
- **An 8-node functional storm test** on the in-memory transport (`tests/sharding_storm.rs`), with real gossip, real verified-sync growth, and real intent messages. Protocol: 8 nodes join and reach full arcs over seeded data → the network must shard down below 60% of full replication with **no sector ever losing its last declared holder** → reach a stable equilibrium (declared coverage unchanged for 6 s, longer than the maximum intent wait) → 3 of 8 nodes are killed simultaneously (victim set chosen on a single atomic snapshot such that survivors still cover every sector, preferring sets that push some sector below target so recovery must exercise growth) → after a 1 s death-detection grace window (see §6.1), no sector may be orphaned, no re-covered sector may be lost again, and coverage must return to the target everywhere. Result: 4/4 consecutive passes (8–29 polite shrinks per run; storm brake engaged 2–4 times per run; zero orphaned sectors including within the grace window).
- **Full battery:** gossip crate 70 tests (default features) and 86 tests (with `sharding`); top-level `kitsune2` crate 13 tests; core crate 99 tests; `clippy --deny warnings` clean in both feature states.

Commits: `ea8e45d` (transport fix, §6.3), `82a5896` (module + tests).

### 5.3 The falsification loop

The storm test initially failed three times; each failure was diagnosed to a distinct cause, and the fixes are part of the results (§6). We note this explicitly: the passing test suite was arrived at by eliminating identified defects, not by weakening assertions — with one principled exception (the death-detection grace window, §6.1), whose scope is precisely characterised and asserted around.

## 6. Findings from the port (not observable in simulation)

### 6.1 Death visibility and view staleness are independent clocks

In the simulation, one parameter (lag) bounds both how stale an agent's view is and how quickly a death becomes visible; waiting `intent_delay > 2×lag_max` therefore *structurally* guarantees a shrink re-check sees any death older than one lag. In kitsune2 this decomposes: view staleness is peer-store propagation, while death visibility is *unresponsive marking* — driven by gossip initiate cadence and connection behaviour. A shrink intent announced before a die-off can execute just after it while the dead peers are still counted (observed experimentally: 128 sectors orphaned by one such execute).

Mitigation implemented: a **storm brake** — whenever any peer newly becomes invisible, all pending shrink intents on the node are cancelled and their dwell counters reset. A residual window remains for deaths younger than the detection latency at execute time; no locally-decided rule can close it, only bound it. Design implication for #160: the shrink wait must be configured to dominate *death-detection latency*, not merely gossip staleness. We also note the failure is one of *declared* coverage: the shrinking node still holds the op data on disk, so prompt re-grow recovers without data loss provided garbage collection is deferred accordingly.

### 6.2 The small-network clamp is a safety parameter, not a tuning knob

Quantised growth is sibling-half-local: an agent can only grow into the adjacent half of its parent block, so growth cannot be *steered* toward a distant under-covered region. In dense networks a cascade always reaches the hole; in sparse ones (observed: 5 survivors, one region at coverage 1 in nobody's sibling half) recovery deadlocks. The simulation masked this with 200-agent density and its clamp default of 25. Consequently `clamp_min_peers` must exceed the population below which sharding is worth having at all — it is *the* designed recovery path for the catastrophic regime. A global under-coverage repair rule (grow anywhere the ring is thin) would remove the dependency but introduces dynamics the sweep never validated; we flag it for Stage-3 simulation before implementation.

### 6.3 The in-memory transport violated the unresponsive-marking contract

`TxImpHnd::set_unresponsive` documents that transports must mark peers on connection/send failure; the production (iroh) transport complies, but the in-memory transport used by kitsune2's own test suites returned errors without marking. Any failure-mode test on that transport was blind to node deaths (observed: post-storm, ghost coverage kept controllers shrinking to level 4 and orphaning re-covered sectors). Fixed in commit `ea8e45d` as a standalone change; no regressions across 99 core tests.

Two further implementation notes are recorded as deltas 1–9 in `kitsune2_port_design.md`, including the model/reality sync gate (a freshly joined agent must never "shrink" from a level it does not actually hold — that would claim authority over unsynced data) and intent-expiry grace semantics.

## 7. Limitations and threats to validity

**Simulation fidelity.** The model assumes full peer visibility (every agent eventually sees every declaration), a single staleness per viewer rather than per pair, honest agents, sync time linear in sectors, and no network partitions or asymmetric reachability. It tests control-loop *dynamics*, not transport behaviour. §6 demonstrates concretely that such idealisations hide real constraints; there may be others.

**Statistical claim scope.** "0/1,248, UB < 0.24%" applies to the *decision rules under the simulated conditions* (N = 200, R = 5, the four scenario families, the stated lag distribution). It does not transfer as a number to other parameter regimes or to the implementation. *(The core safety property behind this number — a sector never dropping below R under concurrent shrinks — is since proven directly, not merely sampled: exhaustive model checking over every reachable state, no violation, for N ≤ 8 (R from 1 to 7), REPORT_stage3.md §9.)*

**Adversarial search scope.** The evolutionary search covers kill schedules within a fixed budget/window; it does not model Byzantine agents (lying declarations, forged intents), message suppression, or eclipse attacks. Intent messages in the PoC are unauthenticated; production use requires signing them (the codebase has the machinery). *(Since addressed in part: receiver-side range-validation of intents is implemented and measured — REPORT_stage3.md §6; Byzantine agents are simulated in REPORT_stage3.md §2.)*

**Implementation validation scope.** The functional test uses 8 in-process nodes, R = 2, accelerated timing, and the (patched) in-memory transport — it validates mechanism wiring end-to-end, not production-scale behaviour, and is timing-based (flake risk on heavily loaded machines; 4/4 locally). The PoC broadcasts intents to all known peers (production would target holders of the vacated range), assumes one local agent per node in its testing (multi-agent paths implemented but lightly exercised), and does not persist controller state across restarts.

**Residual race (§6.1).** Deaths within the detection window of a shrink execute remain locally undecidable. The declared-coverage hole is transient and recoverable while op data is retained; quantifying its probability under realistic parameters (R = 5, production gossip cadences) is open work.

## 8. Artifact inventory and reproduction

| artifact | location |
|---|---|
| simulator, scenarios, variants | `polite_shrink.py` |
| multi-seed sweep driver (checkpointed) | `sweep.py`, `run_sweep_until_done.sh` |
| adversarial search | `adversary.py` |
| determinism check / seed audit | `check_determinism.py`, `check_seeds.py` |
| sweep results (1,248 cells) | `results/sweep.json`, `results/sweep_cells.jsonl`, `results/sweep_summary.md`, `results/sweep.png` |
| adversary results | `results/adversary.json`, `results/adversary.log`, `results/adversary.png` |
| scenario plots, single-seed summary | `results/*.png`, `results/summary.md` |
| port design mapping + deltas 1–9 | `kitsune2_port_design.md` |
| reference implementation | fork branch `feat/sharding-module-v3`, commits `ea8e45d`, `82a5896` |
| reproduction instructions (pinned deps, expected numbers) | `REPRODUCE.md`, `run_all.sh` |

The simulator is byte-deterministic (numpy 2.5.1, matplotlib 3.11.0, Python 3.12.1); `REPRODUCE.md` lists the expected output values. Sweep runtime ≈ 2.5 h on 2 cores; adversary ≈ 15 min; the kitsune2 storm test ≈ 20–60 s per run (`cargo test -p kitsune2_gossip --features sharding --test sharding_storm`).

## 9. Provenance

Study conducted 2026-07-11/12 within the ValiChord project. Design directed and reviewed by Ceri John; simulation, implementation, and analysis executed with AI assistance (Claude, Anthropic); the two-phase shrink's conflict-resolution scheme was motivated by TCAS's coordinated complementary resolution advisories (deterministic asymmetric conflict resolution), suggested by C. John. All results reported here were produced by the committed code and are reproducible from the artifacts above.
