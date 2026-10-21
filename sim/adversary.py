"""
Adversarial search against the arc controllers (Stage-1c).

Threat model: the adversary has the same budget as the churn-storm scenario —
kill 60 of 200 agents (30%) — but chooses WHICH agents die and WHEN, across a
400-tick attack window at equilibrium (targeted node removal / DDoS model).
It optimises the schedule with an evolutionary search (learning-as-search;
the black-box standard for adversarial falsification) to maximise data loss,
then under-replication exposure.

Compared per controller variant: the uniform random storm (baseline), the
best of 40 random schedules (random-search baseline), and the evolved attack.

Usage:   python3 adversary.py            # ~10-15 min on 2 cores
Output:  results/adversary.json, results/adversary.png
"""

from __future__ import annotations

import copy
import json
import multiprocessing as mp
import time

import numpy as np

from polite_shrink import VARIANTS, Config, Sim, make_world

WARMUP = 1500          # ticks to reach equilibrium before the attack
T_END = 2600           # total ticks (700-tick recovery observation)
ATTACK_LO, ATTACK_HI = WARMUP, WARMUP + 400
BUDGET = 60            # kills (= storm scenario's 30% of 200)
POP, GENS, ELITE = 16, 20, 4
N_RANDOM = 40          # random-search baseline evals

_SNAP = None           # per-worker warmup snapshot


def build_snapshot(variant):
    cfg = Config()
    initial, events, joins = make_world(cfg, T_END)   # no scripted events
    sim = Sim(cfg, variant, events, initial, joins)
    for _ in range(WARMUP):
        sim.step()
    return sim


def _init_worker(snap):
    global _SNAP
    _SNAP = snap


def evaluate(genome):
    """genome = (ticks list, victims list). Returns post-attack metrics."""
    ticks, victims = genome
    sim = copy.deepcopy(_SNAP)
    sched: dict[int, list[int]] = {}
    for t, v in zip(ticks, victims):
        sched.setdefault(int(t), []).append(int(v))
    sim.events = sched
    for _ in range(T_END - WARMUP):
        sim.step()
    S = sim.cfg.sectors
    zeros = np.array(sim.m.zero_sectors[WARMUP:])
    under = np.array(sim.m.frac_under[WARMUP:]) * S
    # distinct sectors that ever hit zero copies = real, unrecoverable loss
    cov_hist_floor = np.array(sim.m.floor[WARMUP:])
    return {
        "loss": int(zeros.sum()),
        "exposure": int(under.sum()),
        "floor_min": int(cov_hist_floor.min()),
        "sectors_lost": None,  # filled by re-run in main for winners only
    }


def fitness(res):
    return res["loss"] * 1_000_000 + res["exposure"]


def sectors_lost(snap, genome):
    """Re-run tracking which distinct sectors ever hit zero (data gone)."""
    ticks, victims = genome
    sim = copy.deepcopy(snap)
    sched: dict[int, list[int]] = {}
    for t, v in zip(ticks, victims):
        sched.setdefault(int(t), []).append(int(v))
    sim.events = sched
    lost = np.zeros(sim.cfg.sectors, dtype=bool)
    floors = []
    for _ in range(T_END - WARMUP):
        sim.step()
        cov = sim.cov_h[(sim.t - 1) % sim.H]
        lost |= (cov == 0)
        floors.append(int(cov.min()))
    return int(lost.sum()), floors


# ------------------------------------------------------------ genomes
def rand_genome(rng, n_agents):
    ticks = rng.integers(ATTACK_LO, ATTACK_HI, BUDGET)
    victims = rng.choice(n_agents, BUDGET, replace=False)
    return ticks.tolist(), victims.tolist()


def seed_genomes(rng, snap):
    """Structured hypotheses to seed the search."""
    n = len(snap.agents)
    out = []
    # (a) classic storm: everyone at once
    v = rng.choice(n, BUDGET, replace=False)
    out.append(([ATTACK_LO] * BUDGET, v.tolist()))
    # (b) uniform drip
    v = rng.choice(n, BUDGET, replace=False)
    out.append((np.linspace(ATTACK_LO, ATTACK_HI - 1, BUDGET).astype(int).tolist(),
                v.tolist()))
    # (c)+(d) neighbourhood-targeted: victims whose homes cluster around a
    # random sector, burst and drip
    for ticks in ([ATTACK_LO] * BUDGET,
                  np.linspace(ATTACK_LO, ATTACK_HI - 1, BUDGET).astype(int).tolist()):
        s0 = int(rng.integers(0, snap.cfg.sectors))
        ring = snap.cfg.sectors
        dist = [min((a.home - s0) % ring, (s0 - a.home) % ring)
                for a in snap.agents]
        order = np.argsort(dist)[:BUDGET]
        out.append((list(ticks), [int(i) for i in order]))
    return out


def mutate(rng, genome, n_agents):
    ticks, victims = list(genome[0]), list(genome[1])
    used = set(victims)
    for i in range(BUDGET):
        if rng.random() < 0.25:
            ticks[i] = int(np.clip(ticks[i] + rng.integers(-40, 41),
                                   ATTACK_LO, ATTACK_HI - 1))
        if rng.random() < 0.08:
            free = [a for a in range(n_agents) if a not in used]
            if free:
                used.discard(victims[i])
                victims[i] = int(rng.choice(free))
                used.add(victims[i])
    return ticks, victims


