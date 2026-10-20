# Polite-Shrink — a Proposed Sharding Solution for Holochain's DHT

> **New here?** Start with **[CORE_IDEA.md](CORE_IDEA.md)** — the one-page version of everything below.

> ## Damping the 2021 "hallway dance" leaves a stale-view shrink race wide open. Polite shrink closes it: announce, wait out the staleness, then re-check counting every rival announcer as already gone — and when the margin is thin, the lowest ID waits while the others clear out of its way.

> **The recommended rule is V6, "patient lowest" (October 2026 — [REPORT_stale_views.md](REPORT_stale_views.md)).** Checked exhaustively against every announce schedule and per-node lag with real stale views, and against a death at any moment:
>
> | rule | never loses data to a shrink | always makes progress | shards concurrently |
> |---|---|---|---|
> | V3 — lowest-ID tie-break (the original) | ✗ a staggered cascade, or one ordinary death, defeats it | ✓ | ✓ |
> | V5 — count every announcer as gone | ✓ proven for any N | ✗ identical nodes can cancel each other forever | ✓ |
> | **V6 — V5's count + the lowest ID waits instead of cancelling** | **✓ (V5's proof applies unchanged)** | **✓** | **✓** |
>
> At 200 nodes V6's arcs stay close to V3's (V5's are much wider), it spends **≈ 3× less sync traffic** than V3, and sectors spend **2–8× less time below R** than under V3 (4–20× less than under V5). All of it assumes deaths are noticed before anyone acts on a view still counting the dead node; when detection is far slower, every rule loses data, and only faster detection helps. The original TLA+ proof could not tell these rules apart: it gave every node a perfectly fresh view, under which even a bare re-check is safe.
>
> *Scope, stated plainly: the safety property is that no shrink takes a sector below its redundancy target R (deaths can). The original TLC runs covered five configurations (N = 6–8; R ∈ {1, 2, 3, 4, 7}) under atomic fresh reads; the stale-view checks cover every announce schedule and per-node lag for N ≤ 5, and the V5/V6 safety result has a proof that holds for any N. Honest nodes and prompt death detection are assumed. What is checked is the **gate** (the pre-drop re-check), not the surrounding **policy** (redundancy target, hysteresis constants, growth rule, clamp) — that part is engineering judgement, evidenced by simulation. Robustness to adversaries and to real networks is shown by the simulations and kitsune2-fork runs below — strong evidence, not proof. Proof details: [`spec/`](spec/).*

> ### 🧪 Want to test it? Use V6 on branch [`feat/sharding-v6`](https://github.com/topeuph-ai/kitsune2/tree/feat/sharding-v6)
> The Rust implementation to try is **V6 "patient lowest"** on the kitsune2 fork, branch [`feat/sharding-v6`](https://github.com/topeuph-ai/kitsune2/tree/feat/sharding-v6) — rebased onto kitsune2 `main` (October 2026), behind the existing `sharding` feature flag. V6 is the default there, with withdrawal of abandoned intents on (`withdraw_on_stand_down`); `patient_lowest: false` switches back to the original V3 tie-break for comparison.
> ```
> git clone -b feat/sharding-v6 https://github.com/topeuph-ai/kitsune2.git && cd kitsune2   # needs git + rustup; Rust 1.99 installs itself
> cargo test -p kitsune2_gossip --features sharding --lib sharding        # unit tests + exhaustive stale-view model check of the real re-check code
> cargo test -p kitsune2_gossip --features sharding --test sharding_race  # forced simultaneous race, V6 and V3
> cargo test -p kitsune2_gossip --features sharding --test sharding_stale # nodes acting on 2 s old views, V6
> cargo test -p kitsune2_gossip --features sharding --test sharding_cascade # the staggered cascade, forced: V3 fails, V6 holds
> cargo test -p kitsune2_gossip --features sharding --test sharding_storm # 8-node storm, V6 and V3
> ```
> The cascade test *passes* when V3 loses its copy and V6 keeps one; each command's "a pass means" is in the fork's [SHARDING_V6.md](https://github.com/topeuph-ai/kitsune2/blob/feat/sharding-v6/SHARDING_V6.md). What these tests found: [results/rust_fork_v6.md](results/rust_fork_v6.md).
> Older branches (`feat/sharding-module-v3`, `feat/sharding-agentinfo-encoding`) are kept only because the earlier reports measured them. In the Python simulator the same rule is `polite_shrink.V6`.

> ### 👉 The contribution is two files
> - **[`polite_shrink.py`](polite_shrink.py)** — the polite-shrink controller itself. The idea is a few dozen lines: `_decide` (announce an intent to vacate instead of dropping; don't announce while a lower ID is racing you) and `_execute_intent` (wait out gossip staleness, re-check counting every rival announcer as gone; if that fails only because of higher-ID rivals, wait instead of cancelling). The recommended rule is the `V6` variant; `V3` is the original tie-break, kept because every earlier study measures it.
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
reduced how much had to be tested and maintained while the platform reached stability. Kitsune2 (the 2025 rewrite) carries the sharding machinery behind its off-by-default `sharding` feature flag, but arcs are still clamped — typically to full — rather than dynamically sized, because the safe-sizing controller ([kitsune2 issue #160](https://github.com/holochain/kitsune2/issues/160), opened March 2025) has not yet been built. Full arcs cap how large a network can grow.

*Scoping, so this isn't over-read as history:* the loss rates above are
properties of the control laws **we** model — the naive rule is a reconstruction
of an undamped controller, not a port of whatever Holochain ran in 2021 — and
their stated reason for disabling sharding was testing and maintenance burden,
not observed loss.

**The contribution:** a two-phase **"polite shrink"** controller — announce an
intent to vacate, wait out gossip staleness, re-check counting every rival
announcer as already gone, and only then drop; when the margin is thin, a
TCAS-style ordering decides who goes (the lowest ID waits, the others clear out
of its way) — plus an expanding-ring repair rule for sparse networks. Designed
by ablation, then attacked from every direction we could think of. The current
rule (V6) is the third design: the original lowest-ID tie-break (V3) and the
AgentInfo encoding (V5) each turned out to have a gap the other did not.

> **The empirical record.** In the designed scenarios — a 1,248-run sweep
> (0 runs losing data vs 95.9% for the naive controller), network partitions,
> scale to 5,000 agents, coverage gossip dropping 90% of per-tick deliveries,
> and 33% of the network killed at once on real iroh transport (0 orphaned
> sectors) — no polite-shrink run lost data. Coverage *does* dip below R during
> deaths and churn (the sweep's worst floor is 1); what the gate aims at is that
> no *shrink* is what takes it there.
>
> Data **is** lost in three regimes, each characterised rather than hidden:
> nodes that **lie** about what they store (a sensor problem; the proof-gated
> **verified-coverage** extension removes it in simulation); **slow death
> detection under heavy storms** (at 50% simultaneous death with detection 4–8×
> slower than gossip, V3 loses data in 15–35% of runs — the residual that
> constraint 6 and [RELATED_WORK.md §5](RELATED_WORK.md) quantify); and the
> **V3 tie-break's structural gap** found in October 2026: shown by model checking,
> and forced on the real Rust code, where it takes a sector to zero declared copies
> whenever the timing occurs; how often that timing arises unforced is not yet
> measured ([REPORT_stale_views.md](REPORT_stale_views.md),
> [results/rust_fork_v6.md §7](results/rust_fork_v6.md)).

## Evidence at a glance

| Evidence class | Result |
|---|---|
| **1,248-run robustness sweep** (312 seeds × 4 scenarios, paired against 3 weaker controllers) | **0 sectors lost** (95% UB < 0.24%); weakest controller lost data in 95.9% of runs ([REPORT_stage1.md](REPORT_stage1.md)) |
| **Evolutionary adversarial search** (same kill budget, free choice of who/when, 20 generations) | broke the damped and jittered controllers; did not find an attack on polite shrink. *Weak as a null:* one world, one seed, 320 evaluations — and a 60-kill budget could simply kill every holder of one sector, which no controller survives, so this tests the search more than the rule |
| **Reference implementation** on a kitsune2 fork — **V6 on [`feat/sharding-v6`](https://github.com/topeuph-ai/kitsune2/tree/feat/sharding-v6)** (current, rebased onto kitsune2 `main`, Oct 2026); V3 on [`feat/sharding-module-v3`](https://github.com/topeuph-ai/kitsune2/tree/feat/sharding-module-v3) (the branch the Stage 1–3 and Wind Tunnel results measured). Behind the existing `sharding` feature flag | 8-node storm test on the in-memory transport: shard down, kill 3 of 8, recover to target — no sector ever orphaned, under V3 and under V6. **Forced simultaneous race** (8 agents, target 6, no deaths; [results/rust_fork_v6.md](results/rust_fork_v6.md)): V6's lowest racer waits, the others stand down, it then leaves, and the network settles in ≈ 2–3 s with **zero re-grows in every run**; V3 is also safe there, but churns — median 34 announcements and 10 re-grows per run, taking up to ≈ 1 minute to settle. **The stale-view model check, run on the real Rust code**, reproduces the Python checker's V3 failure counts exactly and finds V6 safe in all 14,054,400 schedules with a death at any tick. **The staggered cascade, forced on the real code** ([§7](results/rust_fork_v6.md)): V3 takes the shared half to zero declared copies in every run once leavers take ≥ 2 s to grow back; V6 keeps a copy every time |
| **Wind Tunnel measurements — real iroh transport, live churn** ([wind_tunnel/results/REPORT_stage2_wind_tunnel.md](wind_tunnel/results/REPORT_stage2_wind_tunnel.md)) | 33% of the network killed simultaneously: **zero orphaned sectors** (that run's intents had already resolved, so the brake was not exercised). In the separate *timed* storm, deaths landed while intents were pending: the brake cancelled all 9, and op-level reachability found **0 of 23,673 ops lost** |
| **Stage-3 robustness studies** ([REPORT_stage3.md](REPORT_stage3.md)) | netsplits + heal: zero durability loss; forged intents: fail-safe (cost-only); scale to 5,000 agents: zero loss where the damped controller loses data; the residual shrink-race measured at 0.002% of holes and transient; the sparse-network deadlock found real and fixed (V4 repair: 120/120 recovery); Byzantine defenses measured — range-validation cuts the forgery cost attack to ~4% (and is implemented on the fork), the serve-audit fully rescues a liar-collapsed network, and **proof-gated "verified coverage" removes the K=R liar ceiling entirely** — flat, zero-loss at every K from 0 to 3R, at a bandwidth cost the operator sets (≈13–16% at adequate audit budget); and **partial liars** (store a strategic fraction, serve some challenges) still cause **zero data loss**, with a mid-fraction margin dip that a higher audit sample-count restores |
| **Lossy-gossip stress** — each viewer's coverage view left incomplete *and* inconsistent (messages dropped, not merely stale), missing peers' shrinks/deaths so it *over-counts* — the dangerous direction ([REPORT_stage3.md §12](REPORT_stage3.md)) | at **90% per-round message drop** the data-loss rate stays *flat* — no loss attributable to the loss itself, across 6,000 runs. **Scope:** drops are per tick, so 90% adds roughly ten ticks of staleness against a fifty-tick wait; one seed loses only at intermediate drop rates; and the intent-announcement channel is kept reliable here, so robustness to lost *intents* is future work |
| **Formal safety checks** ([spec/](spec/), [REPORT_stale_views.md](REPORT_stale_views.md)) | *Original TLA+:* "a sector never drops below R" holds in five configurations — but every node reads the true holder set instantly, so the tie-break is never used and the naive rule's failure isolates nothing. *Stale-view checks (Oct 2026):* exhaustive over announce schedules, per-node lags and a death at any tick, N ≤ 5. A bare re-check fails everywhere; V3 fails a staggered cascade and one-death schedules; V5 is safe but can stall forever; **V6 is safe in all of them at a 1× wait (V5's proof, any N) and always makes progress**. *TLA+ too:* [`spec/StaleShrink.tla`](spec/StaleShrink.tla) restates the stale-view model for TLC, which finds V3's cascade itself and checks V6 safe and live |
| **V6 against V3 and V5 at N = 200** ([results/v6_summary.md](results/v6_summary.md)) | Fresh seeds, standard scenarios + storm severity + slow-detection stress. V6's arcs are close to V3's (a little wider; V5's are much wider), sync traffic ≈ 3× lower than V3, cancel rate as low as V3's, and **time below R 2–8× lower than V3 and 4–20× lower than V5**. Storm 40%: V5 lost data in 11/100 runs, V3 and V6 in 0. The one V6 loss (1 of 100 worlds at storm 30%) began at the storm tick itself — the mass death took every holder at once, no shrink involved; V3's accidental ~2R margin happened to cover it |
| **Is the residual really irreducible by a local rule?** ([REPORT_mz_decomposition.md](REPORT_mz_decomposition.md)) | §11 asserted it; this measures it. A Mori–Zwanzig decomposition over 72 seeds and ~166k gate decisions: detection latency drives the failure mode up **29×** while the part recoverable from an agent's own history stays flat, against a control that detects memory ~8× more strongly where it exists. So a node cannot **learn** its way out — but it *can* be **biased** out, which is the amendment §11 now carries |
| **Which way should a failure detector be wrong?** ([`detector_error_sweep.py`](detector_error_sweep.py), constraint 6b) | **Toward convicting the living — with a ceiling.** Replicated on fresh seeds (150 per point): `P(any loss)` falls **36% → 2.7%** at p ≈ 0.10, then rises again to **15%** at p = 0.40 (non-overlapping 95% intervals; [RELATED_WORK.md §5](RELATED_WORK.md)). At p = 0.40 nodes hold more data *and* lose more, so this is not plain caution; whether the optimum is error cancellation or thrashing is open. Cost is **storage, not bandwidth** — sync cost *falls*, less shrinking meaning less re-growing |
| **Does a mixed network need per-peer detector tuning?** ([`hetero_detector_sweep.py`](hetero_detector_sweep.py)) | **Not measurably — and heterogeneity turns out to help.** Getting one global threshold roughly right is a **38 pp** effect (42% → 4%); tuning each latency class separately adds ≤4 pp, which a selection-bias null test reproduces in 11% of grids by chance. Self-calibrating detectors (φ accrual and relatives) are therefore second-order here. Separately, replicated on fresh seeds: a homogeneous slow network (dl = 192) loses data in **35%** of runs, all-fast (dl = 96) in 15%, and a 50/50 mix in **18%** — **a mixed network tracks its faster half**, the same backbone shape §10 found for a polite minority. (An earlier "0/24" came from an uncommitted probe and did not replicate.) |
| **Upstream findings from doing the work** | kitsune2's mem transport violated its unresponsive-marking contract — fix offered upstream ([PR #572](https://github.com/holochain/kitsune2/pull/572)) — closed by maintainers 2026-09-29: that transport is test-only, so they prefer not to add a feature nothing uses; a broadcast head-of-line liveness bug only real transport could surface (fixed on the fork) |
| **Does the announcement need its own wire message?** ([REPORT_agentinfo_encoding.md](REPORT_agentinfo_encoding.md)) | **No — but it needs one bit.** Carrying the intent on the already-gossiped `AgentInfo` arc claim is model-checked safe and removes ~255 lines plus a wire format; what it cannot carry is *"intending to leave"* vs *"already gone"*, and deriving that from claim age is falsified by a single misclassification. The encoding wins on the shrink race (346× fewer holes), 90%-lossy gossip and storage fairness; it loses on reachability at scale and on how *often* a mass die-off costs data (6–9% of runs vs 1%, against a one-event V3 baseline). *Oct 2026:* on safety alone the stale-view check now favours this encoding — see [REPORT_stale_views.md](REPORT_stale_views.md) |

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
~15 lines the model checks cover — is [REPORT_stage1.md §2.2](REPORT_stage1.md); the
recommended form of it is V6, see [REPORT_stale_views.md](REPORT_stale_views.md).)

| Constraint | Because |
|---|---|
| **Hysteresis, scaled to each agent's *own measured* lag** — grow readily, shrink reluctantly | takes data loss from **95.9% of runs to 24.0%**. Necessary, and *not* sufficient — the rest is the race, which only the gate closes |
| **Jitter buys nothing — don't reach for it first** | **24.3% vs 24.0%.** Desynchronising decision epochs is the textbook first response to control-loop oscillation, and it does not touch this failure mode |
| **The small-network clamp is a safety parameter, not a tuning knob** | below the visible-peer threshold, hold or grow to full arc. Tuning it as a performance dial removes a floor |
| **Ring granularity must scale with N** | a fixed 512-sector ring drives the coverage floor to **1 at N = 5,000** under storm — resolution is lost exactly when it matters |
| **Provision R explicitly** | V3's ~2R equilibrium was *accidental* — a by-product of the shrink cascade stalling. V4 removes it; **V4 at R+1** buys the headroom back deliberately, at comparable cost |
| **Size the shrink wait against death-detection latency, not gossip staleness** | they are independent clocks on a real transport. Detection *faster* than gossip drives the residual race to **zero**; the storm brake shares the detection clock, so it bounds but cannot close it |
| **Decide which way the failure detector should be *wrong*, and give it a ceiling** | convicting a live peer makes a node hold more (costs storage); missing a dead one makes it shrink wrongly (costs data). Erring toward conviction takes `P(any loss)` **40% → 2%** — but past the optimum it worsens again, because the mechanism is one error cancelling another, not caution. The optimum therefore moves with detection latency (constraint 6b) |
| **Don't spend effort on per-peer calibration before the global threshold is right** | one well-chosen global threshold is a **38 pp** effect; tuning per latency class adds ≤4 pp and is not distinguishable from selection noise. Self-calibrating detectors buy little until the first-order effect is already captured |
| **Don't treat a spread of detection speeds as a hazard** | it helps. Replicated on fresh seeds: uniformly slow detection loses data in **35%** of runs, a 50/50 mix with twice-as-fast nodes in **18%** — about what an all-fast network loses (15%). A mixed network tracks its *faster* half — so a policy that homogenises node behaviour may remove a margin it never knew it had (cf. the arc-distribution constraint below) |
| **Don't flatten the arc distribution** | the top decile holds **~91%** of stored sectors — and the skew is hysteresis path-dependence, not the tie-break (corr ≈ +0.08). Those big arcs are the emergent insurance behind sparse recovery's global reach, so **the textbook uniform `R/N` is probably the wrong policy** |

Each constraint traces to a run; sources and full detail in
[REPORT_stage3.md → *Constraints on any sizing policy*](REPORT_stage3.md).

**And what adopting the gate would actually cost.** Not a new wire message —
the announcement can ride on the `AgentInfo` arc claim kitsune2 already gossips
and signs. It does need **one bit** that claim cannot carry: whether a narrowed
arc means *intending to leave* or *already gone*. That is either one field on
an existing struct, or the ID tie-break on a dedicated signal; it cannot be
inferred from the claim's age (a single misclassification loses a copy —
model-checked). Mechanically, `update_storage_arcs` already moves the stored
arc toward a target hint; what is missing is the rule that sets the hint, and
the shrink direction `storage_arc.rs` explicitly leaves to "the host
implementation or some sharding logic". Full comparison of both encodings, and
the axes where the message-free one is *worse*, in
[REPORT_agentinfo_encoding.md](REPORT_agentinfo_encoding.md).

**And the question this study cannot answer: what should R be?** Every result above is
parameterised by it, and none of them decides it — that is a durability-versus-cost
judgement belonging to whoever knows what these networks carry.

**Every test on one page:** [TEST_LEDGER.md](TEST_LEDGER.md) lists everything polite
shrink has been put through — simulation, adversarial, real transport, deployment
realism, and the formal checks — with the result and a link to each write-up.

## The write-ups

- **[REPORT_stage1.md](REPORT_stage1.md)** — the main study: methodology, the 4,992-sim
  sweep, adversarial search, the reference implementation and its findings
  (§6 is the "what simulation hid" section), limitations.
- **[wind_tunnel/results/REPORT_stage2_wind_tunnel.md](wind_tunnel/results/REPORT_stage2_wind_tunnel.md)** — real
  iroh transport under Wind Tunnel: settle, storm, timed-storm; op-level
  reachability verdicts; flake accounting.
- **[REPORT_agentinfo_encoding.md](REPORT_agentinfo_encoding.md)** — can the
  intent ride on `AgentInfo` instead of its own message? Three TLA+ specs, the
  whole Stage-3 battery re-run under the alternative encoding, and Wind Tunnel
  on real transport. Includes the correction that matters most in this repo:
  a durability claim that held at four seeds did not hold at a hundred.
- **[REPORT_stage3.md](REPORT_stage3.md)** — partitions, Byzantine agents,
  scale, the §6.1 race quantified, the §6.2 repair rule simulated before
  implementation, (§7) proof-gated *verified coverage* closing the
  false-declaration liar gap, (§8) *partial* liars and the audit-sample knob,
  and (§9) the original TLA+ model (what it could and could not show is in
  REPORT_stale_views.md). Ends with **"Constraints on any sizing
  policy"** — what these runs establish that *any* target-arc policy has to
  respect (and why the textbook uniform `R/N` is probably the wrong one), kept
  separate from the proven gate.
- **[REPORT_mz_decomposition.md](REPORT_mz_decomposition.md)** — is §11's
  "irreducible by any local rule" actually true? A Mori–Zwanzig decomposition
  of the §6.1 residual into Markovian, memory and orthogonal terms, run as a
  falsification attempt. Detection latency drives the failure mode up **29×**
  while the part recoverable from an agent's own history stays flat — so a node
  cannot *learn* its way out. The companion Shapley attribution
  ([`mz_attribution.py`](mz_attribution.py)) then **narrows the repo's own
  claim**: the seven observables are near-perfect substitutes, so the null
  covers one dimension of observable space, not seven. Together with
  [`detector_error_sweep.py`](detector_error_sweep.py) — which shows a
  deliberately *biased* detector cuts `P(any loss)` 40% → 2% by cancelling the
  over-count rather than inferring it — this amends §11 and adds constraint 6b.
  [`hetero_detector_sweep.py`](hetero_detector_sweep.py) closes the line out:
  per-peer calibration is not resolvable against the **38 pp** gained by getting
  a single threshold roughly right, so self-calibrating detectors (φ accrual and
  relatives) are second-order here — and a *spread* of detection speeds turns out
  to be protective rather than hazardous. Its summary carries both corrections
  that got there: a first grid whose baseline lost nothing, so every cell was
  noise; and a verdict that was an artefact of taking a minimum over 25 cells.
- **[REPORT_stale_views.md](REPORT_stale_views.md)** — *October 2026, read
  this first.* How the recommended rule (V6) was arrived at: the TLA+ model gave
  every node a fresh view, so the tie-break was never exercised; re-checked with
  real stale views, V3 fails a staggered cascade and one-death schedules, V5 is
  safe but can stall, and five candidate hybrids were tested for safety,
  progress and concurrency until one (V6, "patient lowest") passed all three.
- **[RELATED_WORK.md](RELATED_WORK.md)** — the same problem in other fields:
  sensor-network sleep scheduling (the same race, twenty years earlier),
  k-exclusion and the bakery algorithm (the race's classical name), and
  delay-stability theory from congestion control (tested here: no sharp
  oscillation threshold, own-lag scaling helps in the operating range, and
  identical-lag networks oscillate more). Also the fresh-seed replications of
  the two detection-side headlines.
- **[METHOD.md](METHOD.md)** — how claims here are graded and how to check
  them: machine-checked proof vs simulation evidence vs known gap, why the
  ablation ladder is reported instead of the headline number (cf. McGreivy &
  Hakim, *Nat. Mach. Intell.* 2024, on weak baselines), and the repo's
  published corrections. Also states what would falsify the central claim.
- **[spec/README.md](spec/README.md)** — the formal checks: the original model
  (fresh reads, so it could not see the stale-view race) and `StaleShrink.tla`,
  where TLC finds V3's staggered cascade by itself and checks V6 safe and live.
- **[RELATED_regularisation.md](RELATED_regularisation.md)** — *a reading aid, not a result.*
  The shrink race read as an L1 problem, for readers coming from statistics or ML: why the
  objective determines coverage but provably cannot determine which nodes hold it, and why the
  ID tie-break is a Gauss–Seidel sweep order manufactured without a coordinator. Includes what
  the analogy does **not** license.

## Where is the code?

Two places, by design:

- **The rule, as simulated** (Python, this repo): the entire polite-shrink
  mechanism is a few dozen lines — [`polite_shrink.py`](polite_shrink.py), `_decide` (phase 1:
  announce the vacate intent instead of dropping; under V6, not while a
  lower ID is racing you) and `_execute_intent` (phase 2: after the wait,
  re-check the vacated half counting every racing intender as already gone;
  proceed only if still ≥ R, and under V6 the lowest racer waits rather
  than cancelling). The recommended rule is the `V6` variant.
  The V4 expanding-ring repair extension is [`repair_sim.py`](repair_sim.py).
  Everything else here is the machinery for attacking those lines.
- **The rule, as deployable** (Rust, kitsune2 fork):
  [`crates/gossip/src/sharding/`](https://github.com/topeuph-ai/kitsune2/tree/feat/sharding-v6/crates/gossip/src/sharding)
  on branch **`feat/sharding-v6`** — V6 is the default there, and
  `patient_lowest: false` gives the original V3 tie-break. (The earlier
  reports measured branch `feat/sharding-module-v3`, which has V3 only.)
  ~1,800 lines (tests included) behind kitsune2's
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
| **V3 polite** | two-phase shrink: announce intent, wait 2× max lag, re-check counting all lower-id (higher-priority) intenders as already gone, lowest-id proceeds | TCAS tie-break + self-stabilization ("never vacate before your replacement is confirmed") |
| **V4 polite+repair** *(Stage 3)* | + expanding-ring repair: a hole in the level+g ancestor block motivates growth after `grow_need + (g−1)·2·lag` persistence — ring-near agents move first, distant timers reset when the hole closes | expanding-ring search (ad-hoc routing) |
| **V6 polite (patient lowest)** *(2026-10-21, recommended)* | re-check counts **every** racing intender as gone (V5's rule); if that fails only because of higher-ID racers, the lowest racer keeps its announcement up and re-checks next tick instead of cancelling; a node does not announce while a lower ID is racing it. Needs to *see* announcers (a message or one explicit bit on `AgentInfo`) | bakery algorithm's "wait for lower tickets" + TCAS complementary orders |
| **V5 polite (AgentInfo-only)** *(2026-07-25)* | the intent rides on the gossiped arc claim instead of a dedicated message: announcing = publishing the *reduced* arc while still holding the data. No tie-break (peers cannot tell an intender from a departed node), so the gate counts current claimants only | reviewer feedback from Holochain core — reuse what is already gossiped |

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
>
> The announce-then-defer structure has an independent precedent in wireless-sensor
coverage scheduling (Tian & Georganas, 2002), which likewise announces before a
node withdraws and has neighbours discount it; that line of work later moved from
random back-off to deterministic priority ordering — the same V2→V3 correction
found here. The convergence of two unrelated fields on this mechanism is treated
as evidence for it, not as prior art either reinvented.

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
| **Jitter alone is unreliable** | in a 4-seed check V2 lost data in 3 storm runs where V1 had none, yet at seed 42 the reverse holds, and on the 312-seed sweep the two are indistinguishable overall (24.0% vs 24.3%). The mechanism when it does hurt: staggered unilateral drops erode the floor in a slow drip that synchronized drops don't |
| The two-phase handoff is what buys safety | **V3: zero data loss in every seed-check run**; during activation its floor never dips below R; lowest under-replication exposure everywhere |

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
| Coverage stayed continuous through a **33% simultaneous node loss** on real transport | floor never below 6 (≥ R=5), including through the mass death; **0 orphaned sectors**. (Op-level reachability was measured on the timed-storm runs: 0 of 23,673 lost.) |
| The **storm brake** caught the §6.1 intent-death race in the wild | in the timed-storm run, six agents die and the brake cancels **nine** pending shrink intents that had been announced into the die-off on stale views — none executed |
| Real transport surfaced a bug simulation could not | a broadcast head-of-line **liveness bug**, invisible to the in-memory sim, found and fixed on the fork — plus an upstream mem-transport contract bug identified, with a fix offered ([PR #572](https://github.com/holochain/kitsune2/pull/572), open) |
| Sharding actually happens (not just "doesn't break") | equilibrium arc span shrinks to ~0.58–0.63 of full (≈1.6–1.7× gain at N=12, growing with N) while the floor holds above R |

## Stage-3 results — adversaries, scale, repair, and the one real gap

Stage 3 attacks the controller along the four threats [REPORT_stage1.md](REPORT_stage1.md)
§7 left open, then the Byzantine "liar" problem and a formal model check — nine
studies, one command (`./run_stage3.sh`, which now also runs the detection-side group). Full report:
[REPORT_stage3.md](REPORT_stage3.md).

| Question | Answer |
|---|---|
| Netsplit + heal — is data lost? | **No durability loss** in any of 3 geometries × 3 controllers (single seed, 42 — V1 and V2 also lose nothing here, so this does not discriminate); V3's floor never left R, and the heal-time shrink storm is absorbed. Flapping partitions defeat the damped controller (V1), not polite shrink. |
| Forged shrink-intents? | **Fail-safe by construction and measurement** — worst-case forgery is a *cost* attack (2.3× sync, zero loss); receiver-side range-validation cuts it to ~4% and is **implemented on the fork**. |
| Does it survive scale? | **V3 to N=5,000** (rings up to 16,384 sectors), zero loss, per-agent cost flat — where the damped controller starts losing data at **N ≥ 2,000**. |
| The sparse-network recovery deadlock? | Real (V3 without the clamp stuck in 5/90 port-scale seeds); **V4 expanding-ring repair recovers 120/120**, still sharding, no thundering herd. |
| How often does the shrink-race actually bite? | Shrink-executed holes = **0.002% at R=5** (≥99.9% of all holes are generic churn outrunning recovery, not a controller defect), and all transient (median 23 ticks). |
| Nodes that **lie** about what they store? | The one real gap: past **K=R** phantom declarations, data is lost invisibly — sensor integrity, not control. Proof-gated **verified coverage** removes the threshold (zero loss to K=3R); *partial* liars cause zero data loss with a tunable audit-sample knob. |
| Is a *partial* rollout safe (mixed new/old nodes)? | **Yes — no flag day.** With a fraction running polite shrink and the rest still naive, the shrink-race loss is **zero from ~10% adoption** across 312 seeds (a small polite minority becomes the redundancy backbone). Early rollout thins the margin, and the storm brake closes the one race it surfaces — full write-up in [REPORT_stage3.md §10](REPORT_stage3.md) / [REPORT_rolling_upgrade.md](REPORT_rolling_upgrade.md). |
| What if death-detection is a *slower, separate* clock than gossip? | **The §6.1 race stays bounded and small.** Decoupling the death clock from view staleness ([REPORT_stage3.md §11](REPORT_stage3.md)), at storm 30% the race is ≤2/312 runs up to a detection latency of 64 ticks (2.7× the maximum gossip lag) and only at a thin margin — though at storm 50% and 4–8× the maximum lag, V3 loses data in 15–35% of runs ([RELATED_WORK.md §5](RELATED_WORK.md)); detection *faster* than gossip drives it to zero. It's governed by unresponsive-marking speed, not the shrink rule — so the shrink wait is sized against detection latency. |
| What if gossip is *lossy* — each viewer's coverage picture incomplete and inconsistent? | **Polite shrink holds, up to 90% message drop.** Giving each viewer a per-peer lossy view (missing a peer's shrink/death makes it *over-count* — the dangerous direction), the data-loss rate is **flat in the loss axis** across 6,000 runs ([REPORT_stage3.md §12](REPORT_stage3.md)): activation loses nothing at any drop rate, and storm's only losses are the pre-existing correlated mass-death (present at zero loss, non-monotonic in loss), never lossy over-counting. The two-phase re-check doesn't need a complete view. (Scope: this drops coverage/arc declarations; the intent channel the handshake depends on is kept reliable, so lost-*intent* robustness is future work.) |

The ninth Stage-3 study was a model check rather than a test of the core safety
property. It is kept here with what it did and did not show:

## Formal checks (TLA+ / TLC) — what the first model showed, what it missed

The 1,248-run sweep found zero data loss, but a sweep is still *sampling* — it
only visits the interleavings its seeds happen to produce. The core safety
property is small enough to do better than sample: check it exhaustively, over
*every* reachable state of a small system, in
[TLA+](https://lamport.azurewebsites.net/tla/tla.html) and its checker TLC.
Full detail and reproduction: [spec/README.md](spec/README.md).

> **Correction, October 2026.** The first model below let every node read the
> *current* holder set at the moment it acted. Under that assumption even a bare
> re-check is safe, so the model never exercised the tie-break and could not see
> the stale-view race at all. Its "no error" did not mean the race cannot recur.
> The second model, `StaleShrink.tla`, gives nodes stale views; there TLC finds a
> cascade that breaks the original V3 rule and checks the recommended V6 rule
> safe and live. See [REPORT_stale_views.md](REPORT_stale_views.md).

> **Why this is worth far more than a passing test — and who relies on it.**
> A test exercises the handful of event orderings a given run happens to hit;
> concurrency bugs live precisely in the *rare* interleavings it misses. The
> 2021 arc-oscillation was exactly such a bug — surfaced by a test campaign
> rather than ruled out in advance. TLA+ (created
> by Leslie Lamport, who won computing's Turing Award in 2013) with its model
> checker TLC does what testing cannot: it explores **every** possible ordering
> and either finds a failing one or proves none exists. "All tests passed"
> means *we didn't trigger the bug this time*; "model-checked, no error" means
> *no ordering the model allows can trigger it*. That is why the teams who
> cannot afford silent data loss reach for it: **AWS** used TLA+ to catch deep
> bugs in S3, DynamoDB and EBS before customers ever saw them; **Microsoft**
> (Azure Cosmos DB), **MongoDB**, and **CockroachDB** use it on their
> replication and consistency protocols. The caveat is in "the model allows":
> this repo's first model left out stale views, which is exactly where the race
> lives.

**The property (per-sector):**

> a DHT sector never holds fewer than R real copies — no shrink drives it below
> the redundancy target.

It is *per-sector* by design: for any one sector the nodes covering it decide
independently whether to drop it, and the arc geometry only sets *which* nodes
contest *which* sector — so proving it for one contested sector proves it for
the whole ring.

**The first model (2026-07), and its negative control:**

- **`PoliteShrink.tla`** — the V3 rule, with fresh reads. Nodes announce a vacate intent (worst
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

No error, exhaustively, at every configuration tried (with fresh reads):

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

**What this first model does not show.** Its execute step reads the true
holder set, so it assumes away the staleness the rule exists to survive. The
negative control fails because the naive rule has no wait at all, not because
the model can tell a good tie-break from a bad one.

**The stale-view model (2026-10): `StaleShrink.tla`.** Each node reads the state
as it was up to `L` ticks ago (per node), may announce at any tick, and
re-checks `D` ticks later:

| model | rule | wait | TLC result |
|---|---|---|---|
| `StaleShrink.cfg` | V6 | 1× the max lag | no error (safety and progress), 65,001 states |
| `StaleShrinkV6Wait2x.cfg` | V6 | 2× | no error, 245,146 states |
| `StaleShrinkV3Cascade.cfg` | V3 | 2× | **safety violated**: nodes 4, 3, 2, 1 announce a tick apart; the last copy goes |
| `StaleShrinkV6TooShort.cfg` | V6 | 0.5× | **safety violated** (control: no rule is safe with too short a wait) |

**Scope, stated honestly.** Small networks (N ≤ 5), one sector, honest
holders, no deaths in the TLA+ version (the Python checker and its Rust port
add a death at any tick). It **complements, not replaces** the simulations,
which carry what the models abstract away: detailed gossip timing, Byzantine
liars, and arc geometry. Within those limits it shows V6 cannot be made to take
a sector below R by an unlucky interleaving, and that V3 can.

## Run it

```bash
pip install numpy matplotlib
python3 run_experiments.py          # Stage 1: ~45 s, results/*.png + summary.md
python3 check_seeds.py              # Stage 1: seed-robustness check
./run_stage3.sh                     # Stage 3 + the detection-side group: ~3 h on 8 cores
java -cp tla2tools.jar tlc2.TLC -deadlock spec/StaleShrink.tla   # stale-view model check of V6 (needs JRE + tla2tools.jar)
```

The script resolves its own interpreter — it *executes* each candidate rather
than just looking for it on PATH, because on Windows `python3` is usually the
Microsoft Store shim, which is on PATH, is not Python, and makes every study
die instantly. Point it at a specific one with `PYTHON=...`:

```bash
PYTHON=/path/to/venv/bin/python ./run_stage3.sh
```

Before running anything it prints the interpreter and the numpy/matplotlib
versions, aborts if a dependency is missing, and says plainly whether the
environment matches the pins in `REPRODUCE.md` — an off-pin run still produces
useful results, but not byte-reproducible ones, and the log now records which
it was.

`run_stage3.sh` runs the reduction guards first (each asserts an extension model
is byte-identical to the model it extends when its new parameter is off), then
the original nine studies, then the four detection-side ones. Bare invocation
reproduces the published configuration throughout. To run just the latter group,
or to trim it:

```bash
python3 validate_detector_error.py  # guard: p=0 reduces to DecoupledSim exactly
python3 mz_probe.py                 # MZ decomposition, 72 seeds   (~50 min)
python3 mz_attribution.py           # exact Shapley, 128 fits/cell (~7 min)
python3 detector_error_sweep.py     # detector-error sweep         (~25 min)
python3 diag_detector_bias.py       # why the curve turns over     (~5 min)
python3 hetero_detector_sweep.py    # per-peer calibration worth it? (~12 min)
python3 oscillation_sweep.py        # is the dance a delay instability? (~12 min)
python3 detector_replication.py     # fresh-seed replication (~45 min)
python3 v6_study.py                 # V6 vs V3 vs V5 at N=200 (~25 min)
cd spec && python3 timed_check.py --sweep   # stale-view safety (pure stdlib)
cd spec && python3 hybrid_check.py --table  # safety + progress, all candidates
```

These are numpy-only (no sklearn or scipy — the estimators are implemented
directly) and take `--seeds` / `--procs`. The two sweeps write each cell as it
completes and resume from what is already on disk, so an interrupted run can be
restarted without losing work.

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
  property ("never vacate a sector below R") is model-checked for the
  recommended rule (V6) under stale views, for small networks
  (`spec/StaleShrink.tla`; the original §9 model used fresh reads and could not
  see the race), but the broader results — costs, adversary outcomes, the surprising V2
  finding that jitter *without* the handoff is unreliable — characterise this
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
