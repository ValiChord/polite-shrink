# arc_sim — DHT storage-arc controller simulation

> **Full scientific write-up: [`REPORT.md`](REPORT.md)** — methodology, results
> (4,992-sim sweep + adversarial search), the kitsune2 reference
> implementation, findings, and limitations, with a complete artifact
> inventory for reproduction.

**What this is:** a Stage-1 simulation study of the *dynamic sharding* problem
Holochain has parked ([kitsune2 issue #160](https://github.com/holochain/kitsune2/issues/160)):
how should each node in a DHT decide how much of the keyspace to store (its
"storage arc"), using only stale gossip information, without a coordinator,
while never letting any data drop below a redundancy target R?

This is **not** kitsune2 code and runs no network. It models the control-loop
dynamics only, to test which controller ingredients prevent the arc-resizing
oscillation ("the hallway dance") that led Holochain to disable sharding.

## Model

- Ring of 512 sectors; ~200 agents; each agent claims an *aligned power-of-two
  block* of sectors containing its fixed home sector (kitsune's quantised-arc
  design — the only per-agent state is the block "level").
- Redundancy target **R = 5** copies of every sector.
- Each agent sees peers' declared arcs with a fixed per-agent **gossip lag**
  (8–24 ticks) — decisions always use stale information.
- Growing costs sync time proportional to sectors fetched; shrinking is free
  but instantly reduces coverage.

## Controller variants (the ablation)

| | Ingredient added | Idea imported from |
|---|---|---|
| **V0 naive** | react immediately to the stale view | — (the strawman) |
| **V1 damped** | act only after the condition persists ≥ K × *own measured lag* (grow 1×, shrink 4× — "grow eager, shrink slow") | control theory: react slower than your information is stale |
| **V2 +jitter** | desynchronised decision epochs | TCP-RED: break lockstep reactions |
| **V3 polite** | two-phase shrink: announce intent, wait 2× max lag, re-check counting all lower-priority intenders as already gone, lowest-id proceeds | TCAS tie-break + self-stabilization ("never vacate before your replacement is confirmed") |

## Scenarios

1. **activation** — sharding turns on in a full-arc network (today's reality → sharded).
2. **storm** — 30% of agents die simultaneously at equilibrium.
3. **flashcrowd** — 60% more agents join at once.
4. **churn** — continuous ~4%-per-100-ticks turnover.

## Results (seed 42; see `results/summary.md`, plots in `results/`)

| Finding | Evidence |
|---|---|
| Naive control reproduces the oscillation exactly | V0 never settles in any scenario, floor repeatedly hits 0 (data loss), ~15× the resize traffic and sync cost |
| Lag-scaled hysteresis does most of the stabilising | V1 cuts resizes ~15×, eliminates loss in most runs |
| **Jitter alone is unreliable — sometimes harmful** | across seeds, V2 *caused* loss in 3 of 4 storm runs where V1 had none: staggered unilateral drops erode the floor in a slow drip that synchronized drops don't |
| The two-phase handoff is what buys safety | **V3: zero data loss in all 8 runs (4 seeds × 2 scenarios + main run)**; during activation its floor never dips below R at all; lowest under-replication exposure everywhere |

Robustness: `check_seeds.py` repeats activation+storm on seeds 7/99/1234 —
the ordering holds (V0 always loses data; V3 never does).

## Run it

```bash
pip install numpy matplotlib
python3 run_experiments.py          # ~45 s, writes results/*.png + summary.md
python3 check_seeds.py              # seed-robustness check
```

## Honest limitations (Stage-1 by design)

- Full peer visibility (no partial peer discovery); one lag per viewer, not per pair.
- Honest, non-adversarial agents; no Byzantine behaviour.
- Sync time linear in sectors; no bandwidth contention; deaths are instant
  (no graceful leave).
- Instantaneous storm kill means *some* post-storm floor dip is unavoidable —
  what's measured is how controllers respond, not whether dips can be prevented.
- Quantised aligned blocks are a simplification of kitsune2's actual arc
  mechanics; "ticks" are abstract time.
- Findings are simulation evidence about this rule-set, not proofs; the V2
  result in particular may be specific to the exact shrink rule used here.

Next step if pursued: port the V3 controller sketch to a kitsune2 fork behind
a feature flag, using its in-memory test transport (Stage 2), and offer the
measurement scenarios upstream.
