# Formal safety proof (TLA+ / TLC)

> **October 2026 — read [../REPORT_stale_views.md](../REPORT_stale_views.md) first.**
> The specs here let `Execute` read the *current* holder set atomically. Under
> that assumption a bare re-check is already safe, so the tie-break is never
> exercised — `stale_check.py --fresh --no-tb` reproduces TLC's state counts
> exactly and still finds no error. The stale-view check (`timed_check.py`)
> tests the mechanism that matters: acting on a view up to `lag` ticks old. It
> shows the ID tie-break is necessary but not sufficient, and that discounting
> every announcer (V5 / `AgentInfoConservative`) is safe for any N.
> `hybrid_check.py` adds progress: V5 can stall forever, and the recommended
> V6 ("patient lowest") is safe *and* always makes progress.
>
> **[`StaleShrink.tla`](StaleShrink.tla)** is the stale-view model in TLA+,
> checked by TLC itself: it finds V3's staggered cascade on its own and checks
> V6 safe and live (see [Stale views in TLA+](#stale-views-in-tla)).

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

## Stale views in TLA+

`StaleShrink.tla` is `timed_check.py` written in TLA+, so that the stale-view
result rests on TLC as well as on the Python checker and its Rust port. Each
node acts alone, in its own steps (`Announce(n)`, `Recheck(n)`), reading only
its own variables and a snapshot of the system published 1 to L ticks earlier,
the age chosen afresh at every re-check. Time is an explicit clock advanced by
`AdvanceTime` once every due re-check has happened (Abadi–Lamport style);
nodes never read it. It stands for two assumptions: information is at most L
ticks old (a known bound, so a synchronous timing assumption), and a node's
timer fires after D ticks. Any holder may announce at any tick and re-checks
`D` ticks later. `Rule` selects V3 (`"tb"`) or V6 (`"patient"`). The spec was
restructured this way in response to Stephan Merz's review of
[tlaplus/Examples#243](https://github.com/tlaplus/Examples/pull/243); the
first version used one global `Tick` and a lag fixed per node. There are no deaths in this spec, so
`Safety` is "never fewer than R holders". `Progress` says that if anyone
announced and a copy could be spared, someone left.

| model (`.cfg`) | rule | N | R | lag | wait | TLC result | distinct states |
|---|---|---|---|---|---|---|---|
| `StaleShrink` | V6 | 4 | 1 | 2 | 2 (1x) | **no error** (Safety and Progress) | 16,848 |
| `StaleShrinkV6Wait2x` | V6 | 4 | 1 | 2 | 4 (2x) | **no error** | 43,348 |
| `StaleShrinkV3Cascade` | V3 | 4 | 1 | 2 | 4 (2x) | **Safety violated**: nodes 4, 3, 2, 1 announce a tick apart, all 2 ticks stale; the last copy goes at tick 7 | (stops at the counterexample) |
| `StaleShrinkV6TooShort` | V6 | 4 | 1 | 2 | 1 (0.5x) | **Safety violated**, as it must be: no rule is safe when the wait is shorter than the staleness | (stops) |

Further runs with the same spec (TLC 2.19, October 2026), each 1-10 s: V3 at
N=3, R=1, lag 2, wait 2 violated; V3 at N=5, R=2, lag 1, wait 1 no error; V6 no
error at N=3 R=1 (lag 2, wait 2), N=4 R=2 (lag 2, wait 2), N=5 R=2 and N=5 R=3
(lag 1, wait 1). Every verdict matches `timed_check.py`. The restructured spec
gives the same verdicts on all of these; its state counts are lower (16,848 and
43,348, from 65,001 and 245,146) because view ages are no longer part of the
state.

**Limits.** No deaths (the Python checker and its Rust port cover a death at any
tick); one sector; N <= 5. As with `PoliteShrink.tla`, this checks the gate, not
the surrounding policy.

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

# stale views (one spec, several models)
java -cp tla2tools.jar tlc2.TLC -deadlock StaleShrink.tla                                        # V6: no error
java -cp tla2tools.jar tlc2.TLC -deadlock -config StaleShrinkV6Wait2x.cfg StaleShrink.tla        # V6: no error
java -cp tla2tools.jar tlc2.TLC -deadlock -config StaleShrinkV3Cascade.cfg StaleShrink.tla       # V3: Safety violated (the cascade)
java -cp tla2tools.jar tlc2.TLC -deadlock -config StaleShrinkV6TooShort.cfg StaleShrink.tla      # control: Safety violated
```

Edit the `CONSTANTS` block in the `.cfg` files to check other `Nodes` / `R`
(and `Budget`, for `AgentInfoAgeGated`).

## Scope and honesty

`PoliteShrink.tla` and the AgentInfo specs check the safety property under
their abstraction: one sector, execute-time intent visibility, honest holders,
atomic actions. Because execute reads the *current* holder set, they do not
model the staleness the rule exists to survive, so they cannot show that the
rule survives it (see the October note at the top). `StaleShrink.tla` does model
it, for small networks and without deaths: there V3 fails and V6 holds. All of
these complement, not replace, the simulations: they do not model gossip timing
in detail, Byzantine liars (see the sim studies for those), or the arc
geometry.

It is also narrower than "polite shrink is proven", and deliberately so. What
is modelled here is the **gate**: the pre-drop re-check — discount your own
stale declaration, count announced intenders as already gone (lower-id ones
under V3, all of them under V6), proceed only if R remain. The controller's *policy* — redundancy target, hysteresis
constants, growth rule, small-network clamp, intent delay — is not modelled and
is not proven; it is engineering judgement, evidenced by simulation rather than
by TLC. The property therefore reads: *no agent obeying this gate can take a
sector below R, whatever policy drove it to want to.* A different policy can
replace every constant in the controller without invalidating anything in this
directory.
