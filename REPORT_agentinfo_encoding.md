# Can the shrink intent ride on `AgentInfo`? — removing the wire message

**Question:** the reference implementation announces a vacate intent with a
dedicated `Msg::ShrinkIntent` on its own `k2sharding` module channel. Reviewing
that fork, Paul d'Aoust (Holochain core) observed that `AgentInfo` is *already*
gossiped and could carry the same signal, and that a new message type is
plumbing the idea does not need. This study tests the substitution — first as a
proof, then as a measurement.

**Answer, in one line:** the message can go, durability is untouched, and the
bill arrives somewhere else — as a transient *reachability* dip and a more
conservative equilibrium arc.

---

## 1. The encoding

Announcing an intent becomes **publishing the reduced arc while continuing to
hold the data**. Executing is the actual drop; standing down is re-publishing
the wider arc. So a node's *declared* arc and its *held* arc diverge for the
duration of the wait, and everything a peer sees comes from the declared one.

The substitution is not free, and the reason is worth stating precisely: with a
dedicated message a peer can distinguish *"announced but still holding"* from
*"already gone"*. With the arc claim alone it cannot — both are simply absent
from the claim. The TCAS lower-id tie-break needs exactly that distinction as
its input, so it has to be given up or replaced.

**The implementation is a deletion.** In `polite_shrink.py` the encoding is
expressed by *not* populating the intent snapshot (`_store_snapshot`): with the
intent list empty, the grow-side subtraction `cov - icov` and the execute-side
tie-break both degrade to reading `cov` alone, and no decision code changes.
That is the claim about the fork made executable — the intent channel is
removable without touching the controller.

## 2. Safety first: the proof

Three TLA+ specs, model-checked exhaustively at N ≤ 8, R from 1 to 7
([`spec/`](spec/), full table in [`spec/README.md`](spec/README.md)):

| Encoding | Result |
|---|---|
| **A — conservative**: drop the tie-break, proceed iff ≥ R *others* still claim the sector | **No error** at every configuration; state counts identical to `PoliteShrink.tla` |
| **B — optimistic**: keep the tie-break by assuming un-declared means still-holding | **Violated** — and not by an unlucky interleaving but by a *sequential drain*: departed nodes never leave the books, so each departure looks individually safe while coverage falls from 6 to 2 at R = 3 |
| **C — age-gated**: recover the missing bit from `AgentInfo.created_at` | `Budget = 0` (perfect classification) **verifies**, and reduces exactly to `PoliteShrink.tla`. `Budget = 1` is **violated** — one misclassification loses a copy |

So encoding A is what gets measured below. C is ruled out as a heuristic: it
would have to classify *perfectly* under churn, which it will not.

## 3. What is measured

Because declared and held arcs diverge under this encoding, the simulation now
records both:

- **declared coverage** — what a reader can route to. All the original columns
  (`floor_min`, `exposure`, `loss`) are measured on this.
- **held coverage** (`held_loss`) — bytes actually on disk. This is the
  durability ground truth, and the property the proof covers.

For V0–V3 the two coincide exactly, and every published V0–V3 number is
unchanged by this work.

## 4. Results — seed 42, four scenarios

V5 = polite shrink under the AgentInfo-only encoding. V3 = the same controller
with the dedicated intent message.

| scenario | variant | floor_min | exposure | loss (declared) | **held_loss** | sync_cost | cancel rate |
|---|---|---|---|---|---|---|---|
| activation | V3 | 5 | 0 | 0 | 0 | 23,011 | 3.3% |
| activation | **V5** | 0 | 7,167 | 44 | **0** | 1,308 | 12.2% |
| storm | V3 | 4 | 7,331 | 0 | 0 | 27,782 | 3.5% |
| storm | **V5** | 2 | 14,735 | 0 | **0** | 6,174 | 9.1% |
| flashcrowd | V3 | 5 | 0 | 0 | 0 | 34,013 | 5.9% |
| flashcrowd | **V5** | 2 | 2,593 | 0 | **0** | 1,387 | 13.2% |
| churn | V3 | 4 | 7,426 | 0 | 0 | 34,429 | 5.1% |
| churn | **V5** | 0 | 35,681 | 44 | **0** | 11,700 | 5.7% |

