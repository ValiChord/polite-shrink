"""Robustness check: does the variant ordering hold across RNG seeds?
Runs activation + storm for several seeds, prints loss / worst floor /
settle per variant. No plots."""

import numpy as np

from polite_shrink import VARIANTS, Config, Sim, make_world
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
            held = int(np.sum(m.held_zero[t_dist:]))
            floor = int(np.min(m.floor[t_dist:]))
            st = settle_tick(m.resizes, t_dist)
            # held= is printed only where it can differ from loss (V5), so the
            # V0-V3 output stays byte-identical to the published run.
            h = f" held={held}" if v.agentinfo else ""
            row.append(f"{v.name.split()[0]}: loss={loss}{h} floor={floor} "
                       f"settle={'never' if st is None else st - t_dist}")
        print(f"seed={seed:5d} {key:11s} | " + " | ".join(row))
