"""
byz_v6 — the Stage-3 Byzantine studies (byzantine_sim.py) rerun with V6.

byzantine_sim.py measured three attacks against V3 on one seed: forged
"leaving" notices, full-arc liars (agents that declare coverage they do not
store), and the trojan exit (liars vanish at once after the network has thinned
around them). This reruns the same studies for V3 and V6 on several seeds, with
nothing else changed, to see whether V6 moves any of the results.

Expectation from the design: liars inflate the counts every rule trusts, so the
liar threshold (K = R) should not move. Forged notices count as departures under
V6 (every announcer is gone), so they may make V6 more conservative still.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
from multiprocessing import Pool

import numpy as np

import byzantine_sim as bz
from polite_shrink import V6, VARIANTS, Config

RULES = {"V3": VARIANTS[3], "V6": V6}
FRACS = [0.01, 0.02, 0.025, 0.05, 0.10]


def one(args):
    rule, seed = args
    bz.V3 = RULES[rule]                  # the studies read this module global
    cfg = Config(seed=seed)
    out = {"rule": rule, "seed": seed}
    with contextlib.redirect_stdout(io.StringIO()):
        f = bz.run_forge(cfg, ticks=3000, attack_at=1500)
        lv = bz.run_liars(cfg, FRACS, ticks=2600)
        ex = bz.run_liar_exit(cfg, k=cfg.redundancy - 1, exit_at=2200)
    out["forge"] = {k: {"true_floor_min": int(min(m.true_floor[1500:])),
                        "mean_level_end": float(m.mean_level[-1]),
                        "sync": int(m.cum_sync[-1])} for k, m in f.items()}
    out["liars"] = {str(k): {"declared_floor_end": int(m.floor[-1]),
                             "true_floor_end": int(m.true_floor[-1]),
                             "true_zero_end": int(m.true_zero[-1])}
                    for k, m in lv.items()}
    out["exit"] = {k: {"true_floor_min": int(min(m.true_floor[2200:])),
                       "true_zero_ticks": int(sum(m.true_zero[2200:]))}
                   for k, m in ex.items()}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=6)
    ap.add_argument("--procs", type=int, default=3)
    a = ap.parse_args()
    work = [(r, 930000 + s) for s in range(a.seeds) for r in RULES]
    with Pool(a.procs) as p:
        rows = p.map(one, work)
    os.makedirs("results", exist_ok=True)
    with open("results/byz_v6.json", "w") as fh:
        json.dump(rows, fh)
    cfg = Config()
    L = ["# Byzantine studies: V3 against V6", "",
         f"Same scenarios as byzantine_sim.py, {a.seeds} seeds each (930000+), "
         f"N = {cfg.n_agents}, R = {cfg.redundancy}, {cfg.sectors} sectors.", "",
         "## Forged leaving-notices (whole ring, 10 lowest-ID names, from t = 1500)", "",
         "| rule | run | true floor min after attack (worst seed) | mean arc level at end | sync cost (mean) |",
         "|---|---|---|---|---|"]
    for r in RULES:
        sub = [x for x in rows if x["rule"] == r]
        for run in ("clean", "forged intents"):
            v = [x["forge"][run] for x in sub]
            L.append(f"| {r} | {run} | {min(y['true_floor_min'] for y in v)} | "
                     f"{np.mean([y['mean_level_end'] for y in v]):.2f} | "
                     f"{np.mean([y['sync'] for y in v]):,.0f} |")
    L += ["", "## Full-arc liars (declared coverage looks fine in every run)", "",
          "| rule | liars K | true floor at end (worst seed) | sectors with no real copy at end (mean) |",
          "|---|---|---|---|"]
    for r in RULES:
        sub = [x for x in rows if x["rule"] == r]
        for k in sorted({int(k) for k in sub[0]["liars"]}):
            v = [x["liars"][str(k)] for x in sub]
            L.append(f"| {r} | {k} | {min(y['true_floor_end'] for y in v)} | "
                     f"{np.mean([y['true_zero_end'] for y in v]):.1f} |")
    L += ["", f"## Trojan exit (K = R-1 = {cfg.redundancy - 1}) against an honest storm of the same size", "",
          "| rule | run | true floor min after exit (worst seed) | sector-ticks with no real copy (mean) |",
          "|---|---|---|---|"]
    for r in RULES:
        sub = [x for x in rows if x["rule"] == r]
        for run in ("trojan exit", "honest storm"):
            v = [x["exit"][run] for x in sub]
            L.append(f"| {r} | {run} | {min(y['true_floor_min'] for y in v)} | "
                     f"{np.mean([y['true_zero_ticks'] for y in v]):.1f} |")
    text = "\n".join(L) + "\n"
    with open("results/byz_v6_summary.md", "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text)


if __name__ == "__main__":
    main()
