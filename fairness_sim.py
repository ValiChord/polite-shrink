"""
Stage-3 follow-up: rotating the tie-break priority — fairness without
losing the safety proof?

V3's lowest-id-proceeds tie-break systematically lets low-id agents
shrink first, so high-id agents end up holding bigger arcs: equilibrium
level distributions are strongly skewed (we relied on this accidentally
in the §6.2 study — the skew's big arcs gave the cascade global reach).
The skew is a storage-fairness problem for real deployments.

Candidate fix (V3F): replace the static id order with a deterministic
per-epoch permutation — priority key = hash(aid, t // P). The tie-break
only needs to be *deterministic and agreed*, not fixed... but "agreed"
is exactly what an epoch boundary threatens: two contenders evaluating
their intents on opposite sides of a boundary can each see the other as
lower-priority and both proceed. The Stage-1 safety result was proven
with the fixed ordering, so the rotation must re-earn it:

  - safety sweep: storm + churn x 48 seeds x {V3, V3F P=200, V3F P=50}.
    P=200 = 4x the intent wait (boundaries rare relative to intent
    lifetimes); P=50 = every intent straddles a boundary (deliberate
    stress). Loss must stay zero at the safe P; the stress P
    characterises how bad boundary disagreement can get.
  - fairness measurement: correlation(aid rank, level) and the level
    spread at equilibrium — V3 should show the skew, V3F should
    flatten it.

Usage:   python3 fairness_sim.py [--quick]
Output:  results/fairness.png, results/fairness_summary.md,
         results/fairness.json
"""

from __future__ import annotations

import json
import multiprocessing as mp
import sys

import numpy as np

from polite_shrink import VARIANTS, Config, Sim, make_world, vacate_half
from ext_common import BASELINE, INK, MUTED, SERIES, VARIANT_COLOR, plt

V3 = VARIANTS[3]
V3F_COLORS = {200: SERIES[0], 50: SERIES[2]}   # V3 keeps its green


class RotatingSim(Sim):
    """V3 with the execute-time priority rotated per epoch.

    key(aid) = (hash(aid, t//P), aid) — deterministic, portable, total.
    Everything else (announce, wait, count-lower-priority-as-gone) is
    unchanged from Sim._execute_intent.
    """

    def __init__(self, *a, period=200, **kw):
        self.period = period
        super().__init__(*a, **kw)

    def _key(self, aid):
        e = self.t // self.period
        return ((aid * 2654435761 + e * 40503 + 12582917) & 0xFFFFFFFF, aid)

    def _execute_intent(self, a):
        cfg = self.cfg
        cov, lvl, _icov, ilist = self._view(a)
        vs, ve = vacate_half(a.home, a.level, cfg.log2s)
        eff = cov[vs:ve].astype(np.int32)
        if int(lvl[a.aid]) >= a.level:
            eff -= 1
        my_key = self._key(a.aid)
        for aid2, s2, e2 in ilist:
            if self._key(aid2) < my_key:     # rotated priority
                lo, hi = max(vs, s2), min(ve, e2)
                if lo < hi:
                    eff[lo - vs:hi - vs] -= 1
        if bool(eff.min() >= cfg.redundancy):
            self._do_shrink(a)
        else:
            a.intent_at = -1
            a.shrink_acc = 0


def make_sim(name, cfg, events, initial, joins):
    if name == "V3":
        return Sim(cfg, V3, events, initial, joins)
    period = int(name.split("P=")[1])
    return RotatingSim(cfg, V3, events, initial, joins, period=period)


NAMES = ["V3", "V3F P=200", "V3F P=50"]


# ------------------------------------------------------------- safety
def one_safety(args):
    name, scen, seed = args
    cfg = Config(seed=seed)
    ticks, t_dist, kw = {
        "storm": (3000, 1500, dict(storm_at=1500, storm_frac=0.30)),
        "churn": (3000, 1200, dict(churn_from=1200, churn_death_p=0.0004)),
    }[scen]
    initial, events, joins = make_world(cfg, ticks, **kw)
    sim = make_sim(name, cfg, events, initial, joins)
    m = sim.run(ticks)
    S = cfg.sectors
    return {
        "variant": name, "scenario": scen, "seed": seed,
        "loss": int(np.sum(np.array(m.zero_sectors[t_dist:]))),
        "exposure": int((np.array(m.frac_under[t_dist:]) * S).sum()),
        "floor_min": int(min(m.floor[t_dist:])),
    }


