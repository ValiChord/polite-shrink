"""
validate_detector_error — reduction guard for `detector_error_sim.py`.

Asserts that `DetectorErrorSim(false_convict_p=0)` is **byte-identical** to
`DecoupledSim` on every metric series, across scenarios and both clock modes.
This is the repo's standard defence against a modelling bug in an extension
(cf. validate_decoupled.py, validate_message_loss.py, validate_rolling_upgrade.py).

Also checks the obvious monotonicity that the model must satisfy to mean
anything: with p > 0 a viewer's coverage is never *higher* than it would have
been, because false conviction only ever removes claimants.

Usage:  python3 validate_detector_error.py
"""

from __future__ import annotations

import sys

import numpy as np

from polite_shrink import Config, make_world
from rolling_upgrade_sim import assign_initial_variants
from decoupled_sim import DecoupledSim
from detector_error_sim import DetectorErrorSim

SERIES = ["floor", "frac_under", "zero_sectors", "mean_level",
          "resizes", "cum_sync", "held_floor", "held_zero"]

SCENARIOS = {
    "activation": dict(),
    "storm": dict(storm_at=1500, storm_frac=0.30),
    "churn": dict(churn_from=1200, churn_death_p=0.002),
}
TICKS = 3000


def build(seed, kw, frac=1.0):
    cfg = Config(seed=seed)
    initial, events, joins = make_world(cfg, TICKS, **kw)
    variants = assign_initial_variants(len(initial), frac, cfg.seed)
    return cfg, variants, events, initial, joins


def main() -> int:
    failures = []
    for name, kw in SCENARIOS.items():
        for death_lag in (None, 24):
            cfg, variants, events, initial, joins = build(900000, kw)
            a = DecoupledSim(cfg, variants, events, initial, joins, 1.0,
                             death_lag=death_lag).run(TICKS)
            cfg, variants, events, initial, joins = build(900000, kw)
            sim = DetectorErrorSim(cfg, variants, events, initial, joins, 1.0,
                                   death_lag=death_lag, false_convict_p=0.0)
            b = sim.run(TICKS)
            for s in SERIES:
                if not np.array_equal(np.array(getattr(a, s)),
                                      np.array(getattr(b, s))):
                    failures.append(f"{name}/death_lag={death_lag}: {s} differs")
            if sim.false_convictions:
                failures.append(f"{name}: convictions drawn at p=0")
            tag = "coupled" if death_lag is None else f"death_lag={death_lag}"
            print(f"  {name:11} {tag:15} reduction OK", flush=True)

    # Monotonicity: p > 0 must never raise a viewer's coverage.
    cfg, variants, events, initial, joins = build(900000, SCENARIOS["storm"])
    base = DecoupledSim(cfg, variants, events, initial, joins, 1.0, death_lag=24)
    cfg2, v2, e2, i2, j2 = build(900000, SCENARIOS["storm"])
    fc = DetectorErrorSim(cfg2, v2, e2, i2, j2, 1.0, death_lag=24,
                          false_convict_p=0.10)
    for _ in range(400):
        base.step(); fc.step()
    probe = fc.agents[0]
    cov_fc, _, _, _ = fc._view(probe)
    cov_base, _, _, _ = base._view(base.agents[0])
    if (cov_fc.astype(int) > cov_base.astype(int)).any():
        failures.append("monotonicity: false conviction raised coverage")
    else:
        print("  monotonicity  p=0.10           coverage never raised OK",
              flush=True)
    if (cov_fc.astype(int) < 0).any():
        failures.append("coverage went negative")

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  -", f)
        return 1
    print("\nAll reduction and monotonicity checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