def crossover(rng, g1, g2):
    ticks, victims, used = [], [], set()
    for i in range(BUDGET):
        src = g1 if rng.random() < 0.5 else g2
        ticks.append(src[0][i])
        victims.append(src[1][i])
    # repair duplicate victims
    for i in range(BUDGET):
        if victims[i] in used:
            victims[i] = -1
        else:
            used.add(victims[i])
    free = iter([a for a in range(200) if a not in used])
    victims = [v if v >= 0 else int(next(free)) for v in victims]
    return ticks, victims


# ------------------------------------------------------------ search
def attack_variant(variant, pool_size=2):
    rng = np.random.default_rng(2026)
    print(f"\n=== {variant.name} ===")
    t0 = time.time()
    snap = build_snapshot(variant)
    n = len(snap.agents)
    eq_cov = snap.cov_h[(snap.t - 1) % snap.H]
    print(f"  warmup {time.time()-t0:.0f}s; equilibrium coverage "
          f"min={eq_cov.min()} mean={eq_cov.mean():.1f}")

    with mp.Pool(pool_size, initializer=_init_worker, initargs=(snap,)) as pool:
        # baselines
        storm = ([ATTACK_LO] * BUDGET,
                 np.random.default_rng(0).choice(n, BUDGET, replace=False).tolist())
        randoms = [rand_genome(rng, n) for _ in range(N_RANDOM)]
        base_res = pool.map(evaluate, [storm] + randoms)
        storm_res, rand_res = base_res[0], base_res[1:]
        best_rand = max(rand_res, key=fitness)

        # evolutionary search, seeded with structured hypotheses
        pop = seed_genomes(rng, snap)
        pop += [rand_genome(rng, n) for _ in range(POP - len(pop))]
        results = pool.map(evaluate, pop)
        curve = []
        for g in range(GENS):
            ranked = sorted(zip(pop, results), key=lambda pr: -fitness(pr[1]))
            best = ranked[0]
            curve.append(fitness(best[1]))
            print(f"  gen {g:2d}  best loss={best[1]['loss']:6d} "
                  f"exposure={best[1]['exposure']:6d} floor={best[1]['floor_min']}")
            elite = [pr[0] for pr in ranked[:ELITE]]
            children = []
            while len(children) < POP - ELITE:
                cand = [ranked[int(rng.integers(0, POP))] for _ in range(3)]
                p1 = max(cand, key=lambda pr: fitness(pr[1]))[0]
                cand = [ranked[int(rng.integers(0, POP))] for _ in range(3)]
                p2 = max(cand, key=lambda pr: fitness(pr[1]))[0]
                children.append(mutate(rng, crossover(rng, p1, p2), n))
            pop = elite + children
            results = (results if g == GENS - 1 else
                       pool.map(evaluate, pop))
        ranked = sorted(zip(pop, results), key=lambda pr: -fitness(pr[1]))
        best_g, best_r = ranked[0]

    n_lost, floors_evolved = sectors_lost(snap, best_g)
    _, floors_storm = sectors_lost(snap, storm)
    best_r["sectors_lost"] = n_lost

    # attack-shape analysis
    ticks = np.array(best_g[0]); victims = best_g[1]
    homes = np.array([snap.agents[v].home for v in victims])
    span = int(np.ptp(np.sort(homes)))  # crude home-sector spread
    shape = {
        "tick_min": int(ticks.min()), "tick_max": int(ticks.max()),
        "tick_std": float(ticks.std()),
        "frac_first_50_ticks": float((ticks <= ATTACK_LO + 50).mean()),
        "victim_home_spread_sectors": span,
        "victim_home_densest_quarter": float(max(
            ((homes >= q) & (homes < q + 128)).mean()
            for q in range(0, 512, 64))),
    }
    print(f"  BEST: loss={best_r['loss']} exposure={best_r['exposure']} "
          f"sectors_lost={n_lost} shape={shape}")
    return {
        "variant": variant.name,
        "equilibrium_cov_mean": float(eq_cov.mean()),
        "storm": storm_res, "random_best": best_rand, "evolved": best_r,
        "curve": curve, "shape": shape,
        "genome": {"ticks": best_g[0], "victims": best_g[1]},
        "floors_evolved": floors_evolved, "floors_storm": floors_storm,
    }


def main():
    out = []
    for v in VARIANTS[1:]:            # V0 is already broken by random churn
        out.append(attack_variant(v))
    with open("results/adversary.json", "w") as f:
        json.dump(out, f, indent=1)
    print("\nwrote results/adversary.json")
    for r in out:
        print(f"{r['variant']:26s} storm loss={r['storm']['loss']:6d}  "
              f"rand loss={r['random_best']['loss']:6d}  "
              f"evolved loss={r['evolved']['loss']:6d} "
              f"(sectors lost: {r['evolved']['sectors_lost']}) "
              f"exposure {r['storm']['exposure']}->{r['evolved']['exposure']}")


if __name__ == "__main__":
    main()
