"""
detector_replication — independent replication of two detection-side claims.

An October 2026 audit of this repo found two headline detection results that the
committed data could not support as stated:

  A. "A spread of detection speeds is protective": a homogeneous dl=192 network
     loses data in ~40% of runs, a 50/50 mix with dl=96 in 0/24. The 0/24 came
     from a 24-seed probe whose script was never committed, so the claim was not
     reproducible from the repo.
  B. "Erring toward conviction needs a ceiling": loss worsens past the optimum
     (10% at p=0.40 vs 2% at p=0.20). That is 5/48 vs 1/48 — noise-level.

This re-tests both on a FRESH seed range (910000+), disjoint from every seed used
before, with more seeds per cell. Fresh seeds make it a replication rather than
a re-run: if the original numbers were luck, they will not come back.

Same scenario as the originals: storm 50% at t=1500, N=200, R=5, pure V3.
Exact binomial 95% intervals (Clopper-Pearson, computed with the stdlib) are
reported so "different" means something.

Resumable; 3 processes by default.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from multiprocessing import Pool

from detector_error_sweep import run_cell as det_cell
from hetero_detector_sweep import run_cell as het_cell

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
CELLS = os.path.join(RESULTS_DIR, "detector_replication_cells.jsonl")
SEED_BASE = 910000

# A: (label, dl_fast, dl_slow) at p=0 for both classes
HET = [("homogeneous dl=96", 96, 96),
       ("homogeneous dl=192", 192, 192),
       ("50/50 mix dl=96 + dl=192", 96, 192)]
# B: false-conviction rate, homogeneous dl=192
DET_P = [0.0, 0.05, 0.10, 0.20, 0.40]


def work_item(w):
    kind = w[0]
    if kind == "het":
        _, label, dlf, dls, seed = w
        r = het_cell((0.0, 0.0, seed, dlf, dls))
        return {"kind": "het", "label": label, "seed": seed,
                "loss": bool(r["any_held_loss"]), "held": r["held_loss"]}
    _, p, seed = w
    r = det_cell((p, 192, 1.0, seed))
    return {"kind": "det", "p": p, "seed": seed,
            "loss": bool(r["any_held_loss"]), "held": r["held_loss"],
            "eq_level": r["eq_level"], "sync": r["sync"]}


def key(r):
    return (r["kind"], r.get("label"), r.get("p"), r["seed"])


def clopper_pearson(k, n, a=0.05):
    """Exact binomial CI via bisection on the binomial CDF (stdlib only)."""
    def cdf(x, p):
        return sum(math.comb(n, i) * p**i * (1 - p)**(n - i) for i in range(x + 1))
    def solve(f, lo=0.0, hi=1.0):
        for _ in range(60):
            mid = (lo + hi) / 2
            if f(mid):
                hi = mid
            else:
                lo = mid
        return (lo + hi) / 2
    lower = 0.0 if k == 0 else solve(lambda p: 1 - cdf(k - 1, p) >= a / 2)
    upper = 1.0 if k == n else solve(lambda p: cdf(k, p) <= a / 2)
    return lower, upper


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--het-seeds", type=int, default=72)
    ap.add_argument("--det-seeds", type=int, default=150)
    ap.add_argument("--procs", type=int, default=3)
    a = ap.parse_args()
    work = [("het", lab, f, s, SEED_BASE + i) for lab, f, s in HET
            for i in range(a.het_seeds)]
    work += [("det", p, SEED_BASE + i) for p in DET_P for i in range(a.det_seeds)]
    os.makedirs(RESULTS_DIR, exist_ok=True)
    rows, done = [], set()
    if os.path.exists(CELLS):
        for line in open(CELLS, encoding="utf-8"):
            if line.strip():
                r = json.loads(line); rows.append(r); done.add(key(r))
    def wkey(w):
        return ("het", w[1], None, w[4]) if w[0] == "het" else ("det", None, w[1], w[2])
    todo = [w for w in work if wkey(w) not in done]
    print(f"replication: {len(work)} runs ({len(todo)} to run)", flush=True)
    with open(CELLS, "a", encoding="utf-8") as fh, Pool(a.procs) as pool:
        for i, r in enumerate(pool.imap_unordered(work_item, todo), 1):
            fh.write(json.dumps(r) + "\n"); fh.flush(); rows.append(r)
            if i % 50 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)}", flush=True)
    summarise(rows)


def summarise(rows):
    import sys
    L = ["# Detection-side claims: independent replication", "",
         f"Fresh seeds ({SEED_BASE}+, disjoint from every earlier study). Storm 50% at "
         "t=1500, N=200, R=5, pure V3. 95% intervals are exact (Clopper-Pearson).", "",
         f"Environment: Python {sys.version.split()[0]}.", "",
         "## A. Is a spread of detection speeds protective? (p = 0)", "",
         "| network | runs losing data | rate | 95% CI |", "|---|---|---|---|"]
    for lab, _, _ in HET:
        c = [r for r in rows if r["kind"] == "het" and r["label"] == lab]
        if c:
            k, n = sum(r["loss"] for r in c), len(c)
            lo, hi = clopper_pearson(k, n)
            L.append(f"| {lab} | {k}/{n} | {100*k/n:.0f}% | {100*lo:.0f}–{100*hi:.0f}% |")
    L += ["", "## B. Does erring toward conviction need a ceiling? (dl = 192)", "",
          "| p | runs losing data | rate | 95% CI | eq. arc level |",
          "|---|---|---|---|---|"]
    for p in DET_P:
        c = [r for r in rows if r["kind"] == "det" and r["p"] == p]
        if c:
            k, n = sum(r["loss"] for r in c), len(c)
            lo, hi = clopper_pearson(k, n)
            lv = sum(r["eq_level"] for r in c) / n
            L.append(f"| {p} | {k}/{n} | {100*k/n:.1f}% | {100*lo:.1f}–{100*hi:.1f}% | {lv:.2f} |")
    out = os.path.join(RESULTS_DIR, "detector_replication_summary.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("\n".join(L))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