Seed robustness (`check_seeds.py`, seeds 7 / 99 / 1234 × activation + storm):
**V5 `held = 0` in all six runs**, and declared `loss = 0` in all six — the 44
sector-ticks above are specific to seed 42.

### 4.1 Durability — untouched at these seeds, but see §4.9

`held_loss = 0` in every scenario above and in all six `check_seeds` runs. At
this sample size the measurement agrees with the proof: no sector's bytes went
to zero.

> **That claim does not survive a larger sample.** A 100-seed storm sweep
> (§4.9) finds real loss in 6–9% of V5 runs against 1% for V3 — more frequent,
> though smaller per event. The proof is unaffected (it bounds what the *gate*
> can do, not what a mass death can do), but "durability untouched" was an
> artefact of testing four seeds. Read §4.9 before quoting anything here.

### 4.2 The cost is reachability, not durability

Declared coverage *does* dip — to a floor of 0 in two scenarios, where V3 held
5 and 4. But `loss − held_loss = 44 − 0`: **every declared hole was a phantom.**
At each of those sector-ticks the data was on disk, held by a node that had
announced and not yet executed, and therefore invisible to a reader routing on
declared arcs. The exposure figures (sector-ticks below R) tell the same story
an order of magnitude larger: 7,167 vs 0 in activation, 35,681 vs 7,426 in
churn.

This is the real trade the encoding makes, and it is not visible in the TLA+
model, which has no notion of routing. A dedicated intent message keeps the
declared arc wide until the drop actually happens, so it has no such dip.

### 4.3 It shards, but to a wider equilibrium

The sync-cost column looks like a large win — 1,308 vs 23,011 in activation.
It is not free, and the arc levels say why:

| scenario | V3 equilibrium level | V5 equilibrium level |
|---|---|---|
| activation | 0.90 | 3.02 |
| storm | 0.86 | 2.00 |

V5 settles at a **wider arc** — roughly 4× the span in activation. The
mechanism is direct: an announcer removes itself from the declared view, which
lowers what every *other* node sees, which makes their shrink condition harder
to satisfy. The conservative gate is contagious. Less shrinking means less
re-growth, and less re-growth is where the sync saving comes from. So V5 stores
more per node and moves less; it is not a cheaper way to reach the same place.

### 4.4 Retry cost

The question step 2 was set up to answer. Cancellation replaces the tie-break as
the serialisation mechanism, so it should rise — and it does, by **2–4×**:

| scenario | V3 cancel rate | V5 cancel rate | V5 `AgentInfo` re-publishes |
|---|---|---|---|
| activation | 3.3% | 12.2% | 1,677 |
| storm | 3.5% | 9.1% | 1,990 |
| flashcrowd | 5.9% | 13.2% | 1,807 |
| churn | 5.1% | 5.7% | 2,298 |

In absolute terms it stays modest: at worst about one announcement in eight
stands down, against one in thirty for the tie-break. The re-publish traffic is
~1,700–2,300 extra `AgentInfo` publications per run (one per announce, one per
stand-down) — carried on gossip that already exists rather than on a new
channel.

## 4.5 Stage-2 — real iroh transport, and what it can and cannot see

The encoding is implemented on the kitsune2 fork behind a config flag
(`agentinfo_encoding`, default false), so one binary runs both and the Wind
Tunnel harness compares them directly. Same sizing as the published V3 runs:
R = 5, 12 agents, clamp 8; the storm adds a 6-agent cohort (33% of the
18-agent peak) that dies simultaneously.

| run | encoding | final arc span | coverage floor | orphaned sectors | ops lost |
|---|---|---|---|---|---|
| settle | **on** | 0.583 | 6 | 0 | 0 of 21,657 |
| storm 1 | **on** | 0.542 | 6 | 0 | 0 of 23,526 |
| storm 2 | **on** | 0.667 | 6 | 0 | 0 |
| storm 1 | off (control) | 0.625 | 6 | 0 | 0 |
| storm 2 | off (control) | 0.542 | 4 | 0 | 0 |

