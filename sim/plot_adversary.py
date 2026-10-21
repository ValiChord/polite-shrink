"""Plot adversary results: attack strength by method per variant, the
recovery-floor traces under the evolved attack, and the search curves."""

import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

SERIES = ["#1baf7a", "#eda100", "#008300"]   # V1, V2, V3 (match main study)
METHOD = ["#c3c2b7", "#3987e5", "#d03b3b"]   # storm / random-search / evolved
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

data = json.load(open("results/adversary.json"))
names = [d["variant"].split()[0] for d in data]

fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(13, 4.4))
fig.suptitle("A learning adversary vs the three damped controllers "
             "(same budget: 60 targeted kills, 30% of the network)",
             fontsize=12, fontweight="bold", color=INK)

# Panel 1: data loss (sector-ticks at zero copies) by attack method
x = np.arange(len(data)); w = 0.26
methods = [("storm", "uniform random storm"),
           ("random_best", "best of 40 random"),
           ("evolved", "evolved attack")]
for i, (key, lab) in enumerate(methods):
    vals = [d[key]["loss"] for d in data]
    bars = ax1.bar(x + (i - 1) * w, vals, w, color=METHOD[i], label=lab,
                   zorder=3)
    for b, v in zip(bars, vals):
        if v > 0:
            ax1.text(b.get_x() + w / 2, v + 60, f"{v:,}", ha="center",
                     fontsize=7.5, color=INK2)
ax1.set_xticks(x); ax1.set_xticklabels(names)
ax1.set_ylabel("sector-ticks at zero copies (data loss)")
ax1.set_title("Data loss by attack method")
ax1.legend(fontsize=8, loc="upper left")
ax1.grid(True, axis="y", zorder=0)

# Panel 2: recovery floor under the evolved attack
for i, d in enumerate(data):
    f = d["floors_evolved"]
    ax2.plot(np.arange(len(f)), f, color=SERIES[i], lw=1.6, label=names[i])
ax2.axhline(5, color=BASE, ls="--", lw=1)
ax2.text(len(data[0]["floors_evolved"]) - 5, 5.4, "target R = 5", ha="right",
         fontsize=8, color=MUTED)
ax2.axhline(0, color="#d03b3b", lw=0.9, alpha=0.6)
ax2.text(5, 0.4, "0 = data loss", fontsize=8, color="#d03b3b", alpha=0.8)
ax2.axvline(0, color=MUTED, ls=":", lw=0.9)
ax2.set_ylim(-0.6, 14)
ax2.set_xlabel("ticks after attack begins")
ax2.set_ylabel("min copies of any sector")
ax2.set_title("Redundancy floor under the evolved attack")
ax2.legend(fontsize=8, loc="upper right")
ax2.grid(True, axis="y")

# Panel 3: evolutionary search curves (loss component of fitness)
for i, d in enumerate(data):
    curve = [c // 1_000_000 for c in d["curve"]]   # loss component
    ax3.plot(np.arange(len(curve)), curve, color=SERIES[i], lw=1.8,
             marker="o", ms=3, label=names[i])
ax3.set_xlabel("generation")
ax3.set_ylabel("best attack: sector-ticks of data loss")
ax3.set_title("Adversary learning curve")
ax3.legend(fontsize=8, loc="center right")
ax3.grid(True, axis="y")

fig.tight_layout(rect=[0, 0, 1, 0.94])
fig.savefig("results/adversary.png", dpi=150)
print("wrote results/adversary.png")
