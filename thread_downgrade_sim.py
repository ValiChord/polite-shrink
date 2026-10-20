"""
thread_downgrade_sim — Thread router downgrade (OpenThread), and two safer gates.

In a Thread mesh, routers step down to REED on their own when there are more
routers than needed. OpenThread's rule (`Mle::RoleTransitioner::
DecideWhetherToDowngrade` and `HandleTimeTick`, src/core/thread/mle_ftd.cpp,
October 2026):

  on receiving an advertisement from neighbouring router j, start a downgrade
  timer (random 1..120 s) if
    * active routers > 23 (kRouterDowngradeThreshold),
    * at least 7 neighbouring routers with two-way link quality >= 2,
    * j has links at least as good as ours to every one of those neighbours
      ("comparable connectivity"), and no transition is already pending;
  when the timer fires, downgrade if active routers are still > 23.

Only the router count is re-checked when the timer fires. Two routers that each
judged the other a comparable neighbour can both step down, each relying on a
router that is itself leaving. This model asks how often that leaves a hole:
the remaining routers no longer connected to each other, or a device position
no longer within range of any router.

Three gates are compared:

  * "openthread": as written.
  * "recheck": when the timer fires, re-run all the conditions against the
    current view, including that j is still a router.
  * "v6": recheck, plus a downgrade intent carried in advertisements; at the
    re-check, every other router announcing an intent counts as gone (from the
    count, the good neighbours, and as j); if only higher-ID announcers block
    it, wait and re-check a second later; do not start a timer while a
    lower-ID router in range is announcing.

Geometry: routers at random positions in a unit square, link quality 3 within
0.6 r, 2 within r, none beyond. Advertisements are heard from each neighbour on
average every `adv` seconds (Trickle settles at up to 32 s). A router that
steps down drops out of its neighbours' router tables after `notice` seconds
(each neighbour independently, uniform 1..notice; MLE ages out a silent
router, and the leader releases its ID, on that order). Upgrades of REEDs,
which would eventually repair a hole, are not modelled: the measure is whether
a hole opens at all, and for how long the downgrade wave itself takes.

Limits: unit-disk radio, no packet loss, no children table (Thread's "fewer
children than 3x the excess routers" check is assumed to pass), no partitions
or leader election, one wave of downgrades from 32 routers.
"""

from __future__ import annotations

import argparse
import math
import random
import statistics as st

THRESH = 23
MIN_NEIGH = 7
JITTER = 120


def lq(d, r):
    if d <= 0.6 * r:
        return 3
    if d <= r:
        return 2
    return 0


class World:
    def __init__(self, seed, n=32, r=0.42, devices=150, adv=16, notice=60):
        rng = random.Random(seed)
        self.rng = rng
        self.n, self.r, self.adv, self.notice = n, r, adv, notice
        self.pos = [(rng.random(), rng.random()) for _ in range(n)]
        self.L = [[lq(math.dist(self.pos[a], self.pos[b]), r) if a != b else 0
                   for b in range(n)] for a in range(n)]
        self.dev = [(rng.random(), rng.random()) for _ in range(devices)]
        self.ext_id = [rng.getrandbits(32) for _ in range(n)]

    def connected(self, routers):
        routers = list(routers)
        if not routers:
            return False
        seen = {routers[0]}
        stack = [routers[0]]
        rs = set(routers)
        while stack:
            a = stack.pop()
            for b in rs:
                if b not in seen and self.L[a][b] >= 2:
                    seen.add(b)
                    stack.append(b)
        return len(seen) == len(rs)

    def uncovered(self, routers):
        return sum(1 for d in self.dev
                   if not any(math.dist(d, self.pos[a]) <= self.r for a in routers))


