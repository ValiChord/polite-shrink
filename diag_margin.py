"""Connecting mechanism for the storm caveat: does the free-riding naive
majority strip the network's over-provisioning margin?

Floor (min coverage) is held at R by the polite backbone at every adoption
level (shown by the sweep). But resilience to *correlated mass death* depends
on the MARGIN above R — how many redundant holders each sector has beyond the
minimum. If naive agents shrinking to level 0 remove that margin, a low-
adoption network sits closer to the R floor and a 30% die-off is more likely
to wipe a sector's entire holder set.

We measure, at the pre-storm equilibrium (t=1499, averaged over seeds), the
mean and 5th-percentile per-sector coverage as a function of upgraded fraction.
"""

import numpy as np

from polite_shrink import Config, make_world
from rolling_upgrade_sim import MixedSim, assign_initial_variants

SEED_BASE = 100000
FRACS = [0.10, 0.20, 0.50, 0.90, 1.00]
NSEED = 15
KW = dict(storm_at=1500, storm_frac=0.30)

print("Pre-storm equilibrium coverage vs upgraded fraction (mean over "
      f"{NSEED} seeds, measured at t=1499, R=5)")
print("| upgraded f | mean coverage | 5th-pct coverage | floor | "
      "sectors at exactly R | mean margin above R |")
print("|---|---|---|---|---|---|")
for f in FRACS:
    means, p5s, floors, atR, margins = [], [], [], [], []
    for seed in range(SEED_BASE, SEED_BASE + NSEED):
        cfg = Config(seed=seed)
        initial, events, joins = make_world(cfg, 3000, **KW)
        variants = assign_initial_variants(len(initial), f, cfg.seed)
        sim = MixedSim(cfg, variants, events, initial, joins, f)
        for _ in range(1500):          # run up to just before the storm tick
            sim.step()
        cov = np.array(sim.cov_h[(1500 - 1) % sim.H])   # declared coverage t=1499
        means.append(cov.mean())
        p5s.append(np.percentile(cov, 5))
        floors.append(int(cov.min()))
        atR.append(int((cov == cfg.redundancy).sum()))
        margins.append(cov.mean() - cfg.redundancy)
    print(f"| {f:.2f} | {np.mean(means):.1f} | {np.mean(p5s):.1f} | "
          f"{min(floors)} | {np.mean(atR):.0f} | {np.mean(margins):.1f} |")
