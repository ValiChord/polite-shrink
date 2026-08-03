# Plan — test polite-shrink against the current Holochain tooling

**Status: PLAN + EXECUTION LOG. NO MEASUREMENT RESULT IS CLAIMED HERE.**

Written 2026-08-03 and parked on the branch `plan/0.7-conductor-run` so it is not lost.
It is deliberately NOT on `main`: `main` carries results, this carries an intention.

⚠️ **Updated 2026-08-03, later the same day: Campaign B was STARTED. It is not finished and
it has produced NO measurement.** The harness builds and runs, but every scenario run so far
has failed before recording a single operation, for a reason now diagnosed (§7). Nothing in
§1's four claims has changed, and no fifth claim exists. **Read §7 before §3 or §4** — it
corrects §2's cost model and adds four traps that cost real time.

**If you are a future session picking this up: read §0, §5 and §7 before doing anything.**
§5 and §7 are the parts that are easy to get wrong and hard to undo.

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

❌ **CORRECTION 2026-08-03: the fork is on `0.5.0-dev.6`, not `0.5.0-dev.4`.** Read from the
local checkout's own workspace manifest (`version = "0.5.0-dev.6"`). The gap to `v0.5.0` is
therefore *narrower* than this section assumed, and it is precisely the authenticated-relay
work that §3 step 2 already warns about (`3746be1`, `03d21103`, `768b01b1`). Good news, but
do not read it as "no delta" — the rebase is still real and its conflicts still need
recording.

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

~~**Recommended order: B, then A.** B is a smaller build, gives a baseline, and de-risks A.~~

❌ **CORRECTED 2026-08-03 — "B is cheaper than A" IS WRONG, and the error is structural, not
an estimate that came in high.** B requires the *same* from-source Holochain build that §3
scoped to A, because no released Holochain binary can run wind-tunnel's zomes at all (§7.1).
The order B-then-A still stands — B is still the better first measurement — but **B does not
de-risk A by avoiding A's expensive step. It contains it.** Budget the Holochain source build
once, up front, as a shared prerequisite of both campaigns rather than as part of A.

---

## 3. Campaign A — steps

Prerequisites: Rust 1.85+ (edition 2024). A real machine, not a 2-core Codespace — see §5.

1. **Clone the fork.**
   ```bash
   git clone https://github.com/topeuph-ai/kitsune2 /workspaces/kitsune2
   cd /workspaces/kitsune2 && git checkout feat/sharding-module-v3
   ```
   Last commit 2026-07-14, scaffolded against kitsune2 `82a5896` (0.5.0-dev.4 era).

   ✅ **Already done as of 2026-08-03 — do not re-clone.** Two checkouts of the fork exist:
   `/workspaces/kitsune2` (on `feat/sharding-agentinfo-encoding`, one branch *ahead* of the
   `feat/sharding-module-v3` this step names) and `/workspaces/kitsune2-pr` (on
   `fix/mem-transport-unresponsive`). Sharding module confirmed at
   `crates/gossip/src/sharding/`. ⚠️ Decide deliberately which branch the rebase targets —
   this step assumes `feat/sharding-module-v3`, and the newer branch may or may not be what
   should be measured. Note `v0.5.0` is NOT a known tag in that checkout; fetch upstream
   tags before attempting step 2.

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

✅ **CHECK DONE 2026-08-03. No numbers are published.** Evidence:
- **#416** closed 2026-02-12 having delivered *instrumentation only*. Its acceptance criteria
  are "summariser, dashboard, visualizer and summarizer snapshot tests are updated" for the
  six named scenarios. No results are attached to the issue.
- **#214** closed 2025-12-17 with matthme noting the only remaining part was the get-request
  metric, handed to #416. Its stated open question — *"how hard the full arc conductors will
  have to work"* — **is not answered anywhere public.**
- The repo carries **no `results/` directory**; runs report to InfluxDB/Grafana via
  `influx/templates/dashboards/`, and those dashboards are not public.