def run_safety(seeds, workers=6):
    jobs = [(n, s, seed) for n in NAMES for s in ("storm", "churn")
            for seed in seeds]
    with mp.Pool(min(workers, mp.cpu_count())) as pool:
        rows = pool.map(one_safety, jobs)
    agg = {}
    for n in NAMES:
        for s in ("storm", "churn"):
            cell = [r for r in rows if r["variant"] == n
                    and r["scenario"] == s]
            agg[(n, s)] = {
                "runs": len(cell),
                "runs_with_loss": sum(1 for r in cell if r["loss"]),
                "loss_total": sum(r["loss"] for r in cell),
                "floor_min_worst": min(r["floor_min"] for r in cell),
                "exposure_mean": float(np.mean([r["exposure"]
                                                for r in cell])),
            }
            a = agg[(n, s)]
            print(f"  {n:10s} {s:6s} loss in {a['runs_with_loss']}/"
                  f"{a['runs']} runs (total {a['loss_total']} sector-ticks) "
                  f"worst_floor={a['floor_min_worst']} "
                  f"exposure_mean={a['exposure_mean']:.0f}", flush=True)
    return rows, agg


# ------------------------------------------------------------ fairness
def one_fairness(args):
    name, seed = args
    cfg = Config(seed=seed)
    ticks = 2600
    initial, events, joins = make_world(cfg, ticks)
    sim = make_sim(name, cfg, events, initial, joins)
    sim.run(ticks)
    lv = np.array([a.level for a in sim.agents if a.alive], dtype=float)
    aid = np.array([a.aid for a in sim.agents if a.alive], dtype=float)
    width = 2.0 ** lv          # sectors held (fairness is about storage)
    return {
        "variant": name, "seed": seed,
        "corr_aid_level": float(np.corrcoef(aid, lv)[0, 1]),
        "level_std": float(lv.std()),
        "top_decile_share": float(np.sort(width)[-len(width) // 10:].sum()
                                  / width.sum()),
        "levels": [int(x) for x in lv],
    }


def run_fairness(seeds, workers=6):
    jobs = [(n, seed) for n in NAMES for seed in seeds]
    with mp.Pool(min(workers, mp.cpu_count())) as pool:
        rows = pool.map(one_fairness, jobs)
    for n in NAMES:
        cell = [r for r in rows if r["variant"] == n]
        print(f"  {n:10s} corr(aid,level)="
              f"{np.mean([r['corr_aid_level'] for r in cell]):+.3f} "
              f"level_std={np.mean([r['level_std'] for r in cell]):.2f} "
              f"top-10% storage share="
              f"{np.mean([r['top_decile_share'] for r in cell]):.1%}",
              flush=True)
    return rows


# ------------------------------------------------------------- plots
def plot(safety_rows, fair_rows, out):
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2))
    fig.suptitle("Rotating the tie-break: storage fairness vs the safety "
                 "guarantee", fontsize=12, fontweight="bold", color=INK)
    ax_loss, ax_hist, ax_share = axes.flat

    colors = {"V3": VARIANT_COLOR[V3.name],
              "V3F P=200": V3F_COLORS[200], "V3F P=50": V3F_COLORS[50]}

    x = np.arange(2)
    w = 0.25
    for i, n in enumerate(NAMES):
        vals = []
        for s in ("storm", "churn"):
            cell = [r for r in safety_rows if r["variant"] == n
                    and r["scenario"] == s]
            vals.append(sum(1 for r in cell if r["loss"]))
        ax_loss.bar(x + (i - 1) * w, vals, w, color=colors[n],
                    edgecolor=INK, lw=0.4, label=n)
    ax_loss.set_xticks(x)
    ax_loss.set_xticklabels(["storm", "churn"])
    n_seeds = len(safety_rows) // len(NAMES) // 2
    ax_loss.set_title(f"Runs with data loss (of {n_seeds} seeds)")
    ax_loss.set_ylabel("runs")
    ax_loss.set_ylim(0, max(1, ax_loss.get_ylim()[1]))
    if not any(r["loss"] for r in safety_rows):
        ax_loss.text(0.5, 0.5, f"zero losses in all {len(safety_rows)} runs\n"
                     "(including the P=50 boundary stress)",
                     transform=ax_loss.transAxes, ha="center", va="center",
                     color=INK, fontsize=9)
    ax_loss.legend(fontsize=8)

    bins = np.arange(-0.5, 10.5, 1)
    for n in NAMES:
        lv = [x for r in fair_rows if r["variant"] == n for x in r["levels"]]
        ax_hist.hist(lv, bins=bins, histtype="step", lw=1.8,
                     color=colors[n], label=n)
    ax_hist.set_title("Equilibrium level distribution (all seeds pooled)")
    ax_hist.set_xlabel("arc level")
    ax_hist.set_ylabel("agents")
    ax_hist.legend(fontsize=8)

    for i, n in enumerate(NAMES):
        cell = [r["top_decile_share"] for r in fair_rows
                if r["variant"] == n]
        ax_share.bar(i, float(np.mean(cell)), 0.6, color=colors[n],
                     edgecolor=INK, lw=0.4)
        ax_share.errorbar(i, float(np.mean(cell)), yerr=float(np.std(cell)),
                          color=INK, capsize=3, lw=1)
    ax_share.axhline(0.10, color=BASELINE, lw=1, ls="--")
    ax_share.text(0.02, 0.115, "perfect equality = 10%", color=MUTED,
                  fontsize=8, transform=ax_share.get_yaxis_transform())
    ax_share.set_xticks(range(len(NAMES)))
    ax_share.set_xticklabels(NAMES, fontsize=8)
    ax_share.set_title("Storage share held by the top decile of agents")
    ax_share.set_ylabel("fraction of all held sectors")

    for ax in axes.flat:
        ax.grid(True, axis="y")
        ax.margins(x=0.02)
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"wrote {out}")


