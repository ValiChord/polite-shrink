"""
v6_study — does V6 (safe-or-lowest) keep V3's efficiency and V5's safety?

REPORT_stale_views.md shows, by exhaustive model checking, that V3's lowest-id
tie-break fails a staggered cascade, that V5 (discount every announcer) is safe
but can stall, and that V6 — count every racer as gone, and let the lowest
racer wait instead of cancelling — is safe and always makes progress. The model is small (N <= 5). This asks what V6 costs
and buys at N=200 in the repo's own simulator, against V3 and V5:

  A. the four standard scenarios (activation, storm, flashcrowd, churn)
  B. storm severity at 30% and 40% — where REPORT_agentinfo_encoding §4.9 found
     V5 losing data 6-9x more often than V3
  C. the stress regime where V3 loses data in ~35% of runs: storm 50% with
     death detection 192 ticks behind (8x the max gossip lag)

Fresh seed range (920000+). Exact 95% intervals via detector_replication.
Resumable; 5 processes by default.
"""

from __future__ import annotations

import argparse
import json
import os
from multiprocessing import Pool

import numpy as np

from polite_shrink import V6, VARIANTS, Config, Sim, make_world
from decoupled_sim import DecoupledSim
from detector_replication import clopper_pearson

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
CELLS = os.path.join(RESULTS_DIR, "v6_cells.jsonl")
SEED_BASE = 920000
RULES = {"V3": VARIANTS[3], "V5": VARIANTS[4], "V6": V6}
TICKS = 3000
SCEN_A = {"activation": {}, "storm": dict(storm_at=1500, storm_frac=0.30),
          "flashcrowd": dict(crowd_at=1500, crowd_frac=0.60),
          "churn": dict(churn_from=1200, churn_death_p=0.0004)}
SCEN_B = {"storm30": dict(storm_at=1500, storm_frac=0.30),
          "storm40": dict(storm_at=1500, storm_frac=0.40)}
SCEN_C = {"stress50_dl192": dict(storm_at=1500, storm_frac=0.50)}


def run(args):
    part, scen, rule, seed = args
    cfg = Config(seed=seed)
    kw = {**SCEN_A, **SCEN_B, **SCEN_C}[scen]
    initial, events, joins = make_world(cfg, TICKS, **kw)
    v = RULES[rule]
    if part == "C":
        sim = DecoupledSim(cfg, [v] * len(initial), events, initial, joins,
                           1.0, death_lag=192)
    else:
        sim = Sim(cfg, v, events, initial, joins)
    m = sim.run(TICKS)
    held = np.array(m.held_zero)
    return {"part": part, "scen": scen, "rule": rule, "seed": seed,
            "held_loss": int(held.sum()), "any_loss": bool(held.sum() > 0),
            "declared_loss": int(np.array(m.zero_sectors).sum()),
            "exposure": float(np.array(m.frac_under).sum()),
            "eq_level": float(np.mean(m.mean_level[-300:])),
            "sync": int(m.cum_sync[-1]),
            "announces": int(sim.announces), "cancels": int(sim.cancels)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds-a", type=int, default=48)
    ap.add_argument("--seeds-b", type=int, default=100)
    ap.add_argument("--seeds-c", type=int, default=72)
    ap.add_argument("--procs", type=int, default=5)
    a = ap.parse_args()
    work = []
    for part, scens, n in (("A", SCEN_A, a.seeds_a), ("B", SCEN_B, a.seeds_b),
                           ("C", SCEN_C, a.seeds_c)):
        work += [(part, s, r, SEED_BASE + i) for s in scens for r in RULES
                 for i in range(n)]
    os.makedirs(RESULTS_DIR, exist_ok=True)
    rows, done = [], set()
    if os.path.exists(CELLS):
        for line in open(CELLS, encoding="utf-8"):
            if line.strip():
                r = json.loads(line); rows.append(r)
                done.add((r["part"], r["scen"], r["rule"], r["seed"]))
    todo = [w for w in work if w not in done]
    print(f"v6 study: {len(work)} runs ({len(todo)} to run)", flush=True)
    with open(CELLS, "a", encoding="utf-8") as fh, Pool(a.procs) as pool:
        for i, r in enumerate(pool.imap_unordered(run, todo), 1):
            fh.write(json.dumps(r) + "\n"); fh.flush(); rows.append(r)
            if i % 100 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)}", flush=True)
    summarise(rows)


def summarise(rows):
    import sys
    L = ["# V6 against V3 and V5 at N = 200", "",
         "V6 = patient lowest: every racing intender counts as gone; the lowest "
         "racer waits instead of cancelling; higher ids do not announce while a lower "
         "one is racing them. 'time below R' = sector-ticks below R (fraction-weighted). Fresh seeds "
         f"({SEED_BASE}+). 95% intervals are exact.", "",
         f"Environment: Python {sys.version.split()[0]}, numpy {np.__version__}.", ""]
    def block(part, title, scens):
        out = [f"## {title}", "",
               "| scenario | rule | runs losing data | 95% CI | declared loss | "
               "time below R | eq. arc level | sync cost | cancel rate |",
               "|---|---|---|---|---|---|---|---|---|"]
        for s in scens:
            for r in RULES:
                c = sorted((x for x in rows if x["part"] == part and x["scen"] == s
                            and x["rule"] == r), key=lambda x: x["seed"])
                if not c:
                    continue
                n = len(c); k = sum(x["any_loss"] for x in c)
                lo, hi = clopper_pearson(k, n)
                dl = sum(x["declared_loss"] for x in c)
                lv = float(np.mean([x["eq_level"] for x in c]))
                sy = float(np.mean([x["sync"] for x in c]))
                an = sum(x["announces"] for x in c); ca = sum(x["cancels"] for x in c)
                cr = ca / an if an else 0.0
                ex = float(np.mean([x["exposure"] for x in c]))
                out.append(f"| {s} | **{r}** | {k}/{n} | {100*lo:.0f}–{100*hi:.0f}% | "
                           f"{dl:,} | {ex:,.0f} | {lv:.2f} | {sy:,.0f} | {100*cr:.1f}% |")
        return out + [""]
    L += block("A", "A. Standard scenarios", SCEN_A)
    L += block("B", "B. Storm severity (cf. REPORT_agentinfo_encoding §4.9)", SCEN_B)
    L += block("C", "C. Stress: storm 50%, death detection 192 ticks late", SCEN_C)
    out = os.path.join(RESULTS_DIR, "v6_summary.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("\n".join(L)); print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
