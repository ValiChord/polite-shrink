"""Faithfulness guard for the rolling-upgrade fork.

Two things must hold before any mixed-fraction result is trustworthy:

1. REDUCTION. MixedSim must reduce *byte-identically* to the Stage-1 Sim at
   the homogeneous extremes:
       MixedSim(f=0.0) == Sim(V0 naive)
       MixedSim(f=1.0) == Sim(V3 polite shrink)
   on all six metric arrays, in every scenario. If this fails, the fork has
   introduced a modelling difference and no intermediate number can be trusted.

2. FALSIFIABILITY. The all-naive extreme (f=0) must actually LOSE data and the
   all-polite extreme (f=1) must not — otherwise the sweep proves nothing.

Run: python3 validate_rolling_upgrade.py   (exit 0 = all guards pass)
"""

import numpy as np

from polite_shrink import Config, Sim, make_world
from rolling_upgrade_sim import V0, V3, MixedSim, assign_initial_variants

FIELDS = ["floor", "frac_under", "zero_sectors", "mean_level", "resizes", "cum_sync"]

SCEN = [("activation", 2200, {}),
        ("storm", 3000, dict(storm_at=1500, storm_frac=0.30)),
        ("flashcrowd", 3000, dict(crowd_at=1500, crowd_frac=0.60)),
        ("churn", 3000, dict(churn_from=1200, churn_death_p=0.0004))]


def metrics_dict(m):
    return {f: np.array(getattr(m, f)) for f in FIELDS}


def any_loss(m) -> bool:
    """Run-level failure: any tick with a zero-coverage sector (REPORT §2.4)."""
    return bool((np.array(m.zero_sectors) > 0).any())


def pure(cfg, ticks, kw, variant):
    initial, events, joins = make_world(cfg, ticks, **kw)
    return Sim(cfg, variant, events, initial, joins).run(ticks)


def mixed(cfg, ticks, kw, f):
    initial, events, joins = make_world(cfg, ticks, **kw)
    variants = assign_initial_variants(len(initial), f, cfg.seed)
    return MixedSim(cfg, variants, events, initial, joins, f).run(ticks)


ok = True
print("REDUCTION GUARD  (MixedSim extremes must equal pure Sim, byte-identical)")
for key, ticks, kw in SCEN:
    cfg = Config()
    a0 = metrics_dict(mixed(cfg, ticks, kw, 0.0))
    b0 = metrics_dict(pure(cfg, ticks, kw, V0))
    same0 = all(np.array_equal(a0[f], b0[f]) for f in FIELDS)

    a1 = metrics_dict(mixed(cfg, ticks, kw, 1.0))
    b1 = metrics_dict(pure(cfg, ticks, kw, V3))
    same1 = all(np.array_equal(a1[f], b1[f]) for f in FIELDS)

    ok = ok and same0 and same1
    print(f"  [{'OK ' if same0 else 'DIFF'}] {key:11s} f=0.0 == Sim(V0)"
          f"     [{'OK ' if same1 else 'DIFF'}] f=1.0 == Sim(V3)")

print("\nFALSIFIABILITY GUARD  (f=0 must lose data; f=1 must not)")
for key, ticks, kw in SCEN:
    cfg = Config()
    loss0 = any_loss(mixed(cfg, ticks, kw, 0.0))
    loss1 = any_loss(mixed(cfg, ticks, kw, 1.0))
    good = loss0 and not loss1
    ok = ok and good
    print(f"  [{'OK ' if good else 'BAD '}] {key:11s} "
          f"f=0 loses={loss0}  f=1 loses={loss1}")

print("\nALL GUARDS PASS" if ok else "\nGUARD FAILURE")
raise SystemExit(0 if ok else 1)
