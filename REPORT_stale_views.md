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
   it has a short proof. But it can **stall**: identical nodes can cancel each
   other forever.
5. **The recommended rule is V6, "patient lowest"** (§7): V5's count, plus — when
   the margin is thin — the lowest announcer waits instead of cancelling and the
   others get out of its way. Safe by V5's proof, always makes progress, and at
   200 nodes its arcs stay close to V3's with about a third of the sync traffic.
   Its only failure mode, shared with every rule, is a death that has not been
   noticed by the time someone acts on a view that still counts the dead node.

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
- **The recommended rule.** V6 (§7). The two analyses below were written
  before V6 existed and are kept as the record of how it was reached.
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

## 7. Making it live — the hybrid search, and V6

Judged by principle, V5 has a gap of its own, in **progress** rather than
safety. If several nodes announce together and each discounts all the others,
they can all cancel even when one of them could safely leave — and identical
nodes retrying in step then cancel forever. That is the symmetric-deference
livelock the TCAS-style tie-break was introduced to prevent. So the target is a
rule with three properties at once: **safe** (including when an ordinary death
is noticed promptly), **live** (holders always reach R when leaving is safe) and
**concurrent** (many nodes may leave in the same round when the margin allows —
otherwise 200 nodes never finish sharding).

`spec/hybrid_check.py` checks the first two exhaustively with every node a
*persistent* leaver that keeps retrying; `spec/timed_check.py --crash` adds a
death at any tick; `v6_study.py` measures the third at N = 200. Five candidates:

| candidate | safe, no deaths | safe, prompt deaths | always progresses | concurrent at N=200 |
|---|---|---|---|---|
| V3 — lowest-ID tie-break | ✗ cascade | ✗ | ✓ | ✓ |
| V5 — count every announcer | ✓ | ✓ | ✗ stalls (e.g. 133,240 of 160,000 schedules, N=4 R=2) | ✓ |
| V5 + retries ordered by ID rank | ✓ | ✓ | ✗ stalls (15,561) — the retry stagger resonated with the wait | — |
| … + don't announce while a lower ID is visible | ✓ | ✓ | ✗ stalls (6,369) — the lowest ID still discounts higher ones, so they block it | — |
| strict TCAS yield — defer outright to any lower-ID racer | ✓ (wait ≥ 2× lag) | ✓ | ✓ | ✗ — only one node may leave at a time: arcs stay near full, 95% of announcements cancel |
| "safe-or-lowest" — V5's test, or "I'm the lowest and R remain counting the rest" | ✓ (wait ≥ 2× lag) | **✗ one instantly-detected death** | ✓ | ✓ |
| **V6 "patient lowest"** | **✓ (wait ≥ 1× lag)** | **✓** | **✓** | **✓** |

The failures teach the shape of the answer. "Safe-or-lowest" broke on the same
schedule as V3: node 4 leaves via V5's test (correctly allowing for node 3 to
leave too), node 1 then dies and uses up that margin, and node 3 — the lowest —
leaves counting node 4 as still present. The general rule: **a decision survives
deaths only if it never relies on a node that might itself be leaving.** V5 never
relies on an announcer. Strict yield relies on higher announcers but forbids them
to leave — which is why it serialises.

**V6 "patient lowest"** follows that rule exactly:

1. **Count** every racing announcer as gone (V5's rule). Vacate if R remain.
2. **Wait**: if the count fails only because of *higher*-ID racers and no lower
   ID is racing me, keep my announcement up and re-check next tick instead of
   cancelling.
3. **Yield**: don't announce while a lower ID is racing me for the same sectors.

Nobody is ever counted as present while announcing, so §4's proof applies word
for word — waiting and yielding change only *when* decisions happen, never what
a decision may rely on. Progress: the lowest racer never yields; higher racers
fail their own counts, stand down and stay quiet while it waits; once they have
cleared out of its view it re-checks with nobody left to discount. Concurrency
comes from the count itself: when the margin is wide, it passes for many nodes in
the same round.

**Exhaustive results for V6** *(spec/patient_safety.txt, spec/hybrid_table.txt)*:
safe at a wait of 1× lag in all configurations (N = 3–5, R = 1–3, L = 2–3); safe
with a death at any tick when it is noticed before the next decision
(14,054,400 schedules each); fails, like every rule, when a death goes unnoticed
for longer; and **always reaches R** in all eight progress configurations, where
V5 stalls in 35–87% of schedules.

**At N = 200** ([results/v6_summary.md](results/v6_summary.md); fresh seeds,
exact 95% intervals):

| | V3 | V5 | **V6** |
|---|---|---|---|
| equilibrium arc level (4 standard scenarios) | 0.57–1.05 | 0.81–2.23 | **0.80–1.30** |
| sync cost per run | ≈ 19,000–22,000 | ≈ 3,000–9,000 | **≈ 6,000–7,800** |
| cancel rate | 2.7–3.3% | 7.4–9.5% | **2.0–2.8%** |
| time below R (sector-ticks, storm/churn) | 14–22 | 40–48 | **2–10** |
| phantom (declared-only) holes | 0 | 1,800–2,700 per scenario | **0** |
| runs losing data, storm 30% / 40% (×100) | 0 / 0 | 1 / 11 | **1 / 0** |
| runs losing data, storm 50% + detection 192 ticks late (×72) | 26 | 35 | **28** |

Every storm loss for V5 and V6 began **at the storm tick itself**: the mass
death took every holder of some sector in one blow, before any shrink decision.
The difference between rules there is how much spare margin the arcs happened to
hold at that instant; V3's accidental ~2R margin covered all 100 worlds. Under
very late death detection all three lose data in a third or more of runs — the
residual no re-check rule can close (§5). V6 sits closest to the target R the
rest of the time, which is where its lower sync cost and lower time below R
come from.

**Cost.** Like V3, V6 must *see* who is announcing — a dedicated message, or one
explicit "intending to leave" bit on `AgentInfo`. A narrowed arc claim alone
(V5) cannot tell an announcer from a node that has already left, and the
waiting and yielding need exactly that distinction. So the August conclusion of
[REPORT_agentinfo_encoding.md](REPORT_agentinfo_encoding.md) — carry one bit —
stands, for a different reason. V6 is not yet implemented on the Rust fork.

## 8. Limitations

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
python timed_check.py --n 4 --r 2 --lag 2 --wait 5 --rule patient --crash --detect 0  # V6: safe
python hybrid_check.py --table          # safety + progress for every candidate
cd .. && python v6_study.py             # V6 vs V3 vs V5 at N = 200
```

*Research directed by Ceri John; design, implementation, and analysis with AI
assistance (Claude, Anthropic); all results human-reviewed.*
