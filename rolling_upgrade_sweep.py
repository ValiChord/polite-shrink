"""Rolling-upgrade sweep: run-level data-loss rate vs the fraction of the
network that has been upgraded to the polite-shrink controller (V3); the rest
run the naive controller (V0).

For each (scenario, seed, fraction) it runs one paired mixed world and records
the Stage-1 safety metrics (REPORT §2.4):
  - any_loss            : any tick with a zero-coverage sector (primary)
  - loss_sector_ticks   : Sigma_t zero-coverage sectors
  - under_R_sector_ticks: Sigma_t sectors below R  (graded fragility / exposure)
  - min_floor           : worst per-sector coverage over the run

Deterministic: each unit is a pure function of (scenario, seed, fraction);
Python 3.12.1 / numpy 2.5.1. Parallelised across cores; results written to
results/rolling_upgrade_cells.jsonl (resumable) + a printed summary table.

Usage:  python3 rolling_upgrade_sweep.py [--seeds N] [--quick]
"""

import argparse
import json
import os
import sys
from multiprocessing import Pool

import numpy as np

from polite_shrink import Config, make_world
from rolling_upgrade_sim import assign_initial_variants, MixedSim

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
CELLS = os.path.join(RESULTS_DIR, "rolling_upgrade_cells.jsonl")

SCENARIOS = {
    "activation": (2200, {}),
    "storm":      (3000, dict(storm_at=1500, storm_frac=0.30)),
    "flashcrowd": (3000, dict(crowd_at=1500, crowd_frac=0.60)),
    "churn":      (3000, dict(churn_from=1200, churn_death_p=0.0004)),
}

FRACTIONS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99, 1.0]
SEED_BASE = 100000   # same base as the canonical Stage-1 sweep


def run_cell(args):
    scenario, seed, frac = args
    ticks, kw = SCENARIOS[scenario]
    cfg = Config(seed=seed)
    initial, events, joins = make_world(cfg, ticks, **kw)
    variants = assign_initial_variants(len(initial), frac, cfg.seed)
    m = MixedSim(cfg, variants, events, initial, joins, frac).run(ticks)
    zero = np.array(m.zero_sectors)
    under = np.array(m.frac_under) * cfg.sectors     # sectors below R per tick
    return {
        "scenario": scenario, "seed": seed, "fraction": frac,
        "any_loss": bool((zero > 0).any()),
        "loss_sector_ticks": int(zero.sum()),
        "under_R_sector_ticks": float(under.sum()),
        "min_floor": int(min(m.floor)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=40)
    ap.add_argument("--quick", action="store_true",
                    help="8 seeds, coarse fractions (smoke test)")
    args = ap.parse_args()

    fractions = FRACTIONS
    n_seeds = args.seeds
    if args.quick:
        fractions = [0.0, 0.5, 0.8, 0.9, 1.0]
        n_seeds = 8

    seeds = [SEED_BASE + i for i in range(n_seeds)]
    work = [(sc, s, f) for sc in SCENARIOS for s in seeds for f in fractions]
    os.makedirs(RESULTS_DIR, exist_ok=True)

    # --- resume: load any cells already computed, skip them (checkpointing) ---
    rows = []
    done = set()
    if os.path.exists(CELLS):
        with open(CELLS) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                key = (r["scenario"], r["seed"], r["fraction"])
                if key not in done:
                    done.add(key)
                    rows.append(r)
    todo = [w for w in work if w not in done]

    print(f"rolling-upgrade sweep: {len(SCENARIOS)} scenarios x {n_seeds} seeds "
          f"x {len(fractions)} fractions = {len(work)} sims "
          f"({len(done)} already done, {len(todo)} to run)", flush=True)

    with open(CELLS, "a") as fh:            # append — never clobber prior work
        with Pool(processes=min(os.cpu_count(), 8)) as pool:
            for i, row in enumerate(pool.imap_unordered(run_cell, todo), 1):
                fh.write(json.dumps(row) + "\n")
                fh.flush()
                rows.append(row)
                if i % 100 == 0 or i == len(todo):
                    print(f"  {i}/{len(todo)} done "
                          f"({len(done)+i}/{len(work)} total)", flush=True)

    summarise(rows, fractions, n_seeds)


def summarise(rows, fractions, n_seeds):
    lines = []
    lines.append(f"# Rolling-upgrade sweep — data-loss rate vs upgraded fraction\n")
    lines.append(f"Seeds: {n_seeds} (base {SEED_BASE}).  "
                 f"Controllers: fraction f run V3 polite shrink, the rest V0 naive.  "
                 f"Metric: run-level any_loss (any tick with a zero-coverage sector).\n")
    for sc in SCENARIOS:
        lines.append(f"\n## {sc}\n")
        lines.append("| upgraded f | naive nodes | runs w/ loss | loss rate | "
                     "mean loss(sector-ticks) | mean exposure(<R) | worst floor |")
        lines.append("|---|---|---|---|---|---|---|")
        for f in fractions:
            cells = [r for r in rows if r["scenario"] == sc and r["fraction"] == f]
            n = len(cells)
            nloss = sum(r["any_loss"] for r in cells)
            naive_nodes = 200 - round(200 * f)
            mean_lst = np.mean([r["loss_sector_ticks"] for r in cells])
            mean_exp = np.mean([r["under_R_sector_ticks"] for r in cells])
            worst_floor = min(r["min_floor"] for r in cells)
            lines.append(f"| {f:.2f} | {naive_nodes} | {nloss}/{n} | "
                         f"{100*nloss/n:.1f}% | {mean_lst:.0f} | {mean_exp:.0f} | "
                         f"{worst_floor} |")
    out = os.path.join(RESULTS_DIR, "rolling_upgrade_summary.md")
    with open(out, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nwrote {out}\nwrote {CELLS}")


if __name__ == "__main__":
    main()
