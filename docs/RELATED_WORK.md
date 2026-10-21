# Related work from other fields — and what testing them found

*October 2026. A search of other fields for the mathematics of this problem,
followed by experiments that each connection suggested. Read alongside
[REPORT_stale_views.md](../reports/REPORT_stale_views.md), which several of these feed.*

The problem splits into three parts that the repo already showed are separable:
**the race** (two nodes leave at once), **the oscillation** (the hallway dance),
and **the setting** (local decisions under stale views, no coordinator). Each has
a near-relative in another field, and each relative turned out to be worth
something concrete.

## 1. Wireless sensor networks — the same problem, twenty years earlier

Battery-powered sensors save energy by switching off when their patch is already
covered by neighbours: **k-coverage**, where k is this repo's R. They hit exactly
this race — two neighbours each judge themselves redundant and both switch off,
leaving a hole the literature calls a **"blind point"**. Their fixes are this
repo's V1–V2 family: back-off timers and an eligibility re-check before sleeping.

- Tian & Georganas, *A coverage-preserving node scheduling scheme for large
  wireless sensor networks*, WSNA 2002 — an off-duty eligibility rule plus
  back-off-based self-scheduling.
- Wang, Xing, Zhang, Lu, Pless & Gill, *Integrated coverage and connectivity
  configuration in wireless sensor networks* (CCP), SenSys 2003 — arbitrary
  coverage degree K, with a WITHDRAW timer on the active-to-sleep transition.
- Later work reports that **blind points can still occur under CCP**, and that
  time-delay conflict resolution leaves holes when the delays are mis-estimated.

*Verification level:* the mechanisms above come from abstracts and later papers
describing these protocols; the 2002 full text was not read.

**What it adds.** This repo's ablation explains why that field's holes
persisted: desynchronising by *timing* (V2 jitter, back-off) does not close the
race. And [REPORT_stale_views.md](../reports/REPORT_stale_views.md) now shows formally that
a bare wait-and-re-check — the "withdraw timer" pattern, rule `none` there —
fails in every configuration at every wait. Polite shrink is best positioned not
as "a fix for Holochain" but as **the formally analysed version of a pattern a
whole field used heuristically**. No formal treatment of the sensor-network race
turned up in the search.

## 2. k-exclusion and the bakery algorithm — the race has a name

The gate admits exactly the lowest-id **holders − R** announcers and makes the
rest stand down (checked against `spec/PoliteShrink.tla`). That is
**k-exclusion** — at most k processes in the critical section at once — with
k = holders − R: Fischer, Lynch, Burns & Borodin, *Resource allocation with
immunity to limited process failure*, FOCS 1979.

Classic k-exclusion assumes processes read shared state atomically. Polite
shrink approximates atomic reads by **waiting out staleness**, which is the
structure of Lamport's **bakery algorithm** (CACM 1974): announce, wait until
every announcement that could race you is visible, then decide — famous for being
correct even with stale reads. A k-exclusion version exists (Danek, *k-Bakery*).

**What testing it found.** Following the bakery structure literally is what led
to [REPORT_stale_views.md](../reports/REPORT_stale_views.md): the published TLA+ proof gave
nodes atomic reads and so never exercised the tie-break; modelling the stale read
properly shows the ID tie-break (V3) is necessary but not sufficient, while
discounting *every* visible announcer (V5) is safe for any N. In bakery terms,
V3 uses priority not only to decide who goes first but who is *assumed to stay*,
and that second use is what a staggered cascade exploits.

The residual race is also precisely located by this framing: it is the gap
between "waited out the staleness" and "read atomically" — which a death that
has not yet been detected re-opens.

