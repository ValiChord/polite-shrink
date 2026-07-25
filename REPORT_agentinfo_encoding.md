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

### 4.1 Durability is untouched

`held_loss = 0` in every scenario and every seed. The measurement agrees with
the proof: no sector's bytes ever went to zero.

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

## 5. Verdict

**The new wire message is not needed. One bit is.**

Two defensible options, and the choice is not ours to make:

- **Take encoding A.** Delete `protocol.rs`, `intents.rs` and the `k2sharding`
  channel — about 255 lines and a wire format — and accept a transient
  reachability dip plus a wider equilibrium arc. Durability is proven and
  measured intact. Forged intents stop being a threat model at all, because
  `AgentInfoSigned` is signed: the §6 forgery study and its receiver-side
  range-validation both become moot rather than needing to ship.
- **Carry the bit explicitly** — one field on `AgentInfo`, a struct already
  gossiped and already signed. Keeps the tie-break, the tighter equilibrium and
  the wide declared arc through the wait; costs a field on a shared type.

Which is right depends on something this study cannot settle: whether a
transient hole in *declared* coverage is acceptable in Holochain, where the arc
claim drives what peers ask you for. If a reader failing to find data that
demonstrably exists is a problem, take the second option.

## 6. Limitations

- The reachability dip is inferred from declared arcs in the simulation, not
  measured against a real read path. Whether kitsune2 would actually fail such
  a read — or fall back — is not modelled here.
- The equilibrium comparison is V3 vs V5 at identical policy constants. The
  wider V5 equilibrium may partly be a tuning artefact: the hysteresis
  constants were fitted with the dedicated-message encoding in play, and were
  not re-tuned for this one.
- Stage-2 (Wind Tunnel, real iroh transport) and Stage-3 (adversaries, scale,
  repair) have not been re-run under this encoding.
- `AgentInfo` has an `expires_at`; the interaction between announcement
  lifetime and info expiry is unmodelled.

## Reproduce

```bash
python3 run_experiments.py   # table above -> results/summary.md
python3 check_seeds.py       # seed robustness, held= column for V5
java -cp tla2tools.jar tlc2.TLC spec/AgentInfoConservative.tla  # -> No error
java -cp tla2tools.jar tlc2.TLC spec/AgentInfoOptimistic.tla    # -> violated
```
