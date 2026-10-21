"""
spacing_vs_v6 — one-at-a-time departures (Cassandra-style) against V6.

Cassandra's answer to the same stale-view race in gossip (CASSANDRA-7069, the
"two-minute rule") is to space topology changes out: a node bails if it sees
another one changing, and operators wait about two minutes between changes so
each announcement has reached everyone. That is safe but serial. V6 lets
several nodes leave together when the margin allows.

This asks how long it takes to shed spare copies under each rule, and whether
either ever goes below R. One sector, N holders that all want to leave while a
copy can be spared (persistent leavers: after standing down they try again),
per-node view lag 1..L ticks, wait D = L + 1 ticks after announcing.

  * "v6": announce unless a lower-ID announcer is visible; after D ticks,
    count every visible announcer as gone; vacate if R remain; if only
    higher-ID announcers block it, wait and re-check next tick.
  * "operator": Cassandra as documented — a person starts one departure at a
    time, S ticks apart (S = 1200 is the two minutes); each leaves only if its
    view shows R remaining without it.
  * "backoff": the self-triggered version of one-at-a-time — announce only if
    no announcer is visible and no departure has been visible for S ticks;
    after D ticks, vacate only if R remain counting itself gone and no other
    announcer is visible; otherwise stand down and wait a random 0..S ticks
    before trying again (first attempts are spread the same way). The window
    is (D + L) x N: the tightest spacing that lets each departure be seen,
    widened with the number of contenders as any random back-off must be.

1 tick = 100 ms.
"""

from __future__ import annotations

import argparse
import random
import statistics as st


def run(rule, n, r, lag_max, spacing, seed, horizon=120000):
    rng = random.Random(seed)
    nodes = list(range(n))
    lag = {i: rng.randint(1, lag_max) for i in nodes}
    D = lag_max + 1
    holds = set(nodes)
    intent = {}                       # node -> execute tick
    departed_at = {}
    hist = []                         # (holders, intenders, last departure tick)
    init = (frozenset(nodes), frozenset(), -10**9)
    min_holders = n
    last_change = 0
    next_try = {i: rng.randint(0, spacing) for i in nodes}   # backoff only
    op_next = 0                                              # operator only
    for t in range(horizon):
        # 1. due re-checks, each on its own stale view
        for i in sorted(intent):
            if intent.get(i) != t or i not in holds:
                continue
            s = t - lag[i]
            hs, its, _ = hist[s] if s >= 0 else init
            others = set(its) - {i}
            if rule == "v6":
                eff = len((hs - {i}) - others)
                lower = any(m < i for m in others)
                higher = any(m > i for m in others)
                if eff >= r:
                    go = True
                elif higher and not lower:
                    intent[i] = t + 1
                    continue
                else:
                    go = False
            else:
                go = len(hs - {i}) >= r and not others
            del intent[i]
            if not go and rule == "backoff":
                next_try[i] = t + rng.randint(1, spacing)
            if go:
                holds.discard(i)
                departed_at[i] = t
                last_change = t
                min_holders = min(min_holders, len(holds))
        # 2. announcements
        if rule == "operator":
            if t >= op_next and not intent:
                cands = [i for i in sorted(holds)]
                if cands:
                    i = rng.choice(cands)
                    s = t - lag[i]
                    hs = (hist[s] if s >= 0 else init)[0]
                    if len(hs - {i}) >= r:
                        intent[i] = t + D
                    op_next = t + spacing
            cand_iter = []
        else:
            cand_iter = sorted(holds)
        for i in cand_iter:
            if i in intent:
                continue
            s = t - lag[i]
            hs, its, last_dep = hist[s] if s >= 0 else init
            if len(hs - {i}) < r:          # no spare copy visible
                continue
            others = set(its) - {i}
            if rule == "v6":
                if any(m < i for m in others):
                    continue
            else:
                if t < next_try[i] or others or (s - last_dep) < spacing:
                    continue
            intent[i] = t + D
        last_dep_now = max(departed_at.values()) if departed_at else -10**9
        hist.append((frozenset(holds), frozenset(intent), last_dep_now))
        if len(holds) == r and not intent:
            break
        if rule == "operator" and t > op_next + 10 * spacing:
            break
    return last_change, min_holders, len(holds)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=200)
    a = ap.parse_args()
    print("| N | R | lag (s) | rule | spacing | time to shed all spares (s), median [min-max] of finished runs | "
          "ever below R | ended at R |")
    print("|---|---|---|---|---|---|---|---|")
    for n, r in [(8, 2), (20, 5), (50, 5)]:
        for lag_max in (2, 10):
            D = lag_max + 1
            for rule, spacing in [("v6", 0), ("backoff", (D + lag_max) * n), ("operator", 1200)]:
                res = [run(rule, n, r, lag_max, spacing, seed) for seed in range(a.runs)]
                times = [x[0] / 10 for x in res if x[2] == r]
                below = sum(1 for x in res if x[1] < r)
                at_r = sum(1 for x in res if x[2] == r)
                sp = "-" if rule == "v6" else f"{spacing/10:g} s"
                tt = (f"{st.median(times):.1f} [{min(times):.1f}-{max(times):.1f}]"
                      if times else "never finished")
                print(f"| {n} | {r} | {lag_max/10:g} | {rule} | {sp} | {tt} | "
                      f"{below}/{len(res)} | {at_r}/{len(res)} |", flush=True)


if __name__ == "__main__":
    main()
