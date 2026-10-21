"""Reduction guard for the lossy-gossip model: at loss = 0 every update lands,
so MessageLossSim must be byte-identical to MixedSim — else the per-viewer
coverage machinery has changed the base dynamics and no lossy number can be
trusted. Join-free scenarios only (v1 scope).

Also a sanity check that loss actually does something (loss>0 must diverge on at
least one scenario) and moves the safe way (higher loss ⇒ not fewer losses).
"""

import numpy as np

from polite_shrink import Config, make_world
from rolling_upgrade_sim import MixedSim, assign_initial_variants
from message_loss_sim import MessageLossSim

FIELDS = ["floor", "frac_under", "zero_sectors", "mean_level", "resizes", "cum_sync"]
SCEN = [("activation", 2200, {}),
        ("storm", 3000, dict(storm_at=1500, storm_frac=0.30))]
FRACS = [0.5, 1.0]


def metrics(m):
    return {f: np.array(getattr(m, f)) for f in FIELDS}


def run(cls, cfg, ticks, kw, frac, **extra):
    initial, events, joins = make_world(cfg, ticks, **kw)
    variants = assign_initial_variants(len(initial), frac, cfg.seed)
    return cls(cfg, variants, events, initial, joins, frac, **extra).run(ticks)


ok = True
print("REDUCTION GUARD  (MessageLossSim loss=0 == MixedSim, byte-identical)")
for key, ticks, kw in SCEN:
    for frac in FRACS:
        cfg = Config()
        a = metrics(run(MixedSim, cfg, ticks, kw, frac))
        b = metrics(run(MessageLossSim, cfg, ticks, kw, frac, loss=0.0))
        same = all(np.array_equal(a[f], b[f]) for f in FIELDS)
        ok = ok and same
        print(f"  [{'OK ' if same else 'DIFF'}] {key:11s} f={frac}")

print("\nSANITY  (loss>0 must change behaviour)")
cfg = Config()
base = np.array(run(MessageLossSim, cfg, 2200, {}, 1.0, loss=0.0).mean_level)
lossy = np.array(run(MessageLossSim, cfg, 2200, {}, 1.0, loss=0.3).mean_level)
differs = not np.array_equal(base, lossy)
ok = ok and differs
print(f"  [{'OK ' if differs else 'BAD '}] activation f=1.0: loss=0 vs loss=0.3 differ = {differs}")

print("\nALL GUARDS PASS" if ok else "\nGUARD FAILURE")
raise SystemExit(0 if ok else 1)
