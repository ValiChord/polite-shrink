# polite-shrink — dynamic DHT storage-arc sizing that survives churn

**The problem:** Holochain's DHT disabled dynamic sharding in 2021 after
arc-resizing oscillation ("the hallway dance") caused data loss — every node
has stored the full DHT since ([kitsune2 issue
#160](https://github.com/holochain/kitsune2/issues/160)). Full arcs cap how
large a network can grow.

**The contribution:** a two-phase **"polite shrink"** controller — announce an
intent to vacate, wait out gossip staleness, re-check with a deterministic
TCAS-style tie-break, and only then drop — plus an expanding-ring repair rule
for sparse networks. Designed by ablation, then attacked from every direction
we could think of. It hasn't lost a sector yet:

## Evidence at a glance

| Evidence class | Result |
|---|---|
| **1,248-run robustness sweep** (312 seeds × 4 scenarios, paired against 3 weaker controllers) | **0 sectors lost** (95% UB < 0.24%); weakest controller lost data in 95.9% of runs ([REPORT.md](REPORT.md)) |
| **Evolutionary adversarial search** (same kill budget, free choice of who/when, 20 generations) | broke the damped and jittered controllers; **could not make polite shrink lose a single sector** |
| **Reference implementation** on a kitsune2 fork ([`feat/sharding-module-v3`](https://github.com/topeuph-ai/kitsune2/tree/feat/sharding-module-v3), behind the existing `sharding` feature flag) | 8-node storm test on the in-memory transport: shard down, kill 3 of 8, recover to target — no sector ever orphaned |
| **Wind Tunnel measurements — real iroh transport, live churn** ([wind_tunnel/results/REPORT.md](wind_tunnel/results/REPORT.md)) | 33% of the network killed simultaneously at the worst moment: **zero orphaned sectors, zero of 23k+ published ops lost**; the storm brake cancelled all 9 stale-view shrink intents at detection |
| **Stage-3 robustness studies** ([REPORT_stage3.md](REPORT_stage3.md)) | netsplits + heal: zero durability loss; forged intents: fail-safe (cost-only); scale to 5,000 agents: zero loss where the damped controller loses data; the residual shrink-race measured at 0.002% of holes and transient; the sparse-network deadlock found real and fixed (V4 repair: 120/120 recovery) |
| **Upstream findings from doing the work** | kitsune2's mem transport violated its unresponsive-marking contract (fixed, [PR #572](https://github.com/holochain/kitsune2/pull/572)); a broadcast head-of-line liveness bug only real transport could surface (fixed on the fork) |

**What we don't claim:** these are simulation + kitsune2-substrate
measurements on one machine — not a Holochain-conductor deployment, not WAN.
The false-coverage (liar) attack defeats *any* declaration-trusting
controller past K = R liars — that needs sensor integrity, not control law
([REPORT_stage3.md §2](REPORT_stage3.md)). Every number above is
one-command reproducible; see [Run it](#run-it) and `REPRODUCE.md`.

## The write-ups

- **[REPORT.md](REPORT.md)** — the main study: methodology, the 4,992-sim
  sweep, adversarial search, the reference implementation and its findings
  (§6 is the "what simulation hid" section), limitations.
- **[wind_tunnel/results/REPORT.md](wind_tunnel/results/REPORT.md)** — real
  iroh transport under Wind Tunnel: settle, storm, timed-storm; op-level
  reachability verdicts; flake accounting.
- **[REPORT_stage3.md](REPORT_stage3.md)** — partitions, Byzantine agents,
  scale, the §6.1 race quantified, and the §6.2 repair rule simulated
  before implementation.

**The problem in one question:** how should each node in a DHT decide how
much of the keyspace to store (its "storage arc"), using only stale gossip
information, without a coordinator, while never letting any data drop below
a redundancy target R? The sections below describe the Stage-1 simulation
core that answers it; `wind_tunnel/` and the fork carry the answer onto a
real network stack.

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
| **V4 polite+repair** *(Stage 3)* | + expanding-ring repair: a hole in the level+g ancestor block motivates growth after `grow_need + (g−1)·2·lag` persistence — ring-near agents move first, distant timers reset when the hole closes | expanding-ring search (ad-hoc routing) |

V0–V3 are the Stage-1 ablation (results below). **V4 is the Stage-3 addition**
(`repair_sim.py`, REPORT_stage3.md §4): it fixes the sparse-network recovery
deadlock the clamp otherwise papers over (V3 without the clamp: stuck 5/90
port-scale seeds; V4: 120/120 recovered, no herding, zero loss across the
regression battery). Trade-off to know: V4 tracks the target more tightly
(~R+1 vs V3's accidental ~2R over-provisioning), so provision R explicitly
for the storm margin you want — V4 at R+1 dominated V3 at R in our runs.

## Scenarios

1. **activation** — sharding turns on in a full-arc network (today's reality → sharded).
2. **storm** — 30% of agents die simultaneously at equilibrium.
3. **flashcrowd** — 60% more agents join at once.
4. **churn** — continuous ~4%-per-100-ticks turnover.

## Stage-1 results (seed 42; see `results/summary.md`, plots in `results/`)

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
python3 run_experiments.py          # Stage 1: ~45 s, results/*.png + summary.md
python3 check_seeds.py              # Stage 1: seed-robustness check
./run_stage3.sh                     # Stage 3: all five studies, ~40 min on 8 cores
```

Exact expected numbers and environment pins: `REPRODUCE.md`. The Wind Tunnel
harness (`wind_tunnel/`) needs the kitsune2 fork cloned as a sibling
directory — see `wind_tunnel/README.md`.

## Honest limitations of the Stage-1 model (and what later stages closed)

- Full peer visibility (no partial peer discovery); one lag per viewer, not
  per pair. *Partitions/netsplits are now tested in Stage 3
  (`partition_sim.py`); per-pair asymmetric reachability remains unmodelled.*
- The Stage-1 simulator itself assumes honest agents. *Byzantine behaviour —
  forged intents and false coverage declarations — is now tested in Stage 3
  (`byzantine_sim.py`); see REPORT_stage3.md §2 for what each attack can and
  cannot do.*
- Sync time linear in sectors; no bandwidth contention; deaths are instant
  (no graceful leave).
- Instantaneous storm kill means *some* post-storm floor dip is unavoidable —
  what's measured is how controllers respond, not whether dips can be prevented.
- Quantised aligned blocks are a simplification of kitsune2's actual arc
  mechanics; "ticks" are abstract time.
- Findings are simulation evidence about this rule-set, not proofs; the V2
  result in particular may be specific to the exact shrink rule used here.

Where the programme stands: the Stage-2 port to a kitsune2 fork is done
(`REPORT.md`), measured under Wind Tunnel on real iroh transport with live
churn (`wind_tunnel/results/REPORT.md`), and the open risks from REPORT.md §7
are tested in Stage 3 (`REPORT_stage3.md`).

---

> **Provenance:** this research began as `research/arc_sim/` on the
> [ValiChord repo's research branch](https://github.com/ValiChord/ValiChord/tree/research/dht-arc-sharding-sim/research/arc_sim)
> (full commit history preserved here). Links already published to that
> location remain valid; this repository is the canonical home from
> 2026-07-13 on. Research directed by Ceri John (topeuph-ai); design
> elaboration, implementation, and analysis with AI assistance (Claude,
> Anthropic); all results human-reviewed. Citation: `CITATION.cff`.
