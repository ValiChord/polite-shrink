"""Plot the robustness sweep: pooled data-loss rate with 95% bounds, the
under-replication spread across seeds, and per-scenario loss rates."""

import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from polite_shrink import VARIANTS

SERIES = {"V0 naive": "#e34948", "V1 damped": "#1baf7a",
          "V2 damped+jitter": "#eda100", "V3 full (polite shrink)": "#008300"}
SURFACE = "#fcfcfb"; INK = "#0b0b0b"; INK2 = "#52514e"
MUTED = "#898781"; GRID = "#e1e0d9"; BASE = "#c3c2b7"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "text.color": INK, "axes.labelcolor": INK2,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.edgecolor": BASE, "axes.linewidth": 0.8,
    "grid.color": GRID, "grid.linewidth": 0.6,
    "font.family": "sans-serif", "font.size": 9,
    "axes.titlesize": 10, "axes.titleweight": "bold", "legend.frameon": False,
})

d = json.load(open("results/sweep.json"))
names = [v.name for v in VARIANTS]
short = [n.split()[0] for n in names]
colors = [SERIES[n] for n in names]

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.6))
fig.suptitle(f"Robustness across {d['cells_done']} independent world-realisations "
             f"({d['n_sims']:,} simulations)",
             fontsize=12, fontweight="bold", color=INK)

# Panel 1: pooled data-loss rate, with the 95% upper bound as a cap
x = np.arange(len(names))
rates = [d["pooled"][n]["loss_rate"] * 100 for n in names]
uppers = [d["pooled"][n]["loss_rate_upper95"] * 100 for n in names]
bars = ax1.bar(x, rates, 0.6, color=colors, zorder=3)
for xi, r, u in zip(x, rates, uppers):
    ax1.plot([xi, xi], [r, u], color=INK2, lw=1.2, zorder=4)
    ax1.plot([xi - 0.08, xi + 0.08], [u, u], color=INK2, lw=1.2, zorder=4)
    lab = f"{r:.1f}%" if r > 0 else f"0%\n(<{u:.2f}%)"
    ax1.text(xi, u + 2.5, lab, ha="center", fontsize=8.5, color=INK2)
ax1.set_xticks(x); ax1.set_xticklabels(short)
ax1.set_ylabel("% of worlds with any data loss")
ax1.set_ylim(0, 108)
ax1.set_title("Data-loss rate (pooled, all scenarios)")
ax1.grid(True, axis="y", zorder=0)
n_each = d["pooled"][names[0]]["n"]
ax1.text(0.02, 0.97, f"n = {n_each} worlds/variant\ncaps = 95% upper bound",
         transform=ax1.transAxes, va="top", fontsize=8, color=MUTED)

# Panel 2: per-scenario loss rate, grouped
scen = ["activation", "storm", "flashcrowd", "churn"]
w = 0.2
for i, n in enumerate(names):
    vals = [d["per_scenario"][f"{s}|{n}"]["loss_rate"] * 100 for s in scen]
    ax2.bar(np.arange(len(scen)) + (i - 1.5) * w, vals, w,
            color=SERIES[n], label=short[i], zorder=3)
ax2.set_xticks(np.arange(len(scen))); ax2.set_xticklabels(scen)
ax2.set_ylabel("% of worlds with any data loss")
ax2.set_title("Data-loss rate by scenario")
ax2.legend(fontsize=8, ncol=2)
ax2.grid(True, axis="y", zorder=0)

fig.tight_layout(rect=[0, 0, 1, 0.93])
fig.savefig("results/sweep.png", dpi=150)
print("wrote results/sweep.png")
