# Wind Tunnel workspace — V3 polite-shrink sharding experiment

Standalone Cargo workspace that runs the kitsune2 sharding module (V3 polite
shrink, [`feat/sharding-module-v3`](https://github.com/topeuph-ai/kitsune2/tree/feat/sharding-module-v3))
under [Wind Tunnel](https://github.com/holochain/wind-tunnel) on real iroh
transport, with live churn.

## Claim boundary — read first

Results from this workspace are **"measured under Wind Tunnel at the kitsune2
substrate layer over real iroh transport with live churn."** That is the layer
the sharding module lives at and the layer the kitsune team owns.

- This is **not** a full Holochain-conductor run. Holochain pins kitsune2 0.4.x;
  rebuilding it against the fork is out of scope.
- As of 2026-07-12 the settle and storm runs in `results/` are complete: V3
  **has now been measured under Wind Tunnel at this layer** (both verdicts
  PASS — see `results/REPORT.md` for exactly what that does and does not
  claim). Distinct, earlier claims: the standalone simulation (0 loss in 1248
  sweep runs + adversary) and the kitsune2 mem-transport storm test (4/4).
  Keep the three claims separate in every writeup.

## Layout and dependency shape

| Piece | Where it comes from |
|---|---|
| Wind Tunnel framework + `kitsune_wind_tunnel_runner` | git dep on `holochain/wind-tunnel`, pinned to `1cf7ebf` (first main rev binding kitsune2 `0.5.0-dev.4`; the crates.io 0.7.0 runner binds 0.4.1 and is a dead end) |
| `kitsune_client_instrumented` | vendored in `bindings/kitsune_client/` (from the same rev) because the experiment modifies it; `[patch]` on the git source points the runner at the vendored copy |
| `kitsune2_*` | `[patch.crates-io]` → local fork checkout (see prerequisites) |
| `scenarios/kitsune_arc_sharding` | the experiment scenario |

The `sharding` feature on `kitsune2_gossip` doubles as a patch canary: crates.io
gossip has no such feature, so the workspace only builds when the fork patch is
in effect.

This workspace is intentionally separate from `valichord/wind-tunnel/`
(crates.io runner against kitsune2 0.4.x + fragile ed25519/pkcs8 pins). Never
merge them, and never add this workspace to `valichord/Cargo.toml`.

## Prerequisites

- The sharding fork checked out at `/workspaces/kitsune2` on
  `feat/sharding-module-v3` (scaffolded against commit `82a5896`). The
  `[patch.crates-io]` paths in `Cargo.toml` resolve to
  `../../../../kitsune2/crates/*` relative to this directory — adjust there if
  your checkout lives elsewhere.
- Rust with edition-2024 support (1.85+).

## Build

```bash
export PATH="/home/codespace/.cargo/bin:$PATH"
cd research/arc_sim/wind_tunnel
cargo check --workspace
```

## Run

```bash
./run_experiment.sh settle    # main cohort only
./run_experiment.sh storm     # + churn cohort joining late and dying abruptly
```

The script builds the workspace, starts `bootstrap_relay` (one binary =
bootstrap **and** embedded iroh relay, built here so the whole experiment is
one `cargo build --workspace`), runs the main cohort with
`--reporter influx-file`, optionally runs the churn cohort (same `--run-id`,
which is the space id — same id = same DHT; its process exit is abrupt, so
survivors must detect the loss, brake, regrow, and hand off), then analyses.
Artifacts land in `runs/$RUN_ID/` (gitignored — curated results for the
writeup go to a `results/` dir like the sim's).

Everything is env-tunable: `AGENTS`, `DURATION`, `CHURN_AGENTS`,
`CHURN_DELAY`, `CHURN_DURATION`, `PROFILE` (`release`/`debug`), `RUN_ID`,
`PORT`, plus all `K2_SHARDING_*` knobs. The script refuses to run with
`K2_SHARDING_CLAMP_MIN_PEERS >= AGENTS`.

Analysis (`analysis/analyze_run.py`, stdlib-only; matplotlib optional for the
plot) applies the sim's ground-truth checks to the real network's declared
arcs on the real DHT sector grid (`SECTOR_SIZE` 2^23 → 512 sectors, the same
ring size the sim used): per-sector coverage over time using the storm test's
whole-sector containment rule, `floor(t)`, `zero_sectors(t)`, `frac_under R`,
plus the controller event timeline. Verdicts: continuous coverage (no sector
ever orphaned post-warmup) and final redundancy (floor ≥ R). Outputs
`summary.json`, `analysis.txt`, `floor.png`.

## Work items (from the 2026-07-12 plan)

1. ✅ This workspace: git-pinned framework, vendored client, fork patch, stub scenario builds.
2. ✅ Sharding config in the client: `K2ShardingModConfig` built from
   `K2_SHARDING_*` env vars (fail-loud parsing; unset = module defaults), and
   the initial storage-arc hint is `K2_INITIAL_ARC` = `full` (default) or
   `empty` — the controller owns the arc after join. **Every real run must set
   `K2_SHARDING_CLAMP_MIN_PEERS` below the agent count** (default 25 > planned
   12 agents, i.e. the controller would otherwise never engage).
3. ✅ Instrumented metrics (`bindings/kitsune_client/src/arc_metrics.rs`):
   - `arc_state` — every `K2_ARC_SAMPLE_INTERVAL_MS` (default 1000) each agent
     reports its declared arc (`get_cur_storage_arc`, the same surface the
     fork's storm test treats as authoritative): `arc_start`, `arc_end`,
     `arc_span`, `is_empty`, tagged `agent_id`.
   - `sharding_event` — a tracing layer (Wind Tunnel itself never installs a
     tracing subscriber, so the client owns the global default) converts the
     controller's structured events into metrics tagged
     `event` = `grow` | `shrink_intent` | `shrink_executed` |
     `intent_cancelled` | `peer_loss_cancel` | `other` and `agent_id`, with
     `level` and remaining event fields preserved. Unrecognised `sharding:`
     messages land in `other` with the message intact, so fork wording changes
     degrade visibly instead of dropping data.
   - Set `K2_LOG` (EnvFilter syntax, e.g. `kitsune2_gossip=debug`) to also
     print tracing output; `RUST_LOG` only reaches `log`-crate records.
4. ✅ Real scenario + churn orchestration + analysis (see **Run** above).
   Smoke-verified end to end (6 agents, 120 s settle, R=2, clamp 4, debug
   build): 53 controller events captured, 9 executed polite shrinks, mean arc
   span 1.000 → 0.500 → 0.833, coverage floor never below 2, zero orphaned
   sectors — both verdicts PASS. A smoke run is **not** a scientific result;
   item 5 does the real settle/storm runs at the plan's sizing.
5. ✅ Release runs at plan sizing (R=5, 12 agents, clamp 8; storm adds a
   6-agent churn cohort — 33% of the 18-agent peak — dying simultaneously).
   **Both runs: coverage floor never below 6 ≥ R, zero orphaned sectors,
   both verdicts PASS.** Full writeup with claim boundary and caveats (storm
   brake not exercised; `intent_send_failed` = benign self-connect artifact,
   fixed on the fork as `190e204`): `results/REPORT.md`. Reported upstream:
   [kitsune2#160 comment](https://github.com/holochain/kitsune2/issues/160#issuecomment-4951958041)
   (2026-07-12).
