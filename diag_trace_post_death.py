"""For the two storm losses that orphan AFTER the death tick (not at it),
identify exactly which agent dropped the last holder of the orphaned sector,
and whether that agent was polite (V3 — a §6.1 intent-death race) or naive
(V0 — an uncoordinated post-death instant shrink).

At tick t the sim applies: (1) grows complete, (2) polite intents execute,
(3) decisions [naive instant shrinks / polite intent announces], (4) deaths,
(5) snapshot. For storm, deaths only at t=1500, so any coverage drop at a
later tick is a SHRINK — either a polite execute or a naive decision.
"""

import numpy as np

from polite_shrink import Config, block, make_world
from rolling_upgrade_sim import V3, MixedSim, assign_initial_variants

KW = dict(storm_at=1500, storm_frac=0.30)
TICKS = 3000
CASES = [(100109, 0.40, 1508), (100239, 0.10, 1515)]


def covers(agent, sector, log2s):
    if not agent.alive:
        return False
    s, e = block(agent.home, agent.level, log2s)
    return s <= sector < e


for seed, frac, orphan_t in CASES:
    print(f"\n=== seed {seed} f={frac:.2f}, first orphan at t={orphan_t} ===")
    cfg = Config(seed=seed)
    initial, events, joins = make_world(cfg, TICKS, **KW)
    variants = assign_initial_variants(len(initial), frac, cfg.seed)
    died = set(events.get(1500, ()))

    # run to orphan_t-1, snapshot holders per agent; then step once and diff.
    sim = MixedSim(cfg, list(variants), events, initial, joins, frac)
    for _ in range(orphan_t):            # now t == orphan_t (about to compute), state after tick orphan_t-1
        sim.step()
    cov_before = np.array(sim.cov_h[(orphan_t - 1) % sim.H])
    # capture each agent's level+alive before the orphan tick
    before = {a.aid: (a.level, a.alive, getattr(a, "variant", None), a.intent_at)
              for a in sim.agents}
    sim.step()                            # execute tick orphan_t
    cov_after = np.array(sim.cov_h[orphan_t % sim.H])

    orphaned = np.where((cov_before > 0) & (cov_after == 0))[0]
    print(f"  sectors newly orphaned this tick: {len(orphaned)} -> {list(orphaned[:10])}")
    culprits = {}
    for s in orphaned:
        for a in sim.agents:
            aid = a.aid
            lvl_b, alive_b, var_b, _ = before.get(aid, (None, False, None, None))
            if not alive_b or lvl_b is None:
                continue
            covered_before = alive_b and (block(a.home, lvl_b, cfg.log2s)[0]
                                          <= s < block(a.home, lvl_b, cfg.log2s)[1])
            covers_after = covers(a, s, cfg.log2s)
            if covered_before and not covers_after:
                # this agent stopped covering s this tick
                kind = ("DIED" if aid in died and not a.alive else
                        ("V3-polite-shrink" if var_b is V3 else "V0-naive-shrink"))
                culprits.setdefault(kind, set()).add(aid)
    print("  who dropped coverage of the orphaned sectors this tick:")
    for kind, ids in culprits.items():
        print(f"    {kind}: {len(ids)} agents {sorted(list(ids))[:8]}")
    if "V3-polite-shrink" in culprits:
        print("  >>> a POLITE shrink executed into the post-death hole (§6.1 race)")
    elif "V0-naive-shrink" in culprits:
        print("  >>> a NAIVE shrink caused it; polite shrink is not the culprit")
