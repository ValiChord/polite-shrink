# Provenance & Upstream Watch

This document records two things, so the relationship between this research and
upstream development stays traceable over time:

1. **Disclosure record** — when the "polite shrink" idea and its artifacts were first
   made public.
2. **Upstream arc-sizing log** — a dated, append-only record of the state of storage-arc
   sizing in kitsune2 / Holochain, and how it relates to the work in this repository.

Everything here is public and freely reusable under this repository's Apache-2.0 license.
The intent is scholarly provenance, not a claim against anyone: the idea was disclosed
openly precisely so it could be used.

---

## 1. Disclosure record

| Date | Artifact | Where |
|---|---|---|
| 2026-07 | This repository (canonical, Apache-2.0) — controller, simulation studies, TLA+ model, Wind-Tunnel scenarios | `ValiChord/polite-shrink` |
| 2026-07 | `CITATION.cff` — citable metadata for the method | this repo |
| 2026-07 | Comments on the redundancy target-arc issue | `holochain/kitsune2` #160 |
| 2026-07 | Reference PR demonstrating the idea on real transport | `holochain/kitsune2` #572 |
| 2026-07-17 | Idea shared with Holochain contributors via community channels | (public discussion) |

The priority date is fixed by these public, timestamped artifacts. Independent
reproduction of the simulation results has also occurred (see repository history).

---

## 2. Upstream arc-sizing log

Append newest entry first. Each entry: date · source (commit/PR/issue) · observation ·
which polite-shrink pattern it relates to · verbatim quote where useful.

### 2026-07-18 — baseline, code-verified against `holochain/kitsune2` @ `62cf344` (2026-07-17)

State of the relevant machinery at the time this log was opened:

- **Sharding machinery is present but off by default.** `sharding = []` is an empty
  feature in `crates/gossip/Cargo.toml`; the arc-resizing paths compile only under
  `#[cfg(feature = "sharding")]`.
- **A storage-arc controller exists, and it is expand-only.**
  `crates/gossip/src/storage_arc.rs::update_storage_arcs()` moves an agent's *current*
  arc toward its *target* arc, but only ever adopts a **strictly larger** arc
  (`arc.arc_span() > current_storage_arc.arc_span()`); with sharding off it simply sets
  the arc to `DhtArc::FULL`. No code path reduces a current arc.
- **`AgentInfo` already gossips the arc claim.** `AgentInfo.storage_arc`
  (`crates/api/src/agent.rs`) is documented as *"the arc over which this agent claims
  authority"* and is signed and continuously gossiped. A reduced arc could therefore be
  announced through this existing, always-present structure — no new message type is
  required for that purpose.
- **Current/target arc model exists; the target is a host-supplied hint.**
  `get_cur_storage_arc` / `set_cur_storage_arc` / `get_tgt_storage_arc` /
  `set_tgt_storage_arc_hint` are trait methods; the target is set from outside kitsune2
  (a *hint*), and defaults to a full (or empty) arc.
- **No shrink, and no adaptive sizing policy.** The token `"shrink"` does not appear
  anywhere in the source. There is no policy that decides a target arc from network
  conditions (redundancy / peer count).

**Relation to this work.** The plumbing (current/target arc model, `AgentInfo` gossip)
and the *grow* direction already exist upstream. The open piece — the redundancy target-arc
controller tracked in kitsune2 #160 — is the **safe *shrink* direction**: a rule that
reduces an agent's arc without dropping any sector below the desired redundancy R, plus a
way to prove that rule never violates that invariant. That safety rule and its verification
harness are what this repository contributes.

---

## 3. What to watch for

Upstream may implement the same idea without using the words "polite shrink." Signals that
the safe-shrink direction is being built:

- The token **`shrink`** appearing anywhere in the kitsune2 source (currently: absent).
- A path near `set_cur_storage_arc` / in `storage_arc.rs` that adopts an arc with a
  **smaller** span than current, or that lowers `AgentInfo.storage_arc`.
- A **redundancy / coverage gate** guarding an arc reduction (`redundancy`, `coverage`,
  `replica`, a minimum-copies check before shrinking).
- Reduction **coordinated through `AgentInfo`** (a reduced arc observed via gossip) rather
  than a bespoke new message type; any hysteresis / staleness / intent handling around it.
- The **`sharding` feature moving toward default-on** or being stabilized.
- New PRs touching `crates/gossip/src/storage_arc.rs`, or renewed activity on
  `holochain/kitsune2` #160.

---

## 4. How to refresh this log

Reproducible from a clean checkout:

```bash
# 1. Fresh kitsune2 source
git clone --depth 1 https://github.com/holochain/kitsune2.git /tmp/k2 && cd /tmp/k2
git log -1 --format='%h %ci'          # record the commit you checked against

# 2. The single strongest tripwire — is the concept present at all yet?
grep -rin "shrink" crates/*/src        # currently returns nothing

# 3. Is the sharding feature still off by default?
grep -rn "^sharding" crates/gossip/Cargo.toml   # sharding = []  → off

# 4. Has the controller gained a reduce path?
sed -n '20,110p' crates/gossip/src/storage_arc.rs

# 5. Issue / PR activity (needs the gh CLI)
gh issue view 160 --repo holochain/kitsune2 --comments
gh pr list --repo holochain/kitsune2 --search "arc OR storage OR shard"
gh search code --owner holochain "shrink storage_arc" 2>/dev/null
```

Add a dated entry to §2 whenever any of these changes. Keep entries factual: source,
observation, verbatim quote.
