"""V7 against V6 at comparable storage.

In the first V7 study (band_sim.py) V7 settled at about 5.6 copies per sector
against V6's 12-29: V6's extra copies are over-storage V7 removes. Every V7
data loss there began at the storm tick itself (the 30% die-off took every
holder of a sector at once), which is a matter of how many copies are kept,
not of the rule. This compares V6 at R = 5 with V7 (soft ceiling) at R = 5..9,
so the rules can be compared at matching storage.

Usage:  python sim/v7_equal_storage.py [--seeds N] [--procs P]
Output: results/v7_equal_storage.md, results/v7_equal_storage.json
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from multiprocessing import Pool

import numpy as np

from polite_shrink import Config, make_world
from band_sim import Arm, BandSim
from run_experiments import SCENARIOS

CASES = [("V6", Arm("V6"), 5)] + [
    (f"V7 soft, R={r}", Arm("V7 soft", ceiling="soft", alongside=True), r)
    for r in (5, 6, 7, 8, 9)] + [
    (f"V7+urgent, R={r}", Arm("V7 soft+urgent", ceiling="soft", alongside=True,
                              urgent=True), r)
    for r in (5, 6, 7)]
SCEN = [s for s in SCENARIOS if s[0] in ("storm", "churn")]


def one(job):
    key, ticks, t_dist, kw, seed = job
    out = []
    for label, arm, R in CASES:
        cfg = replace(Config(), seed=seed, redundancy=R)
        init, ev, jo = make_world(cfg, ticks, **kw)
        sim = BandSim(cfg, arm, 10**6, ev, init, jo)
        m = sim.run(ticks)
        cov = sim.cov_h[(sim.t - 1) % sim.H]
        widths = np.array([1 << a.level for a in sim.agents if a.alive], float)
        out.append({
            "scenario": key, "seed": seed, "case": label, "R": R,
            "loss": int(np.sum(m.zero_sectors[t_dist:])),
            "loss_after_storm_tick": int(np.sum(m.zero_sectors[t_dist + 1:]))
            if key == "storm" else None,
            "stored": float(widths.sum()),
            "sync_cost": int(m.cum_sync[-1]),
            "resizes": int(np.sum(m.resizes)),
            "floor_min": int(np.min(m.floor[t_dist:])),
            "final_mean_copies": float(cov.mean()),
            "top_decile": float(np.sort(widths)[-max(1, len(widths) // 10):].sum()
                                / widths.sum()),
        })
    return out


def main():
    argv = sys.argv
    seeds = int(argv[argv.index("--seeds") + 1]) if "--seeds" in argv else 24
    procs = int(argv[argv.index("--procs") + 1]) if "--procs" in argv else 3
    jobs = [(k, t, td, kw, 600_000 + i) for k, _t, t, td, kw in SCEN
            for i in range(seeds)]
    with Pool(procs) as pool:
        rows = [r for b in pool.imap_unordered(one, jobs) for r in b]
    lines = ["# V7 against V6 at comparable storage", "",
             f"{seeds} seeds (from 600000), 200 agents. stored = total sectors held "
             "at the end (all nodes); copies = mean copies per sector at the end.", "",
             "| scenario | rule | runs losing data | worst floor | mean copies at end | "
             "mean stored | mean sync | mean resizes | top decile |",
             "|---|---|---|---|---|---|---|---|---|"]
    for key, *_ in SCEN:
        for label, _a, _r in CASES:
            rs = [r for r in rows if r["scenario"] == key and r["case"] == label]
            lines.append(
                f"| {key} | {label} | {sum(r['loss'] > 0 for r in rs)}/{len(rs)} | "
                f"{min(r['floor_min'] for r in rs)} | "
                f"{np.mean([r['final_mean_copies'] for r in rs]):.1f} | "
                f"{np.mean([r['stored'] for r in rs]):.0f} | "
                f"{np.mean([r['sync_cost'] for r in rs]):.0f} | "
                f"{np.mean([r['resizes'] for r in rs]):.0f} | "
                f"{np.mean([r['top_decile'] for r in rs]):.1%} |")
    table = "\n".join(lines) + "\n"
    with open("results/v7_equal_storage.md", "w", encoding="utf-8") as f:
        f.write(table)
    with open("results/v7_equal_storage.json", "w") as f:
        json.dump(rows, f)
    print(table)


if __name__ == "__main__":
    main()
