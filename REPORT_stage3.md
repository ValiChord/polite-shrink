# Stage 3: partitions, Byzantine agents, scale, and the §6.1 race quantified

**Author:** Ceri John ([topeuph-ai](https://github.com/topeuph-ai)), with AI assistance (Claude, Anthropic)
**Date:** 2026-07-13
**Extends:** `REPORT_stage1.md` (Stage 1 simulation + Stage 2 kitsune2 port). Its §7
lists four threats to validity this stage was built to test: network
partitions, Byzantine behaviour, parameter-regime transfer (scale), and the
§6.1 residual race left unquantified — plus the §6.2 global repair rule,
which §6.2 explicitly required simulating before implementation. Stage-1
code (`polite_shrink.py`) is untouched; every extension is a subclass in a new
file, so the Stage-1 byte-determinism claims stand.

## Summary of findings

| # | Question | Answer |
|---|---|---|
| 1 | Does a netsplit + heal orphan data? | **No durability loss in any of 9 runs.** V3's durability floor never left R=5; the heal-time concurrent shrink storm is absorbed. Flapping partitions defeat V1 (1,007 unreachable sector-ticks; never re-settles) but not V3. |
| 2 | Can forged ShrinkIntents make honest nodes abandon coverage? | **No — the channel is fail-safe by construction and measurement.** Worst-case forgery (whole-ring claims in the highest-priority names) causes zero loss; it is a *cost* attack: 2.3× sync, +60% resizes, arcs pinned wider. §6: the range-validation defense cuts it to ~4% and is implemented on the fork. |
| 3 | Can lying about coverage destroy data? | **Yes — catastrophically, and invisibly, past a sharp threshold at K = R.** K full-arc liars: at K=R−1 the network survives on margin 1; at K=R, 27% of the ring has zero real copies while declared coverage reads healthy; at 2R, 70%. No control law can defend: this is sensor integrity, not control. |
| 4 | Does the controller survive scale? | **V3 yes, V1 no.** At N ≥ 2000 the activation cascade makes V1 lose data (up to 1,474 zero-coverage sector-ticks at N=5000); V3 held floor = R with zero loss at every N up to 5000 on rings up to 16,384 sectors, with per-agent costs flat and settle time growing only mildly. |
| 5 | Does §6.2's proposed global repair rule work, and is it safe? | **Yes to both, with one characterized trade-off.** The sparse-network deadlock is real (V3 without the clamp: stuck in 5/90 port-scale seeds, 1/30 clustered seeds at N=200); V4 (expanding-ring repair) recovered **every** run while keeping sharding, no thundering herd in dense networks, zero loss across the whole regression battery. Trade-off: V4 tracks the target R more tightly, removing V3's *incidental* ~2× over-provisioning; running V4 at R+1 buys the margin back at comparable cost. |
| 6 | How often does the §6.1 race actually bite? | **Almost never, even under escalated hazard — in the single-clock model.** Across ~2.3M observed holes, ≥99.9% were pure churn outrunning recovery (the generic replication floor, not a controller defect); shrink-executed holes (§6.1 proper) were 0.002% at R=5 — and zero at R=5/lag=24 at *every* hazard tested. Hole rate scales with hazard at slope ≈ 3–4 (R=5) vs ≈ 2–2.4 (R=3), consistent with the blind-window model. All holes are transient (median 23 ticks, p90 ≈ 95). **Caveat:** these figures couple death-detection to gossip staleness (one lag); the decoupled death-clock is unquantified and is bounded by the storm brake (§6, item 4), not by this decimal. |
| 7 | Can the K = R liar ceiling (finding 3) be removed? | **Yes — proof-gated "verified coverage" makes it disappear, at a bandwidth cost the operator sets.** Counting a peer only while a fresh proof-of-serve backs it holds the true floor at 6.4–6.6 with zero dead sectors at *every* K from 0 to 3R (vs declared coverage's 25–69% ring death from K=R). The pessimism cost in an honest network is a knob: starving the audit is 7.5× sync, but at 6–10 audits/agent-epoch it matches declared sharding at ≈13–16% extra sync. Full-arc liars closed; partial liars measured in finding 8. |
| 8 | Does verified coverage survive *partial* liars (store a strategic fraction, serve some challenges)? | **Yes against data loss, with a measured margin dip and a tunable knob.** A sampled c-check certifies a fraction-p liar with probability p^c; verified coverage loses **zero data at every p** (declared loses 69% of the ring to full liars), but the true floor dips *below R* at intermediate p (3.7 at p=0.5 — the liar both evades often and withholds coverage). Raising the audit sample count restores the margin (floor 5.6 ≥ R by c=3): partial lying is made costly and bounded, not impossible. |
| 9 | Is the core safety property provable, not just well-tested? | **Yes — exhaustively.** TLA+/TLC verifies "a sector never drops below R" over *every* reachable state, no error, for N up to 8 (R from 1 to 7). The naive 2021 rule (no wait, no tie-break) fails the same check with a counterexample, isolating the two-phase tie-break as what buys safety. A proof of the control-loop property, complementing the sampled sims. |
| 10 | Is a *partially* upgraded network (mixed V3/V0 during rollout) safe? | **Yes, from ~10% adoption — no flag day.** Shrink-race loss is zero at every f ≥ 0.10 across 312 seeds in activation/flashcrowd/churn (a cliff, not a slope): a small polite minority forms a redundancy backbone the naive majority free-rides on. Storm keeps a ~0.3% residual — 9/11 unpreventable simultaneous mass-death, 2/11 the §6.1 race, which the storm brake closes. Cost of early rollout: a thinner margin. (`rolling_upgrade_sim.py`, `REPORT_rolling_upgrade.md`) |

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
Defense (i) is now measured and implemented — see item 2 of the §6 addendum.

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
sampled during gossip) is the missing sensor-integrity primitive — its
dynamics are now validated in simulation (item 3 of the §6 addendum). At
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

## 4. The §6.2 global repair rule, simulated before implementation (`repair_sim.py`)

REPORT_stage1.md §6.2 proposed a global under-coverage repair rule to remove the
clamp dependency in sparse networks, and required simulation before
implementation because it "introduces dynamics the sweep never validated."

**The rule (V4 = V3 + expanding-ring repair).** Quantised growth cannot be
steered, but repeated doubling reaches everywhere — so distant holes
*motivate* growth behind a distance-staggered fuse: an agent reacts to an
under-covered sector inside its level+g ancestor block (g ≥ 2; g = 1 is
V3's native sibling-half check) only after the condition persists
`grow_need + (g−1)·2·lag` ticks. Ring-near agents move first; if they
close the hole, everyone further out resets and never grows. No new
message types; growth stays quantised, local-information, hysteresis-gated.

**The deadlock is real, and V4 eliminates it.** In the regime the port
observed it in (8 nodes, R=2, clamp off), V3 stalled — under-covered ring,
resize activity ceased — in **5/90 seeds**; a clustered-survivor geometry
reproduces it even at N=200/R=5 (1/30). **V4 recovered every run in every
case** (90/90 and 30/30), slightly faster than V3 and at ~5% extra sync,
*while still sharding* — unlike the clamp, whose rescue is permanent
full-arc storage on every survivor. Where the deadlock doesn't occur
(random survivor sets — the common case), V3 and V4 are statistically
indistinguishable.

**No thundering herd.** Dense-network probe (all declared holders of one
sector killed at equilibrium, growers counted net of a matched no-kill
control, 8 seeds): V4 responded with *fewer* growers than V3 (100 vs 114
over baseline), recovered faster (median 53 vs 62 ticks), at slightly
lower sync. The staggered fuse holds: distant agents' timers reset when
near agents close the hole.

**Regression battery: zero loss everywhere, one characterized trade-off.**
Across activation/storm/flashcrowd/churn × seeds (26 runs), no run lost
data. But V4 changes the *operating point*: its repair grows fill the
R−1 holes that stall V3's shrink cascade, so the network settles much
closer to the true target (measured at seed 42: mean coverage 6.0 ≈ R+1
vs V3's 10.0 ≈ 2R, with sync cost 8.2k vs 23.0k on activation — 64%
cheaper). The flip side: V3's clunky equilibrium quietly over-provisions
~2×, and that incidental buffer absorbs storms. Across seeds the
post-storm floors overlap (V3: 2–4, V4: 2–5) — no *systematic*
regression — but the margin is now honest rather than accidental:
**V4 at R+1 dominates V3 at R** (post-storm floors 4–6 vs 2–4, churn
floors 4–5 vs 4) at comparable cost. Recommendation for #160: adopt the
repair rule with R provisioned explicitly for the desired margin, rather
than relying on hunting-stall over-provisioning that no one designed and
no spec guarantees.

## 5. The §6.1 residual race, quantified (`race_quantify.py`)

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
- **Scope of these rates.** Every figure in this section is measured in the
  single-clock model, where a dead holder fades from stale views on the same
  gossip lag that governs staleness (`race_quantify.py` subclasses the
  Stage-1 `Sim`; its detection latency *is* the staleness + wait window).
  Real transports decouple these — death-detection via connection timeout is
  a slower, separate clock (the Stage-2 discovery) — which widens the blind
  window and would raise the raw shrink-hole rate above these numbers. That
  decoupled regime is unquantified here; it is exactly what the storm brake
  (not this decimal) exists to bound, and §6 item 4 accordingly rests the
  "leave it alone" decision on clock-independent grounds.

## 6. Addendum (same day): the five follow-ups, dispositioned

Stage 3's findings implied five actions. Each was either done or
deliberately declined, with evidence:

**1. Ring granularity must scale with N — documented recommendation.**
Already evidenced by §3's constant-density series (post-storm floor 4–5
where the fixed ring gives 1). No further work: this is a kitsune2
protocol-parameter decision (`SECTOR_SIZE`), not a controller change.
Interim rule: provision R against agents-per-sector, not as an absolute.

**2. Intent range-validation — simulated AND implemented.**
Simulation (`defense_sim.py`): capping forged intents to what validation
admits reduces the attack from 2.3× sync (77.2k vs 32.9k clean) to **~4%
(34.3k)**; arcs settle at level 1.01 vs the attack's 2.34 (clean 0.85);
resize count returns to baseline (3,623 vs 3,619). Implementation (fork
commit `5224d37`): a structural check at receive (no vacate span can
exceed half the ring) plus consumption-time containment against the
announcer's declared arc on the same peer snapshot the tick's coverage
uses; local agents bypass. Free bonus: stale intents from
already-executed shrinks are dropped instead of double-counted. 84
gossip tests + the storm test + clippy clean.

**3. Serve-audit against liars — simulated; the dynamics work.**
The most conservative variant (each agent samples 2 declared peers per
decision epoch; one failed serve → *per-observer* exclusion, no verdict
gossip, no reputation machinery) fully rescues the K=2R liar collapse:
from ~350 permanently zero-true-copy sectors to a completely re-covered
ring, true floor back to R, in all 3 seeds, ~270–330 ticks after audits
start (`results/defense_summary.md`). Detection time scales as
N·threshold/rate; recovery begins *before* full detection because
partial exclusion already re-triggers growth. Implementation in kitsune2
is future work (it belongs in gossip's sync layer, not the controller);
until then R − K remains the honest safety margin.

**4. The §6.1 race — deliberately left alone.**
The decision rests on three clock-*independent* facts, not on the race's
measured rarity: (i) a shrink-hole's leaver still holds the op data, so it is
a recoverable *declared*-coverage gap, not data loss — the genuinely lethal
holes are pure churn, an R-provisioning question, not a controller defect;
(ii) the storm brake bounds the blind window even when the death-clock
decouples from staleness (§5 scope note), the regime a single-clock number
cannot speak to; (iii) any added shrink-race mechanism would buy complexity
against the wrong risk. The measured rate (§5: 0.002% of holes at R=5 under
absurd hazard, zero at short lags, all transient) is *corroboration* in the
single-clock model, not the load-bearing argument. Decision recorded here so
it isn't re-litigated.

**5. Rotating the tie-break — tested, premise refuted, not adopted.**
We hypothesised the lowest-id-proceeds rule caused the skewed
equilibrium arc distribution. Measured (`fairness_sim.py`): the skew is
real and extreme — the top decile of agents holds ~91% of stored
sectors — but it is **not id-correlated** (corr(aid, level) ≈ +0.08),
and rotating the priority per epoch (V3F) does not flatten it (93% at
either period). Probes show only weak links to home density (−0.10) and
gossip lag (−0.06): the skew is hysteresis-freeze path dependence.
Rotation is *safe* (zero losses in all 288 sweep runs, including a
period chosen so every intent straddles an epoch boundary), so it
remains available if a real fairness mechanism ever needs it — but it
buys nothing today, and the big arcs it would erode are the same
emergent insurance that gave §4's sparse-recovery cascade global reach.
Real storage fairness would need load-aware growth targets: future
work, with that tension named.

## 7. Verified coverage — closing the liar window (`verified_coverage_sim.py`)

§2b and §6 left the sensor-integrity gap open: declarations are the
controller's only coverage signal, so K ≥ R full-arc liars silently destroy
true replication, and the serve-audit of §2 (`defense_sim.py`) only
*subtracts* a liar once an auditor has caught it — an optimistic policy with a
detection-lag window. This study tests the pessimistic inversion.

**Rule.** A declared peer counts toward an agent's coverage *only while that
agent holds a fresh proof-of-serve from it* — a successful audit within
`proof_ttl` ticks. Proofs are minted by the same random audits §2 already
models: an honest peer serves the challenged sector and is certified for the
TTL; a liar serves nothing and is never certified. The shrink safety re-check
(`_execute_intent`) then vacates only when *proven* coverage stays ≥ R, so a
liar contributes zero from the first tick — there is no window and no K = R
threshold. (The unpredictable-sample challenge is the same primitive family as
ValiChord's own attestation challenge/response; a deployment would strengthen
its membership proofs to body-dependent proofs-of-retrievability.)

**Safety** (3 seeds, tail-mean of true coverage; declared and
reactive-exclusion carried for contrast, R = 5):

| policy | K=0 | K=4 | K=5 (=R) | K=10 (2R) | K=15 (3R) |
|---|---|---|---|---|---|
| declared true floor | 5.7 | 1.0 | **0.0** | **0.0** | **0.0** |
| declared ring 0-copy | 0% | 0% | **25.4%** | **68.8%** | **69.5%** |
| reactive-exclusion true floor | 5.7 | 5.0 | 5.3 | 5.3 | 5.0 |
| **verified true floor** | **6.5** | **6.5** | **6.4** | **6.4** | **6.6** |
| verified ring 0-copy | 0% | 0% | 0% | 0% | 0% |

Declared collapses at the threshold (§2b reproduced). Reactive exclusion
recovers the floor to ≈R at every K but pays rising audit-churn sync. Verified
coverage holds the floor at 6.4–6.6 with zero dead sectors at *every* K from 0
to 3R — the curve is flat, because liars never enter the tally, so there is
nothing to detect and nothing to recover from.

**The price is pessimism, and it is a knob.** In an all-honest network (K = 0)
an honest peer un-audited within the TTL also drops out of the tally, so the
controller over-provisions unless the audit budget keeps enough peers fresh:

| audits/epoch × TTL | mean level (0.94 = declared) | sync (27.4k = declared) | peers fresh (of ~195) |
|---|---|---|---|
| 2 × 300 | 3.78 | 205.7k | 78 |
| 4 × 600 | 1.34 | 39.3k | 172 |
| 6 × 600 | 0.96 | 31.7k | 189 |
| 10 × 600 | 0.93 | 31.0k | 198 |

Starving the audit (2/epoch, TTL 300) over-provisions 7.5× on sync and nearly
disables sharding. Raising the budget buys the efficiency straight back: at
6–10 audits per agent-epoch and TTL 600 verified coverage matches declared
coverage's sharding level (0.93–0.96 vs 0.94) at ≈13–16% extra sync. The
design converts the R − K honest-margin ceiling of §6 into a *bandwidth* cost
the operator sets directly.

**Granularity and what is not modelled.** A liar here stores nothing and fails
every audit; a successful audit certifies the peer's *whole declared arc* for
the TTL (the same whole-arc granularity as §2's exclusion). Partial liars —
store a strategic fraction, serve some challenges — need *per-sector* proofs to
pin down and are left as future work; the closed threat is the full-arc liar of
§6.2, the one invisible to declared coverage. Like the serve-audit, this proves
possession at audit time, not willingness to serve the eventual reader —
mitigated in practice by making an audit indistinguishable from a real read
(refusing audits = refusing service), but that identity is asserted here, not
simulated. Determinism holds (audit RNG seeded; two runs byte-identical). A
reference implementation on the kitsune2 fork is future work: challenges would
travel on the same `k2sharding` channel as the intents.

## 8. Partial liars against verified coverage (`partial_liar_sim.py`)

§7 closed the *full-arc* liar and named the open edge: a partial liar that
truly stores a fraction p of its declared arc and can serve *some* challenges.
The audit must be a sampled range-check — a declared arc covers content that
does not exist yet, so it cannot be enumerated: challenge `c` random sectors of
the arc and certify it for the TTL only if all `c` are served. A liar holding
fraction p therefore certifies with probability p^c and, once certified, is
trusted over its *whole* declared arc — including the sectors it does not hold.

**Static sweep (K = 2R liars, c = 2 samples, 3 seeds, tail-mean):**

| p held | declared floor | declared ring 0-copy | verified floor | verified 0-copy |
|---|---|---|---|---|
| 0.00 | 0.0 | 68.8% | 6.7 | 0% |
| 0.25 | 0.0 | 4.2% | 5.3 | 0% |
| 0.50 | 1.0 | 0% | 3.7 | 0% |
| 0.75 | 3.3 | 0% | 3.8 | 0% |
| 0.90 | 5.3 | 0% | 5.3 | 0% |
| 1.00 | 10.0 | 0% | 10.0 | 0% |

Verified coverage loses **no data at any p** (zero dead sectors throughout),
where declared coverage loses 69% of the ring to full liars. It is not free:
at intermediate p the true floor dips *below R* (3.7 at p=0.5) — the partial
liar evades the sample often enough to certify *and* withholds enough real
coverage to matter. Full liars (p=0) are caught by any sample and excluded
(floor 6.7); honest peers (p=1) certify and behave normally. The worst case is
the middle, exactly as the p^c geometry predicts.

**The margin dip is a tunable knob — stringency sweep (p = 0.5, verified):**

| samples c | evade prob p^c | verified floor |
|---|---|---|
| 1 | 0.50 | 1.8 |
| 2 | 0.25 | 3.7 |
| 3 | 0.12 | 5.6 |
| 4 | 0.06 | 6.4 |
| 6 | 0.02 | 7.4 |

Raising the sample count drives evasion down exponentially and lifts the floor
back over R by c = 3, for more audit bandwidth. Verified coverage does not make
partial lying *impossible*; it makes it *costly and bounded* — the adversary
must genuinely store more to stay certified, and the defender sets how much by
choosing c.

Honest boundary: ground truth counts each liar's real holdings, so a partial
liar contributes the coverage it actually provides. Still unmodelled — two
attacks that step outside the p^c geometry. **(a) The fetch-on-challenge
liar:** it stores little but proxies each challenged sector from a real holder
on demand, so it certifies with probability ≈ 1 regardless of `p`. This
defeats the *detection* model above — the sample no longer measures durable
holdings — and is precisely why a deployable audit needs a body-dependent
*proof-of-retrievability* (§7), not a proof-of-can-answer-now. Its data-loss
reach is self-limiting (the proxy fails once honest copies actually run out,
at which point verified coverage drops the liar), but quantifying that residue
is its own study. **(b) The temporal prove-then-drop trojan** (certify, then
abandon within the TTL), a liveness-flavoured attack whose knob is
`proof_ttl`. Both share the §7 boundary: this proves possession at audit time,
not willingness to serve the eventual reader.

## 9. Formal safety proof (`spec/`, TLA+ / TLC)

The sweep's 0-losses-in-1,248-runs is strong evidence but still sampling. The
core safety property is small enough to *prove* — exhaustive model checking
over every reachable state, in TLA+.

The property is per-sector (for any one sector the covering nodes decide
independently, so proving it for one sector proves it for the ring):

> a sector never holds fewer than R real copies.

`spec/PoliteShrink.tla` models the two-phase rule: announce unconstrained
(worst case — everyone announces), execute reading the *current* holder/intent
sets (what the "wait 2× max lag" delay buys), with the lowest-id-proceeds
tie-break. TLC checks `SafeCoverage` with **no error — exhaustively** — at
every configuration tried:

| Nodes | R | distinct states |
|---|---|---|
| 6 | 3 | 656 |
| 7 | 2 | 2,172 |
| 8 | 4 | 5,984 |
| 8 | 1 | 6,560 |
| 8 | 7 | 1,280 |

`spec/NaiveShrink.tla` — the pre-2021 stale-view drop, no wait or tie-break —
is *violated* at each config (TLC returns the hallway-dance counterexample),
proving the model has teeth and that the safety is bought by the two phases,
not the way the model is written. This covers control-loop safety under the
model's abstraction (one sector, execute-time intent visibility, honest
holders); it complements, not replaces, the sims, which carry gossip timing,
Byzantine liars, and geometry. Reproduce: `spec/README.md`.

## 10. Rolling upgrade — a partially-adopted network (`rolling_upgrade_sim.py`)

Every study above runs a *homogeneous* network. A real rollout is mixed: some
nodes run polite shrink (V3), the rest still run the naive controller (V0).
`MixedSim` makes the controller a per-agent property (a fraction *f*, chosen by a
seeded permutation, run V3); a faithfulness guard confirms it reduces
*byte-identically* to `Sim(V0)` at f=0 and `Sim(V3)` at f=1 on all four
scenarios — the primary defence against a modelling bug. Swept at the canonical
312 seeds × 4 scenarios. Full write-up: `REPORT_rolling_upgrade.md`.

**No flag day.** In activation, flashcrowd, and churn the shrink-race loss goes
from *certain* at f=0 to **zero at every f ≥ 0.10, across all 312 seeds** — a
cliff, not a slope. Even a ~10% minority of polite nodes protects the whole
network: they form a self-adjusting **redundancy backbone** (the naive majority
free-rides to level 0 by t≈50; a handful of polite nodes hold the floor at R by
construction, since a polite node refuses to shrink a sector below R).

**Storm exception, dissected honestly.** Storm keeps a low residual — 11 losing
runs over f=0.1–0.95 (≈0.3%), and **zero at f=0.99 and f=1.0**. Pure/near-pure V3
never loses; the *presence of naive free-riders* is what introduces it, by
thinning and concentrating the over-provisioning margin (at f=0.10, 89 sectors
sit at bare R vs ~50 at full adoption). Attributing all 11 losses by
counterfactual and holder-trace (`diag_attribute_all_storm.py`,
`diag_trace_post_death.py`):

- **9 / 11 are pure correlated death** — all holders of a sector die at once at
  t=1500; coverage hits zero the instant they die, before any controller acts.
  No local rule can survive the simultaneous death of a sector's entire holder
  set.
- **2 / 11 are the §6.1 intent-death race** — a *polite* node executes a shrink
  intent announced before the storm, on a stale view that has not yet registered
  the deaths, and drops an already-thinned sector's last holder. The race
  surfaces here but not in pure V3, because the thin backbone leaves no margin to
  absorb the execute; V3's accidental ~2R over-provisioning otherwise hides it.

**The storm brake closes the race (`brake_sim.py`, `brake_storm_sweep.py`).** The
kitsune2 port already cancels all pending intents when a peer death is detected
(§6.1); the base sim has none, which is why the raw race showed through. Adding
it — with death detection on a *separate, faster* clock (`detect_latency`, the
whole §6.1 point) — closes both race seeds whenever the brake fires before the
racing execute (detect_latency ≤ 8 closes both; the wider-gap seed tolerates ≤
15). The full brake storm sweep (312 seeds) confirms it closes the *class*: the
11 above-baseline storm losses drop to **9 — exactly the 2 §6.1-race cases
removed, no new loss introduced anywhere**, the remaining 9 being the pure-death
cases no rule can prevent. This *measures* §6.1's claim: the brake **bounds** the
race, leaving only the irreducible mass-death residual. **With the brake, polite
shrink causes zero data loss even in the mixed network at realistic detection
latencies.**

Design notes for #160: incremental rollout is safe against the shrink race from
~10% adoption; early rollout concentrates storage on the upgraded nodes and thins
the margin (resilience to *correlated* failure rises with adoption); and the
storm brake is **not optional** in a mixed network — the thin backbone surfaces
the §6.1 race that homogeneous over-provisioning hides.

## Limitations

Partition, Byzantine, and scale scenario runs are single-seed (seed 42)
point measurements in the Stage-1 idealised model (full visibility within
a side, one lag per viewer, sync linear in sectors); the race study is the
only one with per-point statistics (40 seeds). Partitions are binary and
clean — no asymmetric reachability, no message loss short of total,
groups fixed at 2. Liars are maximally crude (full arc, never move);
stealthier liars (modest arcs, rotating) would trade damage for
detectability and are unmodelled. Scale stops at N=5000 and inherits the
Stage-1 clamp default. The repair rule was tested at one stagger setting
(2×lag per ring) and its equilibrium-tightening effect was measured in
depth at one seed; the deadlock frequency estimates (5/90, 1/30) carry
the usual small-count uncertainty. The tick→seconds mapping used in extrapolation is
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
| §6.2 repair-rule study | `repair_sim.py` → `results/repair_deadlock.png`, `repair_summary.md`, `repair.json` (staged: `--study deadlock`, `--study rest`, `--study finish`) |
| Byzantine-defense study | `defense_sim.py` → `results/defense.png`, `defense_summary.md`, `defense.json` |
| verified-coverage study | `verified_coverage_sim.py` → `results/verified_coverage.png`, `verified_summary.md`, `verified.json` (`--quick` for a 1-seed pass) |
| partial-liar study | `partial_liar_sim.py` → `results/partial_liar.png`, `partial_summary.md`, `partial_liar.json` (`--quick` for a 1-seed pass) |
| formal safety proof | `spec/PoliteShrink.tla` + `spec/NaiveShrink.tla` (TLA+/TLC; needs a JRE + `tla2tools.jar`; see `spec/README.md`) |
| tie-break fairness study | `fairness_sim.py` → `results/fairness.png`, `fairness_summary.md`, `fairness.json` |
| intent range-validation (Rust) | kitsune2 fork `feat/sharding-module-v3` commit `5224d37` (`crates/gossip/src/sharding/intents.rs`) |
| §6.1 race study | `race_quantify.py` → `results/race.png`, `race_summary.md`, `race.json` |
| rolling-upgrade study | `rolling_upgrade_sim.py` + `brake_sim.py` → `results/rolling_upgrade_{summary.md,cells.jsonl,png}` + `rolling_upgrade_brake_storm_summary.md`; guard `validate_rolling_upgrade.py`; diagnostics `diag_{rolling_upgrade,margin,attribute_all_storm,trace_post_death,brake_reruns}.py`; full write-up `REPORT_rolling_upgrade.md`. Run separately (long): `python3 rolling_upgrade_sweep.py --seeds 312` (≈2–3 h) + `python3 brake_storm_sweep.py --seeds 312` |
| shared style/helpers | `ext_common.py` |
| one-command runner | `./run_stage3.sh` (nine studies, ≈ 55 min on 8 cores; log → `results/stage3_run.log`) |

Same environment as Stage 1 (`REPRODUCE.md`): Python 3.12, numpy 2.5.1,
matplotlib 3.11.0. All seeds fixed; `polite_shrink.py` unmodified.
