"""Full storm sweep WITH the storm brake (BrakeMixedSim), to confirm the brake
closes the two §6.1 intent-death races without introducing any new loss.

Storm only (the other scenarios had zero above-baseline loss and no mass-death
for the brake to act on). 312 seeds × 13 fractions, detect_latency=4 (fast
death detection — below the minimum gossip lag of 8 — representing the port's
separate, faster unresponsive-marking clock). Resumable; deterministic.

Compare against results/rolling_upgrade_summary.md (storm, no brake): 11 losses
above baseline (9 pure-death + 2 §6.1-race). Expectation with the brake: the 2
races close, the 9 pure-death losses remain (unpreventable by any local rule).
"""

import argparse
import json
import os
from multiprocessing import Pool

import numpy as np

from polite_shrink import Config, make_world
from rolling_upgrade_sim import assign_initial_variants
from brake_sim import BrakeMixedSim

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
CELLS = os.path.join(RESULTS_DIR, "rolling_upgrade_brake_storm_cells.jsonl")
KW = dict(storm_at=1500, storm_frac=0.30)
TICKS = 3000
FRACTIONS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99, 1.0]
SEED_BASE = 100000
DETECT_LATENCY = 4


def run_cell(args):
    seed, frac = args
    cfg = Config(seed=seed)
    initial, events, joins = make_world(cfg, TICKS, **KW)
    variants = assign_initial_variants(len(initial), frac, cfg.seed)
    sim = BrakeMixedSim(cfg, variants, events, initial, joins, frac,
                        detect_latency=DETECT_LATENCY)
    m = sim.run(TICKS)
    zero = np.array(m.zero_sectors)
    return {"scenario": "storm_brake", "seed": seed, "fraction": frac,
            "detect_latency": DETECT_LATENCY,
            "any_loss": bool((zero > 0).any()),
            "loss_sector_ticks": int(zero.sum()),
            "min_floor": int(min(m.floor)),
            "brake_fires": int(sim.brake_fires)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=312)
    args = ap.parse_args()
    seeds = [SEED_BASE + i for i in range(args.seeds)]
    work = [(s, f) for s in seeds for f in FRACTIONS]
    os.makedirs(RESULTS_DIR, exist_ok=True)

    rows, done = [], set()
    if os.path.exists(CELLS):
        for line in open(CELLS):
            line = line.strip()
            if line:
                r = json.loads(line)
                k = (r["seed"], r["fraction"])
                if k not in done:
                    done.add(k); rows.append(r)
    todo = [w for w in work if w not in done]
    print(f"brake storm sweep: {args.seeds} seeds × {len(FRACTIONS)} fractions "
          f"= {len(work)} sims ({len(done)} done, {len(todo)} to run), "
          f"detect_latency={DETECT_LATENCY}", flush=True)

    with open(CELLS, "a") as fh:
        with Pool(processes=min(os.cpu_count(), 8)) as pool:
            for i, row in enumerate(pool.imap_unordered(run_cell, todo), 1):
                fh.write(json.dumps(row) + "\n"); fh.flush(); rows.append(row)
                if i % 100 == 0 or i == len(todo):
                    print(f"  {i}/{len(todo)} done", flush=True)
    summarise(rows)


def summarise(rows):
    lines = ["# Storm sweep WITH storm brake (detect_latency=4) — loss vs upgraded fraction\n",
             f"Seeds: {len({r['seed'] for r in rows})}. Compare to storm (no brake) "
             "in rolling_upgrade_summary.md.\n",
             "| upgraded f | runs w/ loss | loss rate | mean loss(sector-ticks) | "
             "worst floor | mean brake fires |", "|---|---|---|---|---|---|"]
    for f in FRACTIONS:
        cells = [r for r in rows if r["fraction"] == f]
        n = len(cells); nloss = sum(r["any_loss"] for r in cells)
        lines.append(f"| {f:.2f} | {nloss}/{n} | {100*nloss/n:.1f}% | "
                     f"{np.mean([r['loss_sector_ticks'] for r in cells]):.1f} | "
                     f"{min(r['min_floor'] for r in cells)} | "
                     f"{np.mean([r['brake_fires'] for r in cells]):.1f} |")
    out = os.path.join(RESULTS_DIR, "rolling_upgrade_brake_storm_summary.md")
    with open(out, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines)); print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
