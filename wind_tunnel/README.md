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
- Until the runs in this workspace complete, **V3 has not passed Wind Tunnel**
  and must not be described as having done so. What it has passed as of
  2026-07-12: the standalone simulation (0 loss in 1248 sweep runs + adversary)
  and the kitsune2 mem-transport storm test (4/4). Those are different claims —
  keep the distinction in every writeup.

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

## Run (once the scenario is real — work items 4–5)

One local binary provides bootstrap **and** iroh relay — the fork's
`bootstrap_srv` embeds the relay (protocol V2):

```bash
cargo run --manifest-path /workspaces/kitsune2/Cargo.toml -p kitsune2_bootstrap_srv
```

Then, sized per the plan (R = 5, ~12 in-process agents — Wind Tunnel kitsune
agents are tokio tasks, not conductors):

```bash
cargo run -p kitsune_arc_sharding -- --agents 12 --duration 300
```

Churn cohort: a second, short `--duration` invocation against the same
bootstrap server; its exit forces unresponsive-marking, regrow, handoff, and
the storm brake on the survivors.

## Work items (from the 2026-07-12 plan)

1. ✅ This workspace: git-pinned framework, vendored client, fork patch, stub scenario builds.
2. ✅ Sharding config in the client: `K2ShardingModConfig` built from
   `K2_SHARDING_*` env vars (fail-loud parsing; unset = module defaults), and
   the initial storage-arc hint is `K2_INITIAL_ARC` = `full` (default) or
   `empty` — the controller owns the arc after join. **Every real run must set
   `K2_SHARDING_CLAMP_MIN_PEERS` below the agent count** (default 25 > planned
   12 agents, i.e. the controller would otherwise never engage).
3. Instrumented metrics: arc-width sampling per tick + shrink-intent events.
4. Real `kitsune_arc_sharding` scenario + churn cohort + post-run coverage/floor
   analysis (the sim's floor check applied to real metrics).
5. Runs mirroring the sim's settle/storm settings, writeup, update kitsune2#160.
