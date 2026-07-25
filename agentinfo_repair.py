"""Does the AgentInfo-only encoding break V4's sparse-network recovery?

REPORT_stage3.md §6.2: V3 without the small-network clamp deadlocks on sparse
networks (stuck in 5 of 90 port-scale seeds); the V4 expanding-ring repair rule
recovers 120/120. V4 is the variant this work would actually recommend, so the
encoding has to be checked against it rather than against V3 alone.

Two ways it could go wrong, and both are measured here:

  * recovery — the conservative gate suppresses shrinking, which should if
    anything help a starved network; but it also narrows what every viewer
    sees, and the repair rule triggers on *seen* holes.
  * spurious repair — a phantom hole (declared-zero while still held) is a
    hole as far as the repair rule can tell, so announcements could provoke
    growth that was never needed. That shows up as extra sync cost and extra
    repair grows, not as loss.

`RepairSim` needs no changes for either encoding: it reads `cov - icov`, and
under the AgentInfo encoding the intent snapshot is empty while `cov` already
excludes announcers, so the expression degrades correctly on its own.

Run:  python3 agentinfo_repair.py [--quick]
"""

from __future__ import annotations

import multiprocessing as mp
import sys

import numpy as np

from polite_shrink import VARIANTS, Config
from repair_sim import DEADLOCK_CASES, RepairSim, deadlock_world

V3, V5 = VARIANTS[3], VARIANTS[4]
SEEDS = 12


def one(job):
    label, clustered, n_surv, n_agents, r, clamp, vname, seed, ticks = job
    variant = V5 if vname == "V5" else V3
    cfg = Config(clamp_min_peers=clamp, seed=seed,
                 n_agents=n_agents, redundancy=r)
    initial, events, joins = deadlock_world(
        cfg, ticks, n_surv, seed + 500, clustered)
    sim = RepairSim(cfg, variant, events, initial, joins)
    m = sim.run(ticks)
    fu = m.frac_under
    rec = next((t for t in range(1520, ticks) if fu[t] == 0.0), None)
    return {
        "case": label, "variant": vname,
        "recovered": rec is not None,
        "rec": (rec - 1500) if rec is not None else None,
        "stuck": rec is None and sum(m.resizes[-300:]) == 0,
        "sync": m.cum_sync[-1] - m.cum_sync[1500],
        "repair_grows": sim.n_repair_grows,
        "held_loss": int(np.sum(m.held_zero[1500:])),
    }


def main():
    quick = "--quick" in sys.argv
    seeds = 4 if quick else SEEDS
    cases = DEADLOCK_CASES[:2] if quick else DEADLOCK_CASES
    ticks = 3200
    # clamp = 0 is the point: it removes the safety net so the repair rule is
    # the only thing that can recover the network.
    jobs = [(lbl, cl, ns, na, r, 0, vn, 1000 * s + 3, ticks)
            for (lbl, cl, ns, na, r) in cases
            for vn in ("V3", "V5")
            for s in range(seeds)]
    with mp.Pool(min(8, mp.cpu_count())) as pool:
        res = pool.map(one, jobs)
    print(f"Sparse-network recovery with V4 repair, clamp = 0 (no safety net), "
          f"{seeds} seeds/case.\n")
    print(f"{'case':14s} {'enc':>4} {'recovered':>10} {'stuck':>6} "
          f"{'med rec':>8} {'med sync':>9} {'repair grows':>13} {'held_loss':>10}")
    for lbl, *_ in cases:
        for vn in ("V3", "V5"):
            rs = [x for x in res if x["case"] == lbl and x["variant"] == vn]
            recs = [x["rec"] for x in rs if x["rec"] is not None]
            print(f"{lbl:14s} {vn:>4} "
                  f"{sum(x['recovered'] for x in rs):>4}/{len(rs):<5} "
                  f"{sum(x['stuck'] for x in rs):6d} "
                  f"{(int(np.median(recs)) if recs else -1):8d} "
                  f"{int(np.median([x['sync'] for x in rs])):9d} "
                  f"{int(np.median([x['repair_grows'] for x in rs])):13d} "
                  f"{sum(x['held_loss'] for x in rs):10d}")


if __name__ == "__main__":
    main()
