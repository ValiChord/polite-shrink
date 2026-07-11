"""
Run the four controller variants through four scenarios and produce
comparison plots + a summary table.

Usage:  python3 run_experiments.py [--quick]
Output: results/<scenario>.png, results/summary.md
"""

from __future__ import annotations

import sys
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from arc_sim import VARIANTS, Config, Sim, make_world

# --- palette (dataviz reference instance, light mode) -------------------
SERIES = ["#2a78d6", "#1baf7a", "#eda100", "#008300"]   # slots 1-4, fixed order
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "text.color": INK, "axes.labelcolor": INK_2,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.edgecolor": BASELINE, "axes.linewidth": 0.8,
    "grid.color": GRID, "grid.linewidth": 0.6,
    "font.family": "sans-serif", "font.size": 9,
    "axes.titlesize": 10, "axes.titleweight": "bold",
    "legend.frameon": False,
})


def rolling(x, w=100):
    x = np.asarray(x, dtype=float)
    if len(x) < w:
        return x
    c = np.cumsum(np.insert(x, 0, 0.0))
    out = (c[w:] - c[:-w]) / w
    return np.concatenate([np.full(w - 1, np.nan), out])


def settle_tick(resizes, t_dist, rate=1.0, hold=300):
    """First tick >= t_dist where the rolling-100 resize rate stays < `rate`
    for `hold` consecutive ticks. None if never."""
    r = rolling(resizes)
    ok = r < rate
    run = 0
    for t in range(t_dist, len(ok)):
        run = run + 1 if ok[t] else 0
        if run >= hold:
            return t - hold + 1
    return None


def summarize(name, m, cfg, t_dist):
    S = cfg.sectors
    under = np.array(m.frac_under) * S
    zeros = np.array(m.zero_sectors)
    post = slice(t_dist, None)
    st = settle_tick(m.resizes, t_dist)
    return {
        "variant": name,
        "settle": (st - t_dist) if st is not None else None,
        "floor_min": int(np.min(m.floor[t_dist:])),
        "exposure": int(under[post].sum()),      # sector-ticks below R
        "loss": int(zeros[post].sum()),          # sector-ticks at zero copies
        "resizes": int(np.sum(m.resizes)),
        "sync_cost": int(m.cum_sync[-1]),
    }


def run_scenario(label, ticks, t_dist, world_kw, cfg):
    initial, events, joins = make_world(cfg, ticks, **world_kw)
    results = {}
    for v in VARIANTS:
        t0 = time.time()
        sim = Sim(cfg, v, events, initial, joins)
        m = sim.run(ticks)
        results[v.name] = m
        print(f"  {label:12s} {v.name:24s} {time.time()-t0:5.1f}s "
              f"floor_min(post)={min(m.floor[t_dist:])} "
              f"resizes={sum(m.resizes)}")
    return results


def plot_scenario(label, title, results, cfg, t_dist, out):
    fig, axes = plt.subplots(2, 2, figsize=(11, 6.6))
    fig.suptitle(title, fontsize=12, fontweight="bold", color=INK)
    ax_floor, ax_rate, ax_lvl, ax_cost = axes.flat

    for i, (name, m) in enumerate(results.items()):
        c = SERIES[i]
        ax_floor.plot(m.floor, color=c, lw=1.6, label=name)
        ax_rate.plot(rolling(m.resizes), color=c, lw=1.6, label=name)
        ax_lvl.plot(m.mean_level, color=c, lw=1.6, label=name)
        ax_cost.plot(np.array(m.cum_sync) / 1000, color=c, lw=1.6, label=name)

    ax_floor.axhline(cfg.redundancy, color=BASELINE, lw=1, ls="--")
    ax_floor.text(0.02, cfg.redundancy + 0.6, f"target R = {cfg.redundancy}",
                  transform=ax_floor.get_yaxis_transform(),
                  ha="left", fontsize=8, color=MUTED)
    ax_floor.axhline(0, color="#d03b3b", lw=0.8, alpha=0.5)
    ax_floor.text(0.02, 0.6, "0 = data loss", transform=ax_floor.get_yaxis_transform(),
                  ha="left", fontsize=8, color="#d03b3b", alpha=0.8)
    ax_floor.set_ylim(-0.8, 25)
    ax_floor.set_title("Redundancy floor (min copies of any sector; y clipped at 25)")
    ax_floor.set_ylabel("copies")

    ax_rate.set_title("Arc-resize rate (rolling 100-tick mean)")
    ax_rate.set_ylabel("resizes / tick")

    ax_lvl.set_title("Mean arc level (9 = full ring, log2 sectors)")
    ax_lvl.set_ylabel("level")

    ax_cost.set_title("Cumulative sync cost (k sector-fetches)")
    ax_cost.set_ylabel("k sectors")

    for ax in axes.flat:
        ax.grid(True, axis="y")
        ax.set_xlabel("tick")
        ax.margins(x=0.01)
        if t_dist > 0:
            ax.axvline(t_dist, color=MUTED, lw=0.9, ls=":")
    ax_floor.legend(loc="upper right", fontsize=8)

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  wrote {out}")


SCENARIOS = [
    # (key, title, ticks, t_disruption, world kwargs)
    ("activation",
     "Sharding activates on a full-arc network (200 agents shrink toward R=5)",
     2200, 0, {}),
    ("storm",
     "Churn storm: 30% of agents die at once (tick 1500, post-settle)",
     3000, 1500, dict(storm_at=1500, storm_frac=0.30)),
    ("flashcrowd",
     "Flash crowd: 60% more agents join at once (tick 1500)",
     3000, 1500, dict(crowd_at=1500, crowd_frac=0.60)),
    ("churn",
     "Continuous churn from tick 1200 (~4% population turnover / 100 ticks)",
     3000, 1200, dict(churn_from=1200, churn_death_p=0.0004)),
]


def main():
    quick = "--quick" in sys.argv
    cfg = Config()
    rows = []
    for key, title, ticks, t_dist, kw in SCENARIOS:
        if quick and key != "storm":
            continue
        print(f"scenario: {key}")
        results = run_scenario(key, ticks, t_dist, kw, cfg)
        plot_scenario(key, title, results, cfg, t_dist, f"results/{key}.png")
        for name, m in results.items():
            rows.append({"scenario": key, **summarize(name, m, cfg, t_dist)})

    # summary table
    hdr = ["scenario", "variant", "settle", "floor_min", "exposure",
           "loss", "resizes", "sync_cost"]
    lines = ["| " + " | ".join(hdr) + " |",
             "|" + "|".join("---" for _ in hdr) + "|"]
    for r in rows:
        lines.append("| " + " | ".join(
            str(r[h]) if r[h] is not None else "never" for h in hdr) + " |")
    table = "\n".join(lines)
    with open("results/summary.md", "w") as f:
        f.write("# Arc-controller simulation summary\n\n"
                "settle = ticks after disruption until resize rate stays "
                "< 1/tick for 300 ticks; floor_min = worst redundancy floor "
                "after disruption; exposure = sector-ticks below R; loss = "
                "sector-ticks at zero copies (data loss); sync_cost = total "
                "sectors fetched+validated.\n\n" + table + "\n")
    print("\n" + table)


if __name__ == "__main__":
    main()
