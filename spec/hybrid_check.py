"""
hybrid_check — safety AND progress for V3, V5 and the hybrid, with retries.

`timed_check.py` showed the safety picture: the lowest-id tie-break (V3) fails a
staggered cascade; discounting every visible announcer (V5) is safe for any N.
But judged by principle, V5 has a gap of its own — in *progress*. If several
nodes announce together and each discounts all the others, they can all cancel
even when one could safely leave; identical nodes retrying in step then cancel
forever. That is the symmetric-deference livelock the TCAS-style tie-break was
introduced to prevent.

The hybrid keeps each idea in the job it is good at:

  * SAFETY (V5's rule): at the re-check, count every visible announcer as gone.
  * PROGRESS (the TCAS rule, moved): after a cancel, retry in id order — a node
    waits rank x S before re-announcing, where rank = how many lower-id
    announcers it saw and S = D + 1. The lowest id goes first; by the time the
    next one re-announces, the first has finished, so they no longer collide.

The tie-break decides *who goes next*, never *who is assumed to stay* — the
same division the bakery algorithm makes. Seeing who is announcing needs an
explicit "intending to leave" signal (a dedicated message, or one bit on
AgentInfo); a narrowed arc claim alone cannot tell an announcer from a node
that has already left.

Model: same timing as `timed_check.py` (announce, wait D, act on a view lag
ticks old, lag per node, same-tick actions in id order and blind to each
other). Every node is a *persistent* leaver: it keeps retrying until it leaves.
Exhaustive over every initial announce time and per-node lag.

  rule     counts at re-check        after a cancel
  v3       lower-id announcers       re-announce next tick (symmetric)
  v5       every announcer           re-announce next tick (symmetric)
  hybrid   every announcer           re-announce after rank x (D+1) ticks

Checked per schedule:
  safety    |holders| >= R at every tick
  progress  holders reach exactly R before the horizon (every departure that
            can safely happen, does). A schedule that ends above R is STUCK.
Also reported: the worst-case number of ticks to reach R.

Pure stdlib. Usage:
  python hybrid_check.py --n 4 --r 2 --lag 2 --wait 5
  python hybrid_check.py --table
"""

from __future__ import annotations

import argparse
import itertools
import sys


def run(N, R, D, ann, lags, rule):
    nodes = range(1, N + 1)
    holds = set(nodes)
    intent = {}                       # node -> execute tick
    next_ann = {n: ann[n - 1] for n in nodes}
    history = {}
    init = (frozenset(nodes), frozenset())
    S = D + 1
    horizon = max(ann) + (N + 2) * (N * S + D + max(lags) + 2)
    reached = None
    for t in range(horizon):
        for n in nodes:
            if intent.get(n) == t and n in holds:
                s = t - lags[n - 1]
                hs, its = history.get(s, init) if s >= 0 else init
                if rule == "patient":
                    e5 = len((set(hs) - {n}) - (set(its) - {n}))
                    if (e5 < R and not any(m < n for m in its)
                            and any(m > n for m in its)):
                        intent[n] = t + 1          # lowest: wait, don't cancel
                        continue
                    eff = e5
                elif rule == "v3":
                    disc = {m for m in its if m < n}
                    eff = len((set(hs) - {n}) - disc)
                elif rule == "combo":
                    e5 = len((set(hs) - {n}) - (set(its) - {n}))
                    lowest = not any(m < n for m in its)
                    eff = e5 if e5 >= R else (len(set(hs) - {n}) if lowest else -1)
                elif rule == "yield":
                    # strict yield: any visible lower-id racer -> cancel;
                    # otherwise higher ids count as staying (they will yield)
                    eff = -1 if any(m < n for m in its) else len(set(hs) - {n})
                else:
                    disc = set(its) - {n}
                    eff = len((set(hs) - {n}) - disc)
                del intent[n]
                if eff >= R:
                    holds.discard(n)
                    if len(holds) < R:
                        return ("UNSAFE", t)
                else:
                    if rule in ("hybrid", "hybrid_rank"):
                        rank = sum(1 for m in its if m < n)
                        next_ann[n] = t + 1 + rank * S
                    else:
                        next_ann[n] = t + 1
        for n in nodes:
            if next_ann.get(n) == t and n in holds and n not in intent:
                if rule in ("hybrid", "patient"):
                    # YIELD: hold off while a lower-id announcer is visible in my
                    # current (stale) view; look again next tick. Changes only
                    # WHEN a node announces, so the V5 safety proof is untouched.
                    s_ = t - lags[n - 1]
                    _, its_now = history.get(s_, init) if s_ >= 0 else init
                    if any(m < n for m in its_now):
                        next_ann[n] = t + 1
                        continue
                intent[n] = t + D
                next_ann[n] = None
        history[t] = (frozenset(holds), frozenset(intent))
        if reached is None and len(holds) == R:
            reached = t
            break
    if len(holds) > R:
        return ("STUCK", None)
    return ("OK", reached)


