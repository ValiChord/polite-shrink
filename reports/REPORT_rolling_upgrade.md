# Rolling upgrade: is a partially-adopted network safe?

**Author:** Ceri John, with AI assistance (Claude, Anthropic).
**Environment:** Python 3.12.1, numpy 2.5.1 (same pins as the base sim; byte-deterministic).
**Scope:** 312 seeds/point (base 100000), all four scenarios (activation, storm,
flashcrowd, churn) — the same seed count and scenario set as the canonical
Stage-1 sweep.
**Code:** `rolling_upgrade_sim.py`, `validate_rolling_upgrade.py`,
`rolling_upgrade_sweep.py`, `brake_sim.py`, `brake_storm_sweep.py`, and the
diagnostics `diag_rolling_upgrade.py`, `diag_margin.py`,
`diag_attribute_all_storm.py`, `diag_trace_post_death.py`, `diag_brake_reruns.py`,
`plot_rolling_upgrade.py`. Results in `results/rolling_upgrade_*`.

## Question

The Stage-1 sweep runs a *homogeneous* network — every node runs the same
controller. A real network never upgrades atomically: during a rollout some
nodes run the new polite-shrink controller (V3) and some still run the old
naive one (V0). So:

> Does the mechanism require a flag-day upgrade, or is a **partially** upgraded
> network already protected — and can a naive minority reintroduce the data loss
> polite shrink was built to prevent?

## Method

`MixedSim` (`rolling_upgrade_sim.py`) is a thin subclass of the base `Sim` in
which the controller variant is a **per-agent** property. A fraction *f* of
nodes (chosen by a seeded permutation, uncorrelated with home sector) run V3
polite shrink; the rest run V0 naive. Joiners are assigned per the same fraction.

**Faithfulness guard (`validate_rolling_upgrade.py`).** rng-consumption order is
preserved so the mixed sim reduces *byte-identically* to the base sim at the
homogeneous extremes — `MixedSim(f=0)` == `Sim(V0)` and `MixedSim(f=1)` ==
`Sim(V3)` on all six metric arrays, in every scenario. This is the primary
defence against a modelling bug in the fork; it also checks falsifiability (f=0
must lose data, f=1 must not). Both pass.

We sweep *f* over 312 seeds × 4 scenarios, recording the run-level safety metric
`any_loss` (any tick with a zero-coverage sector).

## Result 1 — partial rollout is safe against the shrink race, from ≈10% adoption

Run-level data-loss rate vs upgraded fraction (312 seeds):

| upgraded *f* | naive nodes | activation | storm | flashcrowd | churn |
|---|---|---|---|---|---|
| 0.00 | 200 | 312/312 (100%) | 312/312 (100%) | 312/312 (100%) | 312/312 (100%) |
| 0.10 | 180 | **0/312** | 3/312 (1.0%) | **0/312** | **0/312** |
| 0.20 | 160 | 0/312 | 0/312 | 0/312 | 0/312 |
| 0.30–0.80 | 140–40 | 0/312 | 0–1/312 | 0/312 | 0/312 |
| 0.90 | 20 | 0/312 | 3/312 (1.0%) | 0/312 | 0/312 |
| 0.95 | 10 | 0/312 | 1/312 (0.3%) | 0/312 | 0/312 |
| 0.99 | 2 | 0/312 | 0/312 | 0/312 | 0/312 |
| 1.00 | 0 | 0/312 | 0/312 | 0/312 | 0/312 |

(Full per-fraction table: `results/rolling_upgrade_summary.md`; plot:
`results/rolling_upgrade.png`.)

**The transition is a cliff, not a slope.** In three of four scenarios
(activation, flashcrowd, churn) the shrink-race data loss goes from *certain* at
0% adoption to **zero at 10% adoption and every fraction above it, across all
312 seeds**. The mechanism does not need universal adoption: even a small
minority of polite-shrink nodes protects the whole network from the oscillatory
shrink race the naive controller reproduces. The storm scenario is the sole
exception and is dissected in Result 2.

### Mechanism — a self-adjusting "polite backbone" (`diag_rolling_upgrade.py`)

Instrumenting f=0.10 activation shows *why*. The 180 naive nodes collapse from
full arc to **level 0 by t≈50** — they shed nearly all their storage — while the
20 polite nodes shrink slowly and the per-sector **floor holds at exactly R=5
for the whole run**:

```
t=   0  floor=109  mean_lvl(naive)=8.00  mean_lvl(polite)=9.00
t=  50  floor=20   mean_lvl(naive)=0.00  mean_lvl(polite)=9.00
t= 800  floor=5    mean_lvl(naive)=0.00  mean_lvl(polite)=5.95
t=2199  floor=5    mean_lvl(naive)=0.00  mean_lvl(polite)=5.85
```

A polite node is safe *by construction* — it re-checks before every shrink and
refuses to drop a sector below R. So the polite nodes settle into exactly the
arcs that hold the redundancy floor (a handful staying at high levels to blanket
the ring), while the naive nodes free-ride down to minimal arcs. **The polite
minority becomes the network's redundancy backbone.**

## Result 2 — the storm exception, dissected honestly

Storm is the one scenario with residual loss above baseline: **11 losing runs**
across f = 0.1–0.95 (out of 3,432 mixed-storm runs ≈ 0.3%), and **zero at f=0.99
and f=1.00**. Pure/near-pure V3 never loses; it is the *presence of naive
free-riders* that introduces the residual. Two things explain it.

**(a) Free-riding thins and concentrates the margin (`diag_margin.py`).** The
floor is held at R, but by *few, large* polite arcs, so the over-provisioning
margin is thinner at low adoption (pre-storm equilibrium, mean over 15 seeds):

