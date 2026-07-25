"""The decoupled death-clock (§11) under the AgentInfo-only encoding.

§11 separated the two clocks the base model conflates — view staleness (gossip
propagation) and death-detection latency (unresponsive marking) — and found the
§6.1 race stays bounded and small for V3: ≤0.6% even at 2–8× the gossip lag,
and zero when detection is faster than gossip.

This is the axis where a different answer is most plausible, because the
encoding changes what "intent visibility" means. Under V3 an intent is a
message with its own lifetime; under the encoding it is a narrowed arc claim
carried by the same gossip whose staleness is one of the two clocks. So the
handshake's information and the coverage information now share a clock, while
death detection keeps its own.

Homogeneous populations (all V3, then all V5) rather than §11's mixed ones —
the question here is the encoding, not rollout.

Run:  python3 agentinfo_decoupled.py [--quick]
"""

from __future__ import annotations

import multiprocessing as mp
import sys

import numpy as np

from polite_shrink import VARIANTS, Config, make_world
from decoupled_sim import DecoupledSim

V3, V5 = VARIANTS[3], VARIANTS[4]
KW = dict(storm_at=1500, storm_frac=0.30)
TICKS = 3000
DEATH_LAGS = ["coupled", 8, 16, 24, 48, 96, 192]   # gossip lag_max is 24
SEEDS = 24
SEED_BASE = 300000


def run_cell(args):
    dl, vname, seed = args
    variant = V5 if vname == "V5" else V3
    cfg = Config(seed=seed)
    initial, events, joins = make_world(cfg, TICKS, **KW)
    death_lag = None if dl == "coupled" else int(dl)
    # fraction=1.0 with a homogeneous variant list: every agent runs `variant`.
    m = DecoupledSim(cfg, [variant] * len(initial), events, initial, joins,
                     1.0, death_lag=death_lag).run(TICKS)
    z = np.array(m.zero_sectors)
    h = np.array(m.held_zero)
    loss = bool((z > 0).any())
    first = int(np.argmax(z > 0)) if loss else -1
    hl = np.nonzero(h > 0)[0]
    return {"death_lag": dl, "variant": vname, "seed": seed,
            # diagnostics: when did real loss first appear, and how covered
            # was the network on the tick before the mass death?
            "first_held_loss": int(hl[0]) if len(hl) else -1,
            "held_floor_pre": int(m.held_floor[1499]),
            "declared_floor_pre": int(m.floor[1499]),
            # a hole opening strictly after the storm tick is the §6.1 race;
            # one opening exactly at 1500 is the mass death itself
            "race": bool(loss and first > 1500),
            "held_loss": int(h.sum()),
            "held_race": bool((h[1501:] > 0).any() and not (h[1500] > 0)),
            "declared_loss": int(z.sum())}


def main():
    quick = "--quick" in sys.argv
    seeds = 6 if quick else SEEDS
    lags = DEATH_LAGS[:3] if quick else DEATH_LAGS
    jobs = [(dl, vn, SEED_BASE + s) for dl in lags
            for vn in ("V3", "V5") for s in range(seeds)]
    with mp.Pool(min(8, mp.cpu_count())) as pool:
        res = pool.map(run_cell, jobs)
    print(f"Decoupled death-clock, storm scenario, {seeds} seeds/cell. "
          f"Gossip lag_max = 24.")
    print("race = a declared hole opening strictly after the mass death; "
          "held_race = the same on bytes actually on disk.\n")
    print(f"{'death_lag':>10} {'enc':>4} {'race %':>8} {'held_race %':>12} "
          f"{'declared_loss':>14} {'held_loss':>10} {'1st loss':>9} "
          f"{'held_floor_pre':>14}")
    for dl in lags:
        for vn in ("V3", "V5"):
            rs = [x for x in res if x["death_lag"] == dl and x["variant"] == vn]
            n = len(rs)
            print(f"{str(dl):>10} {vn:>4} "
                  f"{100.0*sum(x['race'] for x in rs)/n:7.1f}% "
                  f"{100.0*sum(x['held_race'] for x in rs)/n:11.1f}% "
                  f"{sum(x['declared_loss'] for x in rs):14d} "
                  f"{sum(x['held_loss'] for x in rs):10d} "
                  f"{int(np.median([x['first_held_loss'] for x in rs])):9d} "
                  f"{int(np.median([x['held_floor_pre'] for x in rs])):14d}")


if __name__ == "__main__":
    main()
