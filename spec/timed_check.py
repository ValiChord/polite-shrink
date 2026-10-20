"""
timed_check — exhaustive check of polite shrink with REAL timing and stale views.

What `PoliteShrink.tla` proves, and what it does not
-----------------------------------------------------
The TLA+ spec lets each node execute against the *current* holder set, read
atomically. Under that assumption a bare re-check is already safe — if
|holds \\ {n}| >= R before n drops, |holds| >= R after — so the tie-break term is
never exercised: deleting it leaves the spec "No error" (verified by
`stale_check.py --fresh --no-tb`, which reproduces TLC's state counts exactly).
The proof therefore covers "a re-check against fresh state is safe". It does not
cover the mechanism that makes polite shrink work, which is acting *safely on a
stale view*.

This module checks that mechanism directly, with the simulator's own timing
semantics and no hand-derived abstraction:

  * A node that announces at tick a executes at tick a + D.
  * At execute it reads the world as it was at tick e - lag_n (lag_n in 1..L,
    per node — heterogeneous staleness), i.e. it sees intents active then and
    holders as of then. Departures inside the last lag_n ticks are invisible.
  * eff = |holders_seen \\ {n} \\ TB(n)|; vacate iff eff >= R, else cancel.
    TB(n) = { m in intents_seen : m < n } with the tie-break, {} without.
  * Executes in the same tick are processed in id order and cannot see each
    other (their views are older than the tick), matching `Sim.step`.
  * Announcements are unconstrained (a node may announce whenever it still
    holds), as in the TLA+ spec: the safety argument must not lean on the
    trigger being right.

Every combination of announce time (or never) and per-node lag is enumerated —
an exhaustive search over schedules, not a sample. Safety: |holds| >= R at every
tick.

The question it answers: for which waits D is the rule safe, with and without
the tie-break? The design rule in the repo is D > 2 x max lag. A rule that is
safe at D = 2L+1 and unsafe at smaller D *derives* that factor of 2 rather than
assuming it.

Optional `--crash`: one node may additionally die (leave without announcing) at
any tick, and its death becomes visible to each viewer after `--detect` ticks.
Safety is then "no *shrink* takes the sector below R", since a death alone can.

Pure stdlib. Usage:
  python timed_check.py --n 4 --r 2 --lag 2 --wait 5
  python timed_check.py --n 4 --r 2 --lag 2 --wait 5 --no-tb
  python timed_check.py --sweep            # the table in the report
"""

from __future__ import annotations

import argparse
import itertools
import sys


def run_schedule(n_nodes, R, D, ann, lags, tiebreak, crash=None, detect=0):
    # tiebreak: True -> 'tb' (V3, lower-id intenders), False -> 'none',
    # or a string rule: 'tb' | 'none' | 'all' (V5: every visible intender)
    rule = {True: 'tb', False: 'none'}.get(tiebreak, tiebreak)
    """Simulate one schedule. ann[i] = announce tick or None; lags[i] in 1..L.
    crash = (node, tick) or None. Returns None if safe, else (tick, detail)."""
    nodes = range(1, n_nodes + 1)
    holds = set(nodes)
    intent = {}            # node -> execute tick (active intents)
    departed_at = {}       # node -> tick it left by shrinking
    died_at = {}           # node -> tick it died
    # history[t] = (frozenset holds_visible, frozenset intents) at END of tick t
    history = {}
    init = (frozenset(nodes), frozenset())
    horizon = max([a for a in ann if a is not None] + [0]) + D + 2
    if crash:
        horizon = max(horizon, crash[1] + 2)

    def view_at(t, viewer_lag, viewer):
        s = t - viewer_lag
        hs, its = history.get(s, init) if s >= 0 else init
        hs = set(hs)
        # a death is visible to this viewer exactly `detect` ticks after it
        # happens, independently of gossip staleness (the two clocks are
        # separate in kitsune2: unresponsive marking vs peer-store gossip).
        # Undetected -> still counted, even in a view taken after the death;
        # detected -> removed, even from a view taken before it.
        for m, td in died_at.items():
            if t - td < detect:
                hs.add(m)
            else:
                hs.discard(m)
        return hs, its

    for t in range(horizon):
        # 1. due executes, in id order, each on its own stale view
        for n in nodes:
            if intent.get(n) == t and n in holds:
                hs, its = view_at(t, lags[n - 1], n)
                if rule == 'tb':
                    tb = {m for m in its if m < n}
                elif rule == 'all':
                    tb = set(its) - {n}
                else:
                    tb = set()
                eff = len((hs - {n}) - tb)
                del intent[n]
                if eff >= R:
                    holds.discard(n)
                    departed_at[n] = t
                    if len(holds) < R:
                        return (t, f"node {n} vacated on a view counting "
                                   f"{sorted(hs)}; true holders now {sorted(holds)}")
        # 2. death
        if crash and crash[1] == t and crash[0] in holds:
            holds.discard(crash[0])
            intent.pop(crash[0], None)
            died_at[crash[0]] = t
        # 3. announcements
        for n in nodes:
            a = ann[n - 1]
            if a == t and n in holds and n not in intent and n not in departed_at:
                intent[n] = t + D
        # 4. publish
        history[t] = (frozenset(holds), frozenset(intent))
    return None


