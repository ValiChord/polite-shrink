"""Quantify the §6.1 intent-death race as a function of death-detection latency
— the number REPORT_stage3.md §5 leaves open (its 0.002% is a *coupled*-clock
figure; the decoupled death-clock was "unquantified, bounded by the storm brake").

Storm scenario, sweep uniform death_lag (fast → slow detection) × upgraded
fraction f × seeds. Gossip/view lag stays [8,24]. For each run we record
any_loss and the first-orphan tick, which classifies the loss:
    first_orphan == 1500  -> pure correlated mass death (detection-independent)
    first_orphan  > 1500  -> §6.1 shrink-race (a shrink executed on a view that
                             still counted not-yet-detected deaths)
The race count vs death_lag is the result. death_lag = 'coupled' reproduces the
base single-clock model (each agent's death clock = its own gossip lag).

Resumable; deterministic. Python 3.12.1, numpy 2.5.1.
"""

import argparse
import json
import os
from multiprocessing import Pool

import numpy as np

from polite_shrink import Config, make_world
from rolling_upgrade_sim import assign_initial_variants
from decoupled_sim import DecoupledSim

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
CELLS = os.path.join(RESULTS_DIR, "decoupled_cells.jsonl")
KW = dict(storm_at=1500, storm_frac=0.30)
TICKS = 3000
FRACTIONS = [0.1, 0.3, 0.5, 1.0]
DEATH_LAGS = ["coupled", 4, 8, 12, 16, 24, 32, 48, 64]
SEED_BASE = 100000


def run_cell(args):
    dl, frac, seed = args
    cfg = Config(seed=seed)
    initial, events, joins = make_world(cfg, TICKS, **KW)
    variants = assign_initial_variants(len(initial), frac, cfg.seed)
    death_lag = None if dl == "coupled" else int(dl)
    m = DecoupledSim(cfg, variants, events, initial, joins, frac,
                     death_lag=death_lag).run(TICKS)
    z = np.array(m.zero_sectors)
    loss = bool((z > 0).any())
    first = int(np.argmax(z > 0)) if loss else -1
    return {"death_lag": dl, "fraction": frac, "seed": seed,
            "any_loss": loss, "first_orphan": first,
            "race": bool(loss and first > 1500),
            "death_only": bool(loss and first == 1500),
            "loss_sector_ticks": int(z.sum())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=312)
    args = ap.parse_args()
    seeds = [SEED_BASE + i for i in range(args.seeds)]
    work = [(dl, f, s) for dl in DEATH_LAGS for f in FRACTIONS for s in seeds]
    os.makedirs(RESULTS_DIR, exist_ok=True)

    rows, done = [], set()
    if os.path.exists(CELLS):
        for line in open(CELLS):
            line = line.strip()
            if line:
                r = json.loads(line)
                k = (r["death_lag"], r["fraction"], r["seed"])
                if k not in done:
                    done.add(k); rows.append(r)
    todo = [w for w in work if w not in done]
    print(f"decoupled sweep: {len(DEATH_LAGS)} death_lags × {len(FRACTIONS)} "
          f"fractions × {args.seeds} seeds = {len(work)} sims "
          f"({len(done)} done, {len(todo)} to run)", flush=True)

    with open(CELLS, "a") as fh:
        with Pool(processes=min(os.cpu_count(), 8)) as pool:
            for i, row in enumerate(pool.imap_unordered(run_cell, todo), 1):
                fh.write(json.dumps(row) + "\n"); fh.flush(); rows.append(row)
                if i % 200 == 0 or i == len(todo):
                    print(f"  {i}/{len(todo)} done", flush=True)
    summarise(rows, args.seeds)


def summarise(rows, n_seeds):
    lines = ["# §6.1 race vs death-detection latency (storm, decoupled clock)\n",
             f"Seeds: {n_seeds}. Gossip/view lag = [8,24]. `death_lag` = uniform "
             "death-detection latency; `coupled` = base single-clock model "
             "(death clock = own gossip lag).\n",
             "Race = a shrink executed after the death tick on a view still "
             "counting not-yet-detected deaths. Death-only = orphaned at t=1500 "
             "(mass death, detection-independent).\n"]
    for f in FRACTIONS:
        lines.append(f"\n## upgraded fraction f = {f}\n")
        lines.append("| death_lag | §6.1 races | pure-death losses | any-loss rate |")
        lines.append("|---|---|---|---|")
        for dl in DEATH_LAGS:
            c = [r for r in rows if r["fraction"] == f and r["death_lag"] == dl]
            n = len(c)
            races = sum(r["race"] for r in c)
            deaths = sum(r["death_only"] for r in c)
            anyl = sum(r["any_loss"] for r in c)
            lines.append(f"| {dl} | {races}/{n} | {deaths}/{n} | "
                         f"{100*anyl/n:.1f}% |")
    out = os.path.join(RESULTS_DIR, "decoupled_summary.md")
    with open(out, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines)); print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
