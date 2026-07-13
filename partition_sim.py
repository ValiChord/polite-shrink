"""
Stage-3a: network partitions / netsplits against the arc controllers.

The Stage-1 model assumes full peer visibility; REPORT_stage1.md §7 flags
partitions as untested. This study adds them with the same stale-view
machinery: from the moment of a split, each side's *snapshots* contain
only its own members, so the other side fades out of every agent's lagged
view within one gossip lag — exactly how a mass death presents. A heal
merges the snapshots again, and the other side fades back in.

What a partition uniquely stresses (vs the Stage-1 storm):
  * during the split, each side re-grows to cover the whole ring alone —
    the small side may fall below `clamp_min_peers` (REPORT §6.2's
    designed recovery path);
  * at HEAL, every agent sees ~2x over-coverage at once, so the whole
    network wants to shrink simultaneously — the harshest concurrent-
    shrink stress the controllers have faced;
  * flapping (repeated split/heal at gossip-lag timescale) whipsaws the
    controllers between the two regimes.

Two ground truths are recorded per tick:
  durability   — declared copies counting every alive agent (as Stage-1);
                 zero here means no live replica exists anywhere.
  availability — copies *reachable within each side*; a sector with all
                 copies on the far side is intact but unreachable. This
                 is the honest cost of a partition no controller can
                 remove — what matters is how fast each side re-covers,
                 and that the heal-time shrink storm never converts
                 the transient into durability loss.

Usage:   python3 partition_sim.py [--quick]
Output:  results/partition_<scenario>.png, results/partition_summary.md,
         results/partition.json
"""

from __future__ import annotations

import json
import sys

import numpy as np

from arc_sim import VARIANTS, Agent, Config, Sim, block, make_world, vacate_half
from ext_common import (ALERT, BASELINE, INK, MUTED, VARIANT_COLOR, plt,
                        settle_tick)


class PartitionSim(Sim):
    """Sim with group-restricted visibility.

    `group_of(aid, t)` -> group id of agent `aid` at tick `t` (0..G-1).
    Snapshots are stored per group; an agent's lagged view is the snapshot
    of the group it belonged to at the *viewed* tick, so partition onset
    and heal both propagate with each viewer's own gossip lag.
    """

    def __init__(self, cfg, variant, events, initial, joins,
                 group_of, n_groups=2):
        self.group_of = group_of
        self.n_groups = n_groups
        super().__init__(cfg, variant, events, initial, joins)
        S, H, G = cfg.sectors, self.H, n_groups
        max_agents = self.lvl_h.shape[1]
        self.gcov_h = np.zeros((H, G, S), dtype=np.int16)
        self.gicov_h = np.zeros((H, G, S), dtype=np.int16)
        self.gilist_h = [[[] for _ in range(G)] for _ in range(H)]
        self.groups_h = np.full((H, max_agents), -1, dtype=np.int8)
        self.galive_h: list[list[int]] = [[] for _ in range(H)]
        # Pre-fill history consistent with the t=0 grouping (scenarios
        # start unpartitioned, so this is the whole network in group 0).
        g0 = np.array([group_of(a.aid, 0) for a in self.agents], dtype=np.int8)
        cov0 = np.zeros((G, S), dtype=np.int16)
        for a in self.agents:
            s, e = block(a.home, a.level, cfg.log2s)
            cov0[g0[a.aid], s:e] += 1
        active0 = sorted(set(int(g) for g in g0))
        for i in range(H):
            self.groups_h[i, :len(self.agents)] = g0
            self.gcov_h[i] = cov0
            self.galive_h[i] = active0
        # availability ground truth (per tick, appended in step())
        self.m.avail_floor = []
        self.m.avail_zero = []

    def _store_snapshot(self):
        super()._store_snapshot()
        cfg, idx = self.cfg, self.t % self.H
        G, S = self.n_groups, cfg.sectors
        gcov = np.zeros((G, S), dtype=np.int16)
        gicov = np.zeros((G, S), dtype=np.int16)
        glists: list[list[tuple[int, int, int]]] = [[] for _ in range(G)]
        garr = np.full(self.groups_h.shape[1], -1, dtype=np.int8)
        alive_groups = set()
        for a in self.agents:
            g = self.group_of(a.aid, self.t)
            garr[a.aid] = g
            if not a.alive:
                continue
            alive_groups.add(g)
            s, e = block(a.home, a.level, cfg.log2s)
            gcov[g, s:e] += 1
            if a.intent_at > self.t:
                vs, ve = vacate_half(a.home, a.level, cfg.log2s)
                gicov[g, vs:ve] += 1
                glists[g].append((a.aid, vs, ve))
        self.gcov_h[idx] = gcov
        self.gicov_h[idx] = gicov
        self.gilist_h[idx] = glists
        self.groups_h[idx] = garr
        self.galive_h[idx] = sorted(alive_groups)

    def _view(self, a: Agent):
        idx = (self.t - a.lag) % self.H
        g = int(self.groups_h[idx, a.aid])
        if g < 0:               # agent didn't exist at the viewed tick
            g = self.group_of(a.aid, self.t)
        cov = self.gcov_h[idx, g]
        lvl = np.where(self.groups_h[idx] == g, self.lvl_h[idx], -1)
        icov = self.gicov_h[idx, g]
        ilist = self.gilist_h[idx][g]
        return cov, lvl, icov, ilist

    def step(self):
        super().step()
        idx = (self.t - 1) % self.H
        floors, zeros = [], 0
        for g in self.galive_h[idx]:
            cov_g = self.gcov_h[idx, g]
            floors.append(int(cov_g.min()))
            zeros += int((cov_g == 0).sum())
        self.m.avail_floor.append(min(floors) if floors else 0)
        self.m.avail_zero.append(zeros)


