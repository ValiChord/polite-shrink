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
```

Edit the `CONSTANTS` block in the `.cfg` files to check other `Nodes` / `R`.

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
