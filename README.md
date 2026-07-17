# Polite-Shrink — a Proposed Sharding Solution for Holochain's DHT

> ## Using the polite-shrink pattern, the stale-view arc-shrink race — the one that damping the 2021 "hallway dance" leaves wide open — can no longer cause data loss. Proven by exhaustive model checking, not just tested.
>
> *Scope, stated plainly: this is the honest-node control-loop safety property — a sector never drops below its redundancy target R — machine-checked over **every reachable state** for networks up to N = 8 (R from 1 to 7), then argued to generalise per-sector. The naive rule (no wait, no tie-break) fails the same check with a counterexample. What is proven is the **gate** (the pre-drop re-check), not the surrounding **policy** (redundancy target, hysteresis constants, growth rule, clamp) — that part is engineering judgement, evidenced by simulation. Robustness to adversaries and to real networks is shown by the simulations and kitsune2-fork runs below — strong evidence, not proof. Proof details: [`spec/`](spec/).*

> ### 👉 The contribution is two files
> - **[`polite_shrink.py`](polite_shrink.py)** — the polite-shrink controller itself. The whole idea is ~30 lines: `_decide` (announce an intent to vacate instead of dropping) and `_execute_intent` (wait out gossip staleness, re-check, then a lowest-id-proceeds tie-break).
> - **[`repair_sim.py`](repair_sim.py)** — the V4 expanding-ring repair extension (Stage 3), a subclass that adds recovery for sparse networks.
>
> Every other `.py` file is a study that *attacks* those two — sweeps, an evolutionary adversary, partitions, Byzantine agents, scale, the shrink-race. See [Where is the code?](#where-is-the-code) for the full map.

**The problem:** during Holochain's 2021 sharding tests, nodes reacting to each
other's arc changes from slightly stale views produced *oscillation* — the
["hallway dance"](https://blog.holochain.org/testing-sharding/) (Dev Pulse 107,
13 Nov 2021, Holochain's own analogy). What that write-up never recorded is what
the oscillation **cost**. This study measures it — and the answer is sharper
than "oscillation loses data":

> **Damping the oscillation doesn't stop the loss.** Hysteresis cuts the
> data-loss rate from 95.9% of runs to 24%, and decision-epoch jitter — the
> textbook remedy for control-loop oscillation — adds nothing at all (24.3%).
> What actually destroys data is a race the oscillation merely *accompanies*:
> two agents, each acting on a stale view, abandon the same sector at the same
> moment. That race survives every damping fix we tried. Closing it takes a
> two-phase handshake — and then the loss goes to **zero in 1,248 runs**.

Dynamic sharding has been off by default since 2021. Holochain's account of
*why* is that it was not as well-tested as they wanted, and switching it off
reduced how much had to be tested and maintained while the platform reached
stability — the machinery was re-enabled in Kitsune2 in 2025, but nodes still
run full-arc by default because the safe-sizing controller ([kitsune2 issue
#160](https://github.com/holochain/kitsune2/issues/160)) has not been picked
back up. Full arcs cap how large a network can grow.

*Scoping, so this isn't over-read as history:* the loss rates above are
properties of the control laws **we** model — the naive rule is a reconstruction
of an undamped controller, not a port of whatever Holochain ran in 2021 — and
their stated reason for disabling sharding was testing and maintenance burden,
not observed loss.

**The contribution:** a two-phase **"polite shrink"** controller — announce an
intent to vacate, wait out gossip staleness, re-check with a deterministic
TCAS-style tie-break, and only then drop — plus an expanding-ring repair rule
for sparse networks. Designed by ablation, then attacked from every direction
we could think of.

> **The empirical record: not one sector lost.** Across every test where nodes
> behave honestly — a 1,248-run sweep (0 lost vs 95.9% for the naive
> controller), an evolutionary adversary that couldn't break it, network
> partitions, scale to 5,000 agents, gossip so lossy that 9 in 10 messages are
> dropped, and 33% of the network killed at once on
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
| **Lossy-gossip stress** — each viewer's coverage view left incomplete *and* inconsistent (messages dropped, not merely stale), missing peers' shrinks/deaths so it *over-counts* — the dangerous direction ([REPORT_stage3.md §12](REPORT_stage3.md)) | at **90% per-round message drop** the data-loss rate stays *flat* — no loss attributable to the loss itself, across 6,000 runs; the two-phase re-check never needs a complete view |
| **Formal safety proof** ([spec/](spec/), TLA+/TLC) | "a sector never drops below R" **model-checked exhaustively** — every reachable state, no violation, for N up to 8 (R from 1 to 7); the naive rule (no wait, no tie-break) fails the same check with a counterexample, isolating the two-phase tie-break as what buys safety. Scope: the proof covers the **gate** (the pre-drop re-check), not the policy around it — see [REPORT_stage1.md §2.2](REPORT_stage1.md) |
| **Upstream findings from doing the work** | kitsune2's mem transport violated its unresponsive-marking contract — fix offered upstream ([PR #572](https://github.com/holochain/kitsune2/pull/572), open, awaiting review); a broadcast head-of-line liveness bug only real transport could surface (fixed on the fork) |

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

## For a maintainer: what any policy must respect

Issue #160 asks for a **policy** — *"recommend an appropriate target arc based on the
desired redundancy level."* The cost-optimal answer is nearly trivial: minimum storage
subject to *every sector ≥ R* is `R × ring`, so the ideal arc is `R/N` of it. Every
difficulty is elsewhere — measuring `N` under stale or dishonest views, reaching the
target without a race, not oscillating on the way, and arcs being quantised into
power-of-two halves.

**We deliberately don't propose the policy.** That needs facts this study doesn't have:
what Holochain apps store and how they read it, whether a node is a phone or a server,
what durability is worth against what bandwidth, and what validation requires a node to
hold. What the runs *do* establish is the weaker, defensible thing — the constraints any
policy has to respect, whoever writes it. (This is the *policy* half. The *gate* — the
~15 lines that are actually proven — is [REPORT_stage1.md §2.2](REPORT_stage1.md).)

| Constraint | Because |
|---|---|
| **Hysteresis, scaled to each agent's *own measured* lag** — grow readily, shrink reluctantly | takes data loss from **95.9% of runs to 24.0%**. Necessary, and *not* sufficient — the rest is the race, which only the gate closes |
| **Jitter buys nothing — don't reach for it first** | **24.3% vs 24.0%.** Desynchronising decision epochs is the textbook first response to control-loop oscillation, and it does not touch this failure mode |
| **The small-network clamp is a safety parameter, not a tuning knob** | below the visible-peer threshold, hold or grow to full arc. Tuning it as a performance dial removes a floor |
| **Ring granularity must scale with N** | a fixed 512-sector ring drives the coverage floor to **1 at N = 5,000** under storm — resolution is lost exactly when it matters |
| **Provision R explicitly** | V3's ~2R equilibrium was *accidental* — a by-product of the shrink cascade stalling. V4 removes it; **V4 at R+1** buys the headroom back deliberately, at comparable cost |
| **Size the shrink wait against death-detection latency, not gossip staleness** | they are independent clocks on a real transport. Detection *faster* than gossip drives the residual race to **zero**; the storm brake shares the detection clock, so it bounds but cannot close it |
| **Don't flatten the arc distribution** | the top decile holds **~91%** of stored sectors — and the skew is hysteresis path-dependence, not the tie-break (corr ≈ +0.08). Those big arcs are the emergent insurance behind sparse recovery's global reach, so **the textbook uniform `R/N` is probably the wrong policy** |

Each constraint traces to a run; sources and full detail in
[REPORT_stage3.md → *Constraints on any sizing policy*](REPORT_stage3.md).

**And the question this study cannot answer: what should R be?** Every result above is
parameterised by it, and none of them decides it — that is a durability-versus-cost
judgement belonging to whoever knows what these networks carry.

**Every test on one page:** [TEST_LEDGER.md](TEST_LEDGER.md) lists everything polite
shrink has been put through — simulation, adversarial, real transport, deployment
realism, and the formal proof — with the result and a link to each write-up.

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
  and (§9) the TLA+ formal safety proof. Ends with **"Constraints on any sizing
  policy"** — what these runs establish that *any* target-arc policy has to
  respect (and why the textbook uniform `R/N` is probably the wrong one), kept
  separate from the proven gate.
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
| Real transport surfaced a bug simulation could not | a broadcast head-of-line **liveness bug**, invisible to the in-memory sim, found and fixed on the fork — plus an upstream mem-transport contract bug identified, with a fix offered ([PR #572](https://github.com/holochain/kitsune2/pull/572), open) |
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
| Is a *partial* rollout safe (mixed new/old nodes)? | **Yes — no flag day.** With a fraction running polite shrink and the rest still naive, the shrink-race loss is **zero from ~10% adoption** across 312 seeds (a small polite minority becomes the redundancy backbone). Early rollout thins the margin, and the storm brake closes the one race it surfaces — full write-up in [REPORT_stage3.md §10](REPORT_stage3.md) / [REPORT_rolling_upgrade.md](REPORT_rolling_upgrade.md). |
| What if death-detection is a *slower, separate* clock than gossip? | **The §6.1 race stays bounded and small.** Decoupling the death clock from view staleness ([REPORT_stage3.md §11](REPORT_stage3.md)), the race is ≤0.6% even at 2–8× the gossip lag and only at a thin margin; detection *faster* than gossip drives it to zero. It's governed by unresponsive-marking speed, not the shrink rule — so the shrink wait is sized against detection latency. |
| What if gossip is *lossy* — each viewer's coverage picture incomplete and inconsistent? | **Polite shrink holds, up to 90% message drop.** Giving each viewer a per-peer lossy view (missing a peer's shrink/death makes it *over-count* — the dangerous direction), the data-loss rate is **flat in the loss axis** across 6,000 runs ([REPORT_stage3.md §12](REPORT_stage3.md)): activation loses nothing at any drop rate, and storm's only losses are the pre-existing correlated mass-death (present at zero loss, non-monotonic in loss), never lossy over-counting. The two-phase re-check doesn't need a complete view. |

The ninth Stage-3 study — a *proof* rather than a test of the core safety
property — is important enough to stand on its own:

## Formal safety proof — the shrink race *cannot* recur (TLA+ / TLC)

The 1,248-run sweep found zero data loss, but a sweep is still *sampling* — it
only visits the interleavings its seeds happen to produce. The core safety
property is small enough to do better than sample: **prove** it, by exhaustive
model checking over *every* reachable state of a small system, in
[TLA+](https://lamport.azurewebsites.net/tla/tla.html) and its checker TLC.
Full detail and reproduction: [spec/README.md](spec/README.md).

> **Why this is worth far more than a passing test — and who relies on it.**
> A test exercises the handful of event orderings a given run happens to hit;
> concurrency bugs live precisely in the *rare* interleavings it misses. The
> 2021 arc-oscillation was exactly such a bug — surfaced by a test campaign
> rather than ruled out in advance. TLA+ (created
> by Leslie Lamport, who won computing's Turing Award in 2013) with its model
> checker TLC does what testing cannot: it explores **every** possible ordering
> and either finds a failing one or proves none exists. "All tests passed"
> means *we didn't trigger the bug this time*; "model-checked, no error" means
> *no ordering can trigger it*. That categorical difference is why the teams
> who cannot afford silent data loss reach for it: **AWS** used TLA+ to catch
> deep bugs in S3, DynamoDB and EBS before customers ever saw them; **Microsoft**
> (Azure Cosmos DB), **MongoDB**, and **CockroachDB** use it on their
> replication and consistency protocols. Here it is pointed at the exact race
> that caused Holochain's original data loss — and shows that race can no
> longer happen.

**The property (per-sector):**

> a DHT sector never holds fewer than R real copies — no shrink drives it below
> the redundancy target.

It is *per-sector* by design: for any one sector the nodes covering it decide
independently whether to drop it, and the arc geometry only sets *which* nodes
contest *which* sector — so proving it for one contested sector proves it for
the whole ring.

**Two specs, and a negative control that gives the proof teeth:**

- **`PoliteShrink.tla`** — the real rule. Nodes announce a vacate intent (worst
  case: everyone announces at once), and *execute* only after reading the
  current holder/intent sets — exactly what the "wait 2× max gossip lag" delay
  buys — using the TCAS tie-break (treat every lower-id intender as already
  gone; proceed only if ≥ R remain). **`SafeCoverage` holds on every reachable
  state — no error.**
- **`NaiveShrink.tla`** — the naive behaviour: no wait, no tie-break, each
  node drops on its stale view. **TLC returns a counterexample** — holders drop
  one by one below R, the "hallway dance" in miniature. Same model, minus the
  two phases, and safety *fails* — so the safety is bought by the mechanism,
  not by the way the model happens to be written.

Verified with no error, exhaustively, at every configuration tried:

| Nodes | R | distinct states |
|---|---|---|
| 6 | 3 | 656 |
| 7 | 2 | 2,172 |
| 8 | 4 | 5,984 |
| 8 | 1 | 6,560 |
| 8 | 7 | 1,280 |

```bash
java -cp tla2tools.jar tlc2.TLC spec/PoliteShrink.tla   # -> No error has been found
java -cp tla2tools.jar tlc2.TLC spec/NaiveShrink.tla    # -> Invariant SafeCoverage is violated
```

**Scope, stated honestly.** This proves the *control-loop* safety property —
concurrent stale-view shrinks can never drive a sector below R — under the
model's abstraction: one sector, execute-time intent visibility (the wait),
honest holders, atomic actions. It **complements, not replaces** the
simulations, which carry the things the proof abstracts away: detailed gossip
timing, Byzantine liars, and arc geometry. What it removes is any doubt that
the *rule itself* can be made to lose a copy through an unlucky interleaving —
it cannot.

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
