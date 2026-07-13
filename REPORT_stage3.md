# Stage 3: partitions, Byzantine agents, scale, and the §6.1 race quantified

**Author:** Ceri John ([topeuph-ai](https://github.com/topeuph-ai)), with AI assistance (Claude, Anthropic)
**Date:** 2026-07-13
**Extends:** `REPORT.md` (Stage 1 simulation + Stage 2 kitsune2 port). Its §7
lists four threats to validity this stage was built to test: network
partitions, Byzantine behaviour, parameter-regime transfer (scale), and the
§6.1 residual race left unquantified. Stage-1 code (`arc_sim.py`) is
untouched; every extension is a subclass in a new file, so the Stage-1
byte-determinism claims stand.

## Summary of findings

| # | Question | Answer |
|---|---|---|
| 1 | Does a netsplit + heal orphan data? | **No durability loss in any of 9 runs.** V3's durability floor never left R=5; the heal-time concurrent shrink storm is absorbed. Flapping partitions defeat V1 (1,007 unreachable sector-ticks; never re-settles) but not V3. |
| 2 | Can forged ShrinkIntents make honest nodes abandon coverage? | **No — the channel is fail-safe by construction and measurement.** Worst-case forgery (whole-ring claims in the highest-priority names) causes zero loss; it is a *cost* attack: 2.3× sync, +60% resizes, arcs pinned wider. |
| 3 | Can lying about coverage destroy data? | **Yes — catastrophically, and invisibly, past a sharp threshold at K = R.** K full-arc liars: at K=R−1 the network survives on margin 1; at K=R, 27% of the ring has zero real copies while declared coverage reads healthy; at 2R, 70%. No control law can defend: this is sensor integrity, not control. |
| 4 | Does the controller survive scale? | **V3 yes, V1 no.** At N ≥ 2000 the activation cascade makes V1 lose data (up to 1,474 zero-coverage sector-ticks at N=5000); V3 held floor = R with zero loss at every N up to 5000 on rings up to 16,384 sectors, with per-agent costs flat and settle time growing only mildly. |
| 5 | How often does the §6.1 race actually bite? | **Almost never, even under escalated hazard.** Across ~2.3M observed holes, ≥99.9% were pure churn outrunning recovery (the generic replication floor, not a controller defect); shrink-executed holes (§6.1 proper) were 0.002% at R=5 — and zero at R=5/lag=24 at *every* hazard tested. Hole rate scales with hazard at slope ≈ 3–4 (R=5) vs ≈ 2–2.4 (R=3), consistent with the blind-window model, licensing extrapolation: at realistic churn the rate is negligible (worked example below). All holes are transient — median 23 ticks, p90 ≈ 95. |

## 1. Partitions (`partition_sim.py`)

**Model.** Group-restricted visibility on the Stage-1 machinery: from a
split, each side's snapshots contain only its own members, so the far side
fades from every stale view within one gossip lag — a partition presents
exactly as a mass death, and a heal as a mass join. Two ground truths per
tick: **durability** (live copies anywhere) and **availability** (copies
reachable within each side — the honest, unavoidable partition cost).

**Scenarios** (200 agents, R=5, split at 1500 post-settle): 50/50 split
healing at 2100; 90/10 split (minority of 20 < `clamp_min_peers` = 25);
flapping (three 150-tick splits with 150-tick heals).

**Results** (`results/partition_summary.md`, `results/partition_*.png`):

- **Durability loss: zero, all scenarios, all variants.** During a split
  both sides grow to re-cover the ring alone, so total copies *rise*; the
  danger concentrates at the heal, when every agent sees ~2× over-coverage
  simultaneously. V3's durability floor never left 5; V1/V2 dipped to 2.
- **The heal shrink-storm is V3's win condition:** it re-settles immediately
  (the intent queue serialises the over-coverage drain), where V1 never
  re-settles in either split scenario and keeps hunting to the end of the run.
- **Availability:** on the minority side of 90/10 the clamp fires as designed
  (§6.2's "designed recovery path"): 20 agents go full-arc and the worst
  reachable floor is 1, never 0. Under flapping, V1 lost reachability of
  some sectors for 1,007 sector-ticks; V3 (and V2) never let any sector
  become unreachable on any side.
- V3 also did this cheapest in the 50/50 case (3,793 resizes / 28.5k sync
  vs V1's 5,142 / 63.1k).

## 2. Byzantine agents (`byzantine_sim.py`)

### 2a. Forged shrink-intents — fail-safe, but a cost lever

Tracing V3's two uses of intents shows both can only make coverage look
*lower* (growers subtract announced vacates; executing shrinkers count
lower-priority intenders as gone). Forgery therefore pushes honest agents
toward growing and deferring — the safe direction. Measured worst case
(whole-ring vacate claims forged in the 10 lowest ids' names, sustained
from t=1500): **true floor never below R** (6 ≥ 5), while mean arc level is
pinned at 2.34 vs 0.85 clean, sync cost 77.2k vs 32.9k (2.3×), resizes
5,822 vs 3,619. Forged intents cannot orphan data but can partially
*disable sharding* — a resource-exhaustion lever.

Defenses, in increasing strength: (i) range-validate intents against the
claimed agent's declared arc (local, cheap — kills whole-ring forgeries);
(ii) authenticate sender identity (kitsune2 connections are already
peer-keyed; third-party forgery requires defeating transport auth);
(iii) sign intents (REPORT §7 already requires this for production).

### 2b. False coverage — the real Byzantine gap, threshold at K = R

K liars declare full arcs but store nothing. Declarations are the
controller's *sensor*; every variant trusts them identically, so this is
not a control-law weakness — it is what the control layer cannot see.

| K liars (R=5) | declared floor (end) | true floor (end) | ring with 0 true copies |
|---|---|---|---|
| 2 | 5 | 3 | 0.0% |
| 4 (=R−1) | 5 | 1 | 0.0% |
| 5 (=R) | 5 | 0 | **27.1%** |
| 10 | 10 | 0 | 69.7% |
| 20 | 20 | 0 | 71.1% |

The mechanism: K phantom copies on every sector let honest agents shrink
while declared coverage stays ≥ R; once K ≥ R, entire regions can reach
zero real copies with the dashboard green. **The attack is invisible to
declared coverage by construction.** Trojan ending measured at K = R−1:
liars vanish simultaneously at t=2200; true floor had been squeezed to 1
but recovery completes with zero loss (honest agents see real
under-coverage the moment the phantoms leave). An equal-size honest storm
never dips below 5 — the damage was done by the *lying*, not the leaving.

Implication for #160: the shrink path needs declared arcs to be
*earned* — kitsune2's verified-sync growth gate covers the grow side;
symmetric auditing (e.g., can this peer actually serve what it declares,
sampled during gossip) is the missing sensor-integrity primitive. At
minimum, R should be provisioned assuming some liar mass: the safety
margin is exactly R − K.

## 3. Scale (`scale_sim.py`)

V1 vs V3, activation + storm (30% die), N ∈ {200 … 5000}, two series:
fixed 512-sector ring (density grows 25×) and constant-density (ring up to
16,384 sectors). Settle criterion scaled to population (rate < N/200).

- **Activation is where scale bites, and it selects the controller.** The
  simultaneous shrink-down from full arcs becomes more contended with N.
  V1 loses data at N ≥ 2000 (19 zero-coverage sector-ticks at N=2000-fixed;
  1,071 at 2000-density; 1,474 at 5000-density). **V3: floor exactly R,
  zero loss, at every N in both series.**
- **Storm recovery scales for both** (zero loss everywhere). Caveat worth
  keeping: at N=5000 on the *fixed* ring both variants dip to floor 1 —
  at ~10 agents/sector arcs sit at level 0 and a 30% die-off leaves
  single-copy sectors until regrow. The constant-density series holds
  floor 4–5, so the mitigation is ring granularity (more sectors as N
  grows), not a different control law.
- **Costs stay bounded:** V3 per-agent resizes and sync are flat-to-falling
  with N; activation settle grows mildly (1,104 → 1,694 ticks from N=200
  to 5000-density). No super-linear cascade signature appeared.

## 4. The §6.1 residual race, quantified (`race_quantify.py`)

**Method.** V3, N=200; R ∈ {3,5} × lag_max ∈ {24,48,96} (intent_delay =
2·lag_max+2, warmup scaled 1500+35·lag so slow-hysteresis cells measure a
settled network — a fixed warmup understates rates); churn hazard p from
5e-4 to 3.2e-2 per agent-tick with matching Poisson joins; 40 seeds ×
1500 observed ticks per point (1,680 runs). Every zero-coverage episode is
classified at onset: **shrink-hole** (a shrink executed over the sector
that tick — §6.1 proper) vs **churn-hole** (deaths alone removed the last
copy), with durations tracked to recovery.

**Results** (`results/race_summary.md`, `results/race.png`):

- **The hole regime exists but is churn-dominated.** Of ~2.28M holes
  observed across all cells, ≥99.9% were churn-holes: all live holders of
  a sector died before anyone could regrow — the generic floor of *any*
  R-replicated system under that hazard, static sharding included. The
  controller-specific §6.1 mechanism contributed, at R=5, **19 holes out
  of ~1.0M** (0.002%), all at hazards ≥ 2e-2 (mean node lifetime ≤ 50
  ticks); at R=5/lag=24 it contributed **zero at every hazard**.
- **Scaling behaves as the blind-window model predicts:** log-log slope of
  hole rate vs p ≈ 2.0–2.4 at R=3 vs ≈ 3.0–4.0 at R=5 — raising R steepens
  the exponent (sub-R absolute values are expected: recovery truncates the
  window and the top of the range saturates). At R=5, every hazard
  ≤ 4e-3 — a full population turnover every ~4 minutes at 1 tick ≈ 1 s —
  produced zero holes of any kind in 60,000 observed ticks per point.
- **Holes are transient:** median 23 ticks to re-covered, p90 ≈ 95,
  max 824. And per REPORT §6.1, a shrink-hole's leaver still holds the op
  data, so prompt regrow recovers it; churn-holes are the genuinely lethal
  kind and they are not a controller property.
- **Worked extrapolation** (illustrative, assumptions explicit): R=5,
  lag=24, using the fitted slope 3.97 from the lowest observed point
  (p=8e-3 → 7.7 holes/1000 ticks network-wide). At a realistic hazard
  where deaths consume 1% of the blind window (p ≈ 1.4e-4; e.g. ~2 h mean
  node lifetime with a ~75 s staleness+wait window), the total hole rate
  extrapolates to ~8e-10 per tick for the whole 200-agent network —
  roughly one transient hole per ~40 network-years, of which the
  §6.1-specific share is ~0.002%. The claim is the *scaling*, not the
  decimal: the race is real (Stage 2 observed it once, unmitigated, on a
  real transport), bounded (storm brake), and at production-like hazards
  vanishingly rare relative to the ordinary churn floor that R must be
  provisioned for anyway.

## Limitations

Partition, Byzantine, and scale scenario runs are single-seed (seed 42)
point measurements in the Stage-1 idealised model (full visibility within
a side, one lag per viewer, sync linear in sectors); the race study is the
only one with per-point statistics (40 seeds). Partitions are binary and
clean — no asymmetric reachability, no message loss short of total,
groups fixed at 2. Liars are maximally crude (full arc, never move);
stealthier liars (modest arcs, rotating) would trade damage for
detectability and are unmodelled. Scale stops at N=5000 and inherits the
Stage-1 clamp default. The tick→seconds mapping used in extrapolation is
nominal; the dimensionless quantity is p × window. Ground truth remains
*declared* coverage except where stated (`true_*` metrics). Stage 2
demonstrated concretely that idealisations hide real constraints; these
results say where to look next, not that the search is over.

## Artifacts and reproduction

| artifact | location |
|---|---|
| partition study | `partition_sim.py` → `results/partition_{split5050,split9010,flapping}.png`, `partition_summary.md`, `partition.json` |
| Byzantine study | `byzantine_sim.py` → `results/byz_{forge,liar}.png`, `byz_summary.md`, `byzantine.json` |
| scale study | `scale_sim.py` → `results/scale.png`, `scale_summary.md`, `scale.json` |
| §6.1 race study | `race_quantify.py` → `results/race.png`, `race_summary.md`, `race.json` |
| shared style/helpers | `ext_common.py` |
| one-command runner | `./run_stage3.sh` (≈ 25 min on 8 cores; log → `results/stage3_run.log`) |

Same environment as Stage 1 (`REPRODUCE.md`): Python 3.12, numpy 2.5.1,
matplotlib 3.11.0. All seeds fixed; `arc_sim.py` unmodified.
