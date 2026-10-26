"""How fast does each rule shard down from full arcs?

V6's YIELD rule (no announcing while a lower id races you for an overlapping
range) makes nodes that share a range shrink one at a time. From full arcs,
every node's first shrink drops one of the same two halves, so on some worlds
V6 takes far longer than V3 to settle (seed 600000: 65 nodes still full-arc
at tick 2200). This measures it on fresh seeds, with a longer horizon, for:

  V3          the original tie-break
  V6          patient lowest
  V6+multiwait             V6, with several racers allowed to wait at the
                           re-check (each that would pass counting only
                           itself and lower-id racers)
  V6+multiwait+alongside   ... and a node may also announce alongside
                           lower-id racers when, counting itself and all of
                           them as gone, its half keeps >= R

Usage:  python sim/activation_speed.py [--seeds N] [--procs P] [--ticks T]
Output: results/activation_speed.md, results/activation_speed.json
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from multiprocessing import Pool

import numpy as np

from polite_shrink import VARIANTS, Config, Sim, make_world
from band_sim import Arm, BandSim
from run_experiments import settle_tick

RULES = ["V3", "V6", "V6+multiwait", "V6+multiwait+alongside"]


def build(name, cfg, ev, init, jo):
    if name == "V3":
        return Sim(cfg, VARIANTS[3], ev, init, jo)
    arm = {"V6": Arm("V6"),
           "V6+multiwait": Arm(name, multiwait=True),
           "V6+multiwait+alongside": Arm(name, multiwait=True, alongside=True)}[name]
    return BandSim(cfg, arm, 10**6, ev, init, jo)


def first_tick(series, pred):
    for t, x in enumerate(series):
        if pred(x):
            return t
    return None


def one(job):
    seed, T = job
    cfg = replace(Config(), seed=seed)
    init, ev, jo = make_world(cfg, T)
    out = []
    for name in RULES:
        sim = build(name, cfg, ev, init, jo)
        m = sim.run(T)
        cov = sim.cov_h[(sim.t - 1) % sim.H]
        st = settle_tick(m.resizes, 0)
        out.append({
            "seed": seed, "rule": name,
            "settle": st,
            "mean_level_10": first_tick(m.mean_level, lambda x: x <= 3.0),
            "final_mean_copies": float(cov.mean()),
            "min_floor": int(min(m.floor)),
            "full_arc_left": sum(1 for a in sim.agents
                                 if a.alive and a.level == cfg.log2s),
            "sync_cost": int(m.cum_sync[-1]),
            "resizes": int(np.sum(m.resizes)),
            "loss": int(np.sum(m.zero_sectors)),
        })
    return out


def main():
    argv = sys.argv
    seeds = int(argv[argv.index("--seeds") + 1]) if "--seeds" in argv else 24
    procs = int(argv[argv.index("--procs") + 1]) if "--procs" in argv else 3
    T = int(argv[argv.index("--ticks") + 1]) if "--ticks" in argv else 6000
    jobs = [(600_000 + i, T) for i in range(seeds)]
    with Pool(procs) as pool:
        rows = [r for b in pool.imap_unordered(one, jobs) for r in b]
    lines = ["# Sharding down from full arcs: speed by rule", "",
             f"{seeds} fresh seeds (from 600000), 200 agents, R = 5, {T} ticks. "
             "settle = first tick after which the resize rate stays below 1/tick "
             "for 300 ticks; level<=3 = first tick the mean arc level is 3 or less.", "",
             "| rule | runs losing data | lowest floor | median settle | worst settle | "
             "never settled | median ticks to level<=3 | worst | median final copies | "
             "worst final copies | runs with full-arc nodes left |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for name in RULES:
        rs = [r for r in rows if r["rule"] == name]
        st = [r["settle"] for r in rs if r["settle"] is not None]
        lv = [r["mean_level_10"] for r in rs if r["mean_level_10"] is not None]
        lines.append(
            f"| {name} | {sum(r['loss'] > 0 for r in rs)}/{len(rs)} | "
            f"{min(r['min_floor'] for r in rs)} | "
            f"{int(np.median(st)) if st else '-'} | {max(st) if st else '-'} | "
            f"{len(rs) - len(st)}/{len(rs)} | "
            f"{int(np.median(lv)) if lv else '-'} | "
            f"{max(lv) if lv else '-'} ({len(rs) - len(lv)} never) | "
            f"{np.median([r['final_mean_copies'] for r in rs]):.1f} | "
            f"{max(r['final_mean_copies'] for r in rs):.1f} | "
            f"{sum(r['full_arc_left'] > 0 for r in rs)}/{len(rs)} |")
    table = "\n".join(lines) + "\n"
    with open("results/activation_speed.md", "w", encoding="utf-8") as f:
        f.write(table)
    with open("results/activation_speed.json", "w") as f:
        json.dump(rows, f)
    print(table)


if __name__ == "__main__":
    main()
