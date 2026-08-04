# Conductor-level polite-shrink scenario — design

**Status: DESIGN ONLY. Nothing built, nothing run, no result claimed.**
Written 2026-08-04, after the fork was confirmed to compile into a Holochain 0.7.0 conductor
(`wind-tunnel-patch/README.md`) and the node ceiling was measured at 25+ on this box.

---

## 1. The question, and the claim boundary

**Question:** running inside real Holochain conductors, does the polite-shrink controller hold the
redundancy floor while arcs actually shrink?

Every prior polite-shrink result is the simulator, the TLA+ proof, or the kitsune2-level Wind Tunnel
campaign. None of them is a Holochain conductor. This scenario is the first that could be.

**What it could support:**

- ✅ *"In an N-node Holochain network on Holochain 0.7.0, declared arc coverage never fell below R
  at any observed tick, while mean declared arc size fell from X to Y."*
- ✅ *"Under the stock conductor the same run holds every arc full, so the reduction is attributable
  to the controller."*

**What it could NOT support, and must never be dressed up as:**

- ❌ **Any throughput or latency claim.** The ceiling test measured peak load **93.8 on 8 cores** at
  25 agents. Timing numbers from this box measure the box. This is the same error
  wind-tunnel#679 §2 documents and that `PLAN_0.7_conductor_run.md` §7.10 retracted — repeating it
  after publicly filing the issue would be indefensible.
- ❌ **"Data was never lost."** Declared arc coverage is not proof of stored data. See §4.2.
- ❌ Anything about networks larger than N, or about churn patterns not exercised.

---

## 2. 🔴 The failure mode that makes a pass worthless

**A run with no violations is only meaningful if arcs actually shrank.**

If the controller never engages — clamp fires, feature silently off, arcs pinned — then
`min_arc_coverage` sits at N forever, no violation is recorded, and the run *looks like a pass*.
It would be the same class of result as the fake tests in ValiChord's `CLAUDE.md`: green because the
thing under test was never reached.

**Therefore the scenario has two independent pass conditions, and BOTH are required:**

| # | condition | metric |
|---|---|---|
| 1 | The controller engaged — arcs measurably shrank | `mean_declared_arc_size` falls materially below full |
| 2 | The floor held — coverage never dropped below R | `min_arc_coverage >= R` at every tick |

Condition 1 is the negative control, and it is not optional. **Report both or report nothing.**

---

## 3. Topology and configuration

| parameter | value | why |
|---|---|---|
| agents | **30**, not 25 | `visible_peers = live remote peers + local_agents.len()`; one conductor per agent makes that **N**. The clamp fires below 25, so N=25 is exactly on the edge — a single undiscovered or tombstoned peer drops it under and the controller **grows** instead of shrinking. 30 gives 5 peers of slack. |
| arcs | **left dynamic** | Never call `with_target_arc_factor`. This is the whole point: every upstream arc scenario pins the variable the controller computes. |
| writes | **throttled** (`WRITE_SLEEP_MS`) | 30 conductors unthrottled would sit far past load 93.8. The throttle written for wind-tunnel#679 is what makes this run viable here. |
| duration | **long — start at 1800 s** | 120 s was enough for a ceiling test. Arc convergence plus shrink decisions need far longer, and the shape of the arc-size curve over time is itself the evidence for condition 1. |
| behaviours | writers, readers, and one **observer** per conductor | The observer does the measuring; see §4. |
| space | **new DNA ⇒ new space** | Space ID derives from the DNA hash, so a new scenario zome is effectively a private space. This matters more than usual: foreign agents joining would inject their arcs into our coverage measurement. |

**Arms:** `holochain-stock` and `holochain-polite-shrink`, switched with `wind-tunnel-patch/arm.sh`,
which asserts its canary each way (`K2Sharding` = 0 stock, 62 shrink).

---

## 4. The measurement

### 4.1 Declared arc coverage — exact, not sampled

The four pieces are all confirmed present:

| piece | location |
|---|---|
| `AgentInfo.storage_arc: DhtArc` — public field on the **gossiped** struct | `kitsune2/crates/api/src/agent.rs:175` |
| `DhtArc::contains(loc: u32) -> bool` | `kitsune2/crates/api/src/arc.rs:108` |
| `HoloHash::get_loc() -> u32` | `holochain/crates/holo_hash/src/hash.rs:144` |
| `AdminRequest::AgentInfo`, reachable via `ctx.get().admin_ws_url()` | `admin_interface.rs:360`; `bindings/runner/src/common.rs` |

