"""Re-run the two §6.1-race storm losses WITH the storm brake, sweeping the
death-detection latency, to show whether/when the brake closes them.

Recall: seed 100109 (f=0.40) orphaned at t=1508 (death at 1500 -> 8-tick gap);
seed 100239 (f=0.10) at t=1515 (15-tick gap). The brake should close a loss
whenever detect_latency is small enough to fire before the racing execute.
"""

import numpy as np

from polite_shrink import Config, make_world
from rolling_upgrade_sim import MixedSim, assign_initial_variants
from brake_sim import BrakeMixedSim

KW = dict(storm_at=1500, storm_frac=0.30)
TICKS = 3000
CASES = [(100109, 0.40, 1508), (100239, 0.10, 1515)]
LATENCIES = [2, 4, 6, 8, 10, 12, 16, 20, 24]


def any_loss(m):
    return bool((np.array(m.zero_sectors) > 0).any())


def build(seed, frac):
    cfg = Config(seed=seed)
    initial, events, joins = make_world(cfg, TICKS, **KW)
    variants = assign_initial_variants(len(initial), frac, cfg.seed)
    return cfg, variants, events, initial, joins


for seed, frac, orphan_t in CASES:
    gap = orphan_t - 1500
    print(f"\n=== seed {seed} f={frac:.2f} — race execute at t={orphan_t} "
          f"({gap}-tick gap after the death) ===")
    cfg, variants, events, initial, joins = build(seed, frac)
    base = MixedSim(cfg, list(variants), events, initial, joins, frac).run(TICKS)
    print(f"  no brake            : any_loss={any_loss(base)}")
    for L in LATENCIES:
        cfg, variants, events, initial, joins = build(seed, frac)
        sim = BrakeMixedSim(cfg, list(variants), events, initial, joins, frac,
                            detect_latency=L)
        m = sim.run(TICKS)
        print(f"  brake, detect={L:2d} : any_loss={any_loss(m)}  "
              f"(brake cancelled {sim.brake_fires} intents)")
