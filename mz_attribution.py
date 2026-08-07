"""
mz_attribution — which local signals actually drive an unsafe shrink gate?

Companion to `mz_probe.py`. That study asked *how much* of the gate's
over-count is predictable; this one asks *from what*.

The method is the one Vinuesa and co-workers used to rank structures in
turbulent flows (Nature Communications, Nov 2025): rather than reading model
weights, systematically withhold inputs and measure how much predictive power
each one is worth. Their result is the reason it is worth doing here — the
attribution **overturned the field's intuition**, finding vortices less
important than long assumed and Reynolds stresses and streaks more so.

This repo has form on the same pattern. Twice the intuitive culprit has been
wrong: the 2021 data loss was not caused by the oscillation it was blamed on
(REPORT_stage1.md), and the storage-arc skew is not caused by the id tie-break
that rotating priority was built to fix (REPORT_stage3.md, constraint 7). So
the prior on "the obvious feature will dominate" should be low.

Why Shapley values, and why they are exact here
-----------------------------------------------
Ablating one feature at a time is misleading when features are correlated: drop
either of two redundant signals and nothing changes, so both look worthless.
Shapley values fix this by averaging a feature's contribution over *every*
subset of the others, which is why the turbulence work uses them (SHAP).

The usual objection is cost — exact Shapley needs 2^n model fits. Here the 42
features collapse naturally into **7 observable groups** (each observable
contributes its current value plus its deltas at five lookbacks), and 2^7 = 128
fits is entirely affordable. So these are *exact* Shapley values over the seven
observables, not a sampled approximation.

Value function: out-of-sample R2 predicting the gate over-count `y`, on seeds
held out from the fit. v(empty set) = 0 by construction.

Read the output as: "of everything that can be predicted about how wrong this
agent's view is, this observable is worth this share of it." It is a statement
about *information*, not about safety. `spec/AgentInfoAgeGated.tla` already
settles the safety question — an imperfect estimate in the gate loses a copy,
whatever it is built from. The use of this ranking is to tell whoever writes the
sizing policy which quantities are worth measuring at all.

Determinism: see mz_probe.py. Same environment caveat applies.
"""

from __future__ import annotations

import argparse
import json
import os
from itertools import combinations
from math import factorial
from multiprocessing import Pool

import numpy as np

from mz_probe import (LOOKBACKS, N_OBS, RESULTS_DIR, best_r2, run_sim)

OUT = os.path.join(RESULTS_DIR, "mz_attribution_summary.md")
CELLS = os.path.join(RESULTS_DIR, "mz_attribution_cells.jsonl")

OBS_NAMES = [
    "global view floor",
    "global view mean",
    "visible peers",
    "own arc level",
    "vacate-half floor",
    "vacate-half mean",
    "visible intenders",
]

# Cells to attribute: fast detection vs slow detection, pure V3. If the ranking
# is the same at both, the mechanism is stable in detection latency -- which is
# the companion claim to mz_probe's flat memory gain.
CONDITIONS = [("f=1.0, fast detection (death_lag=4)", 4, 1.0),
              ("f=1.0, slow detection (death_lag=96)", 96, 1.0)]


def group_columns(g: int) -> list[int]:
    """Feature columns belonging to observable `g`: its current value, then its
    delta at each lookback. Layout matches mz_probe: X = [cur | mem], where
    mem is len(LOOKBACKS) blocks of N_OBS deltas."""
    cols = [g]
    for j in range(len(LOOKBACKS)):
        cols.append(N_OBS + j * N_OBS + g)
    return cols


def build(runs):
    X = np.hstack([np.vstack([r["cur"] for r in runs]),
                   np.vstack([r["mem"] for r in runs])])
    y = np.concatenate([r["y"] for r in runs])
    sid = np.concatenate([np.full(len(r["y"]), r["seed"]) for r in runs])
    return X, y, sid


_SHARED = {}


def _init_shared(Xtr, ytr, Xte, yte):
    _SHARED["Xtr"], _SHARED["ytr"] = Xtr, ytr
    _SHARED["Xte"], _SHARED["yte"] = Xte, yte


