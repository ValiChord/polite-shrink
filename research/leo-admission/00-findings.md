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
