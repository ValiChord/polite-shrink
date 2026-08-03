# Plan — test polite-shrink against the current Holochain tooling

**Status: PLAN ONLY. No result is claimed here. Nothing in this file has been run.**

Written 2026-08-03 and parked on the branch `plan/0.7-conductor-run` so it is not lost.
It is deliberately NOT on `main`: `main` carries results, this carries an intention.

**If you are a future session picking this up: read §0 and §5 before doing anything.**
§5 is the part that is easy to get wrong and hard to undo.

---

## 0. Why this exists — one paragraph

The Stage-2 Wind Tunnel campaign (2026-07-12) measured V3 polite-shrink **at the kitsune2
substrate layer** over real iroh transport with live churn. Settle and storm both PASSED.
That campaign explicitly could not go further, because **Holochain 0.6.x pinned kitsune2
0.4.x** while the sharding fork was built on the 0.5.0 line — a whole-line mismatch.

**Holochain 0.7.0 pins kitsune2 `0.5.0`.** Verified 2026-08-03 against the shipped
`holochain-0.7.0` workspace manifest (`kitsune2`, `kitsune2_api`, `kitsune2_core`,
`kitsune2_transport_iroh` all `0.5.0`). The fork was built against `0.5.0-dev.4`. **The
gap is now a dev→release delta inside one line.** So the reason a conductor-level run was
out of scope has expired. See `PROVENANCE.md` §2, entry 2026-08-03.

---

## 1. What is ALREADY done — do not redo any of this

| Claim | Where | Status |
|---|---|---|
| Standalone simulation: 0 data loss across 1248 sweep runs + adversary | `results/` | done |
| kitsune2 mem-transport storm test, 4/4 | fork | done |
| **Wind Tunnel at the kitsune2 layer**, real iroh + churn, settle + storm PASS | `wind_tunnel/results/` | done 2026-07-12 |
| TLA+ exhaustive model check of the gate | `spec/` | done |

⚠️ **Keep these three claims separate in every writeup** — the repo's credibility rests on
that separation, and a fourth claim must not appear by implication.

---

## 2. What this plan would add

**Campaign A — a Holochain-conductor-level run (the valuable one).**
Lifts the claim from *"measured at the kitsune2 substrate layer"* to *"measured in a real
Holochain network"*. This is the measurement that speaks directly to the maintainer
feedback that the 0.7 data model and validation×sharding are the real blocker — a
substrate-layer result does not answer it; a conductor-level one does.

**Campaign B — use upstream's own arc scenarios as the baseline.**
`holochain/wind-tunnel` now ships seven arc scenarios (see §4). Running those against
stock kitsune2 0.5.0 and again against the polite-shrink fork gives a **like-for-like
comparison in the maintainers' own harness**, which is far more persuasive than a foreign
simulator. B is cheaper than A and can be done first.

**Recommended order: B, then A.** B is a smaller build, gives a baseline, and de-risks A.

---

## 3. Campaign A — steps

Prerequisites: Rust 1.85+ (edition 2024). A real machine, not a 2-core Codespace — see §5.

1. **Clone the fork.**
   ```bash
   git clone https://github.com/topeuph-ai/kitsune2 /workspaces/kitsune2
   cd /workspaces/kitsune2 && git checkout feat/sharding-module-v3
   ```
   Last commit 2026-07-14, scaffolded against kitsune2 `82a5896` (0.5.0-dev.4 era).

2. **Rebase the fork onto the kitsune2 `v0.5.0` release.**
   ⚠️ The delta is not empty: the authenticated-relay work (`3746be1`, plus
   `03d21103` relay protocol V2 and `768b01b1` TLS headers) merged between `0.5.0-dev.6`
   and `v0.5.0`. Expect conflicts around transport/relay config, not around the sharding
   module itself. **Record what conflicted** — it is evidence about how well the module
   survives upstream drift, which is itself worth reporting.

3. **Build Holochain 0.7.0 with the fork patched in.**
   ```bash
   git clone --depth 1 --branch holochain-0.7.0 https://github.com/holochain/holochain
   ```
   Add to its workspace `Cargo.toml`:
   ```toml
   [patch.crates-io]
   kitsune2        = { path = "/workspaces/kitsune2/crates/kitsune2" }
   kitsune2_api    = { path = "/workspaces/kitsune2/crates/api" }
   kitsune2_core   = { path = "/workspaces/kitsune2/crates/core" }
   kitsune2_dht    = { path = "/workspaces/kitsune2/crates/dht" }
   kitsune2_gossip = { path = "/workspaces/kitsune2/crates/gossip" }
   ```
   (Mirror whichever `kitsune2_*` crates the 0.7.0 manifest actually names — check, do not
   assume this list is complete.)
   ✅ **Canary:** the `sharding` feature exists only on the fork's `kitsune2_gossip`.
   Enabling it and having the build succeed proves the patch is in effect. The existing
   `wind_tunnel/` workspace already uses this trick — keep it.

