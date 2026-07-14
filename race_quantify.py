"""
Stage-3d: quantifying the §6.1 residual race.

REPORT_stage1.md §6.1: deaths younger than the detection latency at the moment
a shrink executes are locally undecidable — a declared-coverage hole can
open. The storm brake bounds the window; nothing closes it. §7 leaves
"how often, under realistic parameters?" open. The 0/1,248 sweep result
means only that the tested churn never aligned deaths inside the window
— it is an upper bound at one operating point, not a rate.

Method: escalate the hazard until holes actually occur, measure the
rate, and check it against the scaling a skeptic would demand:

    A sector drops to zero declared copies only if all its remaining
    holders (~R after a shrink) disappear within one blind window W
    (staleness + intent wait). With per-agent-per-tick death rate p,
    that is ~ (p·W)^R per opportunity — so on log-log axes, hole rate
    vs p should be a line of slope ≈ R, and raising R by 2 should drop
    the rate by ~(p·W)^2.

If the measured slopes match, extrapolation to production-like hazards
(where p·W is tiny) is principled rather than hopeful.

Every zero-coverage episode is classified at onset:
  shrink-hole — a shrink executed that tick over the sector (the §6.1
                race proper: the re-check missed in-window deaths);
  churn-hole  — deaths alone removed the last copy (the same blind
                window, without a shrink pulling the trigger).
Episode durations are recorded; §6.1 holes are transient by design
(the leaver still has the data on disk) and the duration bounds how
long a prompt re-grow takes to close them.

Grid: V3 only. R ∈ {3,5}; lag_max ∈ {24,48,96} (lag_min = lag_max/3,
intent_delay = 2·lag_max + 2, matching the design rule); p over decades.
Deaths are matched by Poisson joins (stationary population, as the
Stage-1 churn scenario). Warmup runs once per (R, lag) cell and is
snapshot-shared across seeds (adversary.py's pattern).

Usage:   python3 race_quantify.py [--quick]
Output:  results/race.png, results/race_summary.md, results/race.json
"""

from __future__ import annotations

import copy
import json
import multiprocessing as mp
import sys
import time

import numpy as np

from polite_shrink import VARIANTS, Config, Sim, vacate_half
from ext_common import ALERT, BASELINE, INK, MUTED, SERIES, plt

V3 = VARIANTS[3]

OBSERVE = 1500


def warmup_for(lag_max):
    """Settling from full arcs takes ~5-6 levels x (4x-lag persistence +
    intent wait); a fixed warmup leaves slow-hysteresis cells (large lag)
    over-covered and understates hole rates. Scale it."""
    return 1500 + 35 * lag_max
R_VALUES = [3, 5]
LAG_VALUES = [24, 48, 96]
P_VALUES = [5e-4, 1e-3, 2e-3, 4e-3, 8e-3, 1.6e-2, 3.2e-2]
SEEDS_PER_CELL = 40

_SNAP = None


