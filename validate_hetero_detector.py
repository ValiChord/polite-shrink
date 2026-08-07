"""
validate_hetero_detector — reduction guard for `hetero_detector_sim.py`.

Asserts that `HeteroDetectorSim` with both classes set identically is
**byte-identical to `DetectorErrorSim`** at that setting, which in turn reduces
to `DecoupledSim` at p=0 (`validate_detector_error.py`). Checked at several
conviction rates, because the p=0 case alone would not exercise the
`_p_for` override at all.

Also checks the class split is what was asked for and is uncorrelated with home
sector — if class membership were confounded with geography, every per-class
result would be unreadable.

Usage:  python3 validate_hetero_detector.py
"""

from __future__ import annotations

import sys

import numpy as np

from polite_shrink import Config, make_world
from rolling_upgrade_sim import assign_initial_variants
from detector_error_sim import DetectorErrorSim
from hetero_detector_sim import HeteroDetectorSim, FAST, SLOW

SERIES = ["floor", "frac_under", "zero_sectors", "mean_level",
          "resizes", "cum_sync", "held_floor", "held_zero"]
TICKS = 3000
KW = dict(storm_at=1500, storm_frac=0.50)


def build(seed=900000):
    cfg = Config(seed=seed)
    initial, events, joins = make_world(cfg, TICKS, **KW)
    variants = assign_initial_variants(len(initial), 1.0, cfg.seed)
    return cfg, variants, events, initial, joins


def main() -> int:
    failures = []

    for dl in (96, 192):
        for p in (0.0, 0.05, 0.20):
            cfg, v, e, i, j = build()
            a = DetectorErrorSim(cfg, v, e, i, j, 1.0,
                                 death_lag=dl, false_convict_p=p).run(TICKS)
            cfg, v, e, i, j = build()
            b = HeteroDetectorSim(cfg, v, e, i, j, 1.0,
                                  dl_fast=dl, dl_slow=dl,
                                  p_fast=p, p_slow=p).run(TICKS)
            bad = [s for s in SERIES
                   if not np.array_equal(np.array(getattr(a, s)),
                                         np.array(getattr(b, s)))]
            if bad:
                failures.append(f"dl={dl} p={p}: {', '.join(bad)} differ")
            else:
                print(f"  homogeneous dl={dl:<4} p={p:<5} reduction OK",
                      flush=True)

    # Class split: right size, and not confounded with home sector.
    cfg, v, e, i, j = build()
    sim = HeteroDetectorSim(cfg, v, e, i, j, 1.0, dl_fast=24, dl_slow=192,
                            p_fast=0.05, p_slow=0.05, frac_slow=0.5)
    n = len(sim.agents)
    n_slow = sum(1 for x in sim.agents if x.det_class == SLOW)
    if n_slow != round(n * 0.5):
        failures.append(f"class split {n_slow}/{n}, expected {round(n*0.5)}")
    else:
        print(f"  class split      {n_slow}/{n} slow as requested       OK",
              flush=True)

    homes = np.array([x.home for x in sim.agents], dtype=float)
    cls = np.array([1.0 if x.det_class == SLOW else 0.0 for x in sim.agents])
    r = float(np.corrcoef(homes, cls)[0, 1])
    if abs(r) > 0.15:
        failures.append(f"class correlates with home sector (r={r:+.3f})")
    else:
        print(f"  class vs home    r={r:+.3f} (uncorrelated)            OK",
              flush=True)

    # Per-agent latency actually differs when asked.
    lags = {c: {x.death_lag for x in sim.agents if x.det_class == c}
            for c in (FAST, SLOW)}
    if lags[FAST] != {24} or lags[SLOW] != {192}:
        failures.append(f"per-agent death_lag wrong: {lags}")
    else:
        print("  per-agent latency fast=24, slow=192                    OK",
              flush=True)

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  -", f)
        return 1
    print("\nAll reduction and assignment checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