# ------------------------------------------------------------- scenarios
def make_sides(cfg, max_agents, minority_frac):
    """Deterministic side assignment for every agent id that can exist."""
    rng = np.random.default_rng(cfg.seed + 7)
    return (rng.random(max_agents) < minority_frac).astype(np.int8)


def windows_group_of(sides, windows):
    """group_of for split windows: inside any [start, end) window the
    network is split by `sides`; outside it is whole (group 0)."""
    def group_of(aid, t):
        for s, e in windows:
            if s <= t < e:
                return int(sides[aid])
        return 0
    return group_of


SCENARIOS = [
    # (key, title, ticks, split windows, minority fraction)
    ("split5050",
     "50/50 netsplit at 1500, heal at 2100 (200 agents, R=5)",
     3200, [(1500, 2100)], 0.5),
    ("split9010",
     "90/10 netsplit at 1500, heal at 2100 — minority below the clamp",
     3200, [(1500, 2100)], 0.1),
    ("flapping",
     "Flapping partition: three 150-tick splits, 150-tick heals",
     3400, [(1500, 1650), (1800, 1950), (2100, 2250)], 0.5),
]


def run_scenario(key, ticks, windows, minority_frac, cfg, variants):
    initial, events, joins = make_world(cfg, ticks)
    max_agents = len(initial)
    sides = make_sides(cfg, max_agents, minority_frac)
    group_of = windows_group_of(sides, windows)
    results = {}
    for v in variants:
        sim = PartitionSim(cfg, v, events, initial, joins, group_of)
        m = sim.run(ticks)
        results[v.name] = m
        print(f"  {key:10s} {v.name:24s} "
              f"durability floor_min(post)={min(m.floor[windows[0][0]:])} "
              f"avail floor_min(post)={min(m.avail_floor[windows[0][0]:])} "
              f"durability zero-ticks={sum(m.zero_sectors[windows[0][0]:])}")
    return results, sides


def summarize(key, name, m, cfg, windows, ticks):
    t0 = windows[0][0]
    heal = windows[-1][1]
    split_ticks = [t for s, e in windows for t in range(s, e)]
    return {
        "scenario": key, "variant": name,
        "dur_floor_min": int(min(m.floor[t0:])),
        "dur_loss_ticks": int(sum(m.zero_sectors[t0:])),
        "avail_floor_min_split": int(min(m.avail_floor[t] for t in split_ticks)),
        "avail_zero_ticks_split": int(sum(m.avail_zero[t] for t in split_ticks)),
        "avail_zero_ticks_postheal": int(sum(m.avail_zero[heal:])),
        "heal_settle": (lambda st: (st - heal) if st is not None else None)(
            settle_tick(m.resizes, heal)),
        "resizes": int(np.sum(m.resizes)),
        "sync_cost": int(m.cum_sync[-1]),
    }


