"""
Shared plotting style + metrics helpers for the Stage-3 extension studies
(partition_sim.py, byzantine_sim.py, scale_sim.py, race_quantify.py).

Kept separate from run_experiments.py so the Stage-1 artifacts stay
byte-identical; the palette and rcParams are the same validated set.
"""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# --- palette (dataviz reference instance, light mode; validated) --------
SERIES = ["#2a78d6", "#1baf7a", "#eda100", "#008300"]   # slots 1-4, fixed order
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
ALERT = "#d03b3b"

# Color follows the entity, never the slot: variants keep their Stage-1
# colors in every extension plot, even when only a subset is shown.
VARIANT_COLOR = {
    "V0 naive": SERIES[0],
    "V1 damped": SERIES[1],
    "V2 damped+jitter": SERIES[2],
    "V3 full (polite shrink)": SERIES[3],
}

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
