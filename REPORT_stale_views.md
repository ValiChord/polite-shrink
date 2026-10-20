# What the proof actually covers — and the stale-view check it was missing

*October 2026. Written after an external-style audit of this repo found that the
published TLA+ proof does not exercise the tie-break. Everything below is
reproducible from `spec/stale_check.py` and `spec/timed_check.py` (pure stdlib).*

## The short version

1. **The published proof is real but narrow.** `spec/PoliteShrink.tla` lets
   every node act on the *current* holder set, read instantly. Under that
   assumption a plain re-check is already safe, so the tie-break is never used:
   **delete it and the spec still passes**, with identical state counts. The
   proof shows "re-checking against fresh state is safe". It does not show that
   the tie-break is what buys safety — which the README, CORE_IDEA, TEST_LEDGER
   and REPORT_stage3 all said it did.
2. **The mechanism that matters — acting safely on a *stale* view — had never
   been checked formally.** This report checks it, exhaustively, with the
   simulator's own timing rules.
3. **The ID tie-break (V3) is genuinely needed, but it is not enough.** Without
   it, every configuration fails at every wait. With it, small networks are
   safe once the wait exceeds twice the lag — the repo's design rule, now derived
   rather than assumed. But two failure patterns break it: a **staggered cascade**
   of announcers (R=1, any fixed wait, given enough nodes), and **one death plus
   staggered announcements** (R=2, just 4 nodes, even with instant detection).
4. **The AgentInfo-style rule (V5) — discount *every* visible announcer, not just
   lower IDs — is safe for any number of nodes with a wait of just 1× lag**, and
   it has a short proof. Its only failure mode is a death that has not been
   noticed by the time someone acts on a view that still counts the dead node.
5. That reverses the recommendation in
   [REPORT_agentinfo_encoding.md](REPORT_agentinfo_encoding.md) §5, which
   preferred keeping the tie-break. On safety, V5 is now the stronger rule. Its
   documented costs (transient reachability dips, a wider equilibrium, more
   frequent but smaller storm losses) are unchanged and still have to be weighed.

## 1. Why the published proof cannot see the tie-break

`Execute(n)` in `PoliteShrink.tla` reads `holds` — the true current holder set —
atomically. If `|holds \ {n} \ LowerIntenders(n)| ≥ R` then, after n leaves,
`|holds| ≥ R`. But the same is true with the `LowerIntenders` term deleted:
`|holds \ {n}| ≥ R` before the drop already implies `|holds| ≥ R` after it.
Interleaving semantics means two nodes never "decide at the same instant" on the
same picture; each decides on the truth as left by the last one.

`spec/stale_check.py --fresh` reproduces TLC's published state counts exactly —
656, 2,172, 5,984, 6,560 and 1,280 for the five configurations in
[spec/README.md](spec/README.md) — and with `--no-tb` (tie-break deleted) it
gives **the same 656, still no error**. `AgentInfoConservative.tla`, which has no
tie-break at all, also passes for the same reason.

So `NaiveShrink.tla` failing does not isolate the tie-break either: it removes
the wait *and* the re-check *and* the tie-break together.

## 2. The timed model

`spec/timed_check.py` drops all hand-made abstraction and uses the simulator's
semantics directly:

- A node announcing at tick *a* acts at tick *a + D* (the wait).
- When it acts it sees the world as it was at tick *(a + D) − lag*, with
  `lag ∈ 1..L` chosen **per node** — heterogeneous staleness. It sees the
  announcements active then; departures inside its last `lag` ticks are
  invisible.
- Same-tick actions are processed in id order and cannot see each other.
- Announcements are unconstrained, as in the TLA+ spec: a node may announce
  whenever it still holds. The safety argument must not lean on the trigger.

It then enumerates **every** combination of announce time (including "never")
and per-node lag. Safety is `|holders| ≥ R` at every tick. Three rules:

| rule | discounts when it re-checks | corresponds to |
|---|---|---|
| `none` | only itself | a bare re-check — the sensor-network "withdraw timer" pattern |
| `tb` | itself + visible announcers with a **lower** id | V3, the published rule |
| `all` | itself + **every** visible announcer | V5, the AgentInfo encoding |

## 3. Results — no deaths

