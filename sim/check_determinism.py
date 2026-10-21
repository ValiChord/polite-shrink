"""Reproducibility guard: every scenario must produce byte-identical metric
arrays across independent runs, or the 'run ours and get our numbers' claim
is false. Run in CI / before any handoff."""

import numpy as np

from polite_shrink import VARIANTS, Config, Sim, make_world

SCEN = [("activation", 2200, {}),
        ("storm", 3000, dict(storm_at=1500, storm_frac=0.30)),
        ("flashcrowd", 3000, dict(crowd_at=1500, crowd_frac=0.60)),
        ("churn", 3000, dict(churn_from=1200, churn_death_p=0.0004))]

FIELDS = ["floor", "frac_under", "zero_sectors", "mean_level", "resizes", "cum_sync"]


def run_once(key, ticks, kw, variant):
    cfg = Config()
    initial, events, joins = make_world(cfg, ticks, **kw)
    m = Sim(cfg, variant, events, initial, joins).run(ticks)
    return {f: np.array(getattr(m, f)) for f in FIELDS}


ok = True
for key, ticks, kw in SCEN:
    for v in VARIANTS:
        a = run_once(key, ticks, kw, v)
        b = run_once(key, ticks, kw, v)
        same = all(np.array_equal(a[f], b[f]) for f in FIELDS)
        flag = "OK " if same else "DIFF"
        if not same:
            ok = False
        print(f"  [{flag}] {key:11s} {v.name}")

print("\nALL DETERMINISTIC" if ok else "\nNON-DETERMINISM DETECTED")
raise SystemExit(0 if ok else 1)
