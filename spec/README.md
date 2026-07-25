# Formal safety proof (TLA+ / TLC)

The simulation sweep found **0 data losses in 1,248 runs**. That is strong
*evidence*, but it is still sampling. This directory upgrades the core safety
property to a **proof**: exhaustive model checking over *every* reachable state
of a small system, with [TLA+](https://lamport.azurewebsites.net/tla/tla.html)
and its model checker TLC.

## The property

> **A DHT sector never holds fewer than R real copies** — no shrink drives it
> below the redundancy target.

The property is *per-sector*: for any one sector, the nodes covering it decide
independently whether to drop it, and the arc geometry only sets *which* nodes
contest *which* sector. So a single-contested-sector model is the right unit,
and proving it for that sector proves it for the ring.

## The two specs

- **`PoliteShrink.tla`** — the real rule. Nodes announce a vacate intent
  (unconstrained: the worst case is that everyone announces), and *execute* it
  only after reading the current holder/intent sets — which is what the
  "wait 2× max gossip lag" delay buys — using the TCAS-style tie-break (treat
  every lower-id intender as already gone; proceed only if ≥ R remain).
  **Result: `SafeCoverage` holds on every reachable state.**

- **`NaiveShrink.tla`** — the naive behaviour: no wait, no tie-break, each
  node drops on a stale coverage view. **Result: TLC returns a counterexample**
  — holders drop one by one below R (the "hallway dance"). This proves the
  model has teeth: same setup, minus the two phases, and safety fails. So the
  safety is bought by the mechanism, not by the way the model is written.

## Three more specs: can the intent ride on `AgentInfo`?

The rule above assumes a dedicated announcement — `Msg::ShrinkIntent` on the
kitsune2 fork. Reviewing the fork, Paul d'Aoust (Holochain core) pointed out
that `AgentInfo` is **already gossiped** and could carry the same signal, and
that a new message type is plumbing the idea does not need. These three specs
test that, because the substitution is not free: with a dedicated message a
peer can tell *"announced but still holding"* from *"already gone"*; with the
arc claim alone it cannot, since both are simply absent from the claim set.
The TCAS lower-id tie-break needs exactly that distinction as its input.

All three model announcing as **publishing the reduced arc while still holding
the data** — `declared ⊆ holds`, and an intender is a node in `holds \ declared`.

- **`AgentInfoConservative.tla`** (encoding A) — give the tie-break up and read
  only what is observable: proceed iff ≥ R *other* nodes are still claiming the
  sector. **No error.** Safe for a structural reason rather than a subtle one:
  `declared ⊆ holds` and the executing node has already un-declared, so the R
  survivors it counts are real. The "discount your own stale declaration" step
  of the original gate drops out for free.
- **`AgentInfoOptimistic.tla`** (encoding B, the negative control) — keep the
  tie-break by assuming every un-declared node is an intender that is still
  holding. This is the faithful optimistic port, not a strawman: it is what you
  get by taking "reuse `AgentInfo`" literally and leaving the gate as written.
  **Violated.** The counterexample is not an unlucky interleaving but a
  *sequential drain* — departed nodes stay on the books forever, so each
  departure looks individually safe while coverage falls from 6 to 2 at R = 3.
- **`AgentInfoAgeGated.tla`** (encoding C) — try to recover the missing bit from
  `AgentInfo.created_at`: a claim that shrank recently reads as an unexecuted
  intent, an older one as a departure. Modelled as an oracle correct except for
  at most `Budget` departed nodes misread as intenders. **`Budget = 0`: no
  error** — and it reduces exactly to `PoliteShrink.tla`. **`Budget = 1`:
  violated.** Only the dangerous direction of error is modelled; misreading a
  live intender as departed makes the gate stricter, which is safe.

| Nodes | R | A conservative | C age-gated, `Budget=0` | B optimistic | C age-gated, `Budget=1` |
|---|---|---|---|---|---|
| 6 | 3 | no error (656) | no error (656) | violated (566) | violated (566) |
| 7 | 2 | no error (2,172) | no error (2,172) | violated (2,153) | violated (2,153) |
| 8 | 4 | no error (5,984) | no error (5,984) | violated (4,861) | violated (4,861) |
| 8 | 1 | no error (6,560) | no error (6,560) | violated (6,561) | violated (6,561) |
| 8 | 7 | no error (1,280) | no error (1,280) | violated (214) | violated (214) |

Every "no error" state count is identical to `PoliteShrink`'s below, consistent
with the encoding being a re-coordinatisation of the same state space
(`intend ≡ holds \ declared`) whose stricter gate removes no reachable state.

**What this settles.** The announcement needs no new wire message — but it does
need one bit distinguishing *intending* from *departed*, and that bit cannot be
inferred from the arc claim. Either drop the tie-break (A, safe, and a probe
invariant confirms it still drains a sector to exactly R — so the cost is
cancel-and-retry under concurrency, not failure to reach the target), or carry
the bit explicitly. What is ruled out is deriving it from claim age: `Budget = 1`
falsifies safety, so the heuristic would have to be *perfect* under churn.

**What this does not settle.** These are untimed, unfair models: they establish
reachability, not guaranteed progress. How many cancel/retry cycles encoding A
costs when several nodes contend — and the two extra `AgentInfo` publishes per
announce-then-abort — is a question for the simulation, not for TLC.

## What was checked

`PoliteShrink` `SafeCoverage` verified with **no error** — exhaustively, all
reachable states — for every configuration tried:

| Nodes | R | distinct states |
|---|---|---|
| 6 | 3 | 656 |
| 7 | 2 | 2,172 |
| 8 | 4 | 5,984 |
| 8 | 1 | 6,560 |
| 8 | 7 | 1,280 |

`NaiveShrink` is violated at each of these (counterexample found).

## Reproduce

Needs a JRE and `tla2tools.jar` (the TLA+ tools; ~4 MB,
<https://github.com/tlaplus/tlaplus/releases>). From this directory:

```bash
java -cp tla2tools.jar tlc2.TLC PoliteShrink.tla   # -> No error has been found
java -cp tla2tools.jar tlc2.TLC NaiveShrink.tla    # -> Invariant SafeCoverage is violated

# the AgentInfo-only encoding
java -cp tla2tools.jar tlc2.TLC AgentInfoConservative.tla  # -> No error has been found
java -cp tla2tools.jar tlc2.TLC AgentInfoOptimistic.tla    # -> Invariant SafeCoverage is violated
java -cp tla2tools.jar tlc2.TLC AgentInfoAgeGated.tla      # -> depends on Budget in the .cfg
```

Edit the `CONSTANTS` block in the `.cfg` files to check other `Nodes` / `R`
(and `Budget`, for `AgentInfoAgeGated`).

## Scope and honesty

This proves the *control-loop* safety property — concurrent stale-view shrinks
never drive a sector below R — under the model's abstraction: one sector,
execute-time intent visibility (the wait), honest holders, atomic actions. It
is a complement to, not a replacement for, the simulations: it does not model
gossip timing in detail, Byzantine liars (see the sim studies for those), or
the arc geometry. What it removes is any doubt that the *rule itself* can be
made to lose a copy through unlucky interleaving — it cannot.

It is also narrower than "polite shrink is proven", and deliberately so. What
is modelled here is the **gate**: the pre-drop re-check — discount your own
stale declaration, count every lower-id intender as already gone, proceed only
if R remain. The controller's *policy* — redundancy target, hysteresis
constants, growth rule, small-network clamp, intent delay — is not modelled and
is not proven; it is engineering judgement, evidenced by simulation rather than
by TLC. The property therefore reads: *no agent obeying this gate can take a
sector below R, whatever policy drove it to want to.* A different policy can
replace every constant in the controller without invalidating anything in this
directory.
