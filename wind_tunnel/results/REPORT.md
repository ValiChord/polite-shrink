# V3 polite shrink under Wind Tunnel — kitsune2 substrate layer, real iroh transport

**Date:** 2026-07-12
**Code:** ValiChord repo `research/dht-arc-sharding-sim` @ `9fa05a3` (this workspace);
kitsune2 fork `topeuph-ai/kitsune2` `feat/sharding-module-v3` @ `82a5896`;
`holochain/wind-tunnel` @ `1cf7ebf` (git-pinned bindings).
**Machine:** one GitHub Codespace, 8 cores / 32 GB; all agents in-process
(Wind Tunnel kitsune agents are tokio tasks), iroh transport through a local
bootstrap + embedded relay.

## Claim boundary

These results are **measurements of the V3 sharding controller under Wind
Tunnel at the kitsune2 substrate layer, over real iroh transport, with live
churn** — the layer the sharding module lives at.

They are **not**:

- a full Holochain-conductor run (Holochain pins kitsune2 0.4.x; rebuilding it
  against the fork is out of scope);
- a WAN measurement — transport, relay, and connection lifecycle are real
  iroh, but all endpoints share one machine, so latencies are LAN-scale;
- an op-level data-loss measurement — the verdicts are about *declared
  coverage* (the same ground truth the simulation scored);
- statistics — one run per scenario. The sim carries the statistical load
  (0/1,248 across 312 seeds × 4 scenarios); these runs test whether its
  assumptions survive a real network stack.

## Setup

| | settle | storm |
|---|---|---|
| main cohort | 12 agents, 600 s | 12 agents, 600 s |
| churn cohort | — | 6 agents join at t≈241 s, all die simultaneously at t≈363 s (33% of the 18-agent peak) |
| R (target redundancy) | 5 | 5 |
| clamp_min_peers | 8 | 8 |
| controller timing | module defaults (the port's real-time equivalents of the sim constants: grow 1.0× / shrink 4.0× staleness, intent wait 2.5×, min 10 s, check 5 s) | same |
| publish load | 3 ops per agent per ~1 s (jittered) | same |
| sector grid | 512 sectors (`SECTOR_SIZE` 2^23) — identical to the sim's ring | same |

Churn-cohort deaths are process exits with no leave/unregister — from the
survivors' perspective the peers vanish mid-conversation.

## Results

| metric | settle | storm |
|---|---|---|
| polite shrinks executed | 10 | 12 |
| shrink intents announced | 18 | 18 |
| intents cancelled at re-check | 8 | 6 |
| grow events | 1 | 2 |
| mean arc span (post-warmup) | 1.000 → 0.625 | 0.917 → min 0.444 → 0.583 after deaths |
| coverage floor (post-warmup) | **never below 6** | **never below 6, including through the mass death** |
| orphaned sectors (any time post-warmup) | **0** | **0** |
| final-60 s floor vs R=5 | 6 ≥ 5 PASS | 6 ≥ 5 PASS |
| continuous coverage verdict | **PASS** | **PASS** |
| ops published / received (context) | 21,546 / 145,159 | 23,745 / 227,656 |

Storm timeline (see `storm-r5-a12-c6-1/floor.png`): the main cohort declares
FULL (coverage 12), polite-shrinks to span 0.75 by t≈240; the churn cohort
joins and declares FULL (coverage peaks at 14, and the denser network lets
survivors shrink further, span min 0.444); at t≈363 all six churn agents die
at once — coverage steps from 14 to 6 with **no transit below R and no
orphaned sector**, and the controller correctly does *not* regrow (floor 6 ≥
R=5, so growth would be waste).

## Findings

1. **Declared coverage was continuous through a 33% simultaneous node loss on
   a real transport.** The property the sim sweep and the adversarial search
   established — shrink politely enough that mass death never lands on a
   thinly-covered ring — held under real iroh connection churn.

2. **The storm brake was not exercised here.** All shrink intents had
   resolved (~4 min before the deaths), so no `peer_loss_cancel` events fired
   — there was nothing pending to cancel. The intent-death race (§6.1 of the
   main report) is covered by the mem-transport storm test, which times
   deaths against in-flight intents deliberately; these runs demonstrate
   equilibrium robustness, not the race. A storm variant with deaths timed
   into the intent window is the natural follow-up.

3. **Every one of the 18/18 `intent_send_failed` events is a self-connect
   artifact, not a delivery failure.** The intent broadcast loop includes the
   sender's own peer URL and iroh refuses `Connecting to ourself` — exactly
   one failure per intent, error string identical in all 36 events across
   both runs. Delivery to *other* peers never failed. Fork TODO: skip local
   agents' URLs in the broadcast loop (cosmetic; the controller already
   inserts its own intent into its local table).

4. **Equilibrium sharding gain at N=12 is ~1.6–1.7×** (mean span 0.583–0.625
   vs FULL) with floor comfortably above R — consistent with the shrink
   condition's arithmetic at this density (dropping half the ring needs >R
   holders on every dropped sector). The gain grows with N; N=12 is the
   plan's sizing for a single-machine run, not a scaling claim.

## Reproduce

```bash
cd research/arc_sim/wind_tunnel
PROFILE=release AGENTS=12 DURATION=600 RUN_ID=settle-r5-a12-1 \
K2_SHARDING_TARGET_REDUNDANCY=5 K2_SHARDING_CLAMP_MIN_PEERS=8 \
./run_experiment.sh settle

PROFILE=release AGENTS=12 DURATION=600 CHURN_AGENTS=6 CHURN_DELAY=240 \
CHURN_DURATION=120 RUN_ID=storm-r5-a12-c6-1 \
K2_SHARDING_TARGET_REDUNDANCY=5 K2_SHARDING_CLAMP_MIN_PEERS=8 \
./run_experiment.sh storm
```

Prerequisite: the fork checked out at `/workspaces/kitsune2` on
`feat/sharding-module-v3` @ `82a5896` (see workspace README). Each results
subdirectory holds the run's `analysis.txt`, full per-second `summary.json`
timeline, `floor.png`, the runner's `run_summary.jsonl` (captured env), and
the gzipped raw influx metrics. Timing-dependent numbers (event counts, exact
spans) will vary between runs; the verdicts are the reproducible claim.
