"""Does the AgentInfo-only encoding change the false-coverage (liar) threshold?

The Stage-3 liar study (REPORT_stage3.md §6) found that past K = R agents that
declare a full arc while storing nothing, any declaration-trusting controller
loses data invisibly. That attack is unchanged by the encoding — a liar signs a
false arc claim about itself either way — but the *gate* is not: V5 gives up the
tie-break and counts only current claimants, so it is worth checking whether the
threshold moves.

Ground truth here is `true_*`, which counts only honest agents' real storage.
The declared/held split used elsewhere in this work is NOT the right measure in
this study: `_build_held` credits every alive agent, and a liar is alive with a
full-arc level while storing nothing, so held coverage would count the liars.

Run:  python3 agentinfo_liars.py
"""
import numpy as np
from polite_shrink import VARIANTS, Config, make_world
from byzantine_sim import ByzantineSim, pick_byz

V3, V5 = VARIANTS[3], VARIANTS[4]
TICKS = 2600


def main():
    cfg = Config()
    R = cfg.redundancy
    print(f"Liar sweep, R = {R}, N = {cfg.n_agents}, {TICKS} ticks.")
    print("true_* counts only honest agents' real storage; the threshold the "
          "Stage-3 study found sits at K = R.\n")
    print(f"{'K':>4} {'K/R':>5}  "
          f"{'V3 true_floor':>13} {'V3 true_zero':>12}  "
          f"{'V5 true_floor':>13} {'V5 true_zero':>12}")
    for f in (0.0, 0.01, 0.02, 0.025, 0.03, 0.04, 0.05, 0.075):
        k = round(f * cfg.n_agents)
        initial, events, joins = make_world(cfg, TICKS)
        byz = set(pick_byz(cfg, k, cfg.n_agents))
        res = {}
        for v in (V3, V5):
            m = ByzantineSim(cfg, v, events, initial, joins,
                             byz_ids=byz, mode="liar").run(TICKS)
            res[v.name] = m
        m3, m5 = res[V3.name], res[V5.name]
        print(f"{k:4d} {k/R:5.1f}  {m3.true_floor[-1]:13d} {m3.true_zero[-1]:12d}  "
              f"{m5.true_floor[-1]:13d} {m5.true_zero[-1]:12d}")


if __name__ == "__main__":
    main()
