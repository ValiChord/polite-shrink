"""
stale_check — exhaustive model check of polite shrink under STALE views.

Why this exists
---------------
`PoliteShrink.tla` lets every node execute against the *current* holder set,
read atomically. Under that assumption a plain re-check is already safe: if
|holds \\ {n}| >= R before n drops, then |holds| >= R after it. The tie-break
term (`LowerIntenders`) is never exercised, and deleting it leaves the spec
"No error" — which is why `AgentInfoConservative.tla` (no tie-break) also
passes. So the published proof shows that a re-check against fresh state is
safe. It does not show that the tie-break is needed, which is what the docs
claimed it isolates.

The tie-break exists for a different situation: execute reads a view that is
*stale* — it may still count a rival who has already left — while the wait
guarantees the rival's *announcement* is visible. This module checks that
situation directly.

Model (one sector, as in the TLA+ spec)
---------------------------------------
State: `holds`, `intend`, and for each intender n a frozen snapshot
`view[n] = (holds_seen, intend_seen)` taken at some earlier moment.

  Announce(n)   n holds, has not announced           -> n joins intend
  Snapshot(n)   n intends, has no snapshot yet       -> view[n] := (holds, intend)
                (the read that n's decision will use; it may be arbitrarily
                old by the time n executes)
  Execute(n)    n intends and has a snapshot, AND the doorway condition holds:
                every rival that has left since the snapshot (counted in
                holds_seen, absent from holds) appears in intend_seen.
                  eff = |holds_seen \\ {n} \\ TB(n)|
                  eff >= R  -> n leaves holds and intend
                  else      -> n cancels (leaves intend, keeps storing)

  TB(n) = { m in intend_seen : m < n }   with the tie-break
  TB(n) = {}                             without it

The doorway condition is what the wait buys in the simulation. With
intent_delay > 2 x lag, for any two racing intenders, either n's view already
shows m's announcement, or by the time n executes m's departure is already
visible to n (proof sketch in the module docstring of polite_shrink.py and in
REPORT_stage1.md §2.2). It is the "doorway" of Lamport's bakery algorithm, the
classic mutual-exclusion algorithm proven correct with stale ("safe") reads.
Snapshots are real past states, so views are always consistent.

Safety: |holds| >= R in every reachable state.

Validation: `--fresh` reproduces the published TLC state counts for
PoliteShrink.tla (execute reads current state), e.g. 656 for N=6, R=3.

Optional fault: `--crash` lets a node vanish without announcing (a death), and
`--detect` adds the guard that no one executes while holding a view that
counts an undetected crash. Without `--detect`, safety is checked in the form
"no *shrink* is what takes a sector below R", since crashes alone can.

Pure stdlib. Usage:
  python stale_check.py --n 5 --r 2            # with tie-break
  python stale_check.py --n 5 --r 2 --no-tb    # without: expect a violation
  python stale_check.py --n 6 --r 3 --fresh    # reproduce TLC count 656
"""

from __future__ import annotations

import argparse
import sys
from collections import deque


