"""Verify, across EVERY storm run that lost data in the 312-seed sweep, that
the loss was caused by node death (not by a polite-shrink decision).

For each losing (seed, fraction): rerun the byte-identical world with all
polite/naive shrink decisions unchanged but the storm deaths at t=1500 removed.
If any_loss drops to False in every case, then no shrink orphaned a sector —
"polite shrink lost no data" holds across all cases.
"""

import json

import numpy as np

from polite_shrink import Config, make_world
from rolling_upgrade_sim import MixedSim, assign_initial_variants

CELLS = "results/rolling_upgrade_cells.jsonl"
KW = dict(storm_at=1500, storm_frac=0.30)
TICKS = 3000

rows = [json.loads(l) for l in open(CELLS)]
losers = sorted([(r["seed"], r["fraction"]) for r in rows
                 if r["scenario"] == "storm" and r["fraction"] > 0 and r["any_loss"]])

print(f"storm losing runs (f>0): {len(losers)}\n")
all_death = True
for seed, frac in losers:
    cfg = Config(seed=seed)
    initial, events, joins = make_world(cfg, TICKS, **KW)
    variants = assign_initial_variants(len(initial), frac, cfg.seed)

    m_real = MixedSim(cfg, list(variants), events, initial, joins, frac).run(TICKS)
    z = np.array(m_real.zero_sectors)
    first = int(np.argmax(z > 0))

    events_nodeath = {k: v for k, v in events.items() if k != 1500}
    m_cf = MixedSim(cfg, list(variants), events_nodeath, initial, joins, frac).run(TICKS)
    cf_loss = bool((np.array(m_cf.zero_sectors) > 0).any())

    death_caused = (first == 1500) and (not cf_loss)
    all_death = all_death and death_caused
    print(f"  seed {seed} f={frac:.2f}: first_orphan_tick={first} "
          f"(deaths at 1500), loss_without_deaths={cf_loss}  "
          f"-> death-caused={death_caused}")

print(f"\n{'ALL storm losses are death-caused — polite shrink orphaned nothing.' if all_death else 'SOME loss was NOT death-caused — investigate!'}")
raise SystemExit(0 if all_death else 1)