All verdicts PASS on both encodings — continuous coverage, final redundancy,
and op reachability. The controls were run on the same machine in the same
session rather than compared against the earlier published figures.

**The two encodings are indistinguishable at this scale.** Final arc spans
overlap ({0.542, 0.667} on, {0.625, 0.542} off), and the only floor to dip
below R came from the *control*, not the encoding. Two runs per arm is not
enough to rank them, and nothing here should be read as doing so.

**This is not the availability result, and must not be quoted as one.** The
harness runs 12–18 agents; §4.2's phantom holes are a large-N effect. Running
the *simulation* at the harness's own sizing settles whether the two methods
agree:

| | declared loss | held loss |
|---|---|---|
| sim, N = 12, settle & storm, V5 | **0** | 0 |
| sim, N = 5,000 density ring, activation, V5 | 14,718 | 0 |
| sim, N = 5,000 density ring, storm, V5 | 38,394 | 0 |

The sim predicts *zero* effect at N = 12 — which is exactly what real transport
measured. So the Wind Tunnel PASS is not evidence that the encoding is safe to
adopt; it is evidence that **the simulation is right, including about why the
effect is invisible at this size.** The two methods corroborate each other
where they overlap, and the divergence at scale is the sim's alone to report
until a harness can run thousands of agents.

One implementation note, because it nearly became a false finding. The fork's
8-node storm test first failed under the encoding with *"did not recover to
target redundancy; min coverage 1"*. That was a bug in this work, not a
property of the encoding: the storm brake cancels pending intents on peer
loss, and cancelling a narrowed arc claim without widening it back leaves the
agent declaring less than `target_level`, after which the arc-match guard in
`tick_agent` blocks every later decision — including the growth the brake
exists to permit. With the brake restoring the claim, the test passes in 13.8 s
against 14.5 s for the control.

## 4.6 Two more Stage-3 axes: the shrink race, and liars

**The §6.1 shrink race all but disappears.** Re-running the full
race-quantification grid (R ∈ {3,5}, lag_max ∈ {24,48,96}, seven hazard rates,
40 seeds per point — 1,680 runs) under the encoding:

| | V3 | V5 |
|---|---|---|
| shrink-caused holes | 1,732 | **5** |
| churn-caused holes | 2,281,073 | 2,283,704 |
| shrink holes as a share of real holes | 0.0759% | **0.0002%** |

A 346× reduction, with churn holes unchanged to within 0.1%. This is the
conservative gate doing exactly what it should: it is strictly stricter than
the tie-break, so it almost never fires a shrink that opens a hole. Only two
cells in the whole grid produced any shrink hole at all (R=3/lag=24/p=0.016,
and R=5/lag=96/p=0.032). Phantom episodes are counted as their own class and
excluded from both figures: 25,836 episodes, 174,306 sector-ticks, 0.2% of all
zero-declared sector-ticks.

*Read this study's hazard rates carefully.* It deliberately escalates churn far
past anything realistic until holes occur, so both variants show real data loss
here — that is the point of the study, and it does not contradict the
`held_loss = 0` results at the designed rates in §4.

**The liar threshold does not move.** The Stage-3 false-coverage attack (agents
declaring a full arc while storing nothing) collapses both encodings at exactly
K = R:

| K | K/R | V3 true floor / zero sectors | V5 true floor / zero sectors |
|---|---|---|---|
| 4 | 0.8 | 1 / 0 | 1 / 0 |
| 5 | 1.0 | 0 / 139 | 0 / 44 |
| 6 | 1.2 | 0 / 354 | 0 / 354 |
| 10 | 2.0 | 0 / 357 | 0 / 357 |

Identical above the threshold, and marginally better for V5 at the knee. That
is the expected result rather than a reassuring one: a liar signs a false arc
claim about itself under either encoding, so the encoding was never the
defence. The *forged-intent* attack is a different matter — it becomes
inapplicable rather than merely unmeasured, because there is no intent message
to forge and `AgentInfoSigned` is signed.

Note the durability measure used in the liar study is `true_*` (honest agents'
real storage), not the declared/held split used elsewhere: `_build_held`
credits every alive agent, and a liar is alive with a full-arc level while
storing nothing.