def check(n_nodes, R, tiebreak=True, fresh=False, crash=False, detect=False,
          two_sided=True,
          max_states=20_000_000):
    nodes = tuple(range(1, n_nodes + 1))
    full = frozenset(nodes)
    # state = (holds, intend, crashed, views) ; views: tuple sorted (n, hs, is)
    init = (full, frozenset(), frozenset(), (), ())
    seen = {init}
    parent = {init: None}
    q = deque([init])

    def views_dict(v):
        return {n: (hs, is_) for n, hs, is_ in v}

    def pack(d):
        return tuple(sorted((n, hs, is_) for n, (hs, is_) in d.items()))

    def violation(s):
        holds, intend, crashed, v, sw = s
        return len(holds) < R

    def trace(s):
        out = []
        while s is not None:
            out.append(s)
            s = parent[s]
        return out[::-1]

    while q:
        s = q.popleft()
        holds, intend, crashed, v, sw = s
        vd = views_dict(v)
        sawd = dict(sw)
        succ = []

        for n in nodes:
            # Announce
            if n in holds and n not in intend:
                succ.append(("Announce", n,
                             (holds, intend | {n}, crashed, v, sw)))
            # Snapshot (only in stale mode)
            if not fresh and n in intend and n not in vd:
                d = dict(vd)
                d[n] = (holds, intend)
                succ.append(("Snapshot", n, (holds, intend, crashed, pack(d), sw)))
            # Execute
            if n in intend and (fresh or n in vd):
                if fresh:
                    hs, is_ = holds | crashed, intend
                    # fresh = reads current state; with crashes, an undetected
                    # crash still looks present unless --detect
                    if detect:
                        hs = holds
                else:
                    hs, is_ = vd[n]
                    # doorway: rivals that LEFT BY SHRINKING since the snapshot
                    # must have been visible as intenders
                    shrunk_unseen = (hs - holds) - crashed - {n}
                    if not shrunk_unseen <= is_:
                        continue
                    if two_sided and any(n not in sawd.get(m, frozenset())
                                         for m in shrunk_unseen):
                        continue
                    if detect and (hs & crashed):
                        continue  # detection: crashed peers known before acting
                tb = {m for m in is_ if m < n} if tiebreak else set()
                eff = len((hs - {n}) - tb)
                d = dict(vd)
                d.pop(n, None)
                if eff >= R:
                    nsw = tuple(sorted(sawd.items()) + [(n, frozenset(is_))])                         if not fresh else sw
                    ns = (holds - {n}, intend - {n}, crashed, pack(d), nsw)
                    succ.append(("Execute(vacate)", n, ns))
                else:
                    ns = (holds, intend - {n}, crashed, pack(d), sw)
                    succ.append(("Execute(cancel)", n, ns))
            # Crash: a holder vanishes without announcing
            if crash and n in holds:
                d = dict(vd)
                d.pop(n, None)
                succ.append(("Crash", n,
                             (holds - {n}, intend - {n}, crashed | {n}, pack(d), sw)))

        for label, who, ns in succ:
            if ns in seen:
                continue
            seen.add(ns)
            parent[ns] = s
            # Safety: with crashes, only blame a shrink for dropping below R
            bad = violation(ns)
            if crash:
                bad = bad and label == "Execute(vacate)"
            if bad:
                return False, len(seen), trace(ns), (label, who)
            if len(seen) > max_states:
                raise RuntimeError("state budget exceeded")
            q.append(ns)
    return True, len(seen), None, None


def fmt_state(s):
    holds, intend, crashed, v, sw = s
    vs = "; ".join(f"{n}:sees{sorted(hs)}" for n, hs, _ in v)
    c = f" crashed={sorted(crashed)}" if crashed else ""
    return f"holds={sorted(holds)} intend={sorted(intend)}{c}" + (f" views[{vs}]" if vs else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--r", type=int, default=2)
    ap.add_argument("--no-tb", action="store_true", help="drop the tie-break")
    ap.add_argument("--fresh", action="store_true",
                    help="execute reads current state (the published model)")
    ap.add_argument("--one-sided", action="store_true",
                    help="doorway a 1x-lag wait buys (n saw m) instead of 2x (both saw)")
    ap.add_argument("--crash", action="store_true")
    ap.add_argument("--detect", action="store_true")
    a = ap.parse_args()
    ok, n_states, tr, last = check(a.n, a.r, tiebreak=not a.no_tb,
                                   fresh=a.fresh, crash=a.crash,
                                   detect=a.detect, two_sided=not a.one_sided)
    mode = ("fresh" if a.fresh else "stale") + \
           (" no-tiebreak" if a.no_tb else " tiebreak") + \
           (" +crash" if a.crash else "") + (" +detect" if a.detect else "") + (" wait=1x" if a.one_sided else " wait=2x")
    if ok:
        print(f"N={a.n} R={a.r} [{mode}]: NO ERROR, {n_states} distinct states")
        return 0
    print(f"N={a.n} R={a.r} [{mode}]: VIOLATION after {n_states} states; "
          f"last step {last[0]} by node {last[1]}")
    for i, s in enumerate(tr):
        print(f"  {i:2d}. {fmt_state(s)}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
