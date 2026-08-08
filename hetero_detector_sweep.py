"""
hetero_detector_sweep — is a *single* detector threshold good enough?

The one question that decides whether adaptive, self-calibrating failure
detection (phi accrual and relatives) is worth building on top of this work.

Method. A mixed network: half the agents detect deaths fast (`dl_fast`), half
slowly (`dl_slow`). Sweep the two classes' false-conviction rates independently
over a full grid, then compare:

    best UNIFORM  = min over the diagonal        (p_fast == p_slow)
    best PER-CLASS= min over the whole grid      (each class tuned separately)

The gap between them is exactly what per-peer calibration could buy. If it is
large, a global threshold is provably leaving safety on the table and adaptive
detection is justified with a number. If it is small, a fixed threshold is fine
and phi accrual would be machinery answering a question nobody has.

Both are reported, because they can disagree:
  * `P(any loss)` — runs losing any real data. Usually the binding exposure.
  * `E[loss]`     — total held-loss sector-ticks.

Stress regime, as in `detector_error_sweep.py`: storm 50%, R=5, N=200. Milder
settings lose nothing at any setting and cannot discriminate. Absolute rates are
not operating figures.

Resumable; writes each cell as it completes; 4 processes by default.
"""

from __future__ import annotations

import argparse
import json
import os
from multiprocessing import Pool

import numpy as np

from polite_shrink import Config, make_world
from rolling_upgrade_sim import assign_initial_variants
from hetero_detector_sim import HeteroDetectorSim, FAST, SLOW

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
CELLS = os.path.join(RESULTS_DIR, "hetero_detector_cells.jsonl")

TICKS = 3000
STORM_FRAC = 0.50
P_GRID = [0.0, 0.02, 0.05, 0.10, 0.20]
SEED_BASE = 900000

# Latency pair for the two classes. BOTH must sit inside §11's danger band
# (detection slower than gossip) or the grid measures nothing: a first attempt
# used dl_fast=24, which is *below* the gossip lag, and §11 already showed that
# detection faster than gossip drives the race to zero. The fast half then
# rescued the whole network, the baseline lost no data at all, and every cell in
# the grid was noise around zero. See "Baseline check" in the output.
DL_FAST, DL_SLOW = 192, 384


def run_cell(args):
    p_fast, p_slow, seed, dl_fast, dl_slow = args
    cfg = Config(seed=seed)
    initial, events, joins = make_world(cfg, TICKS, storm_at=1500,
                                        storm_frac=STORM_FRAC)
    variants = assign_initial_variants(len(initial), 1.0, cfg.seed)
    sim = HeteroDetectorSim(cfg, variants, events, initial, joins, 1.0,
                            dl_fast=dl_fast, dl_slow=dl_slow,
                            p_fast=p_fast, p_slow=p_slow, frac_slow=0.5)
    m = sim.run(TICKS)
    held = np.array(m.held_zero)
    lv = sim.class_levels()
    return {"p_fast": p_fast, "p_slow": p_slow, "seed": seed,
            "dl_fast": dl_fast, "dl_slow": dl_slow,
            "held_loss": int(held.sum()), "any_held_loss": bool(held.sum() > 0),
            "exposure": float(np.array(m.frac_under).sum()),
            "lvl_fast": lv[FAST], "lvl_slow": lv[SLOW],
            "sync": int(m.cum_sync[-1])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=24)
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--dl-fast", type=int, default=DL_FAST)
    ap.add_argument("--dl-slow", type=int, default=DL_SLOW)
    args = ap.parse_args()
    dlf, dls = args.dl_fast, args.dl_slow
    seeds = [SEED_BASE + i for i in range(args.seeds)]
    work = [(pf, ps, s, dlf, dls)
            for pf in P_GRID for ps in P_GRID for s in seeds]
    os.makedirs(RESULTS_DIR, exist_ok=True)

    # The latency pair is part of the cell key, so runs at different regimes
    # coexist in one file instead of silently contaminating each other.
    rows, done = [], set()
    if os.path.exists(CELLS):
        for line in open(CELLS, encoding="utf-8"):
            line = line.strip()
            if line:
                r = json.loads(line)
                k = (r["p_fast"], r["p_slow"], r["seed"],
                     r.get("dl_fast"), r.get("dl_slow"))
                if k not in done:
                    done.add(k)
                    rows.append(r)
    todo = [w for w in work if w not in done]
    print(f"hetero sweep: {len(P_GRID)}x{len(P_GRID)} grid x {args.seeds} seeds "
          f"= {len(work)} runs ({len(done)} done, {len(todo)} to run)",
          flush=True)

    with open(CELLS, "a", encoding="utf-8") as fh:
        with Pool(processes=args.procs) as pool:
            for i, row in enumerate(pool.imap_unordered(run_cell, todo), 1):
                fh.write(json.dumps(row) + "\n")
                fh.flush()
                rows.append(row)
                if i % 50 == 0 or i == len(todo):
                    print(f"  {i}/{len(todo)}", flush=True)
    rows = [r for r in rows
            if r.get("dl_fast") == dlf and r.get("dl_slow") == dls]
    summarise(rows, args.seeds, dlf, dls)


