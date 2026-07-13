"""
Stage-3c: does the controller behaviour survive scale?

Stage-1's claims are all at N = 200 (REPORT.md §7 scopes them so).
Holochain networks could be thousands of nodes; cascade dynamics,
settle times, and per-agent costs might all degrade with N. This study
runs V1 and V3 through activation and storm at N up to 5000, in two
series:

  fixed    — ring stays 512 sectors, so density (agents per sector)
             grows ~25x and equilibrium arcs shrink toward level 0;
  density  — the ring scales with N (log2s = 9 + round(log2(N/200))),
             holding agents-per-sector roughly constant, so equilibrium
             arc *level* stays put while absolute sector counts grow.

Reported per (N, series, scenario, variant):
  settle      ticks after disruption until the resize rate stays below
              N/200 per tick for 300 ticks (the Stage-1 "1 resize/tick
              at N=200" criterion, scaled to population)
  floor_min   worst redundancy floor after the disruption
  loss        sector-ticks at zero copies after the disruption
  exposure    sector-ticks below R after the disruption
  resizes/agent, sync/agent — the per-node cost of the control loop

Usage:   python3 scale_sim.py [--quick]
Output:  results/scale.png, results/scale_summary.md, results/scale.json
"""

from __future__ import annotations

import json
import multiprocessing as mp
import sys
import time

import numpy as np

from arc_sim import VARIANTS, Config, Sim, make_world
from ext_common import INK, MUTED, VARIANT_COLOR, plt, settle_tick

V1, V3 = VARIANTS[1], VARIANTS[3]

NS = [200, 500, 1000, 2000, 5000]
TICKS = 4200
STORM_AT = 2500


def cfg_for(n, series):
    log2s = 9 if series == "fixed" else 9 + round(np.log2(n / 200))
    return Config(n_agents=n, log2s=log2s)


def one_run(args):
    n, series, scen, vname = args
    cfg = cfg_for(n, series)
    variant = {v.name: v for v in VARIANTS}[vname]
    kw = {} if scen == "activation" else dict(storm_at=STORM_AT,
                                              storm_frac=0.30)
    t_dist = 0 if scen == "activation" else STORM_AT
    initial, events, joins = make_world(cfg, TICKS, **kw)
    t0 = time.time()
    sim = Sim(cfg, variant, events, initial, joins)
    m = sim.run(TICKS)
    dt = time.time() - t0
    S = cfg.sectors
    under = np.array(m.frac_under) * S
    zeros = np.array(m.zero_sectors)
    st = settle_tick(m.resizes, t_dist, rate=n / 200)
    row = {
        "n": n, "series": series, "scenario": scen, "variant": vname,
        "sectors": S,
        "settle": (st - t_dist) if st is not None else None,
        "floor_min": int(np.min(m.floor[t_dist:])),
        "exposure": int(under[t_dist:].sum()),
        "loss": int(zeros[t_dist:].sum()),
        "resizes_per_agent": float(np.sum(m.resizes) / n),
        "sync_per_agent": float(m.cum_sync[-1] / n),
        "mean_level_end": float(m.mean_level[-1]),
        "wall_s": round(dt, 1),
        "floor_series": [int(x) for x in m.floor[::4]],   # decimated for json
    }
    print(f"  N={n:5d} {series:7s} {scen:10s} {vname:24s} "
          f"settle={row['settle']} floor_min={row['floor_min']} "
          f"loss={row['loss']} ({dt:.0f}s)", flush=True)
    return row


def grid(quick):
    ns = [200, 1000] if quick else NS
    scens = ["storm"] if quick else ["activation", "storm"]
    jobs = []
    for n in ns:
        for series in ["fixed", "density"]:
            if n == 200 and series == "density":
                continue          # identical to fixed at N=200
            for scen in scens:
                for v in (V1, V3):
                    jobs.append((n, series, scen, v.name))
    return jobs


def plot(rows, out):
    fig, axes = plt.subplots(2, 2, figsize=(11, 6.6))
    fig.suptitle("Scale study: V1 vs V3, storm scenario (30% die at equilibrium)",
                 fontsize=12, fontweight="bold", color=INK)
    ax_settle, ax_floor, ax_res, ax_sync = axes.flat
    storm = [r for r in rows if r["scenario"] == "storm"]

    styles = {"fixed": "-", "density": "--"}
    for vname in (V1.name, V3.name):
        for series in ("fixed", "density"):
            pts = sorted([r for r in storm
                          if r["variant"] == vname and (
                              r["series"] == series or r["n"] == 200)],
                         key=lambda r: r["n"])
            if not pts:
                continue
            ns = [r["n"] for r in pts]
            c, ls = VARIANT_COLOR[vname], styles[series]
            label = f"{vname.split(' ')[0]} ({series})"
            ax_settle.plot(ns, [r["settle"] if r["settle"] is not None
                                else np.nan for r in pts],
                           color=c, ls=ls, lw=1.6, marker="o", ms=4, label=label)
            ax_floor.plot(ns, [r["floor_min"] for r in pts],
                          color=c, ls=ls, lw=1.6, marker="o", ms=4, label=label)
            ax_res.plot(ns, [r["resizes_per_agent"] for r in pts],
                        color=c, ls=ls, lw=1.6, marker="o", ms=4, label=label)
            ax_sync.plot(ns, [r["sync_per_agent"] for r in pts],
                         color=c, ls=ls, lw=1.6, marker="o", ms=4, label=label)

    ax_settle.set_title("Settle time after storm (ticks; gap = never)")
    ax_settle.set_ylabel("ticks")
    ax_floor.set_title("Worst redundancy floor after storm (0 = data loss)")
    ax_floor.set_ylabel("copies")
    ax_floor.axhline(0, color="#d03b3b", lw=0.8, alpha=0.5)
    ax_res.set_title("Resizes per agent (whole run)")
    ax_res.set_ylabel("resizes / agent")
    ax_sync.set_title("Sync cost per agent (whole run)")
    ax_sync.set_ylabel("sectors / agent")
    for ax in axes.flat:
        ax.set_xscale("log")
        ax.set_xlabel("agents N (log)")
        ax.grid(True, axis="y")
        ax.margins(x=0.02)
    ax_settle.legend(loc="upper left", fontsize=7)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"wrote {out}")


def main():
    quick = "--quick" in sys.argv
    jobs = grid(quick)
    workers = min(6, mp.cpu_count())
    print(f"{len(jobs)} runs on {workers} workers")
    with mp.Pool(workers) as pool:
        rows = pool.map(one_run, jobs)

    with open("results/scale.json", "w") as f:
        json.dump(rows, f)

    hdr = ["n", "sectors", "series", "scenario", "variant", "settle",
           "floor_min", "exposure", "loss", "resizes_per_agent",
           "sync_per_agent", "mean_level_end"]
    lines = ["| " + " | ".join(hdr) + " |",
             "|" + "|".join("---" for _ in hdr) + "|"]
    for r in sorted(rows, key=lambda r: (r["scenario"], r["series"],
                                         r["n"], r["variant"])):
        lines.append("| " + " | ".join(
            (f"{r[h]:.1f}" if isinstance(r[h], float) else str(r[h]))
            if r[h] is not None else "never" for h in hdr) + " |")
    table = "\n".join(lines)
    with open("results/scale_summary.md", "w") as f:
        f.write("# Scale study summary\n\n"
                "settle criterion scaled to population (rate < N/200 per "
                "tick for 300 ticks). loss/exposure = sector-ticks after "
                "the disruption.\n\n" + table + "\n")
    plot(rows, "results/scale.png")
    print("\n" + table)


if __name__ == "__main__":
    main()