## 4.7 Lossy gossip — the encoding closes §12's own caveat

§12 measured polite shrink with each viewer's coverage picture incomplete *and*
inconsistent, and found data loss flat out to 90% message drop. It carried one
scope limit, stated in `message_loss_sim.py`: *"Intents (icov/ilist) stay on the
base lag — lossy intent gossip is future work."*

Under this encoding that gap closes itself, because the announcement **is** the
arc declaration: the channel §12 drops is now the channel the handshake depends
on. So this run answers a question §12 could not — does the gate hold when the
*intent* messages are the ones going missing?

5 seeds × 5 drop rates × 2 scenarios (`agentinfo_message_loss.py`):

| drop rate | V3 held loss | V5 held loss | V5 declared loss (activation) |
|---|---|---|---|
| 0% | 0 | **0** | 224 |
| 25% | 0 | **0** | 44 |
| 50% | 0 | **0** | 304 |
| 75% | 0 | **0** | 132 |
| 90% | 0 | **0** | 218 |

**Zero data loss for both encodings at every drop rate**, and V5's held floor
stays at exactly R = 5 through activation even at 90% drop. The declared-loss
column is flat and non-monotonic in the loss axis — the same signature §12
reported — so what little there is comes from announcements, not from the
dropping.

This is the one axis where the encoding is arguably *better* placed than the
dedicated message: a `ShrinkIntent` on its own channel has never been tested
against message loss at all, and here the equivalent signal is lost by
construction and the invariant still holds.

## 4.8 The repair rule (V4) — and a hypothesis of mine that was wrong

V4 is the variant this work would actually recommend, so the encoding has to be
checked against it. §6.2's deadlock cases, run with `clamp_min_peers = 0` so the
small-network safety net is removed and the repair rule is the only thing that
can recover the network — 12 seeds per case (`agentinfo_repair.py`):

| case | encoding | recovered | stuck | median recovery | repair grows |
|---|---|---|---|---|---|
| random-5 | V3 | 12/12 | 0 | 224 | 51 |
| random-5 | **V5** | **12/12** | 0 | 186 | **12** |
| random-15 | V3 | 12/12 | 0 | 127 | 51 |
| random-15 | **V5** | **12/12** | 0 | 119 | **12** |
| clustered-15 | V3 | 12/12 | 0 | 127 | 52 |
| clustered-15 | **V5** | **12/12** | 0 | 127 | **13** |
| sparse-8@R2 | V3 | 12/12 | 0 | 38 | 0 |
| sparse-8@R2 | **V5** | **12/12** | 0 | 54 | 1 |

Full recovery under both, no deadlock anywhere. **The hypothesis this study was
built to test was wrong**: I expected phantom holes to provoke *spurious*
repair growth, since a declared-zero sector is a hole as far as the repair rule
can tell. The opposite happened — V5 triggers about a quarter as many repair
grows, because it shrinks less in the first place and the network therefore
needs less repairing. Consistent with the wider equilibrium in §4.3.

(The held-loss figures in these runs are large for both encodings and are not a
differentiator: the scenario kills all but 5–15 of 200 agents at once, so real
loss during recovery is inherent to the setup rather than to any controller.)

## 4.9 The correction: more seeds change the durability answer

Every "held_loss = 0" result above rests on four seeds or fewer. Running the
storm scenario at 100 seeds per arm, on the plain simulator, at two severities:

| storm kill | encoding | runs with real loss | total held-loss sector-ticks |
|---|---|---|---|
| 30% | V3 | **1 / 100** | 4,447 |
| 30% | **V5** | **6 / 100** | **2,028** |
| 40% | V3 | **1 / 100** | 8,316 |
| 40% | **V5** | **9 / 100** | **3,723** |

**Both columns have to be quoted together, because they point opposite ways.**
V5 loses real data 6–9× more often, and loses less than half as much of it in
total. V3's losses are rare and large; V5's are more frequent and small. Which
is worse depends on whether the operator's exposure is `P(any loss)` or
`E[loss]` — and for a DHT built around a hard redundancy invariant it is
usually the former, so this counts against the encoding.

