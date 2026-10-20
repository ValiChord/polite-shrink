# Polite-Shrink: The Core Idea

*A one-page on-ramp for the Holochain dev team. Depth is in [README.md](README.md); this is just the idea.*

## In a sentence or two

When a DHT node wants to shrink its storage arc from a stale gossip view, it should **announce an intent to vacate, wait out the staleness, then re-check and drop only if the redundancy target R would still be met — after treating every node that announced a vacate as already gone**, instead of dropping immediately. **When the margin is thin, the lowest ID among the announcers waits instead of giving up, and the others get out of its way.**

That last clause is the load-bearing part. Announce-and-re-check *while everyone still counts each other as present* does **not** close the race: two nodes each removing only themselves both conclude "R will remain" and both drop, and coverage falls below R — the exact 2021 failure.

What closes it is that **a node about to vacate must stop counting toward the redundancy of the nodes it is racing** — and must never rely on a racer who might itself be leaving. October 2026 work tested three ways of arranging that:

| rule | what the re-check does | never loses data to a shrink | always makes progress |
|---|---|---|---|
| V3 — the original TCAS-style tie-break | counts only *lower-ID* announcers as gone | ✗ — it relies on higher-ID announcers staying, and a *staggered cascade* or one ordinary death walks through that gap | ✓ |
| V5 — the AgentInfo encoding | counts *every* announcer as gone | ✓ proven for any number of nodes | ✗ — identical nodes can cancel each other forever |
| **V6 — "patient lowest" (recommended)** | counts every announcer as gone; if that fails only because of higher-ID announcers, the lowest **waits** instead of cancelling, and nobody announces while a lower ID is racing them | **✓ — V5's proof applies unchanged** | **✓** |

V6 keeps the TCAS ordering, but only for deciding **who goes next** when the margin is thin — never for assuming **who stays**. At 200 nodes its arcs stay close to V3's, with about a third of the sync traffic and several times less time below R ([results/v6_summary.md](results/v6_summary.md)). One cost: like V3, it must *see* who is announcing, so it needs a dedicated message or one explicit bit on `AgentInfo` — a narrowed arc claim alone cannot tell an announcer from a node that has already left.

The original TLA+ proof could not tell any of these apart: it gave every node a perfectly fresh view, under which even a bare re-check is safe. The stale-view checks, the cascade, the proof and the five candidate hybrids tried on the way to V6 are in [REPORT_stale_views.md](REPORT_stale_views.md).

## The problem it addresses

