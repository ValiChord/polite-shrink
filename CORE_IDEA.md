# Polite-Shrink: The Core Idea

*A one-page on-ramp for the Holochain dev team. Depth is in [README.md](README.md); this is just the idea.*

## In a sentence or two

When a DHT node wants to shrink its storage arc from a stale gossip view, it should **announce an intent to vacate, wait out the staleness, then re-check and drop only if the redundancy target R would still be met — after treating every node that announced a vacate as already gone**, instead of dropping immediately.

That last clause is the load-bearing part. Announce-and-re-check *while everyone still counts each other as present* does **not** close the race: two nodes each removing only themselves both conclude "R will remain" and both drop, and coverage falls below R — the exact 2021 failure.

What closes it is that **a node about to vacate must stop counting toward the redundancy of the nodes it is racing.** There are two ways to arrange that, and October 2026 work separated them:

- **Discount every announcer** (V5). This falls out of carrying the announcement on the arc claim that is already gossiped — announcing *is* removing yourself from everyone's count. Checked with real stale views it is **safe for any number of nodes**, with a short proof, as long as deaths are noticed before anyone acts on a view still counting them.
- **Discount only lower-ID announcers** (V3, the original TCAS-style tie-break). It applies the principle only halfway: higher-ID announcers still count for lower-ID ones. That is enough for small networks with a wait over twice the lag, but a *staggered cascade* of announcers, or one death plus staggered announcements, walks through the gap.

The original TLA+ proof could not tell these apart: it gave every node a perfectly fresh view, under which even a bare re-check is safe. The stale-view check, the cascade and the proof are in [REPORT_stale_views.md](REPORT_stale_views.md); the costs of each encoding are in [REPORT_agentinfo_encoding.md](REPORT_agentinfo_encoding.md).

## The problem it addresses