The mechanism is not the gate. Loss opens *at* the mass-death tick, not after
it (`held_race` is 0% at every death-detection latency ≤ 48 in the decoupled
sweep), and both encodings enter the storm with an identical pre-storm held
floor of exactly R. The two simply settle into different arc configurations,
and V5's is unluckier more often while failing smaller.

This was found only because the sample grew from 4 seeds to 100. It is the
single most important correction in this report: **§4.1's "durability
untouched" was an artefact of sample size**, and every durability claim here
should be read as "at the seeds tested", with the seed count stated.

### The decoupled death-clock (§11)

The same sweep across death-detection latencies (24 seeds, gossip lag_max 24):

| death lag | V3 held loss | V5 held loss | V5 `held_race` |
|---|---|---|---|
| coupled | 0 | 904 | 0% |
| 8 | 0 | 680 | 0% |
| 16 | 0 | 1,040 | 0% |
| 24 | 0 | 1,280 | 0% |
| 48 | 949 | 2,144 | 0% |
| 96 | 3,895 | 4,320 | 4.2% |
| 192 | 17,128 | 9,328 | 8.3% |

§11's V3 finding holds — loss grows with detection latency and is zero when
detection outruns gossip. V5 carries the §4.9 offset at every latency, and
crosses below V3 at the extreme (192 = 8× the gossip lag), consistent with the
"more often, smaller" shape. `held_race` stays at 0% up to 48, confirming these
are not post-storm gate races.

A methodological note worth keeping: these runs go through `MixedSim`, whose
`__init__` is a deliberate re-implementation. Running the identical seeds
through the plain `Sim` gives **byte-identical** totals (904 held / 1,305
declared / 3-of-24), which is the reduction check that lets the per-agent port
be trusted.

## 4.10 The last three studies: fairness, and the two Byzantine defences

**Fairness — the encoding solves what the rotation fix could not.** V3's
lowest-id tie-break lets low-id agents shrink first, so high-id agents hold
bigger arcs; `fairness_sim.py` answers that with a per-epoch rotating priority
key (V3F), which then has to re-earn the safety proof at epoch boundaries.
Under this encoding the question dissolves instead: there is no tie-break to be
unfair. 24 seeds, activation, same metrics as the fairness study:

| variant | corr(aid, level) | level std | top-decile storage share |
|---|---|---|---|
| V3 | +0.098 | 2.009 | 92.4% |
| V3F (rotating key) | −0.021 | 2.014 | 92.7% |
| **V5** | +0.022 | 1.974 | **43.4%** |

Two things worth separating. The *correlation* is fixed by either approach.
The *concentration* is not: V3F leaves the top decile holding 92.7%, barely
distinguishable from V3's 92.4% — consistent with Stage-3's finding that the
skew is hysteresis path-dependence rather than the tie-break. V5 halves it,
with no rotation machinery and no new proof obligation.

*Read alongside the Stage-3 constraint "don't flatten the arc distribution":*
those big arcs were identified as the emergent insurance behind sparse
recovery's global reach, so halving the concentration is not automatically
good news. The direct check is §4.8, where V5 still recovers 12/12 with fewer
repair grows — in those cases the insurance was not needed. That is evidence,
not a guarantee, and a deployment relying on the skew for reach should measure
it.

**Both Byzantine defences survive the encoding.** These operate on the coverage
*sensor* rather than the announcement, so confirmation was expected; the reason
to run them is that the encoding's gate reads current claimants while verified
coverage filters to proven peers, and two filters composing could in principle
misbehave. They do not. 4 seeds each, `true_*` ground truth (honest agents'
real storage — held coverage would credit a liar that stores nothing):

| study | condition | V3 true zero | V5 true zero |
|---|---|---|---|
| verified coverage | K = 0 … 3R full-arc liars | 0.0 | **0.0** |
| partial liars | p = 0 … 1.0, c = 2, K = 2R | 0.0 | **0.0** |

§7's headline holds under the encoding — verified coverage removes the K = R
threshold, with zero true loss out to K = 3R. §8's holds too, including its
known mid-fraction margin dip: the true floor sags to ≈3.6–3.8 at p = 0.5–0.75
for *both* encodings, against R = 5.

