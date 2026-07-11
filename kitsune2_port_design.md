# Porting V3 "polite shrink" to kitsune2 — design mapping

Stage 2b of the arc-sim study (see `results/sweep_summary.md`: V3 = 0 losses in
1248 runs; V1/V2 ≈ 24%). Target: `topeuph-ai/kitsune2` fork, branch
`feat/sharding-module-v3`, upstream issue holochain/kitsune2#160 ("Add sharding
module": *"determine how many other agents are storing the same data and
recommend an appropriate target arc based on the desired redundancy level"*).

## What upstream already has (verified in source)

| Piece | Where | State |
|---|---|---|
| `sharding` feature flag | `crates/gossip/Cargo.toml` | exists, gates grow-side |
| Grow cur-arc toward target as sectors verifiably sync | `crates/gossip/src/storage_arc.rs` (`update_storage_arcs`, called from gossip round completion) | done upstream |
| Target-arc socket | `LocalAgent::set_tgt_storage_arc_hint` (`crates/api/src/agent.rs:69-76`) — doc says "the sharding module will attempt to determine an ideal target" | socket exists, module absent |
| Module wire routing | `Transport::register_module_handler(space, module, handler)` / `send_module`; wire proto docs list `"sharding"` as an example routing string | ready |
| Per-peer lag signal | `K2PeerMetaStore::last_gossip_timestamp` (`crates/gossip/src/peer_meta_store.rs`, key `gossip:last_timestamp`) | ready |
| Sector math | `kitsune2_dht::{ArcSet, SECTOR_SIZE}`, `DhtArc` in api | ready |
| Multi-node in-process test rig | `crates/gossip/src/harness.rs` (`K2GossipFunctionalTestHarness`: real space + mem transport + mem op store), `mem_transport` in core | ready |

**The missing piece is exactly the sim's controller**: the thing that decides
the target arc, and above all coordinates *shrinking* safely. Growing is safe
by construction (grow-side only claims sectors after verified sync).

## Placement decision

Implement inside `crates/gossip` as a `src/sharding/` submodule behind the
existing `sharding` feature — NOT as a new Builder-level module.

Rationale: (a) the feature flag and the grow-side consumer already live there;
(b) `GossipFactory::create` already receives every dependency we need
(peer_store, local_agent_store, peer_meta_store, transport); (c) zero changes
to `kitsune2_api`/Builder → small, reviewable, non-breaking diff. The design
note can offer extraction into a first-class `ShardingFactory` module (their
CLAUDE.md pattern) as the productionisation path; the controller logic moves
unchanged.

## Sim → kitsune2 mapping

