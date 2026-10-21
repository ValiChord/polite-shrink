"""Storage fairness under the AgentInfo-only encoding.

The fairness study exists because V3's lowest-id-proceeds tie-break
systematically lets low-id agents shrink first, so high-id agents end up
holding bigger arcs (`fairness_sim.py`: correlation of agent id with
equilibrium level, and the share of storage held by the top decile). V3F
answers it by rotating the priority key per epoch, which then has to re-earn
the safety proof at the epoch boundary.

Under the AgentInfo-only encoding the question dissolves rather than being
answered: there is no tie-break to be unfair, because peers cannot distinguish
an intender from a departed node and the gate therefore counts current
claimants only. If that reasoning is right, V5 should show no id-skew at all —
and no rotation machinery is needed to get there.

Measured on the same metrics as the fairness study so the numbers are directly
comparable: corr(aid, level), level spread, and top-decile storage share.

Run:  python3 agentinfo_fairness.py [--quick]
"""

from __future__ import annotations

import multiprocessing as mp
import sys

import numpy as np

from polite_shrink import VARIANTS, Config, Sim, make_world
from fairness_sim import RotatingSim

V3, V5 = VARIANTS[3], VARIANTS[4]
TICKS = 2600
SEEDS = 24


def one(args):
    name, seed = args
    cfg = Config(seed=seed)
    initial, events, joins = make_world(cfg, TICKS)
    if name == "V3F":
        sim = RotatingSim(cfg, V3, events, initial, joins, period=200)
    else:
        sim = Sim(cfg, V5 if name == "V5" else V3, events, initial, joins)
    sim.run(TICKS)
    lv = np.array([a.level for a in sim.agents if a.alive], dtype=float)
    aid = np.array([a.aid for a in sim.agents if a.alive], dtype=float)
    width = 2.0 ** lv
    return {
        "variant": name, "seed": seed,
        "corr": float(np.corrcoef(aid, lv)[0, 1]),
        "std": float(lv.std()),
        "top_decile": float(np.sort(width)[-len(width) // 10:].sum()
                            / width.sum()),
        "held_loss": int(np.sum(sim.m.held_zero)),
    }


def main():
    quick = "--quick" in sys.argv
    seeds = 6 if quick else SEEDS
    names = ("V3", "V3F", "V5")
    jobs = [(n, 4000 + s) for n in names for s in range(seeds)]
    with mp.Pool(min(8, mp.cpu_count())) as pool:
        res = pool.map(one, jobs)
    print(f"Storage fairness at equilibrium, activation scenario, "
          f"{seeds} seeds.\n")
    print(f"{'variant':>8} {'corr(aid,level)':>16} {'level std':>10} "
          f"{'top-decile share':>17} {'held_loss':>10}")
    for n in names:
        rs = [x for x in res if x["variant"] == n]
        print(f"{n:>8} {np.mean([x['corr'] for x in rs]):+16.3f} "
              f"{np.mean([x['std'] for x in rs]):10.3f} "
              f"{np.mean([x['top_decile'] for x in rs]):16.1%} "
              f"{sum(x['held_loss'] for x in rs):10d}")


if __name__ == "__main__":
    main()