V5 then stalls, because identical announcers can all cancel. V6 ("patient
lowest") keeps V5's count and uses the ID order only to decide *who waits*,
never who is assumed to stay.

## 2b. Mutual inclusion — the closer name

k-exclusion caps how many may be *inside*. The polite-shrink invariant is the
mirror image: at least R must stay holding each sector. That is **l-mutual
inclusion**, at least *l* processes in the critical section at all times, and
its two-sided form is the **global (l, k)-critical section problem**: Kamei &
Kakugawa, *An asynchronous message-passing distributed algorithm for the global
critical section problem* (PDAA 2017; extended version
[arXiv:1807.05674](https://arxiv.org/abs/1807.05674)). Their motivating example
is keeping at least *l* servers running while others are switched off to save
cost, which is the shrink decision with servers in place of sector holders.
There is also a local form, where each process has its own bounds over its
neighbourhood (Kakugawa and Kamei's self-stabilising "local (l, k)-critical
section" papers), and UPPAAL timed-automata models of k-exclusion and m-mutual
inclusion algorithms (2021).

How the published solution differs from V6, from the paper itself:

| | Kamei & Kakugawa, l-mutual inclusion | V6 polite shrink |
|---|---|---|
| leaving | ask a quorum who is inside, then acquire and wait for every quorum member's acknowledgement | announce, wait a fixed time, re-check a local (stale) view; no replies |
| concurrent leavers | serialised by a Maekawa-style mutual exclusion | leave together when the margin allows; ID order only decides who waits |
| stale information | handled by blocking until a reply arrives | handled by waiting out a known staleness bound |
| crashes | not modelled ("fault-tolerant design" is future work) | safe with a death at any time if it is noticed before anyone acts on a view still counting the dead node (model-checked, and a proof for any N) |
| many overlapping minimums | one critical section | one minimum per sector, each node in many |
| cost per decision | O(√n) messages with grid or projective-plane quorums | one broadcast, plus one withdrawal if it stands down |

So the problem is known. What is not in this literature, as far as this search
found, is a solution that is coordinator- and permission-free, lets leavers go
concurrently, and stays safe on stale gossip views with failures. That is the
claim to make, and it is narrower than "a new problem". A search on "mutual
inclusion" turned up quorum-based and token-based algorithms, but nothing
gossip-based.

**Where else the same shape appears.** Any duty that many members share, that
each may give up voluntarily, with a floor that must always hold, no
coordinator, and members acting on out-of-date information. Scaling down a
replicated service without a controller is the textbook case: the server-
invocation example above. Sensor-network sleep scheduling (section 1) is
another.

**A contrasting design: Autonomi.** Autonomi's node software
([`WithAutonomi/ant-node`, docs/REPLICATION_DESIGN.md](https://github.com/WithAutonomi/ant-node/blob/main/docs/REPLICATION_DESIGN.md))
avoids voluntary shrinking altogether. Responsibility is fixed by XOR distance:
a record belongs to the closest 7 nodes, and a node never decides to give up a
record it is still responsible for. It prunes only records it has been out of
range for, continuously, for 3 days. Before deleting a record that is only just
out of range, it asks the current close group to prove possession, and deletes
only if 6 of the 7 return valid proofs. Records far out of range are deleted
without proof, a trade-off the design states openly. So the race polite shrink
solves does not arise there, at the cost of re-replicating whenever membership
shifts. Its possession proofs are the same idea as this repo's Stage-3 finding
that verified coverage, not declared coverage, is the real defence against nodes
that lie (REPORT_stage3.md §6–§7).

## 3. Congestion control — the oscillation as a delay instability

Johari & Tan, *End-to-end congestion control for the Internet: delays and
stability* (IEEE/ACM ToN, 2001), and Vinnicombe (IFAC 2002; also Massoulié,
2000) showed that a decentralised network whose sources have **different**
delays is locally stable, for any topology, if **each source scales its gain to
its own round-trip time**. This repo's V1 found the same design rule by
experiment: hysteresis scaled to each node's *own* measured lag.

The theory makes two falsifiable predictions for this controller.
`oscillation_sweep.py` tests both (activation, N=200, R=5, 12 seeds/cell,
resizing measured over the last 2,000 of 5,000 ticks; full table in
[results/oscillation_summary.md](../results/oscillation_summary.md)):

| prediction | result |
|---|---|
| A **sharp threshold**: resizing switches on suddenly as reaction gets faster (the fingerprint of a delay-induced Hopf bifurcation) | **Not supported.** For V3, resizing fades gradually — about 1.2 changes/tick at persistence ≤ 1× lag, falling smoothly to 0.01 at 6× lag. One confound: nodes decide only every 6 ticks, so persistence values below 6 ticks behave identically and the knob is coarse at the low end. |
| **Own-lag scaling beats one network-wide constant** when lags differ | **Partly supported, in the operating range.** V1: own-lag resizes less at almost every setting. V3: own-lag is steadier at high persistence (6× lag: 0.012 vs 0.213 changes/tick) but *less* steady at low persistence (≈1.25 vs 0.70). With 12 seeds the intervals are wide — suggestive, not established. |

**An unprompted finding.** Networks in which every node has the *same* lag
oscillate **more** than mixed-lag networks with the same mean — often two to
three times more (V1 at 2–6× lag: 1.6–2.7 changes/tick vs 0.3–1.1). Identical
nodes react in lockstep. That is this repo's original diagnosis of the hallway
dance — a *symmetry* problem — showing up without being looked for, and it points
the same way as the heterogeneity result in §5 below.

**What it means.** The theorem does not transfer: this controller is quantised
(power-of-two arcs), hysteretic and nonlinear, and the data show no sharp
stability boundary. But the theory's *design rule* — scale reaction to your own
delay — holds where the controller actually operates, and lag diversity is
stabilising rather than hazardous. "The oscillation may be inherent" is better
put as "it fades with persistence and with diversity; there is no cliff".

## 4. Applied topology — elegant, not the next step

de Silva & Ghrist, *Coverage in sensor networks via persistent homology*
(Algebraic & Geometric Topology, 2007), certify coverage from only "who is near
whom" data, with no coordinates; Dłotko, Ghrist, Juda & Mrozek later distributed
the computation. Sheaf theory (Hansen & Ghrist; Robinson) measures whether local
views can be glued into a consistent global one — formally, the local-to-global
problem every node here faces.

Relevant to the "estimate N from stale, possibly dishonest views" part of #160,
but the coverage criterion is conservative and was designed centrally. Filed as
reading, not as a next experiment.

## 5. Replications prompted by the October audit

The audit found two detection-side headlines the committed data could not
support. `detector_replication.py` re-tested both on **fresh seeds** (910000+,
disjoint from every earlier study), storm 50%, pure V3, with exact 95% intervals.
Full table: [results/detector_replication_summary.md](../results/detector_replication_summary.md).

**A spread of detection speeds — direction confirmed, number corrected.**

| network | loses data | 95% interval |
|---|---|---|
| all fast (dl = 96) | 15% (11/72) | 8–26% |
| all slow (dl = 192) | 35% (25/72) | 24–47% |
| half and half | **18%** (13/72) | 10–29% |

A mixed network behaves like its *faster* half. The earlier "0/24" came from a
24-seed probe whose script was never committed, and it does not replicate: the
mix roughly halves the loss rather than removing it.

**Erring toward conviction needs a ceiling — now established.** dl = 192,
150 seeds per point:

| false-conviction rate p | loses data | 95% interval | equilibrium arc |
|---|---|---|---|
| 0 | 36.0% | 28.3–44.2% | 1.37 |
| 0.05 | 10.7% | 6.2–16.7% | 1.29 |
| **0.10** | **2.7%** | 0.7–6.7% | 1.32 |
| 0.20 | 8.7% | 4.7–14.4% | 1.50 |
| 0.40 | 15.3% | 10.0–22.1% | 2.11 |

The optimum is **≈ 0.10**, not the ≈ 0.05 earlier docs quoted, and p = 0.40 is
clearly worse (non-overlapping intervals). At p = 0.40 nodes hold markedly *more*
data and still lose more, so the mechanism is not simple caution; whether it is
error cancellation or thrashing remains open.

*Environment for every new result here: Python 3.14.8 with numpy 2.5.1 and
matplotlib 3.11.0 (library pins match; the Python pin of 3.12.1 does not).*

## Reproduce

```bash
python sim/oscillation_sweep.py          # ~12 min on 4 cores
python sim/detector_replication.py       # ~45 min on 3 cores
cd spec && python timed_check.py --sweep
```

*Research directed by Ceri John; design, implementation, and analysis with AI
assistance (Claude, Anthropic); all results human-reviewed.*