def check(n_nodes, R, L, D, tiebreak=True, crash_mode=False, detect=0,
          stop_at_first=True):
    span = D + 2 * L + 1                # covers every relative offset that matters
    ann_opts = [None] + list(range(span))
    lag_opts = range(1, L + 1)
    count = bad = 0
    first = None
    crash_opts = [None]
    if crash_mode:
        crash_opts = [(c, t) for c in range(1, n_nodes + 1)
                      for t in range(span + D)]
    for ann in itertools.product(ann_opts, repeat=n_nodes):
        if sum(a is not None for a in ann) < 1:
            continue
        for lags in itertools.product(lag_opts, repeat=n_nodes):
            for cr in crash_opts:
                count += 1
                res = run_schedule(n_nodes, R, D, ann, lags, tiebreak, cr, detect)
                if res:
                    bad += 1
                    if first is None:
                        first = (ann, lags, cr, res)
                    if stop_at_first:
                        return False, count, first
    return bad == 0, count, first


def describe(first):
    ann, lags, cr, (t, detail) = first
    s = ", ".join(f"node{i+1}: announce@{a} lag={l}" for i, (a, l) in
                  enumerate(zip(ann, lags)) if a is not None)
    c = f"; node{cr[0]} dies @{cr[1]}" if cr else ""
    return f"[{s}{c}] -> tick {t}: {detail}"


def sweep():
    print("Exhaustive over announce times x per-node lags (L = max lag).")
    print("D = wait between announce and execute.\n")
    print(f"{'N':>2} {'R':>2} {'L':>2} {'D':>3} {'D/L':>5}  {'tie-break':>16}  {'no tie-break':>16}")
    for N, R, L in [(3, 1, 1), (3, 1, 2), (4, 1, 2), (4, 2, 2), (4, 3, 2),
                    (5, 2, 1), (5, 3, 1)]:
        for D in sorted({L, L + 1, 2 * L, 2 * L + 1, 2 * L + 2}):
            row = []
            for tb in (True, False):
                ok, n, _ = check(N, R, L, D, tiebreak=tb)
                row.append("safe" if ok else "VIOLATED")
            print(f"{N:>2} {R:>2} {L:>2} {D:>3} {D/L:>5.1f}  {row[0]:>16}  {row[1]:>16}",
                  flush=True)
        print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--r", type=int, default=2)
    ap.add_argument("--lag", type=int, default=2, help="max per-node lag L")
    ap.add_argument("--wait", type=int, default=5, help="wait D")
    ap.add_argument("--no-tb", action="store_true")
    ap.add_argument("--rule", choices=["tb", "none", "all"], default=None,
                    help="tb = V3 lower-id tie-break; all = V5 discount every "
                         "visible intender; none = bare re-check")
    ap.add_argument("--crash", action="store_true")
    ap.add_argument("--detect", type=int, default=0,
                    help="ticks before a death becomes visible")
    ap.add_argument("--sweep", action="store_true")
    a = ap.parse_args()
    if a.sweep:
        sweep()
        return 0
    rule = a.rule or ('none' if a.no_tb else 'tb')
    ok, n, first = check(a.n, a.r, a.lag, a.wait, tiebreak=rule,
                         crash_mode=a.crash, detect=a.detect)
    tag = (f"N={a.n} R={a.r} L={a.lag} D={a.wait} "
           f"rule={rule}"
           f"{f' crash detect={a.detect}' if a.crash else ''}")
    if ok:
        print(f"{tag}: SAFE over {n:,} schedules")
        return 0
    print(f"{tag}: VIOLATED (after {n:,} schedules)\n  {describe(first)}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