**Without the tie-break (`none`), every configuration fails at every wait** —
N = 3–5, R = 1–3, L = 1–2, D from 1× to 4× the lag. A re-check alone never closes
the race. *(full table: `spec/timed_sweep.txt`)*

**With the tie-break (`tb`), safety needs a long enough wait — and for R = 1 no
fixed wait is enough:**

| N | R | L | smallest safe wait D | D / L |
|---|---|---|---|---|
| 3 | 1 | 2 | 4 | 2.0 |
| 4 | 1 | 2 | 5 | 2.5 |
| 4 | 2 | 2 | 4 | 2.0 |
| 4 | 3 | 2 | 3 | 1.5 |
| 5 | 1 | 2 | **> 5** — still fails at 2L+1 | — |
| 5 | 2 | 2 | 5 | 2.5 |
| 4 | 1 | 3 | **> 7** — still fails at 2L+1 | — |
| 4 | 2 | 3 | 7 | 2.3 |

For small networks the threshold sits at 2L or 2L+1, which is where the repo's
"wait > 2 × max lag" rule came from. But it creeps up for R = 1, and the reason
is structural.

**The staggered cascade** (N=5, R=1, L=2, D=5 — all lags 2, announcements one
tick apart):

| node | leaves at | counted on as its survivor | which had already left at |
|---|---|---|---|
| 5 | tick 5 | node 1 | — (node 1's announcement not yet visible) |
| 4 | tick 6 | node 5 | tick 5 |
| 3 | tick 7 | node 4 | tick 6 |
| 2 | tick 8 | node 3 | tick 7 |
| 1 | tick 9 | node 2 | tick 8 |

Every node discounts the lower-id announcers correctly. But the tie-break also
tells it to count **higher-id** announcers as staying, and in a cascade each one's
"stayer" leaves inside its blind window. Every *pair* of nodes satisfies the
wait's guarantee; the *chain* drains the sector. A longer wait only demands a
longer chain: the first leaver must not see the last announcer, so the chain
must span more than D − L ticks with gaps under L. For any fixed D there is an N
that does it.

**V5 (`all`) is safe in every configuration tested, at a wait of just 1× lag:**
| N | R | L | wait D | result | schedules checked |
|---|---|---|---|---|---|
| 3 | 1 | 2 | 2 (= 1× lag) | **safe** | 4,088 |
| 4 | 1 | 2 | 2 (= 1× lag) | **safe** | 65,520 |
| 4 | 2 | 2 | 2 (= 1× lag) | **safe** | 65,520 |
| 4 | 3 | 2 | 2 (= 1× lag) | **safe** | 65,520 |
| 5 | 1 | 2 | 2 (= 1× lag) | **safe** | 1,048,544 |
| 5 | 2 | 2 | 2 (= 1× lag) | **safe** | 1,048,544 |
| 4 | 1 | 3 | 3 (= 1× lag) | **safe** | 1,185,840 |
| 4 | 2 | 3 | 3 (= 1× lag) | **safe** | 1,185,840 |

It is also safe on both schedules that broke V3 (N=5 R=1 L=2 D=5 over 5,153,600
schedules; N=4 R=1 L=3 D=7 over 4,100,544).

## 4. Why V5 is safe for any N — the proof

> **Claim.** With rule `all` and wait D ≥ every node's lag, and no deaths,
> `|holders| ≥ R` always — for any N, any R, any heterogeneous lags.
>
> **Proof.** Let n act at tick e with lag ℓ ≤ D. It sees holders V and
> announcers I as of tick e − ℓ. Let S be the nodes that left by shrinking in
> the window (e − ℓ, e] — exactly the nodes n still counts but which are gone.
> Any m ∈ S acted at some e_m in that window, so it announced at e_m − D ≤ e − D
> ≤ e − ℓ, and its announcement was still active at e − ℓ (it acted later).
> So m ∈ I. Hence S ⊆ I, and n's estimate
> `|V \ {n} \ I| ≤ |V \ S \ {n}| = |holders now \ {n}|`.
> If the estimate is ≥ R, then at least R holders remain after n leaves. ∎

The argument never mentions N, and nothing in it depends on announcement
timing, so it holds for re-announcements and arbitrarily long cascades. The
reason V3 fails is visible in the same lines: V3 subtracts only the lower-id
part of I, so a higher-id member of S can be counted as a survivor.

This is the "doorway" structure of Lamport's bakery algorithm — announce, wait
until every announcement that could race you is visible, then decide — which is
famous precisely for being correct with stale reads. V5 applies it in its most
conservative form; V3 adds a priority order that the bakery algorithm itself
only uses for *who goes first*, not for *who is assumed to stay*.

## 5. Results — with deaths

One node may also die at any tick (leave without announcing); its death becomes
visible to everyone `detect` ticks later. Safety: no **shrink** takes the sector
below R (a death alone can). N=4, R=2, L=2, D=5:

| rule | death noticed before the next decision | 1 tick later¹ | 2 ticks | 3 ticks |
|---|---|---|---|---|
| V5 `all` | **safe** (14,054,400 schedules) | **safe** | fails | fails |
| V3 `tb` | **fails** | fails | fails | fails |

¹ deaths are applied after the same tick's decisions, so a 1-tick delay still
means "known before anyone next decides".

- **V5 is safe exactly when a death is noticed before anyone acts on a view that
  still counts the dead node.** Any slower and there is a counterexample. That is
  [constraint 6](REPORT_stage3.md#constraints-on-any-sizing-policy) in exact
  form — and it makes the residual a matter of timing luck, which is what the
  §6.1/§11 studies measure statistically.
- **V3 fails even with instant detection.** Node 4 leaves correctly; node 1 then
  dies; node 3 leaves counting the already-departed node 4 as its survivor. The
  same higher-id flaw, needing only one ordinary death.

## 6. What this changes

- **The headline.** "Proven by exhaustive model checking" was true of a property
  close to trivial. The accurate statement is now: the bare re-check is proven
  insufficient under stale views; V5 is proven safe under stale views for any N,
  given prompt death detection; V3 is safe only for small networks and only
  without deaths.
- **The 2× rule.** For V3 it is derived for small N and shown insufficient in
  general. For V5 it is unnecessary — 1× suffices — though a longer wait still
  helps everything that depends on detection.
- **The AgentInfo recommendation.**
  [REPORT_agentinfo_encoding.md](REPORT_agentinfo_encoding.md) §5 recommended
  carrying an explicit "intending to leave" bit so the tie-break could be kept.
  On safety alone, the tie-break is the weaker rule. The case for the explicit
  bit now rests only on V5's *costs* — reachability dips at scale and the
  storm-loss frequency in §4.9 — not on V3 being safer.
- **The empirical record is consistent with this.** The §6.1 race grid found
  1,732 shrink-caused holes for V3 against 5 for V5 (346×). It was attributed
  to detection latency; the higher-id survivor flaw is a second, structural
  candidate. Telling them apart is open work.

## 7. Limitations

- Exhaustive only for small networks (N ≤ 5; ~5–14 million schedules per
  configuration). The V5 claim rests on the proof, not on the enumeration; the
  V3 failures need only one counterexample each.
- One sector, as in the TLA+ spec; holders only leave (no re-growth during the
  window); each node announces at most once in the enumeration (the V5 proof
  does not need this).
- Discrete ticks, one death at most, deaths visible to all viewers at the same
  delay.
- Announcements are unconstrained. A real trigger (hysteresis, the shrink
  condition) makes many of these schedules impossible, so the V3 failures are
  *possible* behaviours of the rule, not measured rates. Whether a cascade
  arises in practice is a simulation question this report does not answer.
- Pure Python; not yet re-expressed in TLA+. A `StalePoliteShrink.tla` that TLC
  can check would be the natural next step for anyone who wants the result in
  the original tool.

## Reproduce

```bash
cd spec
python stale_check.py --n 6 --r 3 --fresh            # 656 states, matches TLC
python stale_check.py --n 6 --r 3 --fresh --no-tb    # still 656, still safe
python timed_check.py --sweep                         # tie-break vs none, table above
python timed_check.py --n 5 --r 1 --lag 2 --wait 5             # the cascade
python timed_check.py --n 5 --r 1 --lag 2 --wait 5 --rule all  # V5: safe
python timed_check.py --n 4 --r 2 --lag 2 --wait 5 --rule tb  --crash --detect 0
```

*Research directed by Ceri John; design, implementation, and analysis with AI
assistance (Claude, Anthropic); all results human-reviewed.*
