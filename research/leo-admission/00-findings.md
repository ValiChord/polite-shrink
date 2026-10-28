# StaleCap for LEO resource admission: audit findings (Stage 1–2)

2026-10-28. Sources: `ValiChord/polite-shrink` @ `1b949b9`, `topeuph-ai/kitsune2` branch
`feat/sharding-v7` @ `0cdcd8e`. TLC 2026.10.28 (nightly build, rev 56d37a9), OpenJDK 21.
Nothing in either repository was modified. Everything here is a read, a TLC run, or a new
probe spec in `tla/`.

Evidence labels: **[T]** reproduced TLC run, **[S]** read in source, **[R]** reasoned only,
**[?]** not checked.

## 1. What the three briefs share

All three ask whether **StaleCap** (the ceiling half of StaleBand; announce, wait `D ≥ L`,
re-check counting *all* announcers, `patient` / `patient_k` tie-break) can be a coordinatorless
admission primitive for a shared, countable reservation pool in a LEO mesh. They differ in
discipline:

| Brief | Strength | Problem |
|---|---|---|
| 1 (refactor + simulate) | Names four concrete Rust defects | Asks for a crate and `README`/`SPECIFICATION` before an audit; assumes `controller.rs` can be "extracted" into a scalar-slot crate (see §5); sets `C=4` per node, which is a local counter, and `R=2` "redundant path reservations", which mixes units |
| 2 (sceptical audit) | Gated stages, fault model first, baselines, "stop if Gate 2 fails" | Too large to do in one pass; includes commercial research |
| 3 (narrow reference impl) | Right scope: one discrete resource, no power/thermal | Says "begin by creating a reference spec if none exists"; one exists |

The coherent thread is Brief 2's gating applied to Brief 3's scope, with Brief 1's four bug claims
checked against source. I did that. I did not do crate packaging, an LEO simulator, or commercial
research; those sit behind gates that are not passed (§6).

## 2. Existing results reproduce [T]

`spec/v7/StaleCap.tla` exists upstream. Re-run unchanged:

| Config (4 nodes, L=2) | Result |
|---|---|
| V6 rule, C=2, D=2 | No error, 20,024 distinct states |
| `patient_k` ("V7"), C=2, D=2 | No error, 18,141 |
| V6 rule, C=2, D=4 (2×) | No error, 40,236 |
| V3 tie-break (lowest-ID), C=2, D=2 | **Safety violated** (control) |

Smallest V3 counterexample (3 nodes, C=2, D=L=2): nodes 1 and 3 announce at t=0; node 2 at t=1.
At t=2, 1 and 3 each commit, because neither sees node 2. At t=3 node 2 commits on a view that
shows only lower-ID node 1, assuming higher-ID node 3 will stand down. Three active against C=2.
Priority was used to decide who is *assumed to stay*, which is exactly the flaw V6 removes.
Log: `tla/logs/upstream_V3_C2_D2_counterexample.log`.

## 3. New probes on LEO-relevant stretches [T]

`tla/StaleCapLEO.tla` is `StaleCap.tla` plus four switches. With all switches neutral it
reproduces upstream's state counts **exactly** (20,024 distinct / 66,943 generated), which is
the check that I changed nothing by accident. All runs: 4 nodes, L=2 unless stated.

**a. Weighted requests (the "8 + 8 against 10" race).** Upstream is unit-weight. I replaced
cardinality with a sum of weights and left every rule alone.

| Weights, C | Rule | Safety `Σw(active) ≤ C` | Someone always admitted |
|---|---|---|---|
| 8,8,2,2 ; C=10 | patient, patient_k | holds | holds |
| 5,4,3,2 ; C=7 | patient, patient_k | holds | holds |

Safety transfers because the argument is "go only if everything visible, summed, fits", not
about cardinality. A naive local check admits 16 against 10 in this scenario by construction.
**Cost found:** a one-shot request can be rejected needlessly. Trace: nodes 1 (8) and 3 (2)
announce, node 2 (8) announces a tick later. Node 1 commits (8). Node 3 withdraws because node 2,
which can never fit beside node 1, was counted as a competitor; 8+2=10 would have fitted. Safe,
but it wastes capacity until a retry. The model has no retry, so how large this effect is under
real traffic is **[?]**.

