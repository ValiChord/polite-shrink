"""
bee_radius_sim — Swarm Bee's storage-radius controller, and fixes for its flip.

Swarm Bee (ethersphere/bee, pkg/storer/reserve.go) sizes each node's
responsibility with a storage radius: a node keeps chunks whose proximity order
(PO) is at least the radius. Lowering the radius by one roughly doubles what
the node is responsible for. The controller, as written:

  * increase: when the reserve is over capacity, `unreserve` evicts chunks below
    the radius, only as many as needed to fit (the eviction target), and raises
    the radius one step at a time while there is nothing left below it to evict;
  * decrease: every wakeup, if the chunks WITHIN the radius are fewer than 50%
    of capacity and syncing is idle, lower the radius by one.

Issue ethersphere/bee#5659 (open, Oct 2026) reports nodes flipping their radius
down and back up on every wakeup, 803 changes in 7 days on 3 nodes, each flip
restarting the puller and leaking streams on peers. Its reading of the code:
the reserve is full but mostly of chunks below the radius, so the within-radius
count stays under 50% while the reserve stays at capacity.

The thresholds (50% to decrease, 100% to increase) are exactly the factor of two
that one radius step changes responsibility by, so there is no hysteresis margin:
when the neighbourhood's content just below the radius is larger than the
content within it, both conditions can hold at once. This model compares:

  * "bee": the controller as written;
  * "no-decrease-at-cap": the reporter's first suggestion, never decrease while
    the reserve is at or above capacity;
  * "evict-first": the reporter's second suggestion, evict out-of-radius chunks
    before evaluating the decrease threshold;
  * "predictive": a polite-shrink-style rule: decrease only if the chunks the
    node already holds at PO radius-1, plus those within the radius, would fit
    with 10% to spare, and only after the decrease condition has held for two
    consecutive wakeups (hysteresis scaled to the controller's own period).

The model is one node. Time step 1 minute; wakeup every 30 minutes (#5659);
the node syncs missing chunks at or above its radius at a fixed rate, and every
radius change pauses syncing for 2 minutes (the puller restart). Capacity and
content are in units of 1/4096 of capacity. Neighbourhood content per PO is a
scenario parameter. This is a model of the mechanism #5659 describes, not of
Bee's whole storer: batch values, expiry and peers' own radii are left out.
"""

from __future__ import annotations

import argparse

C = 4096                 # capacity, in chunk units
WAKE = 30                # minutes between threshold checks
SYNC_RATE = C // 60      # units synced per minute (fills a reserve in ~1 h)
RESTART = 2              # minutes of sync lost per radius change
MAXPO = 16


def ideal_radius(avail):
    """The radius Bee's own thresholds aim for: the largest radius at which
    the node is between half full and full; if there is none (the dead zone),
    the smallest radius that fits."""
    band = [r for r in range(MAXPO + 1) if C // 2 <= sum(avail[r:]) <= C]
    if band:
        return max(band)
    return min(r for r in range(MAXPO + 1) if sum(avail[r:]) <= C)


def run(rule, avail, start_r, start_held, minutes=7 * 24 * 60):
    held = list(start_held)
    r = start_r
    changes = 0
    paused_until = 0
    streak = 0
    ideal = ideal_radius(avail)
    at_ideal = 0
    coverage_sum = 0.0

    def within():
        return sum(held[r:])

    def unreserve():
        nonlocal r, changes, paused_until
        target = sum(held) - C
        while target > 0:
            for po in range(r):                      # evict below the radius
                take = min(held[po], target)
                held[po] -= take
                target -= take
                if target <= 0:
                    return
            if r >= MAXPO:
                return
            r += 1                                   # nothing left below: raise
            changes += 1
            paused_until = t + RESTART

    for t in range(minutes):
        # Sync: fill missing chunks at or above the radius.
        if t >= paused_until:
            budget = SYNC_RATE
            for po in range(r, MAXPO + 1):
                need = avail[po] - held[po]
                if need > 0 and budget > 0:
                    add = min(need, budget)
                    held[po] += add
                    budget -= add
            if sum(held) > C:
                unreserve()
        sync_idle = all(held[po] >= avail[po] for po in range(r, MAXPO + 1))
        # Threshold check.
        if t % WAKE == WAKE - 1 and r > 0:
            if rule == "evict-first":
                for po in range(r):
                    held[po] = 0
            cond = within() < C // 2 and sync_idle
            if rule == "no-decrease-at-cap":
                cond = cond and sum(held) < C
            if rule == "predictive":
                fits = within() + held[r - 1] <= 0.9 * C
                streak = streak + 1 if (cond and fits) else 0
                cond = streak >= 2
            if cond:
                r -= 1
                changes += 1
                paused_until = t + RESTART
                streak = 0
        at_ideal += (r == ideal)
        demand = sum(avail[r:])
        coverage_sum += (within() / demand) if demand else 1.0
    return {"changes": changes, "final_radius": r, "ideal": ideal,
            "time_at_ideal": at_ideal / minutes,
            "mean_coverage": coverage_sum / minutes}


def scenario(name):
    """Neighbourhood content per PO (units), start radius, start holdings."""
    avail = [0] * (MAXPO + 1)
    if name == "deadzone":
        # #5659's shape: within radius 9 is under half capacity, but radius 8
        # would not fit. Reserve starts full, mostly of PO-8 chunks.
        for po, frac in zip(range(9, 14), [0.24, 0.12, 0.06, 0.04, 0.03]):
            avail[po] = int(frac * C)
        avail[8] = int(0.62 * C)
        held = avail[:]
        held[8] = C - sum(avail[9:])
        return avail, 9, held
    if name == "balanced":
        # Ordinary halving: radius 8 fits. A correct controller should move
        # from 9 to 8 once and stay.
        for po, frac in zip(range(8, 14), [0.42, 0.21, 0.11, 0.05, 0.03, 0.02]):
            avail[po] = int(frac * C)
        held = avail[:]
        held[8] = 0
        return avail, 9, held
    if name == "grown":
        # The neighbourhood has outgrown radius 8: the node starts at 8, full,
        # and must rise to 9 and stay.
        for po, frac in zip(range(8, 14), [0.70, 0.30, 0.10, 0.05, 0.03, 0.02]):
            avail[po] = int(frac * C)
        held = [0] * (MAXPO + 1)
        for po in range(8, 14):
            held[po] = avail[po]
        over = sum(held) - C
        held[8] -= over
        return avail, 8, held
    raise ValueError(name)


def main():
    ap = argparse.ArgumentParser()
    ap.parse_args()
    rules = ("bee", "no-decrease-at-cap", "evict-first", "predictive")
    print("| scenario | rule | radius changes in 7 days | final radius (ideal) | "
          "time at ideal radius | mean coverage of responsibility |")
    print("|---|---|---|---|---|---|")
    for sc in ("deadzone", "balanced", "grown"):
        avail, r0, held0 = scenario(sc)
        for rule in rules:
            o = run(rule, avail, r0, held0)
            print(f"| {sc} | {rule} | {o['changes']} | {o['final_radius']} ({o['ideal']}) | "
                  f"{100*o['time_at_ideal']:.0f}% | {100*o['mean_coverage']:.0f}% |")


if __name__ == "__main__":
    main()