def run(rule, w: World, seed, horizon=1800):
    rng = random.Random(seed * 31 + 7)
    n = w.n
    is_router = [True] * n
    left_at = {}                                  # router -> tick it stepped down
    notice_after = {}                             # (viewer, x) -> delay
    timer = [None] * n                            # tick at which timer fires
    trig = [None] * n                             # neighbour j that started it
    intent = [False] * n                          # v6: advertised intent
    out = {"downgrades": 0, "partition_ticks": 0, "uncovered_peak": 0,
           "uncovered_ticks": 0, "first_hole_at": -1, "final_routers": 0,
           "stand_downs": 0, "settled_at": -1}
    base_unc = w.uncovered(range(n))

    def sees_router(i, x, t):
        if x == i:
            return is_router[i]
        if is_router[x]:
            return True
        # stepped down: i still counts it until it notices
        return t - left_at[x] < notice_after[(i, x)]

    def view(i, t):
        return [x for x in range(n) if sees_router(i, x, t)]

    def good_neigh(i, routers):
        return [k for k in routers if k != i and w.L[i][k] >= 2]

    def comparable(i, j, routers):
        for k in good_neigh(i, routers):
            if k == j:
                continue
            if w.L[j][k] < w.L[i][k]:
                return False
        return True

    def conditions(i, j, t, discount):
        rv = [x for x in view(i, t) if x not in discount or x == i]
        if len(rv) <= THRESH:
            return False, "count"
        if len(good_neigh(i, rv)) < MIN_NEIGH:
            return False, "neigh"
        if j not in rv or w.L[i][j] < 2:
            return False, "trigger"
        if not comparable(i, j, rv):
            return False, "comparable"
        return True, ""

    for t in range(horizon):
        # 1. timers firing
        for i in range(n):
            if not is_router[i] or timer[i] != t:
                continue
            j = trig[i]
            if rule == "openthread":
                go = len(view(i, t)) > THRESH
            elif rule == "recheck":
                go, _ = conditions(i, j, t, set())
            else:
                others = {x for x in range(n) if x != i and intent[x] and is_router[x]}
                go, why = conditions(i, j, t, others)
                if not go:
                    lower = [x for x in others if w.ext_id[x] < w.ext_id[i] and w.L[i][x] >= 2]
                    higher = [x for x in others if w.ext_id[x] > w.ext_id[i] and w.L[i][x] >= 2]
                    ok_without_higher, _ = conditions(i, j, t, set(lower))
                    if higher and not lower and ok_without_higher:
                        timer[i] = t + 1          # lowest waits
                        continue
            timer[i] = None
            intent[i] = False
            if go:
                is_router[i] = False
                left_at[i] = t
                for v in range(n):
                    notice_after[(v, i)] = rng.randint(1, w.notice)
                out["downgrades"] += 1
            else:
                out["stand_downs"] += 1
        # 2. advertisements: each router hears each neighbour w.p. 1/adv
        for i in range(n):
            if not is_router[i] or timer[i] is not None:
                continue
            for j in range(n):
                if j == i or not is_router[j] or w.L[i][j] < 2:
                    continue
                if rng.random() >= 1.0 / w.adv:
                    continue
                if rule == "v6":
                    lower_ann = any(intent[x] and is_router[x] and w.L[i][x] >= 2
                                    and w.ext_id[x] < w.ext_id[i] for x in range(n))
                    if lower_ann:
                        break
                ok, _ = conditions(i, j, t, set())
                if ok:
                    timer[i] = t + rng.randint(1, JITTER)
                    trig[i] = j
                    if rule == "v6":
                        intent[i] = True
                    break
        # 3. measure the true state
        routers = [x for x in range(n) if is_router[x]]
        unc = w.uncovered(routers) - base_unc
        part = not w.connected(routers)
        if part:
            out["partition_ticks"] += 1
        if unc > 0:
            out["uncovered_ticks"] += 1
            out["uncovered_peak"] = max(out["uncovered_peak"], unc)
        if (part or unc > 0) and out["first_hole_at"] < 0:
            out["first_hole_at"] = t
        if out["settled_at"] < 0 and all(x is None for x in timer) and \
                sum(is_router) <= THRESH:
            out["settled_at"] = t
    out["final_routers"] = sum(is_router)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=300)
    ap.add_argument("--notice", type=int, default=60)
    a = ap.parse_args()
    rules = ("openthread", "recheck", "v6")
    print(f"notice delay up to {a.notice} s; {a.runs} random layouts of 32 routers\n")
    print("| radio range | rule | runs with a partition | runs ending below 23 | "
          "runs ending below 16 (REEDs would upgrade) | routers at end: median [min] | "
          "runs with uncovered device positions | median s to settle |")
    print("|---|---|---|---|---|---|---|---|")
    for r in (0.35, 0.42, 0.5):
        for rule in rules:
            res = []
            for s in range(a.runs):
                w = World(s, r=r, notice=a.notice)
                if not w.connected(range(w.n)):
                    continue
                res.append(run(rule, w, s))
            holes = [x for x in res if x["first_hole_at"] >= 0]
            parts = [x for x in res if x["partition_ticks"] > 0]
            hole_s = [x["uncovered_ticks"] for x in holes if x["uncovered_ticks"] > 0]
            settle = [x["settled_at"] for x in res if x["settled_at"] >= 0]
            fin = [x["final_routers"] for x in res]
            unc = sum(1 for x in res if x["uncovered_ticks"] > 0)
            print(f"| {r} | {rule} | {len(parts)}/{len(res)} | "
                  f"{sum(f < THRESH for f in fin)}/{len(res)} | "
                  f"{sum(f < 16 for f in fin)}/{len(res)} | "
                  f"{st.median(fin):.0f} [{min(fin)}] | {unc}/{len(res)} | "
                  f"{st.median(settle) if settle else float('nan'):.0f} |", flush=True)


if __name__ == "__main__":
    main()
