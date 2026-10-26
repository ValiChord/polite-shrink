"""Partitions against V7 (V6 floor + StaleCap ceiling), across seeds.

The same three split scenarios as partition_v6.py, on the same fresh seeds,
for V6 and for V7 (soft ceiling, with the announce-alongside repair) at
R = 5 and R = 6. During a split each side sees only its own announced
growers, as it sees only its own holders and leavers, so a grower cannot
defer its repair to a grower on the other side.

Usage:   python sim/partition_v7.py [--seeds N] [--procs P]
Output:  results/partition_v7_summary.md, results/partition_v7.json
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from multiprocessing import Pool

import numpy as np

from polite_shrink import V6, Config, make_world
from partition_sim import (SCENARIOS, PartitionSim, make_sides, summarize,
                           windows_group_of)
from band_sim import Arm, V7Mixin

BASE_SEED = 500_000   # as partition_v6.py

V7_ARM = Arm("V7 soft", ceiling="soft", alongside=True)
V7U_ARM = Arm("V7 soft+urgent", ceiling="soft", alongside=True, urgent=True)
CASES = [("V6", None, 5), ("V7, R=5", V7_ARM, 5), ("V7, R=6", V7_ARM, 6),
         ("V7+urgent, R=5", V7U_ARM, 5), ("V7+urgent, R=6", V7U_ARM, 6)]


class PartitionV7Sim(V7Mixin, PartitionSim):
    def __init__(self, cfg, arm, ceiling, events, initial, joins, group_of):
        PartitionSim.__init__(self, cfg, V6, events, initial, joins, group_of)
        self._init_v7(arm, ceiling)

    def _gview(self, a):
        """Announced growers on the viewer's own side, as of its view."""
        idx = (self.t - a.lag) % self.H
        g = int(self.groups_h[idx, a.aid])
        if g < 0:
            g = self.group_of(a.aid, self.t)
        return [(aid2, ws, we) for aid2, ws, we in self.glist_h[idx]
                if int(self.groups_h[idx, aid2]) == g]


def one(args):
    key, ticks, windows, frac, seed = args
    rows = []
    for label, arm, R in CASES:
        cfg = replace(Config(), seed=seed, redundancy=R)
        initial, events, joins = make_world(cfg, ticks)
        sides = make_sides(cfg, len(initial), frac)
        group_of = windows_group_of(sides, windows)
        if arm is None:
            sim = PartitionSim(cfg, V6, events, initial, joins, group_of)
        else:
            sim = PartitionV7Sim(cfg, arm, 10**6, events, initial, joins, group_of)
        m = sim.run(ticks)
        widths = np.array([1 << a.level for a in sim.agents if a.alive], float)
        rows.append(summarize(key, label, m, cfg, windows, ticks)
                    | {"seed": seed, "stored": float(widths.sum()),
                       "R": R})
    return rows


def main():
    argv = sys.argv
    seeds = int(argv[argv.index("--seeds") + 1]) if "--seeds" in argv else 48
    procs = int(argv[argv.index("--procs") + 1]) if "--procs" in argv else 3
    jobs = [(key, ticks, windows, frac, BASE_SEED + i)
            for key, _title, ticks, windows, frac in SCENARIOS
            for i in range(seeds)]
    with Pool(procs) as pool:
        rows = [r for batch in pool.imap_unordered(one, jobs) for r in batch]

    lines = ["# Partitions against V7, across seeds", "",
             f"{seeds} fresh seeds per scenario (from {BASE_SEED}, as for V6), 200 agents. "
             "Durability: live copies anywhere. Availability: copies reachable within "
             "each side during the split. stored = total sectors held at the end.", "",
             "| scenario | rule | runs losing data | worst durability floor | "
             "worst availability floor in split | mean unreachable sector-ticks in split | "
             "mean after heal | mean settle after heal | mean stored | mean sync |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for key, *_ in SCENARIOS:
        for label, _a, _r in CASES:
            rs = [r for r in rows if r["scenario"] == key and r["variant"] == label]
            settle = [r["heal_settle"] for r in rs if r["heal_settle"] is not None]
            lines.append(
                f"| {key} | {label} | {sum(r['dur_loss_ticks'] > 0 for r in rs)}/{len(rs)} | "
                f"{min(r['dur_floor_min'] for r in rs)} | "
                f"{min(r['avail_floor_min_split'] for r in rs)} | "
                f"{np.mean([r['avail_zero_ticks_split'] for r in rs]):.0f} | "
                f"{np.mean([r['avail_zero_ticks_postheal'] for r in rs]):.0f} | "
                f"{np.mean(settle):.0f} ({len(rs) - len(settle)} never) | "
                f"{np.mean([r['stored'] for r in rs]):.0f} | "
                f"{np.mean([r['sync_cost'] for r in rs]):.0f} |")
    table = "\n".join(lines) + "\n"
    with open("results/partition_v7_summary.md", "w", encoding="utf-8") as f:
        f.write(table)
    with open("results/partition_v7.json", "w") as f:
        json.dump(rows, f)
    print(table)


if __name__ == "__main__":
    main()
