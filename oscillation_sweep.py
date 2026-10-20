"""
oscillation_sweep — is the "hallway dance" a delay instability with a threshold?

The repo has always treated the oscillation as possibly "inherent — a matter of
physics" (CORE_IDEA.md), and separable from durability. Decentralised
delay-stability theory from Internet congestion control says it need not be:
Johari & Tan (IEEE/ACM ToN, 2001) and Vinnicombe (IFAC 2002) showed that a
network of sources with *different* round-trip delays is locally stable, for any
topology, if each source scales its gain inversely with its OWN delay.

Two predictions, both falsifiable here:

  1. THRESHOLD. If the dance is a delay instability, steady-state resizing should
     switch on sharply as the reaction gets faster — i.e. as the shrink
     persistence constant `shrink_k` (persistence = shrink_k x lag; gain ~ 1/k)
     falls below some critical value — rather than fading in smoothly.
  2. SELF-SCALING. Scaling persistence to each agent's OWN lag (what the repo
     does) should be at least as stable as scaling it to one network-wide
     constant of the same average — and the difference should appear only when
     lags differ. With identical lags the two rules are the same rule, which
     makes the homogeneous arm a built-in control.

Caveat stated up front: the theory is for smooth, linearised fluid models. This
controller is quantised (power-of-two arcs), hysteretic and nonlinear, so a
theorem does not transfer — this tests whether its *shape* does.

Scenario: activation (no deaths, no joins), N=200, R=5. The network is given
time to settle, then resizing is measured over the last OBS ticks. Measures:
  resize_rate  mean arc changes per tick (the dance itself)
  level_std    std of mean arc level over the window (its amplitude)
  held_loss    sector-ticks with zero real copies (durability, for reference)

Instrumentation only on top of `polite_shrink.Sim`, via its `_persistence_lag`
hook (which returns `a.lag`, so the default arm is byte-identical to the base
controller). Resumable; 4 processes by default.
"""

from __future__ import annotations

import argparse
import json
import os
from multiprocessing import Pool

import numpy as np

from polite_shrink import VARIANTS, Config, Sim, make_world

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
CELLS = os.path.join(RESULTS_DIR, "oscillation_cells.jsonl")

TICKS = 5000
OBS = 2000
SHRINK_K = [0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0]
VARIANT_IDX = {"V1": 1, "V3": 3}
LAG_SPREADS = {"mixed": (4, 28), "equal": (16, 16)}   # same mean lag (16)
SCALINGS = ["own", "global"]
SEED_BASE = 700000


class ScaledSim(Sim):
    """`own`: persistence scales with the agent's own lag (the repo's rule).
    `global`: every agent uses the same constant, the network's mean lag."""

    def __init__(self, *a, scaling="own", ref_lag=16.0, **kw):
        super().__init__(*a, **kw)
        self.scaling = scaling
        self.ref_lag = float(ref_lag)

    def _persistence_lag(self, a):
        return a.lag if self.scaling == "own" else self.ref_lag


def run_cell(args):
    vname, spread, scaling, sk, seed = args
    lo, hi = LAG_SPREADS[spread]
    cfg = Config(seed=seed, shrink_k=sk, lag_min=lo, lag_max=hi,
                 intent_delay=2 * hi + 2)
    initial, events, joins = make_world(cfg, TICKS)
    sim = ScaledSim(cfg, VARIANTS[VARIANT_IDX[vname]], events, initial, joins,
                    scaling=scaling, ref_lag=(lo + hi) / 2)
    m = sim.run(TICKS)
    rz = np.array(m.resizes[-OBS:])
    lv = np.array(m.mean_level[-OBS:])
    return {"variant": vname, "spread": spread, "scaling": scaling,
            "shrink_k": sk, "seed": seed,
            "resize_rate": float(rz.mean()), "level_std": float(lv.std()),
            "level_mean": float(lv.mean()),
            "held_loss": int(np.array(m.held_zero).sum())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=12)
    ap.add_argument("--procs", type=int, default=4)
    args = ap.parse_args()
    seeds = [SEED_BASE + i for i in range(args.seeds)]
    work = [(v, sp, sc, k, s) for v in VARIANT_IDX for sp in LAG_SPREADS
            for sc in SCALINGS for k in SHRINK_K for s in seeds
            if not (sp == "equal" and sc == "global")]   # identical rule; skip
    os.makedirs(RESULTS_DIR, exist_ok=True)
    rows, done = [], set()
    if os.path.exists(CELLS):
        for line in open(CELLS, encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                rows.append(r)
                done.add((r["variant"], r["spread"], r["scaling"],
                          r["shrink_k"], r["seed"]))
    todo = [w for w in work if w not in done]
    print(f"oscillation sweep: {len(work)} runs ({len(todo)} to run)", flush=True)
    with open(CELLS, "a", encoding="utf-8") as fh, Pool(args.procs) as pool:
        for i, r in enumerate(pool.imap_unordered(run_cell, todo), 1):
            fh.write(json.dumps(r) + "\n"); fh.flush(); rows.append(r)
            if i % 40 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)}", flush=True)
    summarise(rows, args.seeds)


def _cell(rows, **k):
    c = sorted((r for r in rows if all(r[a] == b for a, b in k.items())),
               key=lambda r: r["seed"])
    if not c:
        return None
    rr = np.array([r["resize_rate"] for r in c])
    return {"n": len(c), "rate": rr.mean(), "sem": rr.std(ddof=1) / np.sqrt(len(c))
            if len(c) > 1 else 0.0,
            "lstd": float(np.mean([r["level_std"] for r in c])),
            "lvl": float(np.mean([r["level_mean"] for r in c])),
            "loss": sum(r["held_loss"] > 0 for r in c)}


def summarise(rows, n_seeds):
    import sys
    L = ["# Is the hallway dance a delay instability?", "",
         "Steady-state resizing (arc changes per tick, last "
         f"{OBS} of {TICKS} ticks, activation scenario, N=200, R=5) as the shrink "
         "persistence constant `shrink_k` varies. Persistence = shrink_k x lag, so "
         "reaction gain ~ 1/shrink_k. `own` = persistence scaled to each agent's own "
         "lag (the repo's rule); `global` = one network-wide constant at the same "
         "mean lag. Mixed lags span 4..28; equal lags are all 16 (same mean).", "",
         f"{n_seeds} seeds/cell. Environment: Python {sys.version.split()[0]}, "
         f"numpy {np.__version__}.", ""]
    for v in VARIANT_IDX:
        L += [f"## {v}", "",
              "| shrink_k | mixed, own lag | mixed, global lag | equal lags | "
              "level mean (mixed/own) | runs w/ loss (mixed/own) |",
              "|---|---|---|---|---|---|"]
        for k in SHRINK_K:
            o = _cell(rows, variant=v, spread="mixed", scaling="own", shrink_k=k)
            g = _cell(rows, variant=v, spread="mixed", scaling="global", shrink_k=k)
            e = _cell(rows, variant=v, spread="equal", scaling="own", shrink_k=k)
            f = lambda c: f"{c['rate']:.3f} ± {c['sem']:.3f}" if c else "—"
            L.append(f"| {k} | {f(o)} | {f(g)} | {f(e)} | "
                     f"{o['lvl']:.2f} | {o['loss']}/{o['n']} |" if o else f"| {k} | — |")
        L.append("")
    out = os.path.join(RESULTS_DIR, "oscillation_summary.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("\n".join(L))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
