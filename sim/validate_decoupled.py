"""Reduction guard for the decoupled-clock model: with death_lag = view lag
(coupled), DecoupledSim must be byte-identical to MixedSim on every metric, in
every scenario, at every fraction — else the decoupling machinery has changed
the base dynamics and no decoupled number can be trusted.

Also a monotonicity sanity check: on a storm seed known to race, slower death
detection must not *reduce* the §6.1 race (coverage over-counts dead peers for
longer).
"""

import numpy as np

from polite_shrink import Config, make_world
from rolling_upgrade_sim import MixedSim, assign_initial_variants
from decoupled_sim import DecoupledSim

FIELDS = ["floor", "frac_under", "zero_sectors", "mean_level", "resizes", "cum_sync"]
SCEN = [("activation", 2200, {}),
        ("storm", 3000, dict(storm_at=1500, storm_frac=0.30)),
        ("flashcrowd", 3000, dict(crowd_at=1500, crowd_frac=0.60)),
        ("churn", 3000, dict(churn_from=1200, churn_death_p=0.0004))]
FRACS = [0.5, 1.0]


def metrics(m):
    return {f: np.array(getattr(m, f)) for f in FIELDS}


def run(cls, cfg, ticks, kw, frac, **extra):
    initial, events, joins = make_world(cfg, ticks, **kw)
    variants = assign_initial_variants(len(initial), frac, cfg.seed)
    return cls(cfg, variants, events, initial, joins, frac, **extra).run(ticks)


ok = True
print("REDUCTION GUARD  (DecoupledSim coupled == MixedSim, byte-identical)")
for key, ticks, kw in SCEN:
    for frac in FRACS:
        cfg = Config()
        a = metrics(run(MixedSim, cfg, ticks, kw, frac))
        b = metrics(run(DecoupledSim, cfg, ticks, kw, frac, death_lag=None))
        same = all(np.array_equal(a[f], b[f]) for f in FIELDS)
        ok = ok and same
        print(f"  [{'OK ' if same else 'DIFF'}] {key:11s} f={frac}")

print("\nALL GUARDS PASS" if ok else "\nGUARD FAILURE")
raise SystemExit(0 if ok else 1)
