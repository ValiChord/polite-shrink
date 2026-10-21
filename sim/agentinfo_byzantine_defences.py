"""Do the Byzantine defences still work under the AgentInfo-only encoding?

Two Stage-3 follow-ups are layered on the coverage *sensor* rather than on the
announcement, so the expectation is confirmation rather than news:

  * verified coverage (§7) — a peer counts only while you hold a fresh
    proof-of-serve from it, removing the K = R threshold entirely;
  * partial liars (§8) — a liar that holds a fraction p of its declared arc
    passes a c-sample audit with probability p^c.

The encoding could still interact, because under it the shrink gate reads the
coverage of *current claimants* with no tie-break, and under verified coverage
that set is further filtered to proven peers. Both filters lower the count, so
the composition should be stricter — this run checks that it is, and that
neither defence is weakened.

`true_*` is the ground truth throughout: honest agents' real storage, which is
the right measure when liars are present (held coverage would credit a liar
that stores nothing).

Run:  python3 agentinfo_byzantine_defences.py [--quick]
"""

from __future__ import annotations

import sys

import numpy as np

from polite_shrink import VARIANTS, Config, make_world
from byzantine_sim import pick_byz
from verified_coverage_sim import make_policy_sim
from partial_liar_sim import PartialLiarSim

V3, V5 = VARIANTS[3], VARIANTS[4]


def verified_cell(variant, k, seed, ticks=2600):
    cfg = Config(seed=seed)
    initial, events, joins = make_world(cfg, ticks)
    byz = set(pick_byz(cfg, k, cfg.n_agents)) if k else set()
    sim = make_policy_sim("verified", cfg, events, initial, joins, byz, "liar")
    sim.v = variant                      # policy factory hardcodes V3
    m = sim.run(ticks)
    return (float(np.mean(m.true_floor[-200:])),
            float(np.mean(m.true_zero[-200:])))


def partial_cell(variant, p, k, c, seed, ticks=2200):
    cfg = Config(seed=seed)
    initial, events, joins = make_world(cfg, ticks)
    byz = set(pick_byz(cfg, k, cfg.n_agents))
    sim = PartialLiarSim(cfg, variant, events, initial, joins, byz,
                         policy="verified", hold_frac=p, audit_samples=c)
    m = sim.run(ticks)
    return (float(np.mean(m.true_floor[-200:])),
            float(np.mean(m.true_zero[-200:])))


def main():
    quick = "--quick" in sys.argv
    seeds = [42, 7] if quick else [42, 7, 99, 1234]
    R = Config().redundancy

    print(f"Verified coverage vs K full-arc liars (R = {R}, "
          f"{len(seeds)} seeds).")
    print("The declared-trust policy collapses at K = R; verified coverage "
          "should not, under either encoding.\n")
    ks = [0, 5, 10] if quick else [0, 5, 10, 15]
    print(f"{'K':>4} {'K/R':>5} {'enc':>4} {'true_floor':>11} {'true_zero':>10}")
    for k in ks:
        for name, v in (("V3", V3), ("V5", V5)):
            rs = [verified_cell(v, k, s) for s in seeds]
            print(f"{k:4d} {k/R:5.1f} {name:>4} "
                  f"{np.mean([r[0] for r in rs]):11.2f} "
                  f"{np.mean([r[1] for r in rs]):10.1f}")

    print(f"\nPartial liars under verified coverage "
          f"(K = {2*R}, c = 2 samples, {len(seeds)} seeds).")
    print("p = fraction of its declared arc the liar really holds; it "
          "certifies with probability p^c.\n")
    ps = [0.0, 0.5, 1.0] if quick else [0.0, 0.25, 0.5, 0.75, 1.0]
    print(f"{'p':>5} {'enc':>4} {'true_floor':>11} {'true_zero':>10}")
    for p in ps:
        for name, v in (("V3", V3), ("V5", V5)):
            rs = [partial_cell(v, p, 2 * R, 2, s) for s in seeds]
            print(f"{p:5.2f} {name:>4} "
                  f"{np.mean([r[0] for r in rs]):11.2f} "
                  f"{np.mean([r[1] for r in rs]):10.1f}")


if __name__ == "__main__":
    main()