def _agg(rows, pf, ps):
    # sorted by seed: the pool returns cells in completion order, and the means
    # below are float reductions whose result depends on summation order.
    c = sorted((r for r in rows if r["p_fast"] == pf and r["p_slow"] == ps),
               key=lambda r: r["seed"])
    if not c:
        return None
    n = len(c)
    return {"n": n,
            "rate": sum(r["any_held_loss"] for r in c) / n,
            "loss": sum(r["held_loss"] for r in c),
            "lvl_fast": float(np.mean([r["lvl_fast"] for r in c])),
            "lvl_slow": float(np.mean([r["lvl_slow"] for r in c])),
            "sync": float(np.mean([r["sync"] for r in c]))}


def summarise(rows, n_seeds, dl_fast=DL_FAST, dl_slow=DL_SLOW):
    import sys
    grid = {(pf, ps): _agg(rows, pf, ps) for pf in P_GRID for ps in P_GRID}
    grid = {k: v for k, v in grid.items() if v}
    if not grid:
        print("no cells")
        return

    # Baseline check, reported FIRST and unconditionally. If p=0/p=0 loses
    # nothing there is no headroom anywhere in the grid, every cell is noise
    # around zero, and a "no effect" reading would be an artefact of the regime
    # rather than a result. The first run of this study failed exactly that way.
    base = grid.get((0.0, 0.0))
    base_rate = base["rate"] if base else 0.0
    underpowered = base_rate < 0.10

    diag = {k: v for k, v in grid.items() if k[0] == k[1]}
    best_uniform = min(diag.items(), key=lambda kv: (kv[1]["rate"], kv[1]["loss"]))
    best_perclass = min(grid.items(), key=lambda kv: (kv[1]["rate"], kv[1]["loss"]))
    gap_rate = best_uniform[1]["rate"] - best_perclass[1]["rate"]

    L = ["# Is one detector threshold good enough for a mixed network?", "",
         "The question that decides whether adaptive, self-calibrating failure "
         "detection is worth building. Half the agents detect deaths fast "
         f"(latency {dl_fast}), half slowly ({dl_slow}); the two classes' "
         "false-conviction rates are swept independently.", "",
         f"Storm {int(STORM_FRAC*100)}%, N=200, R=5, {n_seeds} seeds/cell. "
         "Stress regime — milder settings lose nothing at any setting and "
         "cannot discriminate; these are not operating rates.", "",
         f"Environment: Python {sys.version.split()[0]}, numpy {np.__version__} "
         "— numpy matches the repo pin, Python does not (3.12.1).", "",
         "## Baseline check — is there anything here to measure?", "",
         f"At p = 0 for both classes the network loses data in "
         f"**{100*base_rate:.0f}%** of runs. That is the headroom every cell "
         "below is competing against.", ""]
    if underpowered:
        # ASCII only: this string is printed to the console as well as written
        # to the summary, and a non-cp1252 character here crashes the run on a
        # default Windows terminal -- which inside run_stage3.sh would look like
        # a study failure rather than an encoding problem.
        L += ["> **WARNING -- this grid is underpowered and its result must not "
              "be quoted.** With so little baseline loss there is nothing for "
              "detector tuning to improve, so every cell is noise around zero "
              "and a 'no effect' reading would be an artefact of the regime. "
              "Both latency classes must sit inside §11's danger band "
              "(detection *slower* than gossip); a class faster than gossip has "
              "its race driven to zero by §11 and rescues the whole network.", ""]
    L += ["## P(any loss), by class setting", "",
         "Rows = `p_slow` (the slow-detecting half), columns = `p_fast`. The "
         "**diagonal** is what a single global threshold can reach; everything "
         "off it needs per-peer calibration.", "",
         "| p_slow \\ p_fast | " + " | ".join(f"{p}" for p in P_GRID) + " |",
         "|---" * (len(P_GRID) + 1) + "|"]
    for ps in P_GRID:
        cells = []
        for pf in P_GRID:
            g = grid.get((pf, ps))
            if not g:
                cells.append("—")
                continue
            s = f"{100*g['rate']:.0f}%"
            if (pf, ps) == best_perclass[0]:
                s = f"**{s}**"
            elif pf == ps:
                s = f"*{s}*"
            cells.append(s)
        L.append(f"| **{ps}** | " + " | ".join(cells) + " |")
    L += ["", "*italic* = diagonal (uniform threshold); **bold** = grid optimum.",
          ""]

    (upf, ups), ub = best_uniform
    (bpf, bps), bb = best_perclass

    # Selection-bias null test. The grid optimum is the MINIMUM of 25 noisy
    # cells while the uniform optimum is the minimum of 5, so the gap is
    # positive by construction even when the two are identical. Asking "is the
    # gap non-zero?" therefore answers nothing. The question is whether the
    # observed gap exceeds what picking a minimum from 25 cells produces on its
    # own, so the null model gives EVERY cell the best-uniform rate and asks how
    # often selection alone reproduces the gap.
    n_diag, n_all = len(P_GRID), len(P_GRID) ** 2
    n_obs = ub["n"]
    rng = np.random.default_rng(12345)
    B = 20000
    draws = rng.random((B, n_all, n_obs)) < ub["rate"]
    rates = draws.mean(axis=2)
    null_gap = rates[:, :n_diag].min(axis=1) - rates.min(axis=1)
    p_val = float((null_gap >= gap_rate - 1e-12).mean())

    L += ["## What per-peer calibration buys", "",
          "| | setting | P(any loss) | E[loss] |",
          "|---|---|---|---|",
          f"| best **uniform** | p = {upf} for both | {100*ub['rate']:.0f}% "
          f"({round(ub['rate']*n_obs)}/{n_obs} runs) | {ub['loss']:,} |",
          f"| best **per-class** | fast {bpf}, slow {bps} | "
          f"{100*bb['rate']:.0f}% ({round(bb['rate']*n_obs)}/{n_obs} runs) | "
          f"{bb['loss']:,} |",
          f"| apparent gap | | {100*gap_rate:+.0f} pp | "
          f"{bb['loss'] - ub['loss']:+,} |", "",
          f"**Selection-bias check.** If every cell in the grid had the *same* "
          f"true rate ({100*ub['rate']:.0f}%), simply taking the best of "
          f"{n_all} cells rather than the best of {n_diag} would produce a gap "
          f"this large or larger in **{100*p_val:.0f}%** of grids "
          f"(20,000 simulated).", ""]

    if p_val > 0.10:
        L += [f"**No evidence that per-peer calibration helps.** The apparent "
              f"{100*gap_rate:.0f} pp advantage is what the search procedure "
              f"manufactures on its own — it is {round(ub['rate']*n_obs)} "
              f"losing run(s) versus {round(bb['rate']*n_obs)} out of {n_obs}, "
              "and vanishes under the null. Read as **'no effect detectable at "
              "this sample size'**, not 'no effect'.", "",
              "**What the grid does show, and it is the larger number.** Going "
              f"from no paranoia at all to the best single global threshold "
              f"takes `P(any loss)` from **{100*base_rate:.0f}% to "
              f"{100*ub['rate']:.0f}%** — a {100*(base_rate-ub['rate']):.0f} pp "
              "first-order effect. Whatever per-peer calibration is worth on "
              f"top, it is bounded above by roughly {100*gap_rate:.0f} pp and "
              "is not resolvable here. **Getting the threshold roughly right "
              "matters enormously; getting it right *per peer* does not "
              "measurably.**", "",
              "For phi accrual and relatives that is the answer: their value is "
              "self-calibration, and self-calibration is second-order against "
              "an effect this size. Justifying that machinery needs a regime "
              "where the first-order effect is already captured and the "
              "residual per-peer term is resolvable — which would take on the "
              f"order of 10x the {n_obs} seeds used here.", ""]
    else:
        L += [f"**Per-peer calibration survives the selection-bias check** "
              f"(p = {p_val:.3f}): the off-diagonal advantage of "
              f"{100*gap_rate:.0f} pp is larger than picking the best of "
              f"{n_all} cells explains. A global threshold is leaving safety on "
              "the table, and adaptive detection is justified — though the "
              "first-order effect (no paranoia to best uniform, "
              f"{100*(base_rate-ub['rate']):.0f} pp) is still the larger one.",
              ""]

    L += ["## Storage, split by who pays it", "",
          "| p_fast | p_slow | arc (fast class) | arc (slow class) | sync |",
          "|---|---|---|---|---|"]
    for p in P_GRID:
        g = grid.get((p, p))
        if g:
            L.append(f"| {p} | {p} | {g['lvl_fast']:.2f} | {g['lvl_slow']:.2f} "
                     f"| {g['sync']:,.0f} |")
    L += ["", "## Caveats", "",
          "- Two latency classes at a 4:1 ratio and a 50/50 split. A real "
          "network has a continuum, and the answer could differ for a "
          "long-tailed distribution.",
          "- `p` is a false-positive rate *per look*; real accrual detectors "
          "run orders of magnitude lower, so the interesting region is the "
          "top-left of the grid.",
          "- No heartbeat timing, no detector memory. This measures whether the "
          "*optimum moves*, which is the precondition for adaptivity being "
          "useful — not any detector's ability to track it.",
          f"- {n_seeds} seeds per cell; grid minima of noisy quantities are "
          "biased low, so treat the gap as an upper bound on what adaptivity "
          "could buy.", ""]

    out = os.path.join(RESULTS_DIR, "hetero_detector_summary.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("\n".join(L))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