def main():
    quick = "--quick" in sys.argv
    safety_seeds = list(range(1, 9 if quick else 49))
    fair_seeds = list(range(1, 5 if quick else 9))

    print("study: safety sweep")
    safety_rows, agg = run_safety(safety_seeds)
    print("study: fairness at equilibrium")
    fair_rows = run_fairness(fair_seeds)

    with open("results/fairness.json", "w") as f:
        json.dump({"safety": safety_rows,
                   "fairness": fair_rows,
                   "note": "V3F key = (aid*2654435761 + (t//P)*40503 "
                           "+ 12582917) & 0xFFFFFFFF"}, f)

    with open("results/fairness_summary.md", "w") as f:
        f.write("# Rotating tie-break (V3F) — safety and fairness\n\n"
                "## Safety sweep\n\n"
                "| variant | scenario | runs with loss | loss sector-ticks "
                "| worst floor | mean exposure |\n|---|---|---|---|---|---|\n")
        for (n, s), a in agg.items():
            f.write(f"| {n} | {s} | {a['runs_with_loss']}/{a['runs']} | "
                    f"{a['loss_total']} | {a['floor_min_worst']} | "
                    f"{a['exposure_mean']:.0f} |\n")
        f.write("\n## Fairness at equilibrium (no disruption, t=2600)\n\n"
                "| variant | corr(aid, level) | level std | top-decile "
                "storage share |\n|---|---|---|---|\n")
        for n in NAMES:
            cell = [r for r in fair_rows if r["variant"] == n]
            f.write(f"| {n} | "
                    f"{np.mean([r['corr_aid_level'] for r in cell]):+.3f} | "
                    f"{np.mean([r['level_std'] for r in cell]):.2f} | "
                    f"{np.mean([r['top_decile_share'] for r in cell]):.1%} |\n")
    print("wrote results/fairness_summary.md")
    plot(safety_rows, fair_rows, "results/fairness.png")


if __name__ == "__main__":
    main()
