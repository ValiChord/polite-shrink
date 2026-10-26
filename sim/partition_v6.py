"""Partitions against V6, across seeds.

The Stage-3 partition study (partition_sim.py) ran V1-V3 (and later V5) on
one seed; V6, the recommended rule, came later and was never put through it.
This runs the same three scenarios (50/50 split, 90/10 split with the small
side below the clamp, flapping splits) for V3, V5 and V6 on many seeds, and
records durability (live copies anywhere) and availability (copies reachable
within each side).

Usage:   python sim/partition_v6.py [--seeds N] [--procs P]
Output:  results/partition_v6_summary.md, results/partition_v6.json
         (the published partition_* files are left untouched)
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from multiprocessing import Pool

import numpy as np

from polite_shrink import VARIANTS, V6, Config
from partition_sim import SCENARIOS, run_scenario, summarize

V3 = next(v for v in VARIANTS if v.name.startswith("V3"))
V5 = next(v for v in VARIANTS if v.name.startswith("V5"))
RULES = [V3, V5, V6]
BASE_SEED = 500_000   # fresh seeds, disjoint from the published study (42)


def one(args):
    key, ticks, windows, frac, seed = args
    cfg = replace(Config(), seed=seed)
    results, _ = run_scenario(key, ticks, windows, frac, cfg, RULES)
    return [summarize(key, name, m, cfg, windows, ticks) | {"seed": seed}
            for name, m in results.items()]


def main():
    argv = sys.argv
    seeds = int(argv[argv.index("--seeds") + 1]) if "--seeds" in argv else 24
    procs = int(argv[argv.index("--procs") + 1]) if "--procs" in argv else 3
    jobs = [(key, ticks, windows, frac, BASE_SEED + i)
            for key, _title, ticks, windows, frac in SCENARIOS
            for i in range(seeds)]
    with Pool(procs) as pool:
        rows = [r for batch in pool.imap_unordered(one, jobs) for r in batch]

    lines = ["# Partitions against V6, across seeds", "",
             f"{seeds} fresh seeds per scenario (from {BASE_SEED}), 200 agents, R = 5. "
             "Durability: live copies anywhere (held = bytes on disk). "
             "Availability: copies reachable within each side during the split.", "",
             "| scenario | rule | runs losing data (declared) | runs losing data (held) | "
             "worst durability floor | worst availability floor in split | "
             "mean unreachable sector-ticks in split | mean after heal | "
             "mean ticks to settle after heal |",
             "|---|---|---|---|---|---|---|---|---|"]
    for key, *_ in SCENARIOS:
        for v in RULES:
            rs = [r for r in rows if r["scenario"] == key and r["variant"] == v.name]
            if not rs:
                continue
            lost = sum(r["dur_loss_ticks"] > 0 for r in rs)
            lost_h = sum(r["dur_loss_ticks_held"] > 0 for r in rs)
            settle = [r["heal_settle"] for r in rs if r["heal_settle"] is not None]
            lines.append(
                f"| {key} | {v.name} | {lost}/{len(rs)} | {lost_h}/{len(rs)} | "
                f"{min(r['dur_floor_min'] for r in rs)} | "
                f"{min(r['avail_floor_min_split'] for r in rs)} | "
                f"{np.mean([r['avail_zero_ticks_split'] for r in rs]):.0f} | "
                f"{np.mean([r['avail_zero_ticks_postheal'] for r in rs]):.0f} | "
                f"{np.mean(settle):.0f} ({len(rs) - len(settle)} never) |")
    table = "\n".join(lines) + "\n"
    with open("results/partition_v6_summary.md", "w", encoding="utf-8") as f:
        f.write(table)
    with open("results/partition_v6.json", "w") as f:
        json.dump(rows, f)
    print(table)


if __name__ == "__main__":
    main()
