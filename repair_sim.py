"""
Stage-3e: the §6.2 global under-coverage repair rule, simulated before
implementation — exactly as REPORT.md §6.2 requires.

The problem. Quantised growth is sibling-half-local: an agent can only
double its aligned block, so growth cannot be *steered* toward a distant
thin region. In sparse networks (§6.2 observed 5 survivors) a hole can sit
in nobody's sibling half and recovery deadlocks; today the only rescue is
the small-network clamp, which forces every survivor to a FULL arc — safe
but maximally expensive, and it makes `clamp_min_peers` a safety parameter.

The rule under test (V4 = V3 + expanding-ring repair). A distant hole
cannot be reached directly, but repeated doubling reaches everywhere —
so let distant holes *motivate* growth, with a distance-staggered fuse to
prevent the feared thundering herd:

    An agent reacts to an under-covered sector inside its level+g
    ancestor block (g >= 2; g = 1 is V3's native sibling-half check)
    only after the condition has persisted grow_need + (g-1) * 2*lag
    ticks. Ring-near agents therefore move first; if they close the
    hole, everyone further out resets and never grows.

Growth stays quantised, local-information-only, and hysteresis-gated;
the rule adds no new message types.

Studies:
  1. sparse-deadlock: at t=1500 kill all but k in {5, 15} survivors,
     30 seeds x {V3, V4} x {clamp 0, clamp 25}. Does V4 remove the
     clamp dependency (recover with clamp=0), and at what cost vs the
     clamp's everyone-full response?
  2. dense overshoot probe: at equilibrium kill every holder of one
     sector; count how many agents grow in response (herd check) and
     time-to-recovery, V3 vs V4.
  3. regression battery: the four Stage-1 scenarios, V3 vs V4, seeds
     42/7/99/1234 on storm+churn — loss must stay zero and cost deltas
     small (this is "dynamics the sweep never validated", validated).

Usage:   python3 repair_sim.py [--quick]
Output:  results/repair_deadlock.png, results/repair_summary.md,
         results/repair.json
"""

from __future__ import annotations

import json
import math
import multiprocessing as mp
import sys
from collections import defaultdict

import numpy as np

from arc_sim import VARIANTS, Config, Sim, block, make_world
from ext_common import (ALERT, BASELINE, INK, MUTED, SERIES, VARIANT_COLOR,
                        plt)

V3 = VARIANTS[3]
V4_NAME = "V4 polite+repair"
V4_COLOR = SERIES[0]          # new entity; V3 keeps its Stage-1 green
REPAIR_STAGGER_K = 2.0        # extra persistence per ring, x own lag