**So the honest framing is the third option, which this section did not anticipate:**
*"running the measurement their own instrumentation was built to enable, which they
instrumented but have not published."* That is neither "reproducing published results" nor
"measuring what nobody has instrumented" — **and the second of those would be a false claim,
because they did instrument it.** Do not write the stronger version.

---

## 5. Traps — read before starting

1. 🔴 **THE VERSION-NAME TRAP. `holochain_wind_tunnel_runner = "0.7"` on crates.io is a
   Holochain *0.6* runner.** The crate's own version has nothing to do with Holochain's.
   Latest published is **0.7.1 (2026-07-21)**, which still pins `holochain_types ^0.6.3`
   and `kitsune2_api ^0.4.1` — it predates upstream's 0.7 migration by ten days. **Use a
   git dependency pinned to a rev, never the crates.io release.** The existing
   `wind_tunnel/` workspace already does this (rev `1cf7ebf`) and says so.
2. 🟠 **"Do not run this on a 2-core Codespace" — the premise was wrong, the caution was
   right, and the real constraint is DISK.** Measured 2026-08-03: the box is **8-core /
   31 GB**, and 6 conductors + a native build ran on it without thrashing. What actually
   bit was storage — `/workspaces` was **99% full (886 M free)** and a link step died with
   ``ld terminated with signal 7 [Bus error], core dumped``, which reads like a compiler bug
   and is not one. **`/tmp` is a separate 265 G volume with ~241 G free — put source trees,
   `CARGO_TARGET_DIR` and conductor data there** (subject to trap 3). Deleting Cargo
   `incremental/` caches is the cheap reversible way to buy ~4.5 G on `/workspaces`.
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

## 7. Execution log — Campaign B, started 2026-08-03. NO RESULT YET.

**State: the harness builds and runs; no scenario has recorded a single operation.** Setup
below is reusable; the blocker in §7.1 is the reason there is no measurement.

**What is standing up and verified:**
- Upstream harness cloned at rev **`e4861457`** ("feat: Update to Holochain 0.7.0"), 27
  scenarios present including all seven arc scenarios named in §4, plus `unyt_proposal` and
  `unyt_chain_transaction`. Built `mixed_arc_get_agent_activity` clean in **7m10s**; the DNA
  and hApp packed (~600 KB each).
- 🆕 **The arc mechanism is confirmed working end to end.** With
  `--behaviour zero_read:3 --behaviour zero_write:1 --behaviour full_write:2`, the conductor
  configs show `target_arc_factor: 0` for agents 0–3 and `1` for agents 4–5. Wind Tunnel
  starts **one real conductor per agent**, so this is genuinely conductor-level — the thing
  §2 says makes A/B worth more than the Stage-2 substrate result.
- 🆕 **InfluxDB is NOT required.** The runner sets `HOLOCHAIN_INFLUXIVE_FILE` per agent via
  `WT_METRICS_DIR`, so metrics land as line-protocol files that can be read directly.

### 7.1 🔴 THE BLOCKER — no released Holochain binary can run these scenarios

```
ModuleBuild("agent_activity: Error while importing
  \"env\".\"__hc__accept_countersigning_preflight_request_1\": unknown import")
```

Wind Tunnel's workspace `Cargo.toml` (~line 165) enables `hdk` with **both**
`unstable-functions` **and** `unstable-countersigning`. That makes every zome WASM *declare*
the countersigning host-function imports, so the conductor must be built with matching
features to *provide* them. `flake.nix:62` does exactly that:
`cargoExtraArgs = "--features unstable-functions,unstable-countersigning"`.

⚠️ **Both released binaries fail, identically — including the one named "unstable".** Tested
`holochain-x86_64-unknown-linux-gnu` and `holochain-unstable-x86_64-unknown-linux-gnu` from
the `holochain-0.7.0` release: 2312 import errors each. **Do not spend time hunting for a
released binary that works; there isn't one.** The two binaries differ by ~18 KB and the
"unstable" one does not carry the countersigning host functions.

**Consequence:** a Holochain conductor must be built **from source** with those two features
— and, since this is a load test, `--release` (a debug conductor makes the timings
meaningless). This is what invalidates §2's "B is cheaper than A". Nix would supply it via
the flake, but **nix is not installed** on this box.

