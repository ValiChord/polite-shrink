# Polite-Shrink: The Core Idea

*A one-page on-ramp for the Holochain dev team. Depth is in [README.md](README.md); this is just the idea.*

## In a sentence or two

When a DHT node wants to shrink its storage arc from a stale gossip view, it should **announce an intent to vacate, wait out the staleness, then re-check and drop only if the redundancy target R would still be met — after treating every *lower-ID* node that announced the same vacate as already gone** (a deterministic tie-break), instead of dropping immediately.

That last clause is the load-bearing part. Announce-and-re-check *without* the tie-break does **not** close the race: two nodes each removing only themselves both conclude "R will remain" and both drop, and coverage falls below R — the exact 2021 failure. Ordering the contenders by ID so that exactly one proceeds and the rest defer is what actually closes the race that caused the 2021 data loss.

## The problem it addresses

In Holochain's 2021 sharding tests, nodes resized arcs by reacting to each other's *slightly stale* views of who was covering what. Everyone reacting to the same stale picture produced oscillation — the ["hallway dance"](https://blog.holochain.org/testing-sharding/) (Dev Pulse 107). Dynamic sharding has been off by default ever since. Kitsune2 carries the machinery behind an off-by-default `sharding` flag, but arcs are still clamped (typically to full) because the safe-sizing controller — [kitsune2 #160](https://github.com/holochain/kitsune2/issues/160) — hasn't been built.

## The one surprising finding: it was never the oscillation

The 2021 loss looked like an oscillation problem, so the instinct is to damp the oscillation. The whole study exists to test that instinct — and it is wrong. **The true cause of the data loss is a distinct shrink race**, which the oscillation merely accompanies: two nodes, each acting on a stale view, abandon the same sector at the same instant. Damping never touches it.

The evidence, in order:

- Lag-scaled **hysteresis** ("grow eager, shrink slow") cuts the data-loss rate from **95.9% of runs to 24%** — a big dent, but the loss doesn't go away.
- **Jitter** (the textbook first remedy for control-loop oscillation) adds **nothing** — 24.3%.
- The remaining 24% is the **shrink race**, and it survives every damping fix. Only re-checking before the drop (the gate) closes it — and then loss goes to **zero across 1,248 runs**.

The consequence for a rebuilt controller is the useful part: it may well still oscillate — that may be inherent, a matter of physics — but **oscillation and durability turn out to be separable.** Leave the physics alone; close the race, and you don't lose data even while it dances.

## The insight that made it work: break the symmetry by *rule* (TCAS)

The hallway dance is a **symmetry** problem: every node reacts identically to the same stale coverage picture, so they all step the same way at once. The two failed attempts to fix it both try to break that symmetry the wrong way — hysteresis slows everyone down equally, jitter (V2) desynchronises by *timing*, i.e. by luck. Neither works.

The fix comes from **aircraft collision avoidance (TCAS)**. When two planes converge, TCAS does not let them negotiate or rely on timing — it issues *complementary, deterministic* orders (one climbs, one descends) chosen by a fixed tie-break on transponder ID. It exists precisely because symmetric reactions are the failure mode: two people in a corridor both stepping aside the same way, again and again.

Polite-shrink applies exactly that cure to shrinking: when nodes contend to vacate the same sector, **the lowest ID proceeds and the rest defer** — symmetry broken by *rule*, not by timing or luck. That is the difference between V2 (jitter, still loses data) and V3 (polite, loses none).

## The mechanism (≈30 lines)

Two phases, in [`polite_shrink.py`](polite_shrink.py):

1. **Announce**, don't drop. A node that wants to shrink publishes a *vacate intent* for those sectors.
2. **Wait, re-check, then act.** After waiting out gossip staleness, it re-reads holders and intents, applies the **TCAS tie-break** — count every lower-priority (higher-ID) intender as already gone — and drops **only if ≥ R copies remain**.

Across the honest-node tests — a 1,248-run sweep, an evolutionary adversary, partitions, scale to 5,000 agents, 90%-lossy gossip, and 33% of the network killed at once on real iroh transport — **not one sector ever dropped below R**.

## What is proven vs. what is evidence

Stated plainly, because the distinction matters:

- **Proven** (TLA+/TLC, exhaustive over every reachable state, N ≤ 8, R = 1–7): the **gate** — the pre-drop re-check *with its tie-break* — means concurrent stale-view shrinks *cannot* drive a sector below R. The naive rule (no wait, no tie-break) fails the same check with a counterexample.
- **Engineering judgement, evidenced by simulation** (not proven): the surrounding **policy** — what R should be, hysteresis constants, the growth rule, the small-network clamp. The repo deliberately does **not** propose the policy; it establishes the [constraints any policy must respect](README.md#for-a-maintainer-what-any-policy-must-respect).
- **Known gap:** nodes that *lie* about what they store are a sensor problem no controller can out-think. Past K = R false declarations, data is lost invisibly; a proof-gated "verified coverage" extension removes that ceiling **in simulation** but isn't deployed yet.

## Relation to #160

#160 asks for a **policy** (recommend a target arc for a redundancy level). The cost-optimal target is nearly trivial (`R/N` of the ring); every hard part is elsewhere — measuring N under stale/dishonest views, reaching the target without a race, and not oscillating on the way. Polite-shrink is the **safety gate** that makes any such policy safe to run, plus the constraint list for whoever writes the policy.

## Where to look next

- **The mechanism, proven:** [`polite_shrink.py`](polite_shrink.py) + [`spec/`](spec/) (TLA+).
- **The mechanism, deployable:** Rust module on a [kitsune2 fork](https://github.com/topeuph-ai/kitsune2/tree/feat/sharding-module-v3/crates/gossip/src/sharding), behind the existing `sharding` flag.
- **Everything it was tested against:** [TEST_LEDGER.md](TEST_LEDGER.md).

*Research directed by Ceri John; design, implementation, and analysis with AI assistance (Claude, Anthropic); all results human-reviewed.*