In Holochain's 2021 sharding tests, nodes resized arcs by reacting to each other's *slightly stale* views of who was covering what. Everyone reacting to the same stale picture produced oscillation — the ["hallway dance"](https://blog.holochain.org/testing-sharding/) (Dev Pulse 107). Dynamic sharding has been off by default ever since. Kitsune2 carries the machinery behind an off-by-default `sharding` flag, but arcs are still clamped (typically to full) because the safe-sizing controller — [kitsune2 #160](https://github.com/holochain/kitsune2/issues/160) — hasn't been built.

## The one surprising finding: it was never the oscillation

The 2021 loss looked like an oscillation problem, so the instinct is to damp the oscillation. The whole study exists to test that instinct — and it is wrong. **The true cause of the data loss is a distinct shrink race**, which the oscillation merely accompanies: two nodes, each acting on a stale view, abandon the same sector at the same instant. Damping never touches it.

The evidence, in order:

- Lag-scaled **hysteresis** ("grow eager, shrink slow") cuts the data-loss rate from **95.9% of runs to 24%** — a big dent, but the loss doesn't go away.
- **Jitter** (the textbook first remedy for control-loop oscillation) adds **nothing** — 24.3%.
- The remaining 24% is the **shrink race**, and it survives every damping fix. Only the pre-drop re-check *with its tie-break* (the gate) closes it — and then loss goes to **zero across 1,248 runs**.

The consequence for a rebuilt controller is the useful part: it may well still oscillate — that may be inherent, a matter of physics — but **oscillation and durability turn out to be separable.** Leave the physics alone; close the race, and you don't lose data even while it dances.

## The insight that made it work: break the symmetry by *rule* (TCAS)

The hallway dance is a **symmetry** problem: every node reacts identically to the same stale coverage picture, so they all step the same way at once. The two failed attempts to fix it both try to break that symmetry the wrong way — hysteresis slows everyone down equally, jitter (V2) desynchronises by *timing*, i.e. by luck. Neither works.

The fix comes from **aircraft collision avoidance (TCAS)**. When two planes converge, TCAS does not let them negotiate or rely on timing — it issues *complementary, deterministic* orders (one climbs, one descends) chosen by a fixed tie-break on transponder ID. It exists precisely because symmetric reactions are the failure mode: two people in a corridor both stepping aside the same way, again and again.

Polite-shrink applies exactly that cure to shrinking: when nodes contend to vacate the same sector, **the lowest ID proceeds and the rest defer** — symmetry broken by *rule*, not by timing or luck. That is the difference between V2 (jitter, still loses data) and V3 (polite, loses none).

## The mechanism (≈30 lines)

Two phases, in [`polite_shrink.py`](polite_shrink.py):

1. **Announce**, don't drop. A node that wants to shrink publishes a *vacate intent* for those sectors.
2. **Wait, re-check, then act.** After waiting out gossip staleness, it re-reads holders and intents, counts announced intenders as already gone, and drops **only if ≥ R copies remain**. The code's V3 counts only *lower-ID* intenders (the TCAS tie-break); V5 counts all of them, which is the version that survives stale views in general.

Across the honest-node tests — a 1,248-run sweep, an evolutionary adversary, partitions, scale to 5,000 agents, 90%-lossy gossip, and 33% of the network killed at once on real iroh transport — **no run in the designed scenarios lost data** (coverage dips below R during deaths; what the gate aims at is that no *shrink* takes it there). Data is lost under slow death detection in heavy storms, and by nodes that lie — both characterised below.

## What is proven vs. what is evidence

Stated plainly, because the distinction matters:

- **Checked exhaustively, with stale views** ([REPORT_stale_views.md](REPORT_stale_views.md); every announce schedule and per-node lag, N ≤ 5): a bare re-check fails in every configuration; the ID tie-break (V3) is safe for small networks with a wait over twice the lag but fails a staggered cascade (R = 1) and one-death schedules (R = 2); discounting every announcer (V5) is safe in all of them at a 1× wait.
- **Proven for any N:** V5 under stale views, given prompt death detection (proof in [REPORT_stale_views.md](REPORT_stale_views.md) §4). Also proven: *guessing* which un-declared peers have really left fails on one wrong guess (`spec/AgentInfoAgeGated.tla`).
- **What the original TLA+ proof shows** (five configurations, N = 6–8): re-checking against a perfectly fresh view is safe — true, but close to trivial, and it does not exercise the tie-break.
- **Engineering judgement, evidenced by simulation** (not proven): the surrounding **policy** — what R should be, hysteresis constants, the growth rule, the small-network clamp. The repo deliberately does **not** propose the policy; it establishes the [constraints any policy must respect](README.md#for-a-maintainer-what-any-policy-must-respect).
- **Known gap:** nodes that *lie* about what they store are a sensor problem no controller can out-think. Past K = R false declarations, data is lost invisibly; a proof-gated "verified coverage" extension removes that ceiling **in simulation** but isn't deployed yet.

## The one lever outside the gate: how fast deaths are noticed

The V5 gate is proven safe provided a death is noticed before anyone acts on a view that still counts the dead node — and pinning that down turned up the only other thing a policy author has to get right. The three points below are simulation-evidenced, not proven:

- **Size the wait against death-detection latency, not gossip staleness.** They are independent clocks on a real transport (kitsune2's *unresponsive marking* vs peer-store propagation). Detection faster than gossip drives the residual race to zero; slower leaves a residual, and a node cannot *infer* its way out of it from its own observation history (measured, not proven, and only in one dimension of observable space) — though it can be *offset*, which is the next point.
- **Decide which way the detector should be wrong, and cap it.** Convicting a live peer costs storage; missing a dead one costs data. Erring toward conviction takes `P(any loss)` from **36% to 2.7%** at a false-conviction rate near 0.10 — then *worsens* again (15% at 0.40), replicated on fresh seeds with non-overlapping intervals. Nodes at 0.40 hold more data and still lose more, so this is not plain caution; the mechanism is open. Getting one global threshold roughly right is a 38-point effect; tuning it per peer adds ≤4 and is not distinguishable from noise, so a self-calibrating detector is not where the first effort goes.
- **A spread of detection speeds is protective, not hazardous.** Replicated on fresh seeds: a uniformly slow network loses data in 35% of runs, a 50/50 mix with twice-as-fast nodes in 18% — close to an all-fast network's 15%. A mixed network tracks its *faster* half — so homogenising node behaviour can remove a margin nobody knew was there. (The same trap as flattening the arc distribution, which is also load-bearing.)

Detail: [REPORT_mz_decomposition.md](REPORT_mz_decomposition.md), [RELATED_WORK.md](RELATED_WORK.md) §5, and constraint 6b in [REPORT_stage3.md](REPORT_stage3.md).

## Related fields

Sensor networks met this exact race twenty years ago ("blind points" when neighbours switch off together) and used wait-and-re-check heuristics that left holes; the race is the classical **k-exclusion** problem with k = holders − R; and the oscillation is the subject of decentralised delay-stability theory from congestion control. What each connection is worth, and the experiments it prompted: [RELATED_WORK.md](RELATED_WORK.md).

## Relation to the Kitsune2 Github repository issue #160

#160 asks for a **policy** (recommend a target arc for a redundancy level). The cost-optimal target is nearly trivial (`R/N` of the ring); every hard part is elsewhere — measuring N under stale/dishonest views, reaching the target without a race, not oscillating on the way, and (per the section above) how fast the network notices a death. Polite-shrink is the **safety gate** that makes any such policy safe to run, plus the constraint list for whoever writes the policy.

**What it would cost kitsune2 to adopt.** No new wire message: the vacate announcement can ride on the `AgentInfo` arc claim that is already gossiped and already signed. It does need one bit that claim cannot carry — whether a narrowed arc means *"intending to leave"* or *"already gone"* — and that bit cannot be inferred from the claim's age. So it is either one field on an existing struct, or the ID tie-break on a dedicated signal. `update_storage_arcs` already moves the stored arc toward a target hint; what is missing is the rule that sets the hint, and the shrink direction that `storage_arc.rs` currently leaves to "the host implementation or some sharding logic".

## Where to look next

- **The mechanism, proven:** [`polite_shrink.py`](polite_shrink.py) + [`spec/`](spec/) (TLA+).
- **The mechanism, deployable:** Rust module on a [kitsune2 fork](https://github.com/topeuph-ai/kitsune2/tree/feat/sharding-module-v3/crates/gossip/src/sharding), behind the existing `sharding` flag.
- **Everything it was tested against:** [TEST_LEDGER.md](TEST_LEDGER.md).

*Research directed by Ceri John; design, implementation, and analysis with AI assistance (Claude, Anthropic); all results human-reviewed.*