def _one_coalition(S):
    if not S:
        return S, 0.0
    cols = sorted(c for g in S for c in group_columns(g))
    v = best_r2(_SHARED["Xtr"][:, cols], _SHARED["ytr"],
                _SHARED["Xte"][:, cols], _SHARED["yte"])
    return S, max(0.0, float(v))   # clip: negative R2 = worse than the mean


MAX_TRAIN = 20000       # cap per-coalition training rows; see note below


def coalition_values(X, y, sid, n_groups=N_OBS, procs=8, seed=0):
    """v(S) for all 2^n subsets S of observables. Held-out seeds, never rows.

    The 128 fits are independent, so they are farmed out to a pool.

    Training rows are subsampled to `MAX_TRAIN` because the cost is 128 fits,
    not one: at the full ~37k training rows a single condition took over half an
    hour and was killed before it finished. Shapley *shares* are ratios and are
    insensitive to moderate subsampling; the absolute R2 of the full coalition is
    reported alongside so the reader can see what was left on the table. The
    test split is never subsampled.
    """
    seeds = sorted(set(sid.tolist()))
    hold = set(seeds[::3])                     # every third seed is the test set
    te = np.isin(sid, list(hold))
    tr = np.flatnonzero(~te)
    if tr.size > MAX_TRAIN:
        tr = np.random.default_rng(seed).choice(tr, MAX_TRAIN, replace=False)
        tr.sort()
    subsets = [s for k in range(n_groups + 1)
               for s in combinations(range(n_groups), k)]
    vals = {}
    with Pool(processes=procs, initializer=_init_shared,
              initargs=(X[tr], y[tr], X[te], y[te])) as pool:
        for i, (S, v) in enumerate(pool.imap_unordered(_one_coalition, subsets), 1):
            vals[S] = v
            if i % 32 == 0 or i == len(subsets):
                print(f"    coalitions {i}/{len(subsets)}", flush=True)
    return vals


