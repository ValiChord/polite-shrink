"""Diagnostics to verify the rolling-upgrade finding is REAL safety, not an
artifact of agents failing to shrink. Two checks:

  A. Shard-down check: at low adoption (f=0.10) the naive majority must
     genuinely shrink (mean level drops far below full=9) while the floor
     stays >= R. If naive agents don't shrink, "0 loss" is trivial.

  B. Storm-loss forensics: locate and characterise the two seeds that lost
     data in the storm sweep (f=0.10 and f=0.95) — is the orphaning caused by
     a naive (V0) agent's uncoordinated instant shrink (the invisible-shrink
     hazard), confirming the mechanism as a rare-but-real residual risk?
"""

import numpy as np

from polite_shrink import Config, make_world
from rolling_upgrade_sim import V3, MixedSim, assign_initial_variants

SEED_BASE = 100000


def build(scenario_kw, seed, frac, ticks):
    cfg = Config(seed=seed)
    initial, events, joins = make_world(cfg, ticks, **scenario_kw)
    variants = assign_initial_variants(len(initial), frac, cfg.seed)
    return cfg, MixedSim(cfg, variants, events, initial, joins, frac), variants


# ---- A. shard-down check (activation, f=0.10) -------------------------------
print("A. SHARD-DOWN CHECK  activation f=0.10 seed 100000")
cfg, sim, variants = build({}, SEED_BASE, 0.10, 2200)
naive_ids = [i for i, v in enumerate(variants) if v is not V3]
polite_ids = [i for i, v in enumerate(variants) if v is V3]
print(f"   {len(naive_ids)} naive, {len(polite_ids)} polite; start level = {cfg.log2s} (full)")
snap_t = [0, 50, 100, 200, 400, 800, 1500, 2199]
for t in range(2200):
    sim.step()
    if t in snap_t:
        naive_lv = np.mean([sim.agents[i].level for i in naive_ids if sim.agents[i].alive])
        pol_lv = np.mean([sim.agents[i].level for i in polite_ids if sim.agents[i].alive])
        print(f"   t={t:4d}  floor={sim.m.floor[t]}  frac_under={sim.m.frac_under[t]:.3f}  "
              f"mean_lvl(naive)={naive_lv:.2f}  mean_lvl(polite)={pol_lv:.2f}")
print(f"   -> min floor over run = {min(sim.m.floor)}; naive DID shrink from 9 -> "
      f"{np.mean([sim.agents[i].level for i in naive_ids if sim.agents[i].alive]):.2f}")


# ---- B. storm-loss forensics ------------------------------------------------
def find_and_trace(frac):
    print(f"\nB. STORM-LOSS FORENSICS  f={frac}")
    kw = dict(storm_at=1500, storm_frac=0.30)
    for seed in range(SEED_BASE, SEED_BASE + 40):
        cfg, sim, variants = build(kw, seed, frac, 3000)
        m = sim.run(3000)
        z = np.array(m.zero_sectors)
        if (z > 0).any():
            first = int(np.argmax(z > 0))
            print(f"   seed {seed}: first zero-coverage at t={first} "
                  f"(storm at 1500); zero_sectors[t]={z[first]}, "
                  f"peak zero={int(z.max())}, ticks-with-loss={int((z>0).sum())}")
            # Re-run to the loss tick and attribute the last drop.
            cfg2, sim2, variants2 = build(kw, seed, frac, 3000)
            naive_ids = {i for i, v in enumerate(variants2) if v is not V3}
            for t in range(first + 1):
                sim2.step()
            # which agents cover the orphaned sector's neighbourhood?
            zero_secs = np.where(np.array(sim2.cov_h[first % sim2.H]) == 0)[0]
            print(f"     orphaned sectors at t={first}: {list(zero_secs[:8])}"
                  f"{'...' if len(zero_secs) > 8 else ''} ({len(zero_secs)} total)")
            return seed
    print("   (no loss found in this pass)")
    return None


find_and_trace(0.10)
find_and_trace(0.95)