| upgraded *f* | mean coverage | sectors at exactly R | margin above R |
|---|---|---|---|
| 0.10 | 6.8 | **89** | 1.8 |
| 0.50 | 8.1 | 44 | 3.1 |
| 1.00 | 7.9 | 52 | 2.9 |

**(b) Attribution of the 11 losses (`diag_attribute_all_storm.py`,
`diag_trace_post_death.py`) — and this corrects an earlier overclaim.** Not every
storm loss is pure death. Re-running each losing seed with the storm removed but
every shrink decision unchanged, and tracing the agent that dropped the last
holder:

| cause | count | mechanism | preventable locally? |
|---|---|---|---|
| **correlated mass death** | **9 / 11** | all holders of a sector die at once at t=1500; coverage → 0 the instant they die, before any controller acts | **No** — no local rule can survive the simultaneous death of a sector's entire holder set |
| **§6.1 intent-death race** | **2 / 11** | a *polite* node executes a shrink intent announced before the storm, on a stale view that has not yet registered the deaths, and drops an already-thinned sector's last holder | **Yes** — see Result 3 |

The two race cases are seed 100109 (f=0.40, orphan at t=1508) and seed 100239
(f=0.10, orphan at t=1515); in both, a single V3 node's intent-execute is the
proximate cause. This is the documented §6.1 residual, and it appears here — but
not in pure V3 — because the thin backbone leaves no margin to absorb the
execute. Pure V3's accidental ~2R over-provisioning masks the same race.

> **Correction of record.** An earlier draft of this note said "polite shrink
> lost no data through its own mechanism," generalising from two hand-traced
> seeds that happened to be the pure-death kind. The full 312-seed attribution
> shows 2 of 11 storm losses *were* polite-shrink-executed (the §6.1 race). The
> corrected claim is in Result 3.

## Result 3 — the storm brake closes the §6.1 races (`brake_sim.py`, `brake_storm_sweep.py`)

The kitsune2 port already carries a **storm brake**: when a peer death is
detected, all pending shrink intents are cancelled and their dwell counters
reset. The base sim has no brake, which is why the raw §6.1 race showed through.

`brake_sim.py` adds the brake to the mixed sim. Because the single-clock model
ties death visibility to gossip staleness, the brake takes an explicit
`detect_latency` — a death at tick D is detected at D + detect_latency,
independent of gossip lag — modelling the port's *separate, faster*
unresponsive-marking clock (the core §6.1 insight). Re-running the two race
seeds while sweeping detect_latency (`diag_brake_reruns.py`):

| seed | race execute | closed when detection is… | still lost when… |
|---|---|---|---|
| 100109 (f=0.40) | t=1508 (8 ticks after death) | ≤ 8 ticks | ≥ 10 ticks |
| 100239 (f=0.10) | t=1515 (15 ticks after death) | ≤ 12 ticks | ≥ 16 ticks |

The brake closes a loss exactly when it fires before the racing execute — i.e.
when death detection is faster than the intent's remaining wait. With detection
faster than the minimum gossip lag (8), both close. This *measures* the report's
§6.1 statement: the brake **bounds** the race — closing any death detected before
execute — and a residual remains only for deaths that land inside the detection
window, which no local rule can close.

Full storm sweep with the brake (detect_latency=4, 312 seeds;
`results/rolling_upgrade_brake_storm_summary.md`) confirms it closes the *class*,
not just the two traced seeds — and introduces no new loss:

| storm above-baseline losses | count |
|---|---|
| **no brake** | **11 / 3,432** (9 pure-death + 2 §6.1-race) |
| **with brake** | **9 / 3,432** (the 9 pure-death cases only) |

The brake removes **exactly the two §6.1-race losses** (seed 100109 @ f=0.40,
seed 100239 @ f=0.10) and changes nothing else: every other losing seed is a
pure-death case that persists, and no fraction gains a loss. At f=0.10 the count
drops 3 → 2 (one of the three was the race); at f=0.40, 1 → 0.

**Corrected bottom line.** With the storm brake — present in the port, absent in
the base sim — **polite shrink causes zero data loss even in the mixed
rolling-upgrade network** at realistic detection latencies. The only residual
storm losses are the simultaneous mass-death of a sector's entire holder set,
which no local controller (V3, V4, or otherwise) can prevent — a provisioning
and death-detection question, not a flaw in the shrink protocol.

## Design implications for #160

1. **No flag day.** A ~10% minority of polite-shrink nodes eliminates the
   oscillatory shrink-race loss for the whole network. Incremental rollout is
   safe against the failure the mechanism targets.
2. **Early rollout thins the margin.** Naive free-riders shed their redundancy
   onto the upgraded minority, concentrating coverage and thinning the
   over-provisioning margin — so resilience to *correlated* mass failure improves
   as adoption rises. Levers: a less-aggressive legacy controller, or sizing the
   polite backbone above bare R while adoption is low.
3. **The storm brake matters more under partial rollout.** The thin backbone
   surfaces the §6.1 race that pure-V3 over-provisioning hides; the brake closes
   it, so shipping/keeping the brake (and a fast death-detection path) is not
   optional in a mixed network.

## Limitations

- Upgrade assignment is uniform-random, not adversarial (an attacker choosing
  *which* nodes stay naive, or *which* to kill given the backbone layout, is out
  of scope).
- The brake's `detect_latency` is an explicit knob, not derived from a modelled
  gossip/marking cadence; the result is stated *as a function of* it, with the
  honest residual for deaths inside the detection window.
- Inherits all base-sim idealisations: full peer visibility, one lag per viewer,
  honest holders (the mixed network is honest-but-heterogeneous), no real
  transport.