class RaceSim(Sim):
    """Sim that tracks zero-coverage episodes and classifies their cause."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._prev_zero = np.zeros(self.cfg.sectors, dtype=bool)
        self._shrunk_now = np.zeros(self.cfg.sectors, dtype=bool)
        self._open: dict[int, tuple[int, str]] = {}   # sector -> (onset, kind)
        self.holes: list[dict] = []                   # closed episodes

    def _do_shrink(self, a):
        vs, ve = vacate_half(a.home, a.level, self.cfg.log2s)
        self._shrunk_now[vs:ve] = True
        super()._do_shrink(a)

    def step(self):
        self._shrunk_now[:] = False
        super().step()
        cov = self.cov_h[(self.t - 1) % self.H]
        zero = cov == 0
        t0 = self.t - 1
        for k in np.nonzero(zero & ~self._prev_zero)[0]:
            kind = "shrink" if self._shrunk_now[k] else "churn"
            self._open[int(k)] = (t0, kind)
        for k in np.nonzero(self._prev_zero & ~zero)[0]:
            onset, kind = self._open.pop(int(k))
            self.holes.append({"sector": int(k), "onset": onset,
                               "duration": t0 - onset, "kind": kind})
        self._prev_zero = zero.copy()

    def finish(self):
        """Close still-open episodes at end of run (duration = censored)."""
        for k, (onset, kind) in self._open.items():
            self.holes.append({"sector": k, "onset": onset,
                               "duration": self.t - onset, "kind": kind,
                               "censored": True})
        self._open.clear()


def make_cfg(r, lag_max):
    return Config(redundancy=r,
                  lag_min=max(4, lag_max // 3),
                  lag_max=lag_max,
                  intent_delay=2 * lag_max + 2)


def build_snapshot(r, lag_max):
    cfg = make_cfg(r, lag_max)
    S = cfg.sectors
    rng = np.random.default_rng(cfg.seed)
    initial = [(int(rng.integers(0, S)),
                int(rng.integers(cfg.lag_min, cfg.lag_max + 1)))
               for _ in range(cfg.n_agents)]
    # Reserve history capacity for churn joiners added later by observe():
    # expected joiners = p*N*OBSERVE (max p), padded well past the tail.
    # The dummy entry sits beyond the run horizon and never fires.
    warmup = warmup_for(lag_max)
    reserve = int(max(P_VALUES) * cfg.n_agents * OBSERVE * 2) + 256
    dummy_joins = {warmup + OBSERVE + 10: [(0, cfg.lag_min)] * reserve}
    sim = RaceSim(cfg, V3, {}, initial, dummy_joins)
    for _ in range(warmup):
        sim.step()
    return sim


def churn_world(cfg, seed, p, t_from, t_to):
    """Death/join schedule in [t_from, t_to): each alive agent dies with
    prob p per tick; Poisson joins at rate p*N0 keep population level."""
    rng = np.random.default_rng(seed)
    S = cfg.sectors
    events: dict[int, list[int]] = {}
    joins: dict[int, list[tuple[int, int]]] = {}
    alive = set(range(cfg.n_agents))
    next_id = cfg.n_agents
    for t in range(t_from, t_to):
        dead = [a for a in sorted(alive) if rng.random() < p]
        if dead:
            events.setdefault(t, []).extend(dead)
            alive -= set(dead)
        n_join = rng.poisson(p * cfg.n_agents)
        if n_join:
            js = [(int(rng.integers(0, S)),
                   int(rng.integers(cfg.lag_min, cfg.lag_max + 1)))
                  for _ in range(n_join)]
            joins.setdefault(t, []).extend(js)
            alive |= set(range(next_id, next_id + n_join))
            next_id += n_join
    return events, joins


def _init_worker(snap):
    global _SNAP
    _SNAP = snap


def observe(args):
    seed, p = args
    sim = copy.deepcopy(_SNAP)
    events, joins = churn_world(sim.cfg, seed, p, sim.t, sim.t + OBSERVE)
    sim.events, sim.joins = events, joins
    for _ in range(OBSERVE):
        sim.step()
    sim.finish()
    zero_ticks = int(np.sum(np.array(sim.m.zero_sectors[-OBSERVE:])))
    return {
        "seed": seed, "p": p,
        "holes_shrink": sum(1 for h in sim.holes if h["kind"] == "shrink"),
        "holes_churn": sum(1 for h in sim.holes if h["kind"] == "churn"),
        "durations": [h["duration"] for h in sim.holes],
        "zero_sector_ticks": zero_ticks,
        "floor_min": int(min(sim.m.floor[-OBSERVE:])),
    }


def run_cell(r, lag_max, p_values, seeds, workers):
    t0 = time.time()
    snap = build_snapshot(r, lag_max)
    eq_floor = snap.m.floor[-1]
    jobs = [(1000 * s + 1, p) for p in p_values for s in range(seeds)]
    with mp.Pool(workers, initializer=_init_worker, initargs=(snap,)) as pool:
        results = pool.map(observe, jobs)
    out = {}
    for p in p_values:
        rs = [x for x in results if x["p"] == p]
        n_holes = sum(x["holes_shrink"] + x["holes_churn"] for x in rs)
        out[p] = {
            "runs": len(rs),
            "runs_with_hole": sum(1 for x in rs
                                  if x["holes_shrink"] + x["holes_churn"]),
            "holes_shrink": sum(x["holes_shrink"] for x in rs),
            "holes_churn": sum(x["holes_churn"] for x in rs),
            "holes_total": n_holes,
            "zero_sector_ticks": sum(x["zero_sector_ticks"] for x in rs),
            "durations": summarize_durations(
                [d for x in rs for d in x["durations"]]),
            # rates per 1000 ticks of observation, for cross-cell compare
            "rate_per_kticks": 1000.0 * n_holes / (len(rs) * OBSERVE),
            "shrink_rate_per_kticks": 1000.0 * sum(
                x["holes_shrink"] for x in rs) / (len(rs) * OBSERVE),
        }
        print(f"  R={r} lag={lag_max} p={p:.0e}: "
              f"holes={n_holes} (shrink {out[p]['holes_shrink']} / churn "
              f"{out[p]['holes_churn']}) in {len(rs)} runs; "
              f"runs_with_hole={out[p]['runs_with_hole']}", flush=True)
    print(f"  cell R={r} lag={lag_max} done in {time.time()-t0:.0f}s "
          f"(equilibrium floor at snapshot: {eq_floor})", flush=True)
    return out


def summarize_durations(ds):
    """Compact stats instead of raw episode lists (the raw data at high
    hazard is millions of episodes; it is regenerable from the seeds)."""
    if not ds:
        return {"n": 0}
    a = np.asarray(ds)
    hist, edges = np.histogram(a, bins=np.arange(0, a.max() + 26, 25))
    return {"n": int(a.size), "median": float(np.median(a)),
            "p90": float(np.percentile(a, 90)), "max": int(a.max()),
            "hist_bin": 25, "hist": [int(x) for x in hist]}


def fit_slope(ps, rates):
    """log-log OLS slope over points with nonzero rate; None if < 3."""
    xs = [np.log(p) for p, r in zip(ps, rates) if r > 0]
    ys = [np.log(r) for r in rates if r > 0]
    if len(xs) < 3:
        return None
    return float(np.polyfit(xs, ys, 1)[0])


def plot(all_cells, out):
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.4))
    fig.suptitle("§6.1 residual race, measured: declared-coverage holes vs "
                 "churn hazard (V3, N=200)",
                 fontsize=12, fontweight="bold", color=INK)
    ax_rate, ax_frac, ax_dur = axes.flat

    lag_shade = {24: 0.35, 48: 0.65, 96: 1.0}
    r_color = {3: SERIES[0], 5: SERIES[3]}
    for (r, lag), cell in all_cells.items():
        ps = sorted(cell)
        rates = [cell[p]["rate_per_kticks"] for p in ps]
        fracs = [cell[p]["runs_with_hole"] / cell[p]["runs"] for p in ps]
        c = r_color[r]
        a = lag_shade[lag]
        slope = fit_slope(ps, rates)
        lbl = (f"R={r} lag={lag}" +
               (f" (slope {slope:.1f})" if slope is not None else ""))
        shown = [(p, x) for p, x in zip(ps, rates) if x > 0]
        if shown:
            ax_rate.plot([p for p, _ in shown], [x for _, x in shown],
                         color=c, alpha=a, lw=1.6, marker="o", ms=4, label=lbl)
        shr = [(p, cell[p]["shrink_rate_per_kticks"]) for p in ps
               if cell[p]["shrink_rate_per_kticks"] > 0]
        if shr:
            ax_rate.plot([p for p, _ in shr], [x for _, x in shr],
                         color=c, alpha=a, lw=1.2, ls="--", marker="x", ms=4)
        ax_frac.plot(ps, fracs, color=c, alpha=a, lw=1.6, marker="o", ms=4,
                     label=f"R={r} lag={lag}")
    ax_rate.set_xscale("log")
    ax_rate.set_yscale("log")
    ax_rate.set_title("Hole rate vs hazard (dashed × = shrink-holes)")
    ax_rate.set_xlabel("death prob p per agent-tick (log)")
    ax_rate.set_ylabel("holes / 1000 ticks (log)")
    ax_rate.legend(fontsize=7, loc="upper left")

    ax_frac.set_xscale("log")
    ax_frac.set_title("Fraction of runs with ≥1 hole")
    ax_frac.set_xlabel("death prob p per agent-tick (log)")
    ax_frac.set_ylabel("fraction of runs")
    ax_frac.set_ylim(-0.03, 1.03)
    ax_frac.legend(fontsize=7, loc="upper left")

    # aggregate the per-cell duration histograms (25-tick bins)
    agg: dict[int, int] = {}
    n_tot, med_num = 0, 0.0
    for cell in all_cells.values():
        for p in cell.values():
            d = p["durations"]
            if d.get("n"):
                for i, c in enumerate(d["hist"]):
                    agg[i] = agg.get(i, 0) + c
                n_tot += d["n"]
                med_num += d["median"] * d["n"]
    if agg:
        xs = [25 * i for i in sorted(agg)]
        ax_dur.bar(xs, [agg[i] for i in sorted(agg)], width=23,
                   align="edge", color=SERIES[0], edgecolor=INK, lw=0.3)
        med = med_num / n_tot     # n-weighted mean of cell medians
        ax_dur.axvline(med, color=ALERT, lw=1.2, ls="--")
        ax_dur.text(med * 1.1, 0.9, "typical",
                    transform=ax_dur.get_xaxis_transform(),
                    color=ALERT, fontsize=8)
    ax_dur.set_title("Hole durations (ticks until re-covered)")
    ax_dur.set_xlabel("ticks")
    ax_dur.set_ylabel("episodes")

    for ax in axes.flat:
        ax.grid(True, axis="y")
        ax.margins(x=0.03)
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"wrote {out}")


def main():
    quick = "--quick" in sys.argv
    rs = [5] if quick else R_VALUES
    lags = [24] if quick else LAG_VALUES
    ps = P_VALUES[-3:] if quick else P_VALUES
    seeds = 8 if quick else SEEDS_PER_CELL
    workers = min(7, mp.cpu_count())

    all_cells = {}
    for r in rs:
        for lag in lags:
            print(f"cell R={r} lag_max={lag}")
            all_cells[(r, lag)] = run_cell(r, lag, ps, seeds, workers)

    ser = {f"R{r}_lag{lag}": {str(p): {k: v for k, v in cell[p].items()}
                              for p in cell}
           for (r, lag), cell in all_cells.items()}
    with open("results/race.json", "w") as f:
        json.dump({"warmup": "1500 + 35*lag_max", "observe": OBSERVE,
                   "seeds_per_cell": seeds, "cells": ser}, f)

    hdr = ["R", "lag_max", "p", "runs", "runs_with_hole", "holes_shrink",
           "holes_churn", "zero_sector_ticks", "rate_per_kticks"]
    lines = ["| " + " | ".join(hdr) + " |",
             "|" + "|".join("---" for _ in hdr) + "|"]
    slopes = []
    for (r, lag), cell in sorted(all_cells.items()):
        for p in sorted(cell):
            c = cell[p]
            lines.append(f"| {r} | {lag} | {p:.0e} | {c['runs']} | "
                         f"{c['runs_with_hole']} | {c['holes_shrink']} | "
                         f"{c['holes_churn']} | {c['zero_sector_ticks']} | "
                         f"{c['rate_per_kticks']:.4f} |")
        s = fit_slope(sorted(cell),
                      [cell[p]["rate_per_kticks"] for p in sorted(cell)])
        if s is not None:
            slopes.append(f"R={r} lag={lag}: fitted log-log slope {s:.2f}")
    with open("results/race_summary.md", "w") as f:
        f.write("# §6.1 residual-race quantification\n\n"
                f"V3 only, N=200, warmup 1500+35*lag_max, observe {OBSERVE} ticks, "
                f"{seeds} seeds/point. Hole = declared coverage of a sector "
                "hits 0. shrink = a shrink executed over the sector that "
                "tick (§6.1 race proper); churn = deaths alone. Zero holes "
                "at a point = upper bound only, not a rate.\n\n"
                + "\n".join(lines) + "\n\n## Fitted scaling\n\n"
                + ("\n".join(f"- {s}" for s in slopes) if slopes
                   else "- insufficient nonzero points to fit") + "\n")
    plot(all_cells, "results/race.png")
    print("\n".join(slopes) if slopes else "no fittable cells")


if __name__ == "__main__":
    main()