🆕 **Do not sample op locations — compute the exact minimum over the whole ring.** The invariant is a
property of the *location space*, not of any particular op. Arcs are intervals on a `u32` ring, so a
sweep over the 2N interval endpoints gives the **exact** minimum coverage in O(N log N) — trivial at
N=30. Sampling ops would be weaker, need the writers' hashes distributed to the observer, and add
DHT load that perturbs the thing being measured.

`get_loc()` remains useful for §4.2, where specific ops do matter.

### 4.2 Declared vs actually stored — the part the simulator cannot do

A node can announce coverage it has not finished syncing. Declared-vs-actual is **precisely where a
shrink controller could be wrong**, and it is unavailable in the simulator, which has no real storage.

`AdminRequest::DumpFullState` gives ground truth per conductor; 0.7 added paginated state dumps,
which makes it tractable. Expensive, so: sample it at a low rate, not every tick.

⚠️ Treat this as a **second, separate finding**, not as part of the floor claim. Conflating them
would let a storage-lag result contaminate a coverage result, or vice versa.

### 4.3 Gossip staleness — a real limit, and itself a result

`AgentInfo` is gossiped, so each conductor's view of peer arcs is eventually consistent and can be
stale. The simulator has a global oracle; a live network does not. A measured dip may be a genuine
violation or one conductor's stale view.

**Mitigation:** every conductor measures independently and reports its own view. Then:

- a dip in **one** view, absent from others at the same tick → likely staleness, and the *spread
  between views* is a publishable quantification of it;
- a dip in **all** views → a genuine violation.

This is the same phenomenon the Stage-2 campaign already exercised, where the brake cancelled nine
stale-view intents. Measuring the spread turns a caveat into data.

---

## 5. Metrics

| metric | tags | supports | does NOT support |
|---|---|---|---|
| `min_arc_coverage` | `observer` | **The floor claim.** Exact min over the ring, per observer view. | Anything about stored data. |
| `mean_declared_arc_size` | `observer` | **Condition 1** — that the controller engaged at all. | That the shrink was *safe*; that is `min_arc_coverage`. |
| `declared_arc_size` | `agent` | Per-agent shrink trajectories; fairness between agents. | — |
| `arc_coverage_p5 / p50` | `observer` | Shape of coverage, not just its worst point. | — |
| `visible_peers` | `agent` | 🔴 **Guard.** If this dips below 25 the clamp fired and the controller was *growing*. Without it, a clamped run is indistinguishable from a stable one. | — |
| `coverage_view_spread` | — | §4.3 staleness quantification. | — |
| `stored_vs_declared` | `agent` | §4.2, sampled rarely. | The floor claim. |

---

## 6. What would falsify it

Stated up front so the result cannot be reverse-engineered into a pass:

- `min_arc_coverage < R` in **all** observer views at the same tick → the floor was breached. That is
  a real negative result about polite-shrink and must be published as one.
- `mean_declared_arc_size` never falls → the controller did not engage; the run proves nothing and
  must **not** be reported as "no violations found".
- `visible_peers < 25` for sustained periods → the clamp was active; same as above.
- Stock arm shows arcs shrinking → something other than the controller is moving arcs, and the whole
  attribution collapses.

---

## 7. Open items before writing code

1. **Is `clamp_min_peers` settable from conductor config?** `K2ShardingModConfig` registers via
   kitsune2's `set_module_config`, the same mechanism as `advanced: { irohTransport: … }`. If so,
   N could drop and runs get cheaper — but lowering the clamp tests the regime the module's own docs
   exclude, so it is for **debugging only, never for the headline run**. ⚠️ Unverified.
2. **What is R?** The floor is a config value. The run must record the R it was given; a floor claim
   without its R is meaningless.
3. **Does 30 conductors fit?** Ceiling was measured at 25 (load 93.8, 7.9 GB). 30 is ~9.5 GB — memory
   is fine, CPU is the question, and the write throttle is the lever.
4. **Does the observer perturb the measurement?** It polls the admin API, not the DHT, so it should
   not — but confirm rather than assume.
5. **How long until arcs converge?** Unknown at conductor level. A pilot run at N=30 with only the
   arc-size metric would answer it cheaply, before building the full measurement.

**Suggested first build: item 5.** A minimal scenario that does nothing but log declared arc sizes
over 30 minutes at N=30. It answers "does the controller engage under a real conductor, and on what
timescale" — the single fact everything else depends on — and it is a fraction of the work.
