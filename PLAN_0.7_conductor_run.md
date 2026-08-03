# Plan — test polite-shrink against the current Holochain tooling

**Status: PLAN + EXECUTION LOG. NO MEASUREMENT RESULT IS CLAIMED HERE.**

Written 2026-08-03 and parked on the branch `plan/0.7-conductor-run` so it is not lost.
It is deliberately NOT on `main`: `main` carries results, this carries an intention.

⚠️ **Updated 2026-08-03, later the same day: Campaign B's STOCK ARM has run. There is still
NO polite-shrink result and no comparison.** The blocker is cleared, and a stock baseline
exists (3 × 300s, §7.5). **Nothing in §1's four claims has changed and no fifth claim
exists** — a stock baseline is a measurement *of upstream*, not of polite shrink. The fork
has not been rebased and has not been run.

**Read §7 before §3 or §4.** It corrects §2's cost model, records four traps that cost real
time, and carries two findings that change how Campaign B should be run at all: the read-side
metrics vary **per-peer not per-run** (§7.6), and **readers never query the zero-arc writer**
(§7.7) — which is the case §214 most needs covered.

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

### 7.4 ✅ The blocker is CLEARED, and it cost 13 minutes

Holochain 0.7.0 built from source, `--release`, with
`--features unstable-functions,unstable-countersigning`: **13m02s** on an 8-core box.
The scenario then ran with **0 import errors and 0 behaviour failures**.

⚠️ **This softens §7.1 but does not overturn it.** "B is cheaper than A" is still wrong —
B still contains A's build step — but the step is a 13-minute cost, not an afternoon. Do
not let the correction in §2 be read as "B is expensive"; it is not.

### 7.5 STOCK BASELINE — 3 × 300s runs, 2026-08-03