def plot_scenario(key, title, results, cfg, windows, out):
    fig, axes = plt.subplots(2, 2, figsize=(11, 6.6))
    fig.suptitle(title, fontsize=12, fontweight="bold", color=INK)
    ax_dur, ax_avail, ax_lvl, ax_zero = axes.flat

    for name, m in results.items():
        c = VARIANT_COLOR[name]
        ax_dur.plot(m.floor, color=c, lw=1.6, label=name)
        ax_avail.plot(m.avail_floor, color=c, lw=1.6, label=name)
        ax_lvl.plot(m.mean_level, color=c, lw=1.6, label=name)
        ax_zero.plot(m.avail_zero, color=c, lw=1.6, label=name)

    for ax, what in ((ax_dur, "durability"), (ax_avail, "availability")):
        ax.axhline(cfg.redundancy, color=BASELINE, lw=1, ls="--")
        ax.axhline(0, color=ALERT, lw=0.8, alpha=0.5)
        ax.set_ylim(-0.8, 25)
        ax.set_ylabel("copies")
    ax_dur.set_title("Durability floor (min live copies anywhere; y clipped at 25)")
    ax_avail.set_title("Availability floor (min copies reachable on the worst side)")
    ax_lvl.set_title(f"Mean arc level ({cfg.log2s} = full ring)")
    ax_lvl.set_ylabel("level")
    ax_zero.set_title("Unreachable sectors (per side, summed)")
    ax_zero.set_ylabel("sectors")

    for ax in axes.flat:
        ax.grid(True, axis="y")
        ax.set_xlabel("tick")
        ax.margins(x=0.01)
        for s, e in windows:
            ax.axvspan(s, e, color=MUTED, alpha=0.10, lw=0)
    ax_dur.legend(loc="upper right", fontsize=8)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  wrote {out}")


def main():
    quick = "--quick" in sys.argv
    cfg = Config()
    variants = VARIANTS[1:]     # V0 is already broken without partitions
    rows = []
    dump = {}
    for key, title, ticks, windows, frac in SCENARIOS:
        if quick and key != "split5050":
            continue
        print(f"scenario: {key}")
        results, _sides = run_scenario(key, ticks, windows, frac, cfg, variants)
        plot_scenario(key, title, results, cfg, windows,
                      f"results/partition_{key}.png")
        for name, m in results.items():
            rows.append(summarize(key, name, m, cfg, windows, ticks))
        dump[key] = {name: {"floor": m.floor, "avail_floor": m.avail_floor,
                            "zero": m.zero_sectors, "avail_zero": m.avail_zero,
                            "mean_level": m.mean_level,
                            "resizes": m.resizes, "cum_sync": m.cum_sync}
                     for name, m in results.items()}

    hdr = ["scenario", "variant", "dur_floor_min", "dur_loss_ticks",
           "avail_floor_min_split", "avail_zero_ticks_split",
           "avail_zero_ticks_postheal", "heal_settle", "resizes", "sync_cost"]
    lines = ["| " + " | ".join(hdr) + " |",
             "|" + "|".join("---" for _ in hdr) + "|"]
    for r in rows:
        lines.append("| " + " | ".join(
            str(r[h]) if r[h] is not None else "never" for h in hdr) + " |")
    table = "\n".join(lines)
    with open("results/partition_summary.md", "w") as f:
        f.write(
            "# Partition study summary\n\n"
            "dur_* = durability (live copies anywhere; zero = data gone). "
            "avail_* = availability (copies reachable within each side; "
            "zero-ticks = sector-ticks unreachable on some side — the "
            "unavoidable partition cost, shown so recovery speed can be "
            "compared). heal_settle = ticks after final heal until the "
            "resize rate stays < 1/tick for 300 ticks.\n\n" + table + "\n")
    with open("results/partition.json", "w") as f:
        json.dump(dump, f)
    print("\n" + table)


if __name__ == "__main__":
    main()