### 7.2 Four traps that cost real time

1. 🔴 **A totally failed run EXITS 0.** The first attempt had all six agents panic on a
   missing env var and still returned exit status 0, with an empty "Summary of operations"
   table and a `None`-unwrap panic in `in_memory_reporter.rs:56`. **Exit code is not a pass
   signal for this harness. Assert on recorded operations, not on `$?`.**
2. 🔴 **`--reporter in-memory-with-custom-metrics` is REQUIRED.** The default `InMemory`
   reporter **excludes custom metrics** — which is exactly where every arc measurement lives
   (`wt.custom.mixed_arc_*`, including the entry counts and open-connection counts). It is
   entirely possible to run the whole campaign correctly and record nothing that matters.
3. 🟠 **`WT_METRICS_DIR` is mandatory and undocumented in the scenario README** — absent, the
   agent threads panic at `bindings/runner/src/common.rs:868`. `WT_HOLOCHAIN_PATH` is
   optional (falls back to `PATH`); `MIN_AGENTS` defaults to 2. Upstream's own Nomad job
   variants do not set `MIN_AGENTS`, so leave it alone for fidelity.
4. 🟠 **Do not pipe a long run through `| tail`.** It buffers, so nothing is written until
   the process exits — and if the run is killed the entire log is lost. Redirect to a file.

### 7.3 ⚠️ The harness talks to PUBLIC infrastructure, and cannot be told not to

Conductors come up with `ConductorConfig::default()`, which in 0.7.0 is
`bootstrap_url: https://dev-test-bootstrap2.holochain.org` and
`relay_url: https://use1-1.relay.n0.iroh-canary.iroh.link.`. Logs show corresponding
`No space handler found. Message will be dropped.` and `peer that is blocked in the
associated space` chatter.

**The space ID is derived from the DNA hash**, so every party running this same upstream
scenario — including upstream's own Nomad cluster — occupies the same space. There is **no
bootstrap override** in the Wind Tunnel CLI (`connection_string`, `agents`, `behaviour`,
`duration`, `soak`, `no_progress`, `reporter`, `run_id` — that is the whole list) and none in
`HolochainConfigBuilder` (`bin_path`, `agent_name`, `admin_port`, `conductor_root_path`,
`target_arc_factor`, `metrics_path`).

**Judgement:** running stock defaults is faithful to how the maintainers run it, and a
stock-vs-patched comparison stays like-for-like as long as both arms are identical. **But
absolute numbers are not reproducible off this box, and cross-run interference from third
parties is possible.** State this in any writeup. Forcing a local bootstrap means patching
upstream, which would weaken B's "in the maintainers' own harness" claim — that is a real
trade-off, not an obvious win, and should be a deliberate decision.

---

## 8. Definition of done

**Shared prerequisite (blocks BOTH campaigns — see §7.1):**
- [ ] Holochain 0.7.0 built from source, `--release`, with
      `--features unstable-functions,unstable-countersigning`
- [ ] That conductor runs one upstream arc scenario to a non-empty operations summary
      (⚠️ check recorded operations, not exit code — §7.2 trap 1)

**Campaign B — baseline, then comparison:**
- [ ] Baseline: upstream mixed-arc scenarios, stock kitsune2, with
      `--reporter in-memory-with-custom-metrics`
- [ ] Fork rebased onto kitsune2 `v0.5.0`, conflicts recorded
- [ ] Comparison: same scenarios, polite-shrink fork, `sharding` canary confirms the patch
      is in effect
- [ ] Full-arc serving cost compared stock vs patched (the #214 question)

**Campaign A:**
- [ ] Two conductors gossip with the patched build

**Both:**
- [ ] Results curated into `results/` with an explicit claim boundary, including the
      public-infrastructure caveat (§7.3)
- [ ] `PROVENANCE.md` §2 entry, dated — **including if this is abandoned** (§6)
- [ ] This branch merged or deleted, so it does not linger as a stale intention