Upstream's documented local shape (`--agents 6 --behaviour zero_read:3 --behaviour
zero_write:1 --behaviour full_write:2`), repeated 3× so there is a spread rather than one
number. **This is the stock arm only. There is no comparison and no polite-shrink result.**

| metric | full-arc (×2) | zero-arc writer (×1) | zero-arc readers (×3) |
|---|---|---|---|
| `open_connections` | **5.00, 5.00, 5.00** (0.0% spread) | 3.85 (6.5%) | 3.91 (24.7%) |
| entries created | 1579, 2053 / 1587, 2095 / 2107, 2129 | **3101, 3037, 3326** | — |
| zome calls per run | 25962, 26510, 22912 (14.3% spread) | | |
| `retrieval_error_count` | — | — | exactly 3 per run (0.0%) |

🆕 **The #214 signal is present and unanimous.** The single zero-arc writer out-produced
**both** full-arc writers in **every run — 6/6 pairwise comparisons.** Full-arc mean 1,925
entries/node vs zero-arc 3,155, i.e. the zero-arc writer produces **~64% more**. That is the
shape #214 predicts: full-arc nodes paying validation-and-serving cost out of their own write
throughput. ⚠️ Direction is unanimous; **magnitude is one machine, n=3 — quote 64% as
indicative, never as a measurement.**

⚠️ **ThetaSinner's connection prediction does not match, but this is NOT a refutation.** His
#214 comment expects zero-arc open connections ≈ the number of full-arc nodes (2 here),
since *"we don't expect 0-arc nodes to gossip with each other once the network is
bootstrapped."* Observed: **~3.9 of a possible 5**, consistently, across all runs. **Before
this is repeated anywhere, establish what the metric counts** — it is
`network_stats.transport_stats.connections.len()`, which may include bootstrap/relay
connections and not only peer gossip. That distinction decides the whole question.

### 7.6 🔬 Read-side instability — DIAGNOSED: it is per-PEER, not per-run

The read-side metrics were unusable at first sight: `chain_head_delay` spread **209%**,
`highest_observed_action_seq` spread **243%**, driven by a 17× swing in sample count
(253, 259, **4420**). The cause is now identified.

**Readers draw ONE write peer at start (`get_random_agent_with_write_behaviour`) and keep it
for the whole run. How well that particular peer's chain propagates is what varies.**

The decisive evidence is *inside a single run*, where readers split across two full-arc peers
under identical conditions:

| run | peer drawn | authored | max seq observed | tracked | head-moves |
|---|---|---|---|---|---|
| run1 | uhCAkQ-bf5WS | 1579 | 1258 | 0.80× | 80, 96, 77 |
| run2 | uhCAkw4FLNPv | 1587 | 1004 | 0.63× | 94, 93, 72 |
| **run3** | **uhCAksHDgA3Y** | 2129 | **2133** | **1.00×** | **2122, 2120** |
| **run3** | **uhCAkjrdnd7x** | 2107 | 1682 | 0.80× | **178** |

One peer was trackable in near-real-time (2,122 observed advances; seq 2133 against 2129
authored — essentially every action). The other gave 178 chunky updates and lagged by 425.
**A 12× difference in the same run.** So this is not "network conditions on the day".

⚠️ **Low sample count means STALENESS, not less polling.** The scenario emits these metrics
only when the observed head *changes* (`n_jump != 0`), and readers polled at comparable rates
throughout (total zome calls within 14%).

❌ **Holochain #5288 is NOT the explanation — hypothesis raised and dropped the same day.**
#5288 is about `get_agent_activity` returning *empty* responses when the only known peers are
local, which described this setup and looked compelling. **The data refutes it:** reads
succeeded and returned real sequence numbers, with only 3 retrieval errors per run (one per
reader, at startup). The reads are **stale, not empty.** Recorded so nobody re-derives it —
and so the ValiChord warrant-gate concern that cites #5288 is not wrongly reinforced by this.

### 7.7 ⚠️ Readers never query the ZERO-arc writer — scenario-coverage gap

**Measured over 9 runs — 3 × 300s baseline + 6 × 60s selection samples — giving 27
independent reader-draws:**

| observation | count | p under uniform draw from 3 writers |
|---|---|---|
| draws that selected the **zero-arc** writer | **0 / 27** | (2/3)²⁷ ≈ **1.8 × 10⁻⁵** |
| runs where all 3 readers drew the **same** peer | **8 / 9** | ≈ **1.9 × 10⁻⁷** |

Selection is `get_links` on an anchor → `shuffle` → take first, so a uniform draw from three
announced writers is the null. **Both results reject it decisively.** This is not chance.

🆕 **Only ONE full-arc writer is visible per run** — not two, not three. Shuffle-then-first
returns a fixed element only when the list has **one** element.

**Inferred mechanism (strongly supported, not yet directly observed):** readers select before
the write-agent anchor has converged, so they draw from a single-entry link set. A full-arc
writer's own announce link is retrievable immediately; a zero-arc writer's must first reach a
full-arc node, and the second full-arc writer's has not propagated either.

### ✅ DIRECT TEST RUN 2026-08-03 — mechanism CONFIRMED, and it is worse than inferred

`links.len()` was logged inside `get_random_agent_with_write_behaviour` and the scenario run
in a fresh space at the baseline's own 300s duration. **Two runs, identical result:**

| run | selection calls returning 0 candidates | returning 1 | returning 2 or 3 |
|---|---|---|---|
| diag-4 (300s) | 1618 | **3** (one per reader) | **0** |
| diag-5 (300s) | 1916 | **3** (one per reader) | **0** |

**The candidate set is never larger than ONE.** Readers poll and see nothing for ~27s, then
all three simultaneously see a single link, select it, and stop calling.

🔴 **And the one visible writer was a FULL-arc writer in both runs.** Neither the zero-arc
writer *nor the second full-arc writer* ever became visible at selection time:

| run | visible candidate | not visible |
|---|---|---|
| diag-4 | `uhCAkPx83E0…` (full_write) | `uhCAkVBz3…` (zero_write), `uhCAkW4q_…` (full_write) |
| diag-5 | `uhCAk8WUoQ…` (full_write) | `uhCAkLjpEd9…` (zero_write), `uhCAkAofNZ0…` (full_write) |

So the §7.7 inference was right about the mechanism and **understated the problem**: it is
not merely that the zero-arc author is never read — **only one of three announced writers is
ever a candidate.** The scenario's reader population collapses onto a single peer, which is
also why the read-side metrics are effectively a measurement of one connection (§7.6).

### ⚠️ Two methodological findings from running it — both cost real time

1. 🔴 **Zome `debug!` is INVISIBLE by default in a release build.** `wasm_trace` filters on
   `WASM_LOG`, default `[wasm_trace]=debug` — that is **span** filter syntax, and the
   `wasm_trace` span only exists when Holochain is built with the `instrument` feature.
   A release build has no such span, so the filter matches nothing and instrumentation
   silently produces zero output. **Set `WASM_LOG=debug`.** One full diagnostic cycle was
   run and thrown away before this was spotted.
2. 🟠 **Instrumenting this scenario CANNOT avoid changing the space.** Editing the zome
   changes the DNA hash, which changes the space — so the diagnostic never runs in the same
   network as the measurement. Controlled for as follows, and the confound is real:

   | condition | space | iroh connect timeouts | readers found a peer |
   |---|---|---|---|
   | instrumented, 60s | fresh | 13, 13, 15 | **never** (0 candidates in 6945 calls) |
   | **upstream zome, 60s, 3 min later** | established | 1, 0 | **yes — 3/3 readers, both runs** |
   | instrumented, 300s | fresh | — | yes, after ~27s |

   Same box, same duration, minutes apart — **so the difference is the SPACE, not load or
   time of day.** A fresh space did not converge within 60s; the established space did.
   ⚠️ **This means the §7.5 baseline ran in a space already populated by earlier runs.**
   Whether that population was only our own prior conductors or included foreign agents was
   NOT established. Either way it is a reproducibility caveat on the baseline: a
   cold-start network behaves differently, and 60s runs in a fresh space fail outright.

**Why this matters for Campaign B:** if it holds, the scenario never exercises *"read a
zero-arc author's activity"* — the case where the data must be served **entirely** by
full-arc nodes, which is the most load-bearing part of #214's question and the case polite
shrink most needs to speak to. **Check this before treating mixed-arc results as covering
the full-arc serving cost.**

### 7.8 🔴 CAMPAIGN B CANNOT COMPARE POLITE-SHRINK ON THESE SCENARIOS — premise error

**Found 2026-08-03 while preparing the comparison arm, before the build was run.** Two
independent reasons, both from the fork's own source:

**1. Polite shrink cannot engage at this scale.** `K2ShardingConfig::clamp_min_peers`
defaults to **25**. `crates/gossip/src/sharding/controller.rs:308`:

```rust
// Small-network clamp: too few visible peers, hold a full arc.
if (visible_peers as u32) < cfg.clamp_min_peers {
    if ctl.declared_level < MAX_LEVEL { self.start_grow(agent, ctl); }
    return;
}
```

Below 25 peers the controller does not merely decline to shrink — it **grows** agents
toward a full arc. The scenario runs **6**. So a patched run would either be identical to
stock, or would actively fight the scenario by growing its pinned zero-arc nodes. The
module's own docs say small networks "gain nothing from sharding and are the most fragile
under it", so lowering the clamp to force engagement would test polite shrink in the regime
it explicitly excludes — a result that is easy to attack and deserves to be.

**2. The deeper mismatch — the scenarios pin the variable polite shrink computes.** Every
one of upstream's seven arc scenarios sets the arc statically via conductor config
(`with_target_arc_factor(0)`). Polite shrink's whole thesis is that the arc should be
derived dynamically under a redundancy floor. The two answer complementary questions —
*"what does a mixed-arc network cost?"* versus *"can a network reach a mixed-arc
configuration safely?"* — and a stock-vs-patched run on a pinned-arc scenario tests neither.

⚠️ **This is a premise error in §2, not a problem with the fork.** "Use upstream's own arc
scenarios as the baseline" is a good instinct for credibility and the wrong instrument for
this claim. **A conductor-level polite-shrink test needs a purpose-built scenario:** ~25+
nodes, arcs left dynamic, measuring whether redundancy ever drops below target while load
falls. That is Stage-2's experiment lifted to conductor level, and it is real work — do not
smuggle it in as "one more scenario".

✅ **What survives, and it is the better deliverable.** The scenario defect (§7.7), the fix,
and the zero-arc visibility result (§7.9) are self-contained, are what upstream's own
instrumentation was built to surface, and stand whether or not anyone is interested in
polite shrink. Ship that; treat the conductor-level polite-shrink test as separate work.

### 7.9 🆕 RESULT — a zero-arc author's chain is nearly invisible to readers

With the §7.7 fix applied, readers cover all three writers for the first time and the
zero-arc author is read. **6 runs × 300s.** ❌ **An early single-run reading of "5.4%
visible" was quoted before replication and did NOT hold — the magnitude is unstable. The
direction did hold.**

**Zero-arc author visibility, every run where coverage was complete:**

| run | authored | max seq visible | visible | full-arc peers, same run |
|---|---|---|---|---|
| fixed/1 | 3177 | 172 | **5.4%** | 99.7%, 97.2% |
| fixed/3 | 3174 | 6 | **0.2%** | 93.5%, 99.1% |
| fixed2/2 | 3358 | 2336 | **69.6%** | 92.8%, 99.9% |

**What replicates and what does not:**
- ✅ **Direction, 3 of 3:** the zero-arc author is read *less completely than every full-arc
  author in the same run*, every time. Full-arc sits at **93–100%** across all runs.
- ❌ **Magnitude, not at all:** 0.2% / 5.4% / 69.6%. **Do not quote a figure.** The honest
  claim is "substantially and variably worse, never better".
- ✅ **Zero-arc nodes author the MOST, 4 of 4:** 3177, 3174, 3358, 3086 versus ~1900–2750
  for full-arc. The §7.5 write-side signal replicates under the fixed scenario.

⚠️ **Announcement propagation is itself unreliable, and this is arguably the bigger finding.**
Only **3 of 6** runs reached full writer visibility:

| outcome | runs | what the reader did |
|---|---|---|
| all 3 writers visible | 3 | full coverage, zero-arc author read |
| only 2 visible | 2 | bounded fallback selected from 2; **no zero-arc coverage** |
| never selected at all | 1 | first fix version, before the fallback existed |

That last row was a flaw in the **fix**, not only in the scenario: v1 traded "always selects,
but only one peer" for "selects correctly or not at all", and produced a run with healthy
writers (7741 entries), zero failures, zero iroh timeouts — and no reader data whatsoever.
Fixed with a bounded wait plus a new **`write_peers_visible_at_selection`** metric tagged
`complete: true|false`. Verified doing its job: the two fallback runs recorded
`value: 2, complete: false`, the full run `value: 3, complete: true`. **That metric is the
part most worth proposing upstream** — it converts a silent, invisible degradation into
something every ordinary run records.

### 7.10 ❌ §7.9's zero-arc finding is RETRACTED — it was LOAD, and a rate sweep proves it

**The single most important correction in this file. §7.9's zero-arc visibility deficit does
not survive.** A three-point write-rate sweep (3 runs each, 300s, same box, same build) shows
it was contention on this machine, not a property of zero-arc nodes.

*visibility = highest action seq a reader observed ÷ (entries the author wrote + 5).*

❌ **Denominator corrected 2026-08-03.** The first version divided by the raw entry count and
produced visibilities **above 100%**, which is nonsense and would have been the first thing a
maintainer queried. Chain seq counts **all** actions, not just sample entries: each writer has 6
actions before its first entry (Dna, AgentValidationPkg, agent key, InitZomesComplete, the cap
grant from `admin_authorize_signing_credentials`, the `announce_write_behaviour` link), so N
entries put the head at seq **N+5**. Verified: observed-minus-authored is exactly +5 on every
fully-tracked writer row. **Numbers below are the corrected ones.**

| write rate | zero-arc visibility | full-arc visibility | runs with complete writer coverage |
|---|---|---|---|
| **0 ms** — the scenario's current default, ~10/s | **0.2%, 5.4%, 69.5%** | 85.2–99.6% (n=10) | **3 of 6** |
| **250 ms** — ~3/s | **96.4%, 98.4%, 99.1%** | 99.8–100.0% | **3 of 3** |
| **1000 ms** — ~0.9/s | **98.6%, 98.6%, 98.9%** | 100.0% ×6 | **3 of 3** |

🆕 **The corrected denominator exposes something the broken one hid: a small residual gap.** Once
the machine can keep up, zero-arc authors sit at **96–99%** against a flat **100%** for full-arc —
**6 of 6 runs**. That is consistent with the extra hop a zero-arc author's data must make before
it is readable, and it is a lag of a handful of actions, not a collapse. **This is the honest
version of what §7.9 tried to claim:** the structural effect is real, consistent, and *small*;
the dramatic numbers were load.

**Throttle the writer even slightly and a zero-arc author is tracked as completely as a
full-arc one.** There is no structural zero-arc read penalty in this data. ⚠️ **Do not repeat
the §7.9 numbers anywhere.** They measure this Codespace under self-inflicted overload.

🆕 **The announcement-propagation unreliability was the same cause.** Complete writer coverage
went from 3-of-6 unthrottled to **3-of-3 at both throttled rates**. So §7.9's "only half the
runs achieve coverage" is also load, not a network property.

### 7.11 ✅ What actually survives — and it is a cleaner contribution

1. **The selection defect is real and independent of load.** The candidate set was measured
   directly at **exactly one** (§7.7's direct test). Selection races announcement propagation
   with no lower bound, so it *can* commit to a single peer. Under overload it does so every
   time. ⚠️ **Not established: whether it still bites at low load** — the throttled runs all
   had the fix active, so they cannot answer that. Say so.
2. **🆕 The scenario's default write rate overloads a single machine badly enough to destroy
   its own measurement.** At 0 ms it produced 0.2% visibility and half the runs without full
   coverage; at 250 ms everything is near-perfect. **And the sibling scenario
   `mixed_arc_must_get_agent_activity` already throttles** — batches of 10 then a 5s sleep,
   ~2/s — while `mixed_arc_get_agent_activity` has no throttle at all. A ~5× difference in
   write pressure between two scenarios in the same family, which also means **their results
   are not comparable with each other.** That reads as an oversight rather than a decision,
   and it is the easiest thing here for upstream to accept.
3. **`write_peers_visible_at_selection`** — turns a silent degradation into a recorded number.
4. **The fork rebase**: `feat/sharding-module-v3` onto kitsune2 `v0.5.0`, 6 commits, **zero
   conflicts** (branch `sharding-v3-on-v0.5.0`), answering §3 step 2.

⚠️ **Method note worth keeping.** The retraction came from asking "can we just run it slower?"
before publishing. A load-induced artefact and a structural finding look identical at one
operating point; **a rate sweep is cheap and separates them.** Do this before quoting any
number off a saturated machine — the sweep cost ~35 minutes and prevented a false claim.

---

## 8. Definition of done

**Shared prerequisite (blocks BOTH campaigns — see §7.1):**
- [x] Holochain 0.7.0 built from source, `--release`, with
      `--features unstable-functions,unstable-countersigning` — 13m02s, 2026-08-03
- [x] That conductor runs one upstream arc scenario to a non-empty operations summary
      (⚠️ check recorded operations, not exit code — §7.2 trap 1)

**Blocking Campaign B's validity — resolve BEFORE the comparison arm:**
- [ ] Establish what `open_connections` counts (peer gossip only, or bootstrap/relay too).
      The ThetaSinner comparison in §7.5 is uninterpretable until this is settled.
- [x] Direct test of the §7.7 mechanism — **DONE, mechanism confirmed.** Only ONE of three
      announced writers is ever a candidate, and it was a full-arc writer in both runs.
- [ ] 🔴 **Decide what to do about it, because it invalidates the scenario as a probe of the
      #214 question as currently run.** Readers never query a zero-arc author, so mixed-arc
      results do **not** cover the full-arc serving cost — the headline question. Options:
      periodic re-selection instead of once; forced peer assignment by behaviour; or a
      longer warm-up before readers select. ⚠️ Any of these is a **change to upstream's
      scenario**, so it trades the "measured in the maintainers' own harness" claim (§2) for
      a measurement that actually answers the question. **That trade is the real decision
      facing Campaign B — take it deliberately, and if the scenario is modified, say so
      plainly rather than implying an unmodified upstream run.**
- [ ] Consider reporting the single-candidate finding upstream — it affects anyone using
      these scenarios, and #214/#416 are the natural threads. Draft, do not send unsolicited.
- [ ] Decide whether read-side metrics can carry a comparison at all. Per-peer variation is
      12× within a single run (§7.6); write-side metrics (9–14% spread) are the usable ones.

**Campaign B — baseline, then comparison:**
- [x] Baseline: `mixed_arc_get_agent_activity`, stock kitsune2, 3 × 300s, with
      `--reporter in-memory-with-custom-metrics` — §7.5
- [ ] Baseline: the other six arc scenarios (only one of seven has been run)
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
