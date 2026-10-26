# V6 "patient lowest" — the rule, its assumptions, and what backs each claim

One page for a reviewer. Details and history are in
[REPORT_stale_views.md](reports/REPORT_stale_views.md) and
[results/rust_fork_v6.md](results/rust_fork_v6.md).

## Problem

Nodes each hold some sectors of a DHT. Any node may stop holding a sector
("shrink"), but every sector must keep at least **R** holders. There is no
coordinator; each node decides from its own view of the network, which may be
out of date. (In the literature this is called *l-mutual inclusion*; here R-mutual inclusion.)

## The rule

For a node `n` that wants to vacate a range `V` (in the Rust code:
`announce_shrink`, `execute_intent`, `patient_recheck`, `lower_racer`):

```
announce:  if some lower-ID node is announcing a vacate overlapping V: do nothing now
           else: broadcast intent(n, V, expires = now + 2·wait), set re-check at now + wait

re-check (at the set time, on n's current view):
           eff = holders of V other than n, minus every OTHER announcer overlapping V
           if min over V of eff >= R:                        vacate V, done
           elif a higher-ID announcer overlaps V
                and no lower-ID announcer overlaps V:        keep the intent, re-check next tick
                                                             (refresh its expiry so it never lapses)
           else:                                             withdraw the intent, stand down
```

`wait` is at least the node's measured gossip staleness (Rust:
`max(lag × intent_wait, intent_min_wait_ms)`).

## Assumptions

- **A1. Bounded staleness.** Every node's view of holders and of intents is at
  most `L` old, and `wait ≥ L`.
- **A2. Intents outlive the departure.** A node's intent stays visible to
  everyone until its departure is visible to everyone. (Rust: an intent expires
  one `wait` after its re-check, and a waiting node refreshes it; this holds
  while A1 holds.)
- **A3. Deaths are noticed in time.** A node that dies is noticed by everyone
  before anyone acts on a view that still counts it. (Since 21 October the
  code enforces A1 for holders and bounds A3 locally, `require_recent_contact`:
  a shrink counts only holders heard from within the wait, so a silent holder
  stops counting one wait after its last message. See
  [rust_fork_v6.md §12](results/rust_fork_v6.md).)
- **A4. Honest declarations.** A node that says it holds a range does hold it.
- **A5. Authentic intents.** An intent comes from the node it names. (Rust: only
  intents arriving from the node's own declared address are counted.)

## Guarantees under those assumptions

- **G1. Safety.** No shrink takes any sector below R. Deaths can, and that case
  is A3.
- **G2. Progress.** If a node wants to leave and a copy can be spared, some node
  eventually leaves.
- **G3. Concurrency.** When the margin allows, several nodes leave in the same
  round. The ID order decides only who *waits*, never who is assumed to stay.

**Why G1 holds (any N).** Let `n` re-check at time `e` on a view of age
`ℓ ≤ L ≤ wait`. Any node `m` that left in `(e − ℓ, e]` is still a holder in
`n`'s view, but it announced at least `wait ≥ ℓ` before leaving and its intent
was still live (A2), so `m` is among the announcers `n` subtracts. So `n`'s
count never includes a node that has already gone. If the count clears R, at
least R holders remain after `n` leaves. Waiting and yielding only change *when*
a node acts, never what it counts.

## What backs each claim

| claim | evidence |
|---|---|
| G1 for small N, every schedule | Rust model check on the real re-check code: 0 failures in every schedule up to 6 nodes (3 × 16.8 M), and in 906 M with a death at any tick (with prompt detection); Python checker agrees; TLC on `spec/StaleShrink.tla` agrees |
| G1 needs `wait ≥ L` (A1) | sweep: 0% failing from wait = lag; 1.9% at 2/3, 20% at 1/3 |
| G1 needs A3 | sweep: 0% failing while a death is noticed within 1 tick (wait 2); 6.5% at 2 ticks, 36% at 6 |
| G1 on a real network stack | storms over the in-memory and iroh transports, 8–32 nodes: never an orphaned sector; forced staggered cascade: V3 orphans a range, V6 does not |
| rollout | V6 alongside nodes that never shrink, a one-by-one replacement of such nodes, and mixed V6 timing settings: never below target, never a part with no holder ([rust_fork_v6.md §10](results/rust_fork_v6.md)) |
| G1 under churn | an hour of random kills, joins and staleness changes, 7–14 nodes: no shrink below target, no part without a holder; the short-wait control fails ([rust_fork_v6.md §11](results/rust_fork_v6.md)) |
| G2 | model: no stalls in any schedule (up to 6 nodes); forced simultaneous race: the lowest waits, then leaves; no node left able to shrink |
| G3 | 200-node simulation: arcs close to V3's with about a third of the sync traffic |
| A5 | unit tests: a forged intent cannot displace a genuine one; withdrawals remove only the intent they name |
| tests can fail | controls: V3 on the cascade, V6 with a too-short wait, both fail; mutation testing: 18 planted bugs, all caught (11 at first, every safety bug among them; tests added for the other 7) — [rust_fork_v6.md §9](results/rust_fork_v6.md) |

## Not guaranteed

- **Speed from full arcs:** G2 holds, but V6's yield makes nodes that share a
  range announce one at a time, so sharding down from full arcs can be several
  times slower than V3, and on some worlds very slow. The *alongside* repair
  fixes this; see [REPORT_v7.md](reports/REPORT_v7.md).
- **A4 violated (liars):** false declarations defeat every timing rule once
  liars reach R. The defence is verified coverage, simulated but not built.
- **A1/A3 violated:** with a wait shorter than the staleness, or deaths noticed
  late, safety degrades (measured above). This is the operational limit: death
  detection and the lag estimate must stay inside the wait.
- **The surrounding policy** (R, hysteresis, growth, clamp) is engineering
  judgement, not part of G1–G3.
- **Scale and WAN:** exhaustive checks stop at 6 nodes; network tests stop at 32
  nodes on one machine.