4. **Sanity-gate before any scenario work:** start two conductors, confirm they gossip,
   confirm `sharding` is compiled in. If this fails, stop — nothing downstream is
   interpretable.

5. **Then run scenarios** (§4).

---

## 4. Campaign B — upstream's arc scenarios

`holochain/wind-tunnel` `main` migrated to Holochain **0.7.0 on 2026-07-31** and pins
`hdk 0.7.0` / `hdi 0.8.0` / `kitsune2 0.5.0`. Seven arc scenarios ship in `scenarios/`:

```
full_arc_create_validated_zero_arc_read
mixed_arc_get_agent_activity
mixed_arc_must_get_agent_activity
zero_arc_create_and_read
zero_arc_create_data
zero_arc_create_data_validated
unyt_chain_transaction_zero_arc
```

Their provenance: issues **#161** (conductor control, closed 2025-09-26) → **#214**
(mixed full/zero arc scenarios, opened by **ThetaSinner** — who also opened kitsune2
**#160** — closed 2025-12-17) → **#416** (records *get requests served by full-arc nodes*;
closed 2026-02-12; needed the metric added in holochain PR #5451).

**The interesting measurement:** #214's stated open question was *"how hard the full arc
conductors will have to work to carry the validation load and serve data for the zero arc
conductors"*. With #416's metric, that is now measurable. Run the mixed-arc scenarios
**stock** vs **with polite-shrink**, and compare full-arc serving cost.

⚠️ **Check first whether upstream already published results.** If they have, the honest
framing is "reproducing and extending their measurement", not "measuring what nobody has".

---

## 5. Traps — read before starting

1. 🔴 **THE VERSION-NAME TRAP. `holochain_wind_tunnel_runner = "0.7"` on crates.io is a
   Holochain *0.6* runner.** The crate's own version has nothing to do with Holochain's.
   Latest published is **0.7.1 (2026-07-21)**, which still pins `holochain_types ^0.6.3`
   and `kitsune2_api ^0.4.1` — it predates upstream's 0.7 migration by ten days. **Use a
   git dependency pinned to a rev, never the crates.io release.** The existing
   `wind_tunnel/` workspace already does this (rev `1cf7ebf`) and says so.
2. 🔴 **Do not run this on a 2-core Codespace.** A native Holochain build plus
   multi-conductor scenarios will thrash. On 2026-08-03 that box was emitting SQLCipher
   ENOMEM under sweettest alone. Use a real machine.
3. 🟠 **`/tmp` does not survive a Codespace restart.** Any 0.7 binaries or reference
   clones fetched into scratchpad are gone after a stop. Re-fetch, do not assume.
4. 🟠 **The `[patch.crates-io]` paths in `wind_tunnel/Cargo.toml` are relative**
   (`../../kitsune2/crates/*`). Adjust if the checkout moves.
5. 🟠 **Keep the existing `wind_tunnel/` workspace separate from
   `valichord/wind-tunnel/`.** Different runner, different kitsune2 line, fragile pins.
   Never merge them.

---

## 6. Claim discipline — what may and may not be said

**May be claimed if A succeeds:** *"polite-shrink was measured in a real Holochain 0.7
network."* That is a new and materially stronger claim than the Stage-2 result.

**May be claimed if B succeeds:** *"measured in the maintainers' own harness, against
their own mixed-arc scenarios, stock vs patched."*

**MUST NOT be claimed:**
- that the full-arc serving cost was previously unmeasured — see §4 and `PROVENANCE.md`
- that a conductor run validates the *policy* rather than the gate — the TLA+ proof covers
  the ~15-line gate, not the policy; that distinction is already documented and must hold
- anything that blurs the four existing claims in §1

**If a campaign fails or is abandoned, record that too**, in `PROVENANCE.md` §2 with the
date and the reason. A failed attempt with a stated cause is evidence; silence is not.

---

## 7. Definition of done

- [ ] Fork rebased onto kitsune2 `v0.5.0`, conflicts recorded
- [ ] Holochain 0.7.0 builds with the patch, `sharding` canary confirms it
- [ ] Two conductors gossip with the patched build
- [ ] Baseline: upstream mixed-arc scenarios, stock kitsune2
- [ ] Comparison: same scenarios, polite-shrink fork
- [ ] Results curated into `results/` with an explicit claim boundary
- [ ] `PROVENANCE.md` §2 entry, dated
- [ ] This branch merged or deleted, so it does not linger as a stale intention
