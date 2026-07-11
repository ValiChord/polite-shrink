"""Robustness check: does the variant ordering hold across RNG seeds?
Runs activation + storm for several seeds, prints loss / worst floor /
settle per variant. No plots."""

import numpy as np

from arc_sim import VARIANTS, Config, Sim, make_world
from run_experiments import settle_tick

SCEN = [("activation", 2200, 0, {}),
        ("storm", 3000, 1500, dict(storm_at=1500, storm_frac=0.30))]

for seed in (7, 99, 1234):
    for key, ticks, t_dist, kw in SCEN:
        cfg = Config(seed=seed)
        initial, events, joins = make_world(cfg, ticks, **kw)
        row = []
        for v in VARIANTS:
            m = Sim(cfg, v, events, initial, joins).run(ticks)
            loss = int(np.sum(m.zero_sectors[t_dist:]))
            floor = int(np.min(m.floor[t_dist:]))
            st = settle_tick(m.resizes, t_dist)
            row.append(f"{v.name.split()[0]}: loss={loss} floor={floor} "
                       f"settle={'never' if st is None else st - t_dist}")
        print(f"seed={seed:5d} {key:11s} | " + " | ".join(row))
