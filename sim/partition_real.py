"""Splits with realistic growth, and pinned nodes.

The split studies (partition_sim.py, partition_v6.py, partition_v7.py) let a
growing node "sync" its new range after a fixed time, whether or not any copy
of that range was reachable on its side of the split. In reality a node cut off
from the rest can fetch only what its own side holds, and a range with no copy
anywhere is gone. Here a grow completes only once every sector it adds has a
live holder on the grower's current side; until then it keeps waiting.

Second, pinned nodes: a node may choose to keep everything (a server, an
office's main machine). A pinned node starts full and never shrinks. The
question is whether a small group that pins one of its own machines keeps
access to everything during a split, and what pinning costs everyone else.

Cases: V6 and V7 (soft ceiling, alongside, critical repair) at R = 6 and 8,
each with no pinned node and with one pinned node in the smaller group.

Usage:   python sim/partition_real.py [--seeds N] [--procs P]
Output:  results/partition_real_summary.md, results/partition_real.json
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from multiprocessing import Pool

import numpy as np

from polite_shrink import V6, Config, block, make_world
from partition_sim import (SCENARIOS, PartitionSim, make_sides, summarize,
                           windows_group_of)
from partition_v7 import PartitionV7Sim, V7C_ARM

BASE_SEED = 500_000


class RealisticMixin:
    """Growth needs a reachable source; pinned nodes never shrink."""

    def _init_real(self, pinned):
        self.pinned = set(pinned)
        self.grows_held_back = 0

    def _reachable(self, a, lo, hi):
        """Does every sector in [lo, hi) have a live holder on a's side now?"""
        g = self.group_of(a.aid, self.t)
        cov = np.zeros(hi - lo, dtype=np.int16)
        for b in self.agents:
            if b.alive and b.aid != a.aid and self.group_of(b.aid, self.t) == g:
                s, e = block(b.home, b.level, self.cfg.log2s)
                s, e = max(s, lo), min(e, hi)
                if s < e:
                    cov[s - lo:e - lo] += 1
        return bool(cov.min() > 0)

    def step(self):
        log2s = self.cfg.log2s
        for a in self.agents:
            if a.alive and 0 <= a.sync_until <= self.t:
                new_s, new_e = block(a.home, a.sync_target, log2s)
                old_s, old_e = block(a.home, a.level, log2s)
                # The sectors this grow adds: the target block minus the old one.
                parts = [(new_s, old_s), (old_e, new_e)]
                if not all(self._reachable(a, lo, hi) for lo, hi in parts if lo < hi):
                    a.sync_until = self.t + 1
                    self.grows_held_back += 1
        super().step()

    def _decide(self, a):
        if a.aid in self.pinned:
            return
        super()._decide(a)


class RealV6(RealisticMixin, PartitionSim):
    def __init__(self, cfg, events, initial, joins, group_of, pinned):
        PartitionSim.__init__(self, cfg, V6, events, initial, joins, group_of)
        self._init_real(pinned)


class RealV7(RealisticMixin, PartitionV7Sim):
    def __init__(self, cfg, events, initial, joins, group_of, pinned):
        PartitionV7Sim.__init__(self, cfg, V7C_ARM, 10**6, events, initial,
                                joins, group_of)
        self._init_real(pinned)


CASES = [("V6", RealV6, 5), ("V7, R=6", RealV7, 6), ("V7, R=8", RealV7, 8)]


def one(args):
    key, ticks, windows, frac, seed = args
    rows = []
    for label, cls, R in CASES:
        for pin in (False, True):
            cfg = replace(Config(), seed=seed, redundancy=R)
            initial, events, joins = make_world(cfg, ticks)
            sides = make_sides(cfg, len(initial), frac)
            group_of = windows_group_of(sides, windows)
            small = [i for i in range(len(initial)) if sides[i] == 1]
            pinned = small[:1] if (pin and small) else []
            sim = cls(cfg, events, initial, joins, group_of, pinned)
            # gaps on the small side at the moment of the split
            sim.run(windows[0][0])
            cov = np.zeros(cfg.sectors, dtype=np.int16)
            for a in sim.agents:
                if a.alive and sides[a.aid] == 1:
                    s, e = block(a.home, a.level, cfg.log2s)
                    cov[s:e] += 1
            gaps = int((cov == 0).sum())
            m = sim.run(ticks - windows[0][0])
            widths = np.array([1 << a.level for a in sim.agents if a.alive], float)
            rows.append(summarize(key, label, m, cfg, windows, ticks)
                        | {"seed": seed, "pinned": pin, "small_gaps": gaps,
                           "stored": float(widths.sum()),
                           "held_back": sim.grows_held_back})
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
    lines = ["# Splits with realistic growth, and pinned nodes", "",
             f"{seeds} seeds per scenario (from {BASE_SEED}), 200 agents. Growth completes "
             "only when every added sector has a live holder on the grower's side. "
             "'pinned' = one node in the smaller group keeps everything. small-side gaps "
             "= sectors with no copy on the smaller side at the moment of the split.", "",
             "| scenario | rule | pinned | runs losing data | mean small-side gaps | "
             "runs with any small-side gap | mean unreachable sector-ticks in split | "
             "mean after heal | mean stored | mean sync |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for key, *_ in SCENARIOS:
        for label, _c, _r in CASES:
            for pin in (False, True):
                rs = [r for r in rows if r["scenario"] == key
                      and r["variant"] == label and r["pinned"] == pin]
                lines.append(
                    f"| {key} | {label} | {'yes' if pin else 'no'} | "
                    f"{sum(r['dur_loss_ticks'] > 0 for r in rs)}/{len(rs)} | "
                    f"{np.mean([r['small_gaps'] for r in rs]):.0f} | "
                    f"{sum(r['small_gaps'] > 0 for r in rs)}/{len(rs)} | "
                    f"{np.mean([r['avail_zero_ticks_split'] for r in rs]):.0f} | "
                    f"{np.mean([r['avail_zero_ticks_postheal'] for r in rs]):.0f} | "
                    f"{np.mean([r['stored'] for r in rs]):.0f} | "
                    f"{np.mean([r['sync_cost'] for r in rs]):.0f} |")
    table = "\n".join(lines) + "\n"
    with open("results/partition_real_summary.md", "w", encoding="utf-8") as f:
        f.write(table)
    with open("results/partition_real.json", "w") as f:
        json.dump(rows, f)
    print(table)


if __name__ == "__main__":
    main()