**b. Staleness beyond L (partition, queueing, loss).** `Slack` lets a view be `L+Slack` old.

| Slack | D | Result |
|---|---|---|
| 1 | 2 | **Safety violated** |
| 1 | 3 (≥ L+Slack) | No error, 77k+ states |

The guarantee is conditional on the delay bound actually holding. Re-sizing `D` to the true
bound restores it; nothing detects that the bound has failed. In LEO the bound is the open
question: occlusion and routing delay are not propagation delay.

**c. Hidden assumption: one consistent cut.** Upstream hands an observer one atomic snapshot of
"who is active" and "who is announcing". Real gossip delivers the commit and the intent change as
separate messages. `Indep=TRUE` ages the two halves independently.

| Indep | Linger (intent stays visible after commit) | Result |
|---|---|---|
| TRUE | 0 | **Safety violated** (unit, and weighted 5,4,3,2 C=7) |
| TRUE | 2 (= L) | No error (unit 87k states, weighted 67k) |

So a faithful reading of `StaleCap.tla` that drops the intent on commit is unsafe once the two
messages travel separately. The fix is the analogue of upstream's A2: an intent must outlive the
commit becoming visible. The Rust avoids this by design (intent expiry is `execute_at + wait`
and is not withdrawn on success **[S]**), so the gap is in the *spec-to-implementation
contract*, not in the shipped code. It would bite a clean-room reimplementation, which is what
Brief 1's "zero-dependency crate" would be.

Not modelled **[?]**: crash/restart of an *active* node that forgets its own commitment
(unsafe by construction without stable storage, so it is a stated requirement, not a finding),
message duplication, true per-pair partitions.

## 4. Claims in the briefs, checked

| Claim | Verdict |
|---|---|
| `D ≥ L` ensures relevant announcements are visible | **Only with** (i) the bound holding for every message, (ii) intents outliving the commit's visibility (§3c). Fails with Slack > 0 at fixed D [T] |
| Lowest-ID tie-break prevents oversubscription | **False** as the sole rule [T, §2]. It only decides who waits; all announcers must still be counted |
| `patient` / `patient_k` prevent oversubscription | Safe in every checked model above [T], finite (N=4, L≤3), within the stated assumptions |
| Passing TLC means the ceiling cannot be exceeded | Holds for the model's assumptions and sizes only. Not shown for N>5 or for the Rust |

Category for the main guarantee: **an invariant of the model under stated environmental
assumptions, at finite size.** Not an unconditional invariant, and not shown for the Rust.

## 5. Brief 1's four "known bugs" against the Rust [S]

File `crates/gossip/src/sharding/controller.rs`, commit `0cdcd8e`. Coordinated growth is **off
by default** (`coordinated_growth`), so none of this affects the default configuration.