class RepairSim(Sim):
    """V3 plus the expanding-ring repair rule."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.repair_acc = defaultdict(int)   # aid -> persistence ticks
        self.n_repair_grows = 0

    def _decide(self, a):
        super()._decide(a)
        cfg = self.cfg
        # Only when V3 decided nothing: no grow in flight, no intent
        # pending (a pending intent delays repair by <= intent_delay —
        # accepted for simplicity), not already full.
        if a.sync_until >= 0 or a.intent_at >= 0 or a.level >= cfg.log2s:
            self.repair_acc[a.aid] = 0
            return
        cov, _lvl, icov, _ilist = self._view(a)
        eff = (cov - icov).astype(np.int32)
        # Holes inside my own block can't be fixed by my growth, and holes
        # in the sibling half are V3's native grow condition: mask my
        # level+1 parent block, scan only g >= 2 rings.
        p1s, p1e = block(a.home, a.level + 1, cfg.log2s)
        for g in range(2, cfg.log2s - a.level + 1):
            ps, pe = block(a.home, a.level + g, cfg.log2s)
            seg = eff[ps:pe].copy()
            seg[p1s - ps:p1e - ps] = cfg.redundancy
            if int(seg.min()) < cfg.redundancy:
                self.repair_acc[a.aid] += cfg.eval_every
                need = (math.ceil(cfg.grow_k * a.lag)
                        + (g - 1) * math.ceil(REPAIR_STAGGER_K * a.lag))
                if self.repair_acc[a.aid] >= need:
                    self._start_grow(a)
                    self.n_repair_grows += 1
                    self.repair_acc[a.aid] = 0
                return
        self.repair_acc[a.aid] = 0


def make_sim(name, cfg, events, initial, joins):
    cls = RepairSim if name == V4_NAME else Sim
    return cls(cfg, V3, events, initial, joins)


# ---------------------------------------------------- 1. sparse deadlock
def deadlock_world(cfg, ticks, n_survivors, seed, clustered=False):
    """Kill all but n_survivors at t=1500. `clustered=False` picks
    survivors at random (holes everywhere -> the native sibling-half
    cascade engages). `clustered=True` picks survivors whose homes all
    lie in the lower half-ring — the §6.2 geometry: the lower half can
    satisfy every survivor's sibling half at moderate levels, while the
    upper half sits under-covered in *nobody's* sibling half."""
    initial, events, joins = make_world(cfg, ticks)
    rng = np.random.default_rng(seed)
    pool = ([i for i, (h, _) in enumerate(initial) if h < cfg.sectors // 2]
            if clustered else list(range(cfg.n_agents)))
    survivors = set(int(x) for x in
                    rng.choice(pool, n_survivors, replace=False))
    events[1500] = [a for a in range(cfg.n_agents) if a not in survivors]
    return initial, events, joins


DEADLOCK_CASES = [
    # (label, clustered, n_survivors, n_agents, R)
    # N=200/R=5 cases probe whether the deadlock appears at Stage-1 scale;
    # sparse-8@R2 reproduces the regime the port actually observed it in
    # (8 nodes, R=2, homogeneous arc sizes — §6.2).
    ("random-5", False, 5, 200, 5),
    ("random-15", False, 15, 200, 5),
    ("clustered-15", True, 15, 200, 5),
    ("sparse-8@R2", False, 5, 8, 2),
]


def _deadlock_one(job):
    label, clustered, n_surv, n_agents, r, clamp, name, seed, ticks = job
    cfg = Config(clamp_min_peers=clamp, seed=seed,
                 n_agents=n_agents, redundancy=r)
    initial, events, joins = deadlock_world(
        cfg, ticks, n_surv, seed + 500, clustered)
    sim = make_sim(name, cfg, events, initial, joins)
    m = sim.run(ticks)
    fu = m.frac_under
    rec = next((t for t in range(1520, ticks) if fu[t] == 0.0), None)
    return {
        "case": label, "clamp": clamp, "variant": name,
        "rec": (rec - 1500) if rec is not None else None,
        # stuck = still under-covered AND resize activity has ceased
        "stuck": rec is None and sum(m.resizes[-300:]) == 0,
        "sync": m.cum_sync[-1] - m.cum_sync[1500],
        "floor": int(min(m.floor[1520:])),
    }


def run_deadlock(seeds, ticks=3200, workers=6):
    jobs = []
    for label, clustered, n_surv, n_agents, r in DEADLOCK_CASES:
        # the 8-node runs are ~50x cheaper; use 3x the seeds to pin
        # down the (low) deadlock frequency
        case_seeds = (seeds if n_agents > 8 else
                      [s + 1000 * k for k in range(3) for s in seeds])
        for clamp in (0, 25):
            for name in (V3.name, V4_NAME):
                for seed in case_seeds:
                    jobs.append((label, clustered, n_surv, n_agents, r,
                                 clamp, name, seed, ticks))
    with mp.Pool(min(workers, mp.cpu_count())) as pool:
        outs = pool.map(_deadlock_one, jobs)

    rows = []
    for label, *_ in DEADLOCK_CASES:
        for clamp in (0, 25):
            for name in (V3.name, V4_NAME):
                cell = [o for o in outs if o["case"] == label
                        and o["clamp"] == clamp and o["variant"] == name]
                recs = [o["rec"] for o in cell if o["rec"] is not None]
                row = {
                    "case": label, "clamp": clamp, "variant": name,
                    "recovered": len(recs), "runs": len(cell),
                    "stuck": sum(1 for o in cell if o["stuck"]),
                    "rec_median": float(np.median(recs)) if recs else None,
                    "sync_post_mean": float(np.mean([o["sync"]
                                                     for o in cell])),
                    "floor_min_worst": int(min(o["floor"] for o in cell)),
                }
                rows.append(row)
                print(f"  {label:13s} clamp={clamp:2d} {name:18s} "
                      f"recovered {row['recovered']}/{row['runs']} "
                      f"stuck={row['stuck']} "
                      f"median_rec={row['rec_median']} "
                      f"sync={row['sync_post_mean']:.0f}", flush=True)
    return rows


# ------------------------------------------------- 2. dense overshoot
def _count_growers(sim, until, window_end):
    """Advance sim to `until`, returning the set of agents that STARTED a
    grow inside [window_start=sim.t, window_end)."""
    grew = set()
    while sim.t < until:
        pre = {a.aid: a.sync_until for a in sim.agents}
        sim.step()
        if sim.t - 1 < window_end:
            for a in sim.agents:
                if a.sync_until >= 0 and pre.get(a.aid, -1) < 0:
                    grew.add(a.aid)
    return grew


def run_overshoot(seeds, ticks=2600, kill_at=1500, window=300):
    """Kill every declared holder of one sector at equilibrium. Herd
    check: growers within `window` ticks of the kill, minus the growers
    a matched no-kill control produces in the same window (ordinary
    hunting is not 'response')."""
    rows = []
    for name in (V3.name, V4_NAME):
        delta_n, rec_ticks, extra_sync, kills = [], [], [], []
        for seed in seeds:
            cfg = Config(seed=seed)
            initial, events, joins = make_world(cfg, ticks)
            probe = make_sim(name, cfg, events, initial, joins)
            control = make_sim(name, cfg, dict(events), initial, joins)
            for _ in range(kill_at):
                probe.step()
            cov_now = probe.cov_h[(probe.t - 1) % probe.H]
            k0 = int(np.argmin(cov_now))
            victims = [a.aid for a in probe.agents
                       if a.alive and block(a.home, a.level, cfg.log2s)[0]
                       <= k0 < block(a.home, a.level, cfg.log2s)[1]]
            sync_before = probe.sync_cost
            probe.events = {kill_at: victims}
            grew = set()
            rec = None
            while probe.t < ticks:
                pre = {a.aid: a.sync_until for a in probe.agents}
                probe.step()
                if probe.t - 1 < kill_at + window:
                    for a in probe.agents:
                        if a.sync_until >= 0 and pre.get(a.aid, -1) < 0:
                            grew.add(a.aid)
                cov = probe.cov_h[(probe.t - 1) % probe.H]
                if rec is None and cov[k0] >= cfg.redundancy:
                    rec = probe.t - 1 - kill_at
            for _ in range(kill_at):
                control.step()
            base = _count_growers(control, kill_at + window, kill_at + window)
            delta_n.append(len(grew) - len(base))
            rec_ticks.append(rec)
            extra_sync.append(probe.sync_cost - sync_before)
            kills.append(len(victims))
        recs = [r for r in rec_ticks if r is not None]
        row = {
            "variant": name, "killed_mean": float(np.mean(kills)),
            "growers_over_baseline_mean": float(np.mean(delta_n)),
            "growers_over_baseline_max": int(max(delta_n)),
            "recovery_median": float(np.median(recs)) if recs else None,
            "unrecovered": sum(1 for r in rec_ticks if r is None),
            "sync_post_mean": float(np.mean(extra_sync)),
        }
        rows.append(row)
        print(f"  overshoot {name:18s} growers-over-baseline "
              f"mean={row['growers_over_baseline_mean']:.1f} "
              f"max={row['growers_over_baseline_max']} "
              f"rec_median={row['recovery_median']} "
              f"sync={row['sync_post_mean']:.0f}", flush=True)
    return rows


# ------------------------------------------------- 3. regression battery
BATTERY = [
    ("activation", 2200, 0, {}),
    ("storm", 3000, 1500, dict(storm_at=1500, storm_frac=0.30)),
    ("flashcrowd", 3000, 1500, dict(crowd_at=1500, crowd_frac=0.60)),
    ("churn", 3000, 1200, dict(churn_from=1200, churn_death_p=0.0004)),
]


def run_battery(extra_seeds):
    """V3 vs V4 at R=5, plus V4 at R=6 on storm/churn: V4 tracks the
    target more tightly (it repairs the holes that stall V3's shrink
    cascade), which trades away V3's *incidental* ~2R over-provisioning;
    the R+1 rows show the explicit knob buying the margin back."""
    rows = []
    for key, ticks, t_dist, kw in BATTERY:
        seeds = [42] + (extra_seeds if key in ("storm", "churn") else [])
        configs = [(V3.name, 5), (V4_NAME, 5)]
        if key in ("storm", "churn"):
            configs.append((V4_NAME, 6))
        for seed in seeds:
            for name, r in configs:
                cfg = Config(seed=seed, redundancy=r)
                initial, events, joins = make_world(cfg, ticks, **kw)
                sim = make_sim(name, cfg, events, initial, joins)
                m = sim.run(ticks)
                S = cfg.sectors
                rows.append({
                    "scenario": key, "seed": seed, "variant": name,
                    "R": cfg.redundancy,
                    "loss": int(np.sum(np.array(m.zero_sectors[t_dist:]))),
                    "exposure": int((np.array(m.frac_under[t_dist:]) * S).sum()),
                    "floor_min": int(min(m.floor[t_dist:])),
                    "resizes": int(np.sum(m.resizes)),
                    "sync": int(m.cum_sync[-1]),
                    "repair_grows": getattr(sim, "n_repair_grows", 0),
                })
                row = rows[-1]
                print(f"  {key:10s} seed={seed:5d} {name:18s} R={row['R']} "
                      f"loss={row['loss']} floor={row['floor_min']} "
                      f"resizes={row['resizes']} sync={row['sync']} "
                      f"repair_grows={row['repair_grows']}", flush=True)
    return rows


# ------------------------------------------------------------- plotting
def plot_deadlock(rows, out):
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2))
    fig.suptitle("§6.2 repair rule: sparse-network recovery without the clamp",
                 fontsize=12, fontweight="bold", color=INK)
    ax_rec, ax_sync, ax_time = axes.flat

    combos = [(v, c) for v in (V3.name, V4_NAME) for c in (0, 25)]
    labels = [f"{'V3' if v == V3.name else 'V4'} clamp={c}" for v, c in combos]
    colors = [VARIANT_COLOR[V3.name] if v == V3.name else V4_COLOR
              for v, _ in combos]
    hatch = ["" if c else "//" for _, c in combos]   # clamp0 hatched

    cases = [c[0] for c in DEADLOCK_CASES]
    x = np.arange(len(cases))
    w = 0.2
    order = {c: i for i, c in enumerate(cases)}
    for i, (v, c) in enumerate(combos):
        rs = [r for r in rows if r["variant"] == v and r["clamp"] == c]
        rs = sorted(rs, key=lambda r: order[r["case"]])
        frac = [r["recovered"] / r["runs"] for r in rs]
        sync = [r["sync_post_mean"] / 1000 for r in rs]
        med = [r["rec_median"] if r["rec_median"] is not None
               else np.nan for r in rs]
        ax_rec.bar(x + (i - 1.5) * w, frac, w, color=colors[i],
                   hatch=hatch[i], edgecolor=INK, lw=0.4, label=labels[i])
        ax_sync.bar(x + (i - 1.5) * w, sync, w, color=colors[i],
                    hatch=hatch[i], edgecolor=INK, lw=0.4, label=labels[i])
        ax_time.bar(x + (i - 1.5) * w, med, w, color=colors[i],
                    hatch=hatch[i], edgecolor=INK, lw=0.4, label=labels[i])

    for ax, title, ylab in ((ax_rec, "Runs fully re-covered (fraction)",
                             "fraction of seeds"),
                            (ax_sync, "Post-kill sync cost (k sectors, mean)",
                             "k sectors"),
                            (ax_time, "Median recovery time (ticks)",
                             "ticks")):
        ax.set_xticks(x)
        ax.set_xticklabels(cases, fontsize=8)
        ax.set_title(title)
        ax.set_ylabel(ylab)
        ax.grid(True, axis="y")
    ax_rec.set_ylim(0, 1.05)
    ax_rec.legend(fontsize=7, loc="lower right")
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"wrote {out}")