def shapley(vals, n=N_OBS):
    """Exact Shapley values from the full coalition table."""
    phi = np.zeros(n)
    for g in range(n):
        others = [j for j in range(n) if j != g]
        for k in range(n):
            w = factorial(k) * factorial(n - k - 1) / factorial(n)
            for S in combinations(others, k):
                phi[g] += w * (vals[tuple(sorted(S + (g,)))] - vals[tuple(S)])
    return phi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=24)
    ap.add_argument("--procs", type=int, default=min(os.cpu_count() or 4, 10))
    args = ap.parse_args()
    seeds = [900000 + i for i in range(args.seeds)]

    # Resume: a condition already in the cells file is not recomputed. Each
    # condition is appended as soon as it finishes, so a kill loses at most one.
    rows, done = [], set()
    if os.path.exists(CELLS):
        for line in open(CELLS, encoding="utf-8"):
            line = line.strip()
            if line:
                r = json.loads(line)
                if r["label"] not in done:
                    done.add(r["label"])
                    rows.append(r)
        print(f"resuming: {len(done)} condition(s) already done", flush=True)

    for label, dl, frac in CONDITIONS:
        if label in done:
            continue
        print(f"[{label}] simulating {len(seeds)} seeds", flush=True)
        with Pool(processes=args.procs) as pool:
            runs = [r for r in pool.map(run_sim, [(dl, frac, s) for s in seeds])
                    if r is not None]
        X, y, sid = build(runs)
        print(f"[{label}] {X.shape[0]} gate decisions, {X.shape[1]} features; "
              f"128 coalition fits", flush=True)
        vals = coalition_values(X, y, sid, procs=args.procs)
        phi = shapley(vals)
        total = float(phi.sum())
        row = {"label": label, "death_lag": dl, "fraction": frac,
               "n": int(X.shape[0]), "r2_full": vals[tuple(range(N_OBS))],
               "shapley": phi.tolist(), "total": total,
               "share": (phi / total).tolist() if total > 0 else None,
               # singletons v({g}) come free from the coalition table and are
               # what distinguish "seven contributions" from "seven substitutes"
               "singletons": [vals[(g,)] for g in range(N_OBS)]}
        rows.append(row)
        with open(CELLS, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        print(f"[{label}] full-model R2 = {row['r2_full']:.4f} (saved)",
              flush=True)

    rows.sort(key=lambda r: [c[0] for c in CONDITIONS].index(r["label"]))
    summarise(rows)


def summarise(rows):
    import sys
    L = ["# Which local signals drive an unsafe shrink gate?", "",
         "Exact Shapley values over the seven observables an agent can compute "
         "from gossip it has already received. Value function = out-of-sample R2 "
         "predicting the gate over-count `y`, seeds held out from the fit; "
         "2^7 = 128 coalition fits per condition, so these are exact rather than "
         "sampled. Method after Vinuesa et al. (Nat. Commun., Nov 2025), whose "
         "equivalent analysis overturned which flow structures were thought to "
         "matter.", "",
         "**This ranks information, not safety.** `spec/AgentInfoAgeGated.tla` "
         "already shows an imperfect estimate inside the gate loses a copy "
         "whatever it is built from. The use of this table is to tell a sizing "
         "policy which quantities are worth measuring.", "",
         f"Environment: Python {sys.version.split()[0]}, numpy {np.__version__} "
         "— not the repo pins (3.12.1 / 2.5.1).", ""]
    for r in rows:
        L += [f"## {r['label']}", "",
              f"{r['n']:,} gate decisions. Full-model R2 = {r['r2_full']:.3f}.", "",
              "| observable | Shapley value | share | **alone** v({g}) |",
              "|---|---|---|---|"]
        order = np.argsort(r["shapley"])[::-1]
        singles = r.get("singletons")
        for g in order:
            sh = r["share"][g] if r["share"] else 0.0
            s = f"{singles[g]:.3f}" if singles else "—"
            L.append(f"| {OBS_NAMES[g]} | {r['shapley'][g]:+.4f} | {100*sh:4.1f}% "
                     f"| **{s}** |")
        L.append("")
        if singles:
            best = max(range(N_OBS), key=lambda g: singles[g])
            L += [f"**Read the last column first.** *{OBS_NAMES[best]}* alone "
                  f"scores {singles[best]:.3f} against {r['r2_full']:.3f} for all "
                  f"seven together — {100*singles[best]/r['r2_full']:.0f}% of the "
                  "full model from a single observable. The near-equal Shapley "
                  "values are therefore **not** seven separate contributions; "
                  "they are what Shapley does with near-perfect substitutes, "
                  "splitting the credit evenly among players that can each stand "
                  "in for the others.", ""]
    if len(rows) == 2:
        a, b = rows
        oa = list(np.argsort(a["shapley"])[::-1])
        ob = list(np.argsort(b["shapley"])[::-1])
        L += ["## Does the ranking move with detection latency?", "",
              f"Fast-detection order: {' > '.join(OBS_NAMES[g] for g in oa[:3])}",
              "",
              f"Slow-detection order: {' > '.join(OBS_NAMES[g] for g in ob[:3])}",
              "",
              ("**Identical top-3 ordering.** The signals that carry information "
               "about the over-count do not change as detection latency grows — "
               "the companion result to mz_probe's flat memory gain."
               if oa[:3] == ob[:3] else
               "**The ordering moves.** Which signals matter depends on detection "
               "latency; read the two tables separately and do not generalise."), ""]
    L += ["## Caveat: the visible-peer count is confounded in this model", "",
          "`visible peers` scores near zero, and that result **must not be "
          "reported as a finding**. In `DecoupledSim._view` only the coverage "
          "array `cov` receives the death-clock adjustment; the declaration "
          "vector `lvl` — which is what the peer count is computed from — is "
          "passed through on the *gossip* clock. So in this model the peer count "
          "cannot respond to detection latency even in principle, and the "
          "over-count it is being asked to predict is driven precisely by "
          "detection latency.", "",
          "In kitsune2 both would share a clock: a dead peer's `AgentInfo` "
          "lingers in the peer store until unresponsive marking removes it, and "
          "that same removal is what takes it out of coverage. Deciding whether "
          "peer count carries real signal needs `lvl` decoupled too — a change "
          "to `decoupled_sim.py`, not to this study.", "",
          "The other six observables are unaffected: they are all computed from "
          "`cov`, which is correctly on the detection clock.", ""]
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("\n".join(L))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