| Brief 1 claim | In source? | Direction of harm |
|---|---|---|
| `grow_recheck` uses `id < own_id`, not the patient rule | **Yes** (`grow_recheck`, counts only lower-ID growers; `execute_grow` has no Wait outcome) | This is the V3 rule, whose model has a counterexample (§2). Over-admission, i.e. a ceiling breach. Mapping Rust grow ↔ TLA `tb` is **[R]**, not run |
| Storm brake cancels pending shrinks without a withdrawal | **Yes** (brake block: `pending.take()` and `intents.remove`, no `withdraw_intent`) | Peers keep counting the ghost for up to `2·wait`. They over-count, so liveness cost only **[R]** |
| Sender-absolute expiry on the wire | **Yes** (`expires_at_us`, then `receive_intent` compares to the receiver's `Timestamp::now()`) | Sender clock *behind* receiver drops the intent early, breaking A2, which is a **safety** direction. Sender *ahead* only lingers. Tolerance is roughly the slack `wait − L` **[R]** |
| `view_delay` skips `live_grows` | **Yes** (`view_delay.apply(now, peers, live_intents)`; `live_grows` is read just above it) | Test-coverage gap: stale-view tests exercise shrink races but not grow races |

I did not build or run the fork's tests, and I did not change any fork code.

Brief 1's Task 1 premise is also off: `controller.rs` is 2,019 lines of arc/sector arithmetic
(`min_over`, `add_sectors`, `subtract_sectors` on `Vec<u32>` coverage arrays). A scalar-slot
admission primitive keeps the *rule*, not that code; it is a reimplementation, and `StaleCapLEO.tla`
is the better starting contract.

## 6. Gates

| Gate | Decision | Basis |
|---|---|---|
| 1: reproduce, understand protocol | **Pass** | §2 |
| 2: defensible capacity-safety property | **Pass, narrowly** | Finite-model invariant for discrete unit/weighted requests given D ≥ true staleness and intent linger; breaks as predicted when either fails (§3) |
| 3: Rust implements the model | **Not established** | Shrink side has a Rust model-check upstream (not re-run here); grow side uses the V3 rule (§5) |
| 4: real advantage over existing approaches | **Not established; the burden is unmet** | Below |
| 5–6: demo, packaging, outreach | **Blocked** | Depend on 3–4 |

**Why Gate 4 is open, and what would close it.**
- If the contested resource lives on one satellite (a terminal's laser slots), its owner decides
  locally and no distributed protocol is needed. StaleCap only matters for a pool shared across
  ≥2 satellites. **[R]**
- **Static quota** gives a hard ceiling under *any* partition with no timing assumption; its cost
  is utilisation.
- **Escrow / bounded-counter** schemes (rights pre-allocated and transferred between nodes;
  from memory, O'Neil 1986 and Balegas et al. on Bounded Counters, **not re-checked here**) also
  give a hard ceiling with no timing assumption. StaleCap's only visible advantage is that it needs
  no pre-assigned rights; its price is a timing assumption that LEO partitions can violate silently.
- The ceiling under partition is fail-closed only if silent nodes are counted as possibly holding
  (upstream `StaleBandNet` describes this; I did not re-run it). That never reclaims capacity from a
  crashed holder, so a reservation lease is needed, and a lease needs a clock bound: it brings the
  timing assumption back in.

**Cheapest experiment that could end this:** simulate one shared pool with static quotas, escrow
and StaleCap under a stated arrival process and a *measured-style* delay distribution with
occasional exceedances of `L`. Compare utilisation, rejection rate and breaches. If escrow or
static quota matches StaleCap's utilisation, stop. That uses the existing probe spec's rules and
needs no flight-specific claim.

## 7. Recommendation

Proceed to the baseline-comparison simulation only. Do not publish a crate, claim LEO
applicability, or contact anyone yet. Keep the framing the briefs share: admission supervision
above independent hardware protection, never a safety interlock. Fix the three Rust items in §5
only if coordinated growth is going to be enabled; I have not done so.

## 8. Baseline comparison result (Stage 4 experiment, run 2026-10-28)

`sim/baseline_compare.py`, output in `baseline_compare_output.txt`. One shared pool, C=16 unit
slots, 8 nodes, L=3, D=3, mean hold 30 ticks, per-node FIFO queue with 60-tick patience,
3 seeds, 6000 ticks. All parameters hypothetical. Lag is uniform 1..L, but with probability `p`
(0, 0.02, 0.1) a lag is 4L, i.e. the delay bound is violated. Demand skew 0 (balanced) or
1 (Zipf-like hotspot). **Suggested by simulation [sim], not a model-checked result.**

| What | Observation |
|---|---|
| Ceiling breaches | Static and escrow: **0 everywhere**. StaleCap: 0 at p=0; breaches appear at p=0.02 and grow at p=0.1 (up to 35 breach-ticks, overshoot 1 unit) |
| Utilisation and acceptance, load 0.8 | Escrow ≈ StaleCap (0.76–0.78 vs 0.75–0.77 util; 0.98–0.99 accept). Both beat static under skew (0.57 util, 0.74 accept) |
| Same, overloaded (load 1.2) | **Escrow clearly ahead of StaleCap**: 0.95 vs 0.81–0.82 util; 0.80–0.82 vs 0.67–0.71 accept. StaleCap's conservative counting of competing announcers under contention costs real capacity |
| Static quota, balanced demand | Not far behind (0.91 util at load 1.2), and loses badly only under skew |

**Reading.** In this model StaleCap has no advantage on any metric: escrow equals or beats it on
utilisation, acceptance and latency, and keeps a hard ceiling with no timing assumption.
StaleCap alone breaches when the delay bound is violated. Gate 4 therefore fails on the evidence
so far.

**Caveats that favour escrow, so the comparison is not fair to StaleCap yet:**
- Escrow here has reliable messages. If a transfer message or a node is lost, rights are
  stranded (capacity leaks); this is not modelled and is escrow's real weakness. StaleCap needs
  nothing transferred, so it degrades differently. Add message loss and crashes before concluding.
- Escrow needs a rights-recovery story for crashed holders, which brings back a failure-detection
  assumption; StaleCap's equivalent is the lease question in §6.
- StaleCap here uses a consistent-cut view per observed pair (findings §3c is not exercised).

**Decision.** Do not proceed to a crate or an LEO simulator. One more cheap experiment decides it:
add message loss and node crash to the sim and measure stranded capacity for escrow against
breaches for StaleCap. If StaleCap still has no regime where it wins, stop and keep the work as
a research note on the V6/V7 rule (its value for the shrink problem is unaffected).

## 9. Fairer comparison: crashes and permanent node death (run 2026-10-28)

`sim/baseline_compare2.py` (adds crashes to §8's script), output in
`baseline_compare2_output.txt`. Skew 1, 6 seeds, 9000 ticks. A crashed node is down 40 ticks and
its held units are freed by a lease at that point; with probability `perm` (0.25) it never returns.
Crash rate 0.0003 per node per tick. Transport loss is modelled as delay spikes for **both**
schemes (probability p=0.05 of a 4L lag), on the reasoning that a real escrow retransmits
transfers rather than losing rights. `util_last` is utilisation over the final third of the run.
**[sim]; hypothetical parameters; high variance because few nodes die per run.**

| Regime | Result |
|---|---|
| No crashes, or transient crashes only | Same picture as §8: escrow ≥ StaleCap on every metric; StaleCap breaches once p>0 |
| Permanent deaths, load 0.8 | Roughly a tie (`util_last` 0.40–0.45 for all three); most demand died with the node |
| **Permanent deaths, load 1.2** | **StaleCap ahead:** `util_last` 0.63 (p=0) and 0.76 (p=0.05) against escrow 0.44 and 0.41, static 0.45; acceptance 0.83–0.86 against escrow 0.75–0.82. Escrow had 0.58–0.62 of C stranded in dead nodes' rights on average |
| StaleCap breaches in that regime | 0 at p=0, up to 12 breach-ticks at p=0.05 (all 1 unit over) |

**What this establishes.** The one advantage StaleCap has is structural and now visible:
nothing is bound to a node, so a dead node strands nothing, whereas escrow and static quota lose
a dead node's rights for good. It pays for that with a hard dependence on the delay bound
(breaches at p>0) and with lower utilisation under plain overload (§8).

**Caveats, none yet tested:**
- Escrow can be given a recovery path (declare a node dead and re-mint its rights). Doing that
  safely needs agreement on death, which is a coordinator or consensus step, and it needs a
  failure-detection timing bound: the same kind of assumption StaleCap makes. A comparison
  against *escrow with recovery* is the next fair test; I expect the gap to narrow.
- Permanent loss of 25% of the capacity is a heavy hypothetical; with fewer deaths the gap shrinks.
- The StaleCap sim still uses consistent-cut views; its breaches under delay spikes would be
  worse with independent message delays and no linger (§3c).

**Updated decision.** Gate 4 is no longer a flat fail: StaleCap has one demonstrable niche, a
shared pool where nodes die for good and capacity must remain usable without recovery
machinery, provided the delay bound is trustworthy. Whether that niche exists for an LEO
constellation is **[?]**: satellites that fail permanently do happen, but whether a pool's
capacity is bound to the failed satellite, and whether recovery is already handled by existing
network management, are unanswered. Next fair test: escrow-with-recovery in the same sim. Still
no crate, LEO simulator or outreach.

## 10. Escrow with recovery (run 2026-10-28)

`sim/baseline_compare3.py`, output `baseline_compare3_output.txt`. `escrow_rec` re-mints a dead
node's rights among live nodes at lease expiry (40 ticks) plus a detection margin Td=8, so units
it held are already freed. A false suspicion (a heartbeat delayed beyond Td, probability p per
10 ticks per live node) re-mints a *live* node's rights while it still holds units. Same pool and
caveats as §9. **[sim], hypothetical, crude failure-detector model.**

| Regime (load 1.2, 25% of crashes permanent) | `util_last` | accept | breach ticks (worst seed) | max overshoot |
|---|---|---|---|---|
| Plain escrow, any p | 0.41–0.44 | 0.75–0.82 | 0 | 0 |
| Escrow + recovery, perfect detection (p=0) | **0.72** | **0.93** | 0 | 0 |
| StaleCap, p=0 | 0.63 | 0.83 | 0 | 0 |
| Escrow + recovery, p=0.05 | 0.56 | 0.91 | **1742** | **8** |
| StaleCap, p=0.05 | **0.76** | 0.86 | 12 | 1 |

At load 0.8 with no crashes and p=0.05, escrow + recovery breached for up to 496 ticks (overshoot 7)
where StaleCap breached for up to 7 ticks (overshoot 1); at p=0 neither breached.

**Reading.** The three schemes trade the same thing differently:

| Scheme | Hard ceiling | Capacity after permanent node death | Needs a timing assumption |
|---|---|---|---|
| Static quota | Always | Lost for good | No |
| Plain escrow | Always | Lost for good | No |
| Escrow + recovery | Only if failure detection is right | Recovered | Yes (detection + lease) |
| StaleCap | Only if message delay ≤ L | Never stranded | Yes (delay bound) |

With a trustworthy detector, escrow + recovery beats StaleCap outright. When the timing
assumption fails, both breach, but differently in this model: StaleCap's breaches are short races
of about one unit, escrow + recovery's are large, long, and persist until the wrongly re-minted
rights are reconciled. That graceful degradation is StaleCap's only edge left, and it is a
property of how the failure looks, not of avoiding it. **Neither gives a hard ceiling under an
unbounded delay or false suspicion; only plain escrow and static quota do, at the cost of
stranded capacity.**

**Limits of this result.** The false-suspicion model re-mints a node's entire rights, which a
careful design would avoid (for example by re-minting only after the suspect acknowledges
revocation, which needs a reachable node and so fails exactly when it matters). Overshoot size
depends on that choice. I did not tune either side.

## 11. Where this leaves the question

- Gate 4 (a real advantage over existing approaches) is **not met**. The remaining case for
  StaleCap is narrow: no pre-assigned rights, no recovery machinery, and small short-lived
  overshoot when its delay bound is violated.
- That case is worth something only to a buyer who can accept a breach of 1 unit under a delay
  fault but cannot accept stranded capacity or a recovery protocol. No such buyer is evidenced.
- The delay bound is the load-bearing assumption. For satellite links it would have to be
  *measured*, with the exceedance rate known; if exceedances are frequent, plain escrow or static
  allocation wins. This is the one quantity that would reopen the question.
- Recommendation: stop LEO work here unless someone supplies a real exceedance rate for a
  specific shared pool. Keep the V6/V7 rule's value for the shrink problem, which is unaffected.

## 12. V3 / V6 / V7 and the recent-contact rule, head to head (run 2026-10-28)

`sim/baseline_compare4.py`, output `baseline_compare4_output.txt`. Same pool and caveats as §9–10.
Version names follow polite-shrink `spec/v7`: **V3** = lowest-ID tie-break, **V6** = `patient`
(only the lowest waits), **V7** = `patient_k` (multiwait: every waiter that still fits among
lower IDs waits). "+ recent-contact" defers a decision while any peer's view is older than L
(the ceiling-side rule from upstream `StaleBandNet`); a peer silent for ≥ lease + Td is
ignored, so a dead node stalls admissions for about 48 ticks. **[sim]; hypothetical.**

**The control works.** V3 breaches the ceiling in every scenario even with no delay spikes
(81–233 breach-ticks, overshoot 1–2). V6 and V7 breach 0 ticks at p=0 in every scenario. So
the sim can see a breach, and the V6/V7 result at p=0 is not an artefact of it being blind.

| Scenario (load, p, crashes) | V6 | V7 | V6 + contact | V7 + contact | Escrow + recovery |
|---|---|---|---|---|---|
| 1.2, 0, none: `util_last` / accept | 0.82 / 0.71 | 0.82 / 0.69 | 0.82 / 0.71 | 0.82 / 0.69 | 0.96 / 0.81 |
| 1.2, 0, perm deaths | 0.63 / 0.83 | **0.71 / 0.88** | 0.56 / 0.88 | 0.54 / 0.88 | 0.72 / 0.93 |
| 1.2, 0.05, none: breach ticks | 24 | 3 | **0** | **0** | 2436 |
| 1.2, 0.05, perm deaths: `util_last` / breach ticks | 0.76 / 12 | 0.65 / 3 | 0.61 / **0** | 0.57 / **0** | 0.56 / 1742 |
| 0.8, 0.05, perm deaths: `util_last` / breach ticks | 0.45 / 6 | 0.48 / 14 | 0.51 / **0** | 0.59 / **0** | 0.46 / 118 |

**Findings.**
1. **V7 beats V6 mainly when capacity churns after deaths** (0.71 vs 0.63 utilisation, 0.88 vs
   0.83 accepted, lower latency). With no deaths and plain overload the two are within noise;
   V7 does not fix the overload cost against escrow (0.82 vs 0.96).
2. **V7's multiwait also breaches less under spikes** (3 vs 24 and 12 vs 3 ticks), but at the
   hardest cell it gave up utilisation (0.65 vs 0.76); one seed set, so treat that as noisy.
3. **Recent-contact removes every breach** in all tested cells with spikes (0 ticks), at a price:
   late-run utilisation falls (V6 0.76 → 0.61 in the hardest cell) and, with crashes but no
   spikes, drops further (0.40 → 0.29 at load 0.8) because everyone waits out a dead node.
4. **In the hardest cell** (load 1.2, spikes, permanent deaths) V7 + contact has utilisation
   0.57 against escrow + recovery's 0.56 and **zero breaches against 1,742 ticks and overshoot 8**.
   This is the first regime where a StaleCap variant is ahead of every baseline on both axes.

**Why this is weaker than it looks.**
- The contact rule is given an idealised sensor: any view older than L is detected as such, and
  a dead peer is identified exactly after lease + Td. If staleness were sometimes undetected, the
  rule would let breaches back in; I did not model that.
- The escrow false-suspicion model is crude and harsh (§10). A more careful escrow recovery
  could narrow the gap.
- One topology, one skew, hypothetical numbers, 6 seeds. The cell above is the single regime
  where the ordering flips.

**Updated decision.** Gate 4 is open again, but only conditionally: V7 + recent-contact beats the
baselines tried so far **if** staleness of a peer's view is reliably observable and permanent node
loss with overload is a realistic regime. Neither condition is evidenced for LEO. The next
fair test is to degrade the sensor: let a fraction of stale views go undetected and see how fast
breaches return. If they return quickly, the advantage was the idealised detector.
