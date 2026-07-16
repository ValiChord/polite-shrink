"""Plot rolling-upgrade results: data-loss rate vs upgraded fraction.

Reads results/rolling_upgrade_cells.jsonl (written by rolling_upgrade_sweep.py)
and produces results/rolling_upgrade.png — loss rate (%) vs upgraded fraction
f, one line per scenario, with the naive-node count on a secondary annotation.
"""

import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

RES = os.path.join(os.path.dirname(__file__), "results")
CELLS = os.path.join(RES, "rolling_upgrade_cells.jsonl")

rows = [json.loads(l) for l in open(CELLS)]
scenarios = sorted({r["scenario"] for r in rows})
fractions = sorted({r["fraction"] for r in rows})

fig, ax = plt.subplots(figsize=(8, 5))
for sc in scenarios:
    xs, ys = [], []
    for f in fractions:
        cells = [r for r in rows if r["scenario"] == sc and r["fraction"] == f]
        xs.append(f)
        ys.append(100 * sum(c["any_loss"] for c in cells) / len(cells))
    ax.plot([100 * x for x in xs], ys, marker="o", label=sc)

ax.set_xlabel("network upgraded to polite shrink (%)")
ax.set_ylabel("runs with data loss (%)")
ax.set_title("Rolling upgrade: does a naive minority reintroduce data loss?")
ax.grid(True, alpha=0.3)
ax.legend()
n_seeds = len({r["seed"] for r in rows})
ax.text(0.02, 0.02, f"{n_seeds} seeds/point; V0 naive + V3 polite mix",
        transform=ax.transAxes, fontsize=8, alpha=0.6)
out = os.path.join(RES, "rolling_upgrade.png")
fig.tight_layout()
fig.savefig(out, dpi=130)
print(f"wrote {out}")