| Sim concept | kitsune2 realisation |
|---|---|
| sector | `ArcSet` sector index (u32 ring / `SECTOR_SIZE`) |
| per-sector coverage | count of `AgentInfoSigned.storage_arc` (peer store `get_all()`) + local agents' cur arcs covering the sector |
| own measured gossip lag | `now − last_gossip_timestamp(peer)` aggregated over responsive peers (p95, clamped by config) |
| grow dwell = 1× lag | timer per local agent before widening tgt hint |
| shrink dwell = 4× lag | timer before *starting* a shrink (phase 1) |
| announce intent | new wire msg `ShrinkIntent { agent, current_arc, proposed_arc, announced_at, expires_at }`, module routing string `"sharding"`, proto file `crates/gossip/proto/sharding.proto` (their prost pipeline, `cargo make proto`) |
| wait 2× max-lag then recheck | phase-2 timer; recheck coverage with intent table applied |
| count lower-id intenders as gone | subtract dropped sectors of intenders with lower `AgentId` from coverage before deciding |
| lowest-id proceeds | if conflict remains and we are not lowest conflicting id → cancel (let intent expire) |
| apply shrink | `set_tgt_storage_arc_hint(smaller)` + `set_cur_storage_arc(smaller)` (dropping authority is the one direct cur-arc write the module makes) |
| target redundancy R | module config `target_redundancy` (issue #160's "desired redundancy level") |

Incoming `ShrinkIntent`s land in an expiring intent table (map agent→intent);
broadcast fan-out for the PoC = all peers in peer store (fine at test scale;
flagged as a scaling consideration for the note — production would target
peers overlapping the dropped sectors).

## Controller loop (tokio interval task, like gossip initiate)

1. Snapshot peer store + local agents → per-sector coverage.
2. Update lag estimate.
3. Per local agent: under-covered adjacent sectors → grow tgt after grow-dwell.
   Over-covered own sectors (≥ R + margin everywhere we'd drop) → two-phase
   polite shrink as above.
4. Expire stale intents.

## Storm test (the point of the exercise)

`crates/gossip/tests/` or harness-based test, `#[cfg(feature = "sharding")]`:
N in-process nodes (≈10, not the sim's hundreds), join with FULL arcs, seed
ops, enable controller, wait for shard-down; then abort ~30% of nodes at once;
continuously assert the union of live nodes' cur arcs covers the full ring
(no sector orphaned) and that the network re-stabilises. Flashcrowd variant
(add nodes) if cheap. Params scaled: sim ticks → wall-clock via short
configured intervals so the test runs in seconds.

## Implementation deltas from the sim (discovered while porting)

Recorded for the design note — each is a place where the real system
differs from the sim's idealisation, and what the port does about it:

1. **Death visibility = unresponsive marking.** In the sim, a dead agent
   vanishes from the declared snapshot after one lag. In kitsune2, a dead
   peer's signed AgentInfo lingers in peer stores until it expires (~20 min)
   — but gossip already marks peers *unresponsive* when rounds fail
   (`initiate.rs`). The controller discounts unresponsive peers from
   coverage; that is the mechanism by which a storm becomes visible.
2. **Coverage excludes self by construction.** The sim's `cov` includes
   everyone and subtracts "me" contextually. The port computes
   others-coverage directly (peer store minus own agents, plus sibling
   local agents per deciding agent) — same arithmetic
   (`shrink consider: others ≥ R+1`, `execute: others − lower-id intenders ≥ R`),
   fewer stale-self edge cases. Grow check therefore never counts our own
   stale larger declaration — a slightly more conservative (safety-biased)
   deviation.
3. **Intent expiry carries a grace period.** Sim intents vanish at their
   execute tick. Wire intents carry `expires_at = execute_at + wait`, so
   growers stay conservative while an executed shrink propagates.
4. **Lag is measured, not assigned.** Per-viewer lag becomes the p90 of
   `now − last_gossip_timestamp` over responsive peers (key
   `gossip:last_timestamp` in the peer meta store), clamped to configured
   bounds; the ceiling doubles as the cold-start assumption.
5. **512 sectors for free.** `SECTOR_SIZE = 2^23` → 512 sectors — identical
   to the sim's default ring (`log2s = 9`). Level semantics carry over 1:1.
6. **Grow completion is observed, not scheduled.** The sim schedules
   `sync_until`; the port sets the target hint and watches for the existing
   verified-sync machinery (`storage_arc.rs`) to raise the current arc to
   the target block, gating decisions meanwhile.
7. **Death visibility runs on a different clock than view staleness —
   the sim's single lag parameter hides this.** (Found by a failing storm
   test: an intent announced pre-storm executed 100 ms post-storm counting
   dead peers that had not yet been marked unresponsive; 128 sectors
   orphaned.) In the sim, `intent_delay > 2×lag` structurally guarantees a
   pre-execute re-check sees any death older than one lag. In kitsune2,
   deaths become visible only via unresponsive marking, whose latency is
   set by gossip initiate cadence + connection timeout, not by peer-store
   staleness. Port adds a **storm brake**: any newly-invisible peer cancels
   all pending shrink intents node-wide (persistence must re-accumulate).
   Residual window: deaths invisible at execute time (younger than the
   marking latency); bounded by keeping shrink persistence ≥ detection
   latency. This coupling — polite-shrink wait must dominate *death
   detection*, not just gossip staleness — is a design-note headline, and
   a knob issue #160 should expose.
8. **Model/reality sync gate.** A freshly joined agent has an empty current
   arc; the controller must never "shrink" from a level it does not
   actually hold (that would *claim* unsynced data). Decisions are gated on
   `cur_arc == block(target_level)`.
9. **Sibling-half-local growth cannot rescue distant thin regions — the
   small-network clamp is the designed recovery path for the sparse
   regime.** (Found by a failing recovery: 5 survivors sharded to small
   arcs, one region at coverage 1 was in nobody's sibling half; grows = 0;
   stuck.) The sim masked this with 200-agent density and a 25-peer clamp
   default. Consequence: `clamp_min_peers` is a safety parameter, not a
   tuning knob — it must exceed the population where sharding is worth
   having at all. A production controller may want an explicit global
   under-coverage repair rule (grow anywhere the ring is thin), but that
   is *new* dynamics the sweep never validated — flag for Stage-3 sim
   work before building it.

## Verification protocol (their CLAUDE.md)

`cargo fmt` → `cargo make static` → `cargo test -p kitsune2_gossip --features
sharding` (+ `-p kitsune2` if integration crate touched). Proto changes via
`cargo make proto`, never hand-edit `gen/`.