In Holochain's 2021 sharding tests, nodes resized arcs by reacting to each other's *slightly stale* views of who was covering what. Everyone reacting to the same stale picture produced oscillation — the ["hallway dance"](https://blog.holochain.org/testing-sharding/) (Dev Pulse 107). Dynamic sharding has been off by default ever since. Kitsune2 carries the machinery behind an off-by-default `sharding` flag, but arcs are still clamped (typically to full) because the safe-sizing controller — [kitsune2 #160](https://github.com/holochain/kitsune2/issues/160) — hasn't been built.

## The one surprising finding: it was never the oscillation

The 2021 loss looked like an oscillation problem, so the instinct is to damp the oscillation. The whole study exists to test that instinct — and it is wrong. **The true cause of the data loss is a distinct shrink race**, which the oscillation merely accompanies: two nodes, each acting on a stale view, abandon the same sector at the same instant. Damping never touches it.

The evidence, in order:

- Lag-scaled **hysteresis** ("grow eager, shrink slow") cuts the data-loss rate from **95.9% of runs to 24%** — a big dent, but the loss doesn't go away.
- **Jitter** (the textbook first remedy for control-loop oscillation) adds **nothing** — 24.3%.
- The remaining 24% is the **shrink race**, and it survives every damping fix. Only the pre-drop re-check (the gate — V3's version at the time) closes it — and then loss goes to **zero across 1,248 runs**.

The consequence for a rebuilt controller is the useful part: it may well still oscillate — that may be inherent, a matter of physics — but **oscillation and durability turn out to be separable.** Leave the physics alone; close the race, and you don't lose data even while it dances.

## The insight that made it work: break the symmetry by *rule* (TCAS)

The hallway dance is a **symmetry** problem: every node reacts identically to the same stale coverage picture, so they all step the same way at once. The two failed attempts to fix it both try to break that symmetry the wrong way — hysteresis slows everyone down equally, jitter (V2) desynchronises by *timing*, i.e. by luck. Neither works.

The fix comes from **aircraft collision avoidance (TCAS)**. When two planes converge, TCAS does not let them negotiate or rely on timing — it issues *complementary, deterministic* orders (one climbs, one descends) chosen by a fixed tie-break on transponder ID. It exists precisely because symmetric reactions are the failure mode: two people in a corridor both stepping aside the same way, again and again.

Polite-shrink applies that cure to shrinking: when nodes contend to vacate the same sector and the margin is thin, **the lowest ID goes and the rest get out of its way** — symmetry broken by *rule*, not by timing or luck. That is the difference between V2 (jitter, still loses data) and the polite variants.

**What October 2026 changed about this insight.** The original V3 applied TCAS halfway: the higher-ID node subtracted the lower one *and still went ahead*, while the lower one counted the higher one as staying — both "partly climbed". In a staggered cascade every node counts a higher-ID announcer as its survivor just as that one leaves. V6 applies TCAS properly: complementary orders, one side acts and the other gets out of the way completely. The TCAS idea was right; the first implementation of it was not.

## The mechanism (≈30 lines)

Two phases, in [`polite_shrink.py`](polite_shrink.py):

1. **Announce**, don't drop. A node that wants to shrink publishes a *vacate intent* for those sectors — unless it can see a lower ID already racing it for them, in which case it waits.
2. **Wait, re-check, then act.** After waiting out gossip staleness, it re-reads holders and intents, counts **every** announced rival as already gone, and drops **only if ≥ R copies remain**.
3. **If the re-check fails only because of higher-ID rivals**, the node is the lowest racer: it keeps its announcement up and re-checks next tick instead of cancelling. The higher IDs fail their own re-checks, stand down, and stay quiet while it waits — so it gets through.

This is the `V6` variant. The code also keeps V0–V5 so every earlier study can still be reproduced.

Across the honest-node tests — a 1,248-run sweep, an evolutionary adversary, partitions, scale to 5,000 agents, 90%-lossy gossip, and 33% of the network killed at once on real iroh transport — **no run in the designed scenarios lost data** (coverage dips below R during deaths; what the gate aims at is that no *shrink* takes it there). Data is lost under slow death detection in heavy storms, and by nodes that lie — both characterised below.

## What is proven vs. what is evidence

Stated plainly, because the distinction matters:

- **Checked exhaustively, with stale views** ([REPORT_stale_views.md](REPORT_stale_views.md); every announce schedule, per-node lag and death time, N ≤ 5): a bare re-check fails in every configuration; V3 fails a staggered cascade (R = 1) and one-death schedules (R = 2); V5 is safe but can stall forever; **V6 is safe in all of them at a 1× wait and always makes progress.**
- **Proven for any N:** the V5/V6 safety rule under stale views, given prompt death detection (proof in [REPORT_stale_views.md](REPORT_stale_views.md) §4 — V6's waiting never counts an announcer as present, so the proof applies unchanged). Progress for V6 is checked exhaustively for N ≤ 5 and argued, not proven, beyond that. Also proven: *guessing* which un-declared peers have really left fails on one wrong guess (`spec/AgentInfoAgeGated.tla`).
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

- **The mechanism, simulated and model-checked:** [`polite_shrink.py`](polite_shrink.py) (`V6`) + [`spec/`](spec/) + [REPORT_stale_views.md](REPORT_stale_views.md).
- **The mechanism, deployable — and the one to test:** V6 as a Rust module on the kitsune2 fork, branch [`feat/sharding-v6`](https://github.com/topeuph-ai/kitsune2/tree/feat/sharding-v6/crates/gossip/src/sharding), behind the existing `sharding` flag. V6 is the default there; `patient_lowest: false` gives V3 for comparison.
- **Everything it was tested against:** [TEST_LEDGER.md](TEST_LEDGER.md).

*Research directed by Ceri John; design, implementation, and analysis with AI assistance (Claude, Anthropic); all results human-reviewed.*
