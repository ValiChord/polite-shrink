"""
Multi-seed robustness sweep. Runs every controller variant on every scenario
across many independent world-realisations (seeds), to turn point estimates
into loss-rate confidence bounds.

Each (scenario, seed) builds ONE world and runs all four variants on it (paired
comparison). Total sims = scenarios * seeds * variants.

Usage:   python3 sweep.py --seeds 312         # ~5000 sims
         python3 sweep.py --seeds 8            # quick timing
Output:  results/sweep.json, results/sweep_summary.md
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import time

import numpy as np

from arc_sim import VARIANTS, Config, Sim, make_world

CELLS_FILE = "results/sweep_cells.jsonl"   # one completed (scenario,seed) per line

# (key, ticks, t_disruption, world_kwargs)
SCENARIOS = [
    ("activation", 2200, 0, {}),
    ("storm", 3000, 1500, dict(storm_at=1500, storm_frac=0.30)),
    ("flashcrowd", 3000, 1500, dict(crowd_at=1500, crowd_frac=0.60)),
    ("churn", 3000, 1200, dict(churn_from=1200, churn_death_p=0.0004)),
]
SEED_BASE = 100000


def run_cell(args):
    """One (scenario, seed): build world once, run all variants, return
    compact per-variant scalars."""
    key, ticks, t_dist, kw, seed = args
    cfg = Config(seed=seed)
    initial, events, joins = make_world(cfg, ticks, **kw)
    out = {}
    for v in VARIANTS:
        m = Sim(cfg, v, events, initial, joins).run(ticks)
        zeros = np.array(m.zero_sectors[t_dist:])
        under = np.array(m.frac_under[t_dist:]) * cfg.sectors
        loss = int(zeros.sum())
        out[v.name] = {
            "loss": loss,
            "any_loss": bool(loss > 0),
            "floor_min": int(np.min(m.floor[t_dist:])),
            "exposure": int(under.sum()),
        }
    return key, seed, out


def rule_of_three(n, failures):
    """95% upper bound on the failure rate. Exact zero-failure case uses the
    rule of three; otherwise a normal-approx upper bound."""
    if n == 0:
        return None
    p = failures / n
    if failures == 0:
        return 3.0 / n
    se = (p * (1 - p) / n) ** 0.5
    return min(1.0, p + 1.96 * se)


def load_cells():
    """Read all completed cells (dedup by (key,seed), last wins)."""
    done = {}
    if os.path.exists(CELLS_FILE):
        with open(CELLS_FILE) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                done[(r["key"], r["seed"])] = r["out"]
    return done


def aggregate_and_write(seeds_target):
    """Aggregate whatever cells have completed into sweep.json + summary.md."""
    done = load_cells()
    agg, pooled = {}, {}
    for (key, _seed), out in done.items():
        for vname, r in out.items():
            agg.setdefault((key, vname), []).append(r)
            pooled.setdefault(vname, []).append(r)

    def stats(rs):
        n = len(rs)
        fails = sum(r["any_loss"] for r in rs)
        expo = np.array([r["exposure"] for r in rs])
        floor = np.array([r["floor_min"] for r in rs])
        return {
            "n": n, "loss_runs": fails,
            "loss_rate": fails / n,
            "loss_rate_upper95": rule_of_three(n, fails),
            "exposure_mean": float(expo.mean()),
            "exposure_p95": float(np.percentile(expo, 95)),
            "floor_min_worst": int(floor.min()),
            "floor_min_mean": float(floor.mean()),
        }

    n_cells = len(done)
    result = {
        "seeds_target": seeds_target,
        "cells_done": n_cells,
        "n_sims": n_cells * len(VARIANTS),
        "per_scenario": {f"{k}|{v}": stats(rs) for (k, v), rs in agg.items()},
        "pooled": {v: stats(rs) for v, rs in pooled.items()},
    }
    with open("results/sweep.json", "w") as f:
        json.dump(result, f, indent=1)

    if not pooled:
        return result
    lines = [f"# Robustness sweep — {n_cells} (scenario,seed) cells, "
             f"{n_cells * len(VARIANTS)} simulations\n",
             "## Pooled across all four scenarios\n",
             "| variant | runs | runs with data loss | loss rate | 95% upper bound | "
             "worst floor | mean exposure |",
             "|---|---|---|---|---|---|---|"]
    for v in VARIANTS:
        s = result["pooled"].get(v.name)
        if not s:
            continue
        ub = s["loss_rate_upper95"]
        lines.append(
            f"| {v.name} | {s['n']} | {s['loss_runs']} | {s['loss_rate']*100:.2f}% | "
            f"< {ub*100:.2f}% | {s['floor_min_worst']} | {s['exposure_mean']:.0f} |")
    lines.append("\n## Per scenario (runs with data loss / runs)\n")
    lines.append("| scenario | " + " | ".join(v.name for v in VARIANTS) + " |")
    lines.append("|---|" + "|".join("---" for _ in VARIANTS) + "|")
    for key, *_ in SCENARIOS:
        cells = []
        for v in VARIANTS:
            s = result["per_scenario"].get(f"{key}|{v.name}")
            cells.append(f"{s['loss_runs']}/{s['n']}" if s else "-")
        lines.append(f"| {key} | " + " | ".join(cells) + " |")
    with open("results/sweep_summary.md", "w") as f:
        f.write("\n".join(lines) + "\n")
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=312)
    ap.add_argument("--procs", type=int, default=mp.cpu_count())
    args = ap.parse_args()

    all_tasks = [(key, ticks, t_dist, kw, SEED_BASE + s)
                 for (key, ticks, t_dist, kw) in SCENARIOS
                 for s in range(args.seeds)]
    done = load_cells()
    tasks = [t for t in all_tasks if (t[0], t[4]) not in done]
    print(f"target {len(all_tasks)} cells; {len(done)} already done; "
          f"{len(tasks)} to run on {args.procs} procs "
          f"({len(tasks) * len(VARIANTS)} sims)", flush=True)

    t0 = time.time()
    written = 0
    with open(CELLS_FILE, "a") as cf, mp.Pool(args.procs) as pool:
        for i, (key, seed, out) in enumerate(
                pool.imap_unordered(run_cell, tasks, chunksize=2)):
            cf.write(json.dumps({"key": key, "seed": seed, "out": out}) + "\n")
            written += 1
            if written % 20 == 0:
                cf.flush(); os.fsync(cf.fileno())     # kill-proof checkpoint
            if (i + 1) % 50 == 0 or i + 1 == len(tasks):
                el = time.time() - t0
                proj = el / (i + 1) * len(tasks)
                print(f"  {i+1}/{len(tasks)} cells  {el:5.0f}s  "
                      f"(~{proj:.0f}s total)  checkpoint={written}", flush=True)
                aggregate_and_write(args.seeds)       # periodic snapshot
    aggregate_and_write(args.seeds)
    print(f"done. {time.time()-t0:.0f}s. "
          f"aggregated {len(load_cells())} cells -> results/sweep.json", flush=True)


if __name__ == "__main__":
    main()
