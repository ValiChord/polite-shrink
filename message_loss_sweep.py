"""Does lossy gossip break polite shrink? Sweep gossip message-loss probability
× upgraded fraction × seeds on the join-free scenarios (activation, storm), and
measure run-level data loss.

Lossy gossip makes a viewer's coverage picture incomplete: missing a peer's
shrink/death → over-count → risk of shrinking into a hole. Polite shrink's
two-phase re-check runs on the same lossy view, so this is a real test of the
mechanism (not just the naive controller). loss=0 reproduces the base sim
(validate_message_loss.py). Resumable; deterministic. Python 3.12.1, numpy 2.5.1.
"""

import argparse
import json
import os
from multiprocessing import Pool

import numpy as np

from polite_shrink import Config, make_world
from rolling_upgrade_sim import assign_initial_variants
from message_loss_sim import MessageLossSim

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
CELLS = os.path.join(RESULTS_DIR, "message_loss_cells.jsonl")
SCENARIOS = {"activation": (2200, {}),
             "storm": (3000, dict(storm_at=1500, storm_frac=0.30))}
FRACTIONS = [0.1, 0.5, 1.0]
LOSSES = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
SEED_BASE = 100000


def run_cell(args):
    sc, frac, loss, seed = args
    ticks, kw = SCENARIOS[sc]
    cfg = Config(seed=seed)
    initial, events, joins = make_world(cfg, ticks, **kw)
    variants = assign_initial_variants(len(initial), frac, cfg.seed)
    m = MessageLossSim(cfg, variants, events, initial, joins, frac,
                       loss=loss).run(ticks)
    z = np.array(m.zero_sectors)
    loss_flag = bool((z > 0).any())
    onset = 1500 if sc == "storm" else 0
    first = int(np.argmax(z > 0)) if loss_flag else -1
    return {"scenario": sc, "fraction": frac, "loss": loss, "seed": seed,
            "any_loss": loss_flag, "first_orphan": first,
            "post_onset": bool(loss_flag and first >= onset),
            "loss_sector_ticks": int(z.sum()),
            "mean_final_level": float(np.mean(m.mean_level[-200:]))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=100)
    args = ap.parse_args()
    seeds = [SEED_BASE + i for i in range(args.seeds)]
    work = [(sc, f, l, s) for sc in SCENARIOS for f in FRACTIONS
            for l in LOSSES for s in seeds]
    os.makedirs(RESULTS_DIR, exist_ok=True)

    rows, done = [], set()
    if os.path.exists(CELLS):
        for line in open(CELLS):
            line = line.strip()
            if line:
                r = json.loads(line)
                k = (r["scenario"], r["fraction"], r["loss"], r["seed"])
                if k not in done:
                    done.add(k); rows.append(r)
    todo = [w for w in work if w not in done]
    print(f"message-loss sweep: {len(SCENARIOS)}×{len(FRACTIONS)}×{len(LOSSES)}×"
          f"{args.seeds} = {len(work)} sims ({len(done)} done, {len(todo)} to run)",
          flush=True)

    with open(CELLS, "a") as fh:
        with Pool(processes=min(os.cpu_count(), 8)) as pool:
            for i, row in enumerate(pool.imap_unordered(run_cell, todo), 1):
                fh.write(json.dumps(row) + "\n"); fh.flush(); rows.append(row)
                if i % 200 == 0 or i == len(todo):
                    print(f"  {i}/{len(todo)} done", flush=True)
    summarise(rows, args.seeds)


def summarise(rows, n_seeds):
    lines = ["# Does lossy gossip break polite shrink? Data loss vs message-loss rate\n",
             f"Seeds: {n_seeds}. Join-free scenarios. loss = per-round gossip drop "
             "probability; loss=0 = base sim.\n"]
    for sc in SCENARIOS:
        for f in FRACTIONS:
            lines.append(f"\n## {sc}, upgraded fraction f={f}\n")
            lines.append("| loss | runs w/ data loss | rate | mean final level |")
            lines.append("|---|---|---|---|")
            for l in LOSSES:
                c = [r for r in rows if r["scenario"] == sc
                     and r["fraction"] == f and r["loss"] == l]
                n = len(c)
                nl = sum(r["any_loss"] for r in c)
                lvl = np.mean([r["mean_final_level"] for r in c])
                lines.append(f"| {l:.1f} | {nl}/{n} | {100*nl/n:.1f}% | {lvl:.2f} |")
    out = os.path.join(RESULTS_DIR, "message_loss_summary.md")
    with open(out, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines)); print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