def main():
    quick = "--quick" in sys.argv
    # staged execution: `--study deadlock` and `--study rest` run the
    # heavy halves separately (each fits a 10-minute budget); the default
    # runs whatever stages are missing and assembles outputs.
    study = (sys.argv[sys.argv.index("--study") + 1]
             if "--study" in sys.argv else "all")
    seeds = list(range(1, 7 if quick else 31))
    extra = [] if quick else [7, 99, 1234]

    if study in ("deadlock", "all"):
        print("study: sparse deadlock")
        dead = run_deadlock(seeds)
        with open("results/repair_stage_deadlock.json", "w") as f:
            json.dump(dead, f)
    if study in ("rest", "all"):
        print("study: dense overshoot probe")
        over = run_overshoot(seeds[:4] if quick else seeds[:8])
        print("study: regression battery")
        batt = run_battery(extra)
        with open("results/repair_stage_rest.json", "w") as f:
            json.dump({"overshoot": over, "battery": batt}, f)
    if study not in ("deadlock", "rest", "all", "finish"):
        raise SystemExit(f"unknown --study {study}")
    if study in ("finish",) or study == "all":
        pass
    else:
        return   # summary/plot happen in the finish (or all) invocation

    with open("results/repair_stage_deadlock.json") as f:
        dead = json.load(f)
    with open("results/repair_stage_rest.json") as f:
        rest = json.load(f)
    over, batt = rest["overshoot"], rest["battery"]

    with open("results/repair.json", "w") as f:
        json.dump({"deadlock": dead, "overshoot": over, "battery": batt,
                   "stagger_k": REPAIR_STAGGER_K}, f, indent=1)

    with open("results/repair_summary.md", "w") as f:
        f.write("# §6.2 repair-rule study\n\n"
                "V4 = V3 + expanding-ring repair (react to a hole in the "
                "level+g ancestor block after grow_need + (g-1)*2*lag).\n\n"
                "## Sparse deadlock (kill to k survivors at t=1500; "
                "clustered = §6.2 geometry, survivors' homes in one "
                "half-ring)\n\n"
                "| case | clamp | variant | recovered | stuck | "
                "median rec (ticks) | mean post-kill sync | worst floor |\n"
                "|---|---|---|---|---|---|---|---|\n")
        for r in dead:
            f.write(f"| {r['case']} | {r['clamp']} | {r['variant']} | "
                    f"{r['recovered']}/{r['runs']} | {r['stuck']} | "
                    f"{r['rec_median']} | {r['sync_post_mean']:.0f} | "
                    f"{r['floor_min_worst']} |\n")
        f.write("\n## Dense overshoot probe (all holders of one sector "
                "killed at equilibrium; growers net of a matched "
                "no-kill control)\n\n"
                "| variant | growers over baseline (mean) | (max) | "
                "median recovery | unrecovered | mean post-kill sync |\n"
                "|---|---|---|---|---|---|\n")
        for r in over:
            f.write(f"| {r['variant']} | "
                    f"{r['growers_over_baseline_mean']:.1f} | "
                    f"{r['growers_over_baseline_max']} | "
                    f"{r['recovery_median']} | {r['unrecovered']} | "
                    f"{r['sync_post_mean']:.0f} |\n")
        f.write("\n## Regression battery (Stage-1 scenarios; V4 R=6 rows "
                "= the explicit-knob margin buy-back)\n\n"
                "| scenario | seed | variant | R | loss | floor_min | "
                "exposure | resizes | sync | repair grows |\n"
                "|---|---|---|---|---|---|---|---|---|---|\n")
        for r in batt:
            f.write(f"| {r['scenario']} | {r['seed']} | {r['variant']} | "
                    f"{r['R']} | {r['loss']} | {r['floor_min']} | "
                    f"{r['exposure']} | {r['resizes']} | {r['sync']} | "
                    f"{r['repair_grows']} |\n")
    print("wrote results/repair_summary.md")
    plot_deadlock(dead, "results/repair_deadlock.png")


if __name__ == "__main__":
    main()