V5 carries a small consistent margin offset throughout — true floor about
0.2–0.4 copies lower than V3 at the same K or p. Not a threshold change, but
the same direction as §4.9's finding, and worth naming rather than rounding
away.

## 5. Verdict

**The new wire message is not needed. One bit is.**

Two defensible options, and the choice is not ours to make:

- **Take encoding A.** Delete `protocol.rs`, `intents.rs` and the `k2sharding`
  channel — about 255 lines and a wire format. Buys: the §6.1 shrink race
  effectively gone (§4.6), zero loss under 90% gossip drop *including* lost
  announcements (§4.7), V4 repair intact (§4.8), storage fairness solved
  without the rotation machinery that could not solve it (§4.10), and forged
  intents removed as a threat model outright, since `AgentInfoSigned` is
  signed. Costs: a transient reachability dip that worsens with N (§4.2,
  §4.4), and a 6–9× higher frequency of real loss under mass death (§4.9).
- **Carry the bit explicitly** — one field on `AgentInfo`, a struct already
  gossiped and already signed. Keeps the tie-break, the tighter equilibrium,
  the wide declared arc through the wait, and V3's storm loss frequency; costs
  a field on a shared type.

**On the evidence here, the second option.** Two independent findings point the
same way and neither is about elegance: the reachability cost grows with
network size, which is the one axis sharding exists to serve; and the frequency
of real loss under mass death is several times higher, which is the number a
DHT operator with a hard redundancy target actually budgets against. Encoding A
is genuinely better on the race and on lossy gossip, and if `P(any loss)` were
not the binding constraint that trade might go the other way — but it usually
is.

What would change this recommendation: a real-transport measurement at large N
showing the reachability dip does not materialise, or an operator for whom
`E[loss]` rather than `P(any loss)` is the exposure that matters.

## 6. Limitations

- The reachability dip is inferred from declared arcs in the simulation, not
  measured against a real read path. Whether kitsune2 would actually fail such
  a read — or fall back — is not modelled here.
- The equilibrium comparison is V3 vs V5 at identical policy constants. The
  wider V5 equilibrium may partly be a tuning artefact: the hysteresis
  constants were fitted with the dedicated-message encoding in play, and were
  not re-tuned for this one.
- **Scale is the binding limitation on the real-transport evidence.** Wind
  Tunnel ran 12–18 agents; the availability effect appears in simulation
  between N = 200 (44 sector-ticks) and N = 5,000 (38,394). No measurement on
  real transport at the scale where the effect exists, and the harness cannot
  currently reach it.
- Two Wind Tunnel runs per arm. Enough to say "no difference detected", not
  enough to rank the encodings.
- **Stage-3 is now complete for this encoding**: partitions, scale, the race
  grid, liars, lossy gossip, V4 repair, the decoupled death-clock, fairness,
  verified coverage and partial liars have all been re-run. The forged-intent
  study is inapplicable rather than pending — `AgentInfoSigned` is signed, so
  there is no intent to forge.
- Seed counts vary by study (4–100) and are stated per table. §4.9 is the
  cautionary case: the durability answer changed between 4 seeds and 100, so
  treat any single-digit-seed result here as provisional.
- The lossy-gossip run drops coverage/arc declarations, which under this
  encoding *are* the announcements. It does not separately model an announcer
  whose narrowed claim is delivered to some peers and not others *within* a
  single decision — the per-viewer `known` matrix does produce exactly that,
  but it has not been isolated as its own study.
- The equilibrium-arc comparison in §4.3 is a simulation result at N = 200 and
  is **not** reproduced on real transport at N = 12, where the spans overlap.
- `AgentInfo` has an `expires_at`; the interaction between announcement
  lifetime and info expiry is unmodelled.

## Reproduce

```bash
python3 run_experiments.py   # table above -> results/summary.md
python3 check_seeds.py       # seed robustness, held= column for V5
java -cp tla2tools.jar tlc2.TLC spec/AgentInfoConservative.tla  # -> No error
java -cp tla2tools.jar tlc2.TLC spec/AgentInfoOptimistic.tla    # -> violated
```
