# polite-shrink — dynamic DHT storage-arc sizing that survives churn

> ## Using the polite-shrink pattern, the arc-shrink race that forced Holochain to disable sharding in 2021 can no longer cause data loss — proven by exhaustive model checking, not just tested.
>
> *Scope, stated plainly: this is the honest-node control-loop safety property — a sector never drops below its redundancy target R — machine-checked over **every reachable state** for networks up to N = 8 (R from 1 to 7), then argued to generalise per-sector. The naive 2021 rule fails the same check with a counterexample. Robustness to adversaries and to real networks is shown by the simulations and kitsune2-fork runs below — strong evidence, not proof. Proof details: [`spec/`](spec/).*

> ### 👉 The contribution is two files
> - **[`polite_shrink.py`](polite_shrink.py)** — the polite-shrink controller itself. The whole idea is ~30 lines: `_decide` (announce an intent to vacate instead of dropping) and `_execute_intent` (wait out gossip staleness, re-check, then a lowest-id-proceeds tie-break).
> - **[`repair_sim.py`](repair_sim.py)** — the V4 expanding-ring repair extension (Stage 3), a subclass that adds recovery for sparse networks.
>
> Every other `.py` file is a study that *attacks* those two — sweeps, an evolutionary adversary, partitions, Byzantine agents, scale, the shrink-race. See [Where is the code?](#where-is-the-code) for the full map.

**The problem:** Holochain's DHT disabled dynamic sharding in 2021 after
arc-resizing oscillation ("the hallway dance") caused data loss — every node
has stored the full DHT since ([kitsune2 issue
#160](https://github.com/holochain/kitsune2/issues/160)). Full arcs cap how
large a network can grow.

**The contribution:** a two-phase **"polite shrink"** controller — announce an
intent to vacate, wait out gossip staleness, re-check with a deterministic
TCAS-style tie-break, and only then drop — plus an expanding-ring repair rule
for sparse networks. Designed by ablation, then attacked from every direction
we could think of.

> **The empirical record: not one sector lost.** Across every test where nodes
> behave honestly — a 1,248-run sweep (0 lost vs 95.9% for the naive
> controller), an evolutionary adversary that couldn't break it, network
> partitions, scale to 5,000 agents, and 33% of the network killed at once on
> real iroh transport (0 of 23k+ ops lost) — polite-shrink has never dropped a
> sector below the redundancy target R, and the core safety property is
> formally proven. The *only* failure mode is nodes that **lie** about what
> they store — a sensor problem no controller can out-think — and the
> proof-gated **verified-coverage** extension drives even that to zero data
> loss.

## Evidence at a glance

| Evidence class | Result |
|---|---|
| **1,248-run robustness sweep** (312 seeds × 4 scenarios, paired against 3 weaker controllers) | **0 sectors lost** (95% UB < 0.24%); weakest controller lost data in 95.9% of runs ([REPORT_stage1.md](REPORT_stage1.md)) |
| **Evolutionary adversarial search** (same kill budget, free choice of who/when, 20 generations) | broke the damped and jittered controllers; **could not make polite shrink lose a single sector** |
| **Reference implementation** on a kitsune2 fork ([`feat/sharding-module-v3`](https://github.com/topeuph-ai/kitsune2/tree/feat/sharding-module-v3), behind the existing `sharding` feature flag) | 8-node storm test on the in-memory transport: shard down, kill 3 of 8, recover to target — no sector ever orphaned |
| **Wind Tunnel measurements — real iroh transport, live churn** ([wind_tunnel/results/REPORT_stage2_wind_tunnel.md](wind_tunnel/results/REPORT_stage2_wind_tunnel.md)) | 33% of the network killed simultaneously at the worst moment: **zero orphaned sectors, zero of 23k+ published ops lost**; the storm brake cancelled all 9 stale-view shrink intents at detection |
| **Stage-3 robustness studies** ([REPORT_stage3.md](REPORT_stage3.md)) | netsplits + heal: zero durability loss; forged intents: fail-safe (cost-only); scale to 5,000 agents: zero loss where the damped controller loses data; the residual shrink-race measured at 0.002% of holes and transient; the sparse-network deadlock found real and fixed (V4 repair: 120/120 recovery); Byzantine defenses measured — range-validation cuts the forgery cost attack to ~4% (and is implemented on the fork), the serve-audit fully rescues a liar-collapsed network, and **proof-gated "verified coverage" removes the K=R liar ceiling entirely** — flat, zero-loss at every K from 0 to 3R, at a bandwidth cost the operator sets (≈13–16% at adequate audit budget); and **partial liars** (store a strategic fraction, serve some challenges) still cause **zero data loss**, with a mid-fraction margin dip that a higher audit sample-count restores |
| **Formal safety proof** ([spec/](spec/), TLA+/TLC) | "a sector never drops below R" **model-checked exhaustively** — every reachable state, no violation, for N up to 8 (R from 1 to 7); the naive 2021 rule fails the same check with a counterexample, isolating the two-phase tie-break as what buys safety |
| **Upstream findings from doing the work** | kitsune2's mem transport violated its unresponsive-marking contract (fixed, [PR #572](https://github.com/holochain/kitsune2/pull/572)); a broadcast head-of-line liveness bug only real transport could surface (fixed on the fork) |

**What we don't claim:** these are simulation + kitsune2-substrate
measurements on one machine — not a Holochain-conductor deployment, not WAN.
On liars (false coverage declarations): both the attack *and* its defenses
are measured — past K = R phantom declarations any declaration-trusting
controller loses data; the serve-audit rescues even a K = 2R collapse, and
proof-gated verified coverage removes the threshold outright (flat and
zero-loss to K = 3R, [REPORT_stage3.md §6–§7](REPORT_stage3.md)) — but both
defenses exist only in simulation so far, so a *deployed* network's honest
margin today is still R − K until the audit ships on the fork. Every number above is one-command reproducible; see
[Run it](#run-it) and `REPRODUCE.md`.

## The write-ups

- **[REPORT_stage1.md](REPORT_stage1.md)** — the main study: methodology, the 4,992-sim
  sweep, adversarial search, the reference implementation and its findings
  (§6 is the "what simulation hid" section), limitations.
- **[wind_tunnel/results/REPORT_stage2_wind_tunnel.md](wind_tunnel/results/REPORT_stage2_wind_tunnel.md)** — real
  iroh transport under Wind Tunnel: settle, storm, timed-storm; op-level
  reachability verdicts; flake accounting.
- **[REPORT_stage3.md](REPORT_stage3.md)** — partitions, Byzantine agents,
  scale, the §6.1 race quantified, the §6.2 repair rule simulated before
  implementation, (§7) proof-gated *verified coverage* closing the
  false-declaration liar gap, (§8) *partial* liars and the audit-sample knob,
  and (§9) the TLA+ formal safety proof.
- **[spec/README.md](spec/README.md)** — the formal proof: the two-phase rule
  model-checked safe over every reachable state, the naive rule falsified.

## Where is the code?

Two places, by design:

- **The rule, as proven** (Python, this repo): the entire polite-shrink
  mechanism is ~30 lines — [`polite_shrink.py`](polite_shrink.py), `_decide` (phase 1:
  announce the vacate intent instead of dropping) and `_execute_intent`
  (phase 2: after the wait, re-check the vacated half counting every
  lower-priority intender as already gone; proceed only if still ≥ R).
  The V4 expanding-ring repair extension is [`repair_sim.py`](repair_sim.py).
  Everything else here is the machinery for attacking those lines.
- **The rule, as deployable** (Rust, kitsune2 fork):
  [`crates/gossip/src/sharding/`](https://github.com/topeuph-ai/kitsune2/tree/feat/sharding-module-v3/crates/gossip/src/sharding)
  on branch `feat/sharding-module-v3` — ~1,300 lines behind kitsune2's
  existing `sharding` feature flag, with `ShrinkIntent` as a wire message
  on the `k2sharding` module channel, plus the storm brake, the
  small-network clamp, and receiver-side range-validation of intents
  (the forged-intent defense measured in REPORT_stage3.md §6). It lives on the fork because it is a module *inside* kitsune2's
  crate structure, offered upstream via
  [#160](https://github.com/holochain/kitsune2/issues/160); the
  `wind_tunnel/` harness here measures it over real transport.

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

> **TCAS?** The Traffic Collision Avoidance System in aircraft cockpits.
> When two planes converge, both get *coordinated, complementary* orders —
> one climbs, the other descends — picked by a deterministic tie-break on
> transponder ID, never negotiated in the moment. It exists because the
> failure mode of symmetric reactions is exactly the hallway dance: two
> people blocking a corridor, each stepping aside to the same side, again
> and again. The 2021 arc oscillation was nodes doing the hallway dance
> with storage arcs — everyone reacting identically to the same stale
> coverage picture. The polite-shrink tie-break applies TCAS's cure to
> shrinking: when two nodes contend to vacate the same sectors, identity
> (lowest agent ID) decides who proceeds and who defers — symmetry broken
> by rule, not by timing or luck.

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

## Stage-2 results — the controller on real iroh transport (Wind Tunnel)

Stage 1 is simulation. Stage 2 puts the *same* controller — ported into a
kitsune2 fork behind the existing `sharding` flag — onto **real iroh transport
with live connection churn**, and measures it under Wind Tunnel. This is where
"survives on the model" becomes "survives on the wire." Full report:
[wind_tunnel/results/REPORT_stage2_wind_tunnel.md](wind_tunnel/results/REPORT_stage2_wind_tunnel.md).

| Finding | Evidence |
|---|---|
| Coverage stayed continuous through a **33% simultaneous node loss** on real transport | floor never below 6 (≥ R=5), including through the mass death; **0 orphaned sectors; 0 of 23,745 published ops lost** |
| The **storm brake** caught the §6.1 intent-death race in the wild | in the timed-storm run, six agents die and the brake cancels **nine** pending shrink intents that had been announced into the die-off on stale views — none executed |
| Real transport surfaced a bug simulation could not | a broadcast head-of-line **liveness bug**, invisible to the in-memory sim, found and fixed on the fork — plus an upstream mem-transport contract bug fixed ([PR #572](https://github.com/holochain/kitsune2/pull/572)) |
| Sharding actually happens (not just "doesn't break") | equilibrium arc span shrinks to ~0.58–0.63 of full (≈1.6–1.7× gain at N=12, growing with N) while the floor holds above R |

## Stage-3 results — adversaries, scale, repair, and the one real gap

Stage 3 attacks the controller along the four threats [REPORT_stage1.md](REPORT_stage1.md)
§7 left open, then the Byzantine "liar" problem and a formal proof — nine
studies, one command (`./run_stage3.sh`). Full report:
[REPORT_stage3.md](REPORT_stage3.md).

| Question | Answer |
|---|---|
| Netsplit + heal — is data lost? | **No durability loss in 9/9 runs**; V3's floor never left R, and the heal-time shrink storm is absorbed. Flapping partitions defeat the damped controller (V1), not polite shrink. |
| Forged shrink-intents? | **Fail-safe by construction and measurement** — worst-case forgery is a *cost* attack (2.3× sync, zero loss); receiver-side range-validation cuts it to ~4% and is **implemented on the fork**. |
| Does it survive scale? | **V3 to N=5,000** (rings up to 16,384 sectors), zero loss, per-agent cost flat — where the damped controller starts losing data at **N ≥ 2,000**. |
| The sparse-network recovery deadlock? | Real (V3 without the clamp stuck in 5/90 port-scale seeds); **V4 expanding-ring repair recovers 120/120**, still sharding, no thundering herd. |
| How often does the shrink-race actually bite? | Shrink-executed holes = **0.002% at R=5** (≥99.9% of all holes are generic churn outrunning recovery, not a controller defect), and all transient (median 23 ticks). |
| Nodes that **lie** about what they store? | The one real gap: past **K=R** phantom declarations, data is lost invisibly — sensor integrity, not control. Proof-gated **verified coverage** removes the threshold (zero loss to K=3R); *partial* liars cause zero data loss with a tunable audit-sample knob. |
| Provable, not just tested? | **Yes** — TLA+/TLC checks "a sector never drops below R" over *every* reachable state (N ≤ 8, R 1–7); the naive 2021 rule fails the same check with a counterexample. |

## Run it

```bash
pip install numpy matplotlib
python3 run_experiments.py          # Stage 1: ~45 s, results/*.png + summary.md
python3 check_seeds.py              # Stage 1: seed-robustness check
./run_stage3.sh                     # Stage 3 + follow-ups: nine studies, ~80 min on 8 cores
java -cp tla2tools.jar tlc2.TLC spec/PoliteShrink.tla   # formal proof (needs JRE + tla2tools.jar)
```

Exact expected numbers and environment pins: `REPRODUCE.md`. The Wind Tunnel
harness (`wind_tunnel/`) needs the kitsune2 fork cloned as a sibling
directory — see `wind_tunnel/README.md`.

## Honest limitations

What still holds today, after Stage 3 — stated as current constraints, not history:

- **The Byzantine defenses are simulated, not yet deployed.** The controller
  runs on a kitsune2 fork, but the two defenses against nodes that lie about
  what they store — the serve-audit and proof-gated verified coverage
  (REPORT_stage3.md §6–§8) — exist only in simulation so far. So a *deployed*
  network's honest margin against false-coverage declarations is still R − K
  until the audit ships. Partial liars are now measured (§8): still zero data
  loss, but a margin dip at intermediate held-fractions that a higher audit
  sample-count restores. The temporal *prove-then-drop* trojan remains future
  work.
- **Reachability is modelled coarsely.** One gossip lag per viewer, not per
  pair; partitions are binary. Per-pair asymmetric reachability is unmodelled.
- **Model idealisations.** Sync time is linear in sectors with no bandwidth
  contention; deaths are instant (no graceful leave); arcs are quantised
  aligned blocks (a simplification of kitsune2's real mechanics); "ticks" are
  abstract time.
- **Storm dips are inherent to the test, by design.** An instantaneous mass
  kill makes *some* post-storm floor dip unavoidable; the metric is how the
  controller responds, not whether dips can be prevented.
- **Most findings are simulation evidence, not proof.** The *core safety*
  property ("never vacate a sector below R") is now formally model-checked
  (§9), but the broader results — costs, adversary outcomes, the surprising V2
  finding that jitter *without* the handoff is harmful — characterise this
  rule-set on this model, not theorems, and may be specific to it.

For the other side of the ledger — what the controller has been shown to
**withstand** (33% of the network killed at once on real transport, an
evolutionary adversary, network partitions, forged intents, scale to 5,000
agents, and false-coverage liars) — see [Evidence at a glance](#evidence-at-a-glance)
above. The Stage-2 port to a kitsune2 fork is done (`REPORT_stage1.md`) and
measured under Wind Tunnel on real iroh transport with live churn
(`wind_tunnel/results/REPORT_stage2_wind_tunnel.md`).

---

> **Provenance:** this research began as `research/arc_sim/` on the
> [ValiChord repo's research branch](https://github.com/ValiChord/ValiChord/tree/research/dht-arc-sharding-sim/research/arc_sim)
> (full commit history preserved here). Links already published to that
> location remain valid; this repository is the canonical home from
> 2026-07-13 on. Research directed by Ceri John (topeuph-ai); design
> elaboration, implementation, and analysis with AI assistance (Claude,
> Anthropic); all results human-reviewed. Citation: `CITATION.cff`.