def check(N, R, L, D, rule):
    span = D + 2 * L + 1
    n_sched = unsafe = stuck = 0
    worst = 0
    first_bad = None
    for ann in itertools.product(range(span), repeat=N):
        for lags in itertools.product(range(1, L + 1), repeat=N):
            n_sched += 1
            status, t = run(N, R, D, ann, lags, rule)
            if status == "UNSAFE":
                unsafe += 1
                first_bad = first_bad or ("unsafe", ann, lags, t)
            elif status == "STUCK":
                stuck += 1
                first_bad = first_bad or ("stuck", ann, lags, t)
            else:
                worst = max(worst, t)
    return dict(n=n_sched, unsafe=unsafe, stuck=stuck, worst=worst, first=first_bad)


def fmt(res):
    s = "safe" if not res["unsafe"] else f"UNSAFE x{res['unsafe']:,}"
    p = "always" if not res["stuck"] else f"STUCK x{res['stuck']:,}"
    w = f"{res['worst']}" if not res["stuck"] else "-"
    return s, p, w


def table(configs):
    print("Every node is a persistent leaver; exhaustive over initial announce times")
    print("and per-node lags. 'progress' = holders always reach exactly R.\n")
    print(f"{'N':>2} {'R':>2} {'L':>2} {'D':>2}  {'rule':<7} {'safety':<14} {'progress':<14} {'worst ticks':>11} {'schedules':>11}")
    for N, R, L, D in configs:
        for rule in ("v3", "v5", "hybrid_rank", "hybrid", "yield", "combo", "patient"):
            res = check(N, R, L, D, rule)
            s, p, w = fmt(res)
            print(f"{N:>2} {R:>2} {L:>2} {D:>2}  {rule:<7} {s:<14} {p:<14} {w:>11} {res['n']:>11,}", flush=True)
        print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--r", type=int, default=2)
    ap.add_argument("--lag", type=int, default=2)
    ap.add_argument("--wait", type=int, default=5)
    ap.add_argument("--rule", choices=["v3", "v5", "hybrid_rank", "hybrid", "yield", "combo", "patient"], default=None)
    ap.add_argument("--table", action="store_true")
    a = ap.parse_args()
    if a.table:
        table([(3, 1, 2, 5), (4, 1, 2, 5), (4, 2, 2, 5), (4, 3, 2, 5),
               (4, 2, 2, 2), (5, 1, 1, 3), (5, 2, 1, 3), (5, 3, 1, 3)])
        return 0
    for rule in ([a.rule] if a.rule else ["v3", "v5", "hybrid_rank", "hybrid", "yield", "combo", "patient"]):
        res = check(a.n, a.r, a.lag, a.wait, rule)
        s, p, w = fmt(res)
        print(f"N={a.n} R={a.r} L={a.lag} D={a.wait} {rule:<7} safety={s} progress={p} "
              f"worst={w} ({res['n']:,} schedules)")
        if res["first"]:
            kind, ann, lags, t = res["first"]
            print(f"   first {kind}: announce={ann} lags={lags}" + (f" tick {t}" if t else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
