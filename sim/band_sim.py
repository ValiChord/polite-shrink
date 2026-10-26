"""V7 in the full simulator: V6 (the floor) plus StaleCap (the ceiling).

V6 coordinates LEAVING (announce, wait out the staleness, re-check counting
every rival announcer as gone). Growing is uncoordinated in V6: every node
that sees a short sector grows on its own, so one gap can draw several
growers. V7 adds StaleCap's rule for GROWING: announce, wait, re-check
counting the other announced growers, with silent nodes read the cautious way
for each bound. The TLA+ models StaleBand and StaleBandNet check that a floor
and a ceiling can be kept together on one resource; this asks what that means
for sharding, where data comes in power-of-two blocks, nodes act repeatedly,
and growth is the repair after deaths.

Arms:
  V6                 today's rule; growth uncoordinated.
  V6+alongside       V6 with the announce-time repair: a node may announce
                     alongside lower-id racers when, counting itself and all
                     of them as gone, its half keeps >= R (V6 makes nodes
                     sharing a range announce one at a time).
  V7 soft            V6+alongside, plus announced, coordinated growth: grow
                     only if the half is still short counting LOWER-id
                     announced growers as already there. The floor always
                     wins: no hard ceiling.
  V7 hard            V7 soft, plus a hard ceiling C: a grower also requires no
                     sector of the half to exceed C, counting every other
                     announced grower. The ceiling can then refuse a repair.
  V7 soft+multiwait  V7 soft, and at a failed leave re-check every racer that
                     would pass counting only itself and lower-id racers
                     waits (V6: only the single lowest waits).

Usage:  python sim/band_sim.py [--seeds N] [--procs P] [--ceiling C]
Output: results/v7_summary_C<C>.md, results/v7_C<C>.json
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, replace
from multiprocessing import Pool

import numpy as np

from polite_shrink import V6, Config, Sim, make_world, sibling_half, vacate_half
from run_experiments import SCENARIOS, settle_tick


@dataclass(frozen=True)
class Arm:
    name: str
    ceiling: str = "none"   # growth rule: "none" (V6), "soft" or "hard" (V7)
    multiwait: bool = False # several racers may wait at a failed re-check
    alongside: bool = False # announce alongside lower ids when there is room
    urgent: bool = False    # grow at once (no coordination) when 2+ copies short


ARMS = [Arm("V6"),
        Arm("V6+alongside", alongside=True),
        Arm("V7 soft", ceiling="soft", alongside=True),
        Arm("V7 hard", ceiling="hard", alongside=True),
        Arm("V7 soft+multiwait", ceiling="soft", alongside=True, multiwait=True)]


class V7Mixin:
    """The V7 decision rules, on top of any Sim subclass (the plain Sim, or
    PartitionSim for splits). Call `_init_v7` after the base __init__."""

    def _init_v7(self, arm: Arm, ceiling: int):
        self.arm = arm
        self.C = ceiling
        # grow intents: aid -> (execute tick, ws, we)
        self.gint: dict[int, tuple[int, int, int]] = {}
        self.glist_h = [[] for _ in range(self.H)]
        self.grow_announces = 0
        self.grow_withdrawn = 0
        self.ceiling_refusals = 0     # repairs refused by the hard ceiling

    # -- snapshots: also publish announced growers
    def _store_snapshot(self):
        super()._store_snapshot()
        self.glist_h[self.t % self.H] = [(aid, ws, we) for aid, (_t, ws, we)
                                         in self.gint.items()
                                         if self.agents[aid].alive]

    def _gview(self, a):
        return self.glist_h[(self.t - a.lag) % self.H]

    # -- growth: announce instead of growing at once
    def _start_grow(self, a):
        if self.arm.ceiling == "none" or a.level >= self.cfg.log2s or \
                getattr(self, "_executing_grow", False):
            return super()._start_grow(a)
        # The small-network clamp is an emergency safety rule: below
        # clamp_min_peers visible peers a node grows at once, as under V6.
        _cov, lvl, _icov, _il = self._view(a)
        if int((lvl[:len(self.agents)] >= 0).sum()) < self.cfg.clamp_min_peers:
            self.gint.pop(a.aid, None)
            return super()._start_grow(a)
        # Urgent repair: two or more copies short somewhere in the half means
        # a real loss (deaths, a split), not drift; repair at once, as V6
        # does, and keep coordination for single-copy gaps.
        if self.arm.urgent:
            ws, we = sibling_half(a.home, a.level, self.cfg.log2s)
            eff = (_cov[ws:we] - _icov[ws:we]).astype(np.int32)
            if int(eff.min()) < self.cfg.redundancy - 1:
                self.gint.pop(a.aid, None)
                return super()._start_grow(a)
        if a.aid in self.gint:
            return
        ws, we = sibling_half(a.home, a.level, self.cfg.log2s)
        self.gint[a.aid] = (self.t + self.cfg.intent_delay, ws, we)
        a.grow_acc = a.shrink_acc = 0
        a.intent_at = -1             # a pending shrink is abandoned
        self.grow_announces += 1

    def _execute_grow(self, a):
        _t, ws, we = self.gint.pop(a.aid)
        cfg = self.cfg
        cov, _lvl, icov, _ilist = self._view(a)
        glist = self._gview(a)
        eff = (cov[ws:we] - icov[ws:we]).astype(np.int32)   # floor view
        lower = eff.copy()
        allg = cov[ws:we].astype(np.int32)                   # ceiling view
        for aid2, s2, e2 in glist:
            if aid2 == a.aid:
                continue
            lo, hi = max(ws, s2), min(we, e2)
            if lo < hi:
                allg[lo - ws:hi - ws] += 1
                if aid2 < a.aid:
                    lower[lo - ws:hi - ws] += 1
        # The small-network clamp (hold everything below clamp_min_peers) is a
        # safety rule, not a repair: it bypasses the band.
        clamped = int((_lvl[:len(self.agents)] >= 0).sum()) < cfg.clamp_min_peers
        needed = clamped or bool(lower.min() < cfg.redundancy)
        if not needed:
            self.grow_withdrawn += 1
            return
        if (self.arm.ceiling == "hard" and not clamped
                and int((allg + 1).max()) > self.C):
            self.ceiling_refusals += 1
            return
        self._executing_grow = True
        try:
            super()._start_grow(a)
        finally:
            self._executing_grow = False

    # -- the announce-time repair (alongside)
    def _yields(self, a, ilist):
        """V6 holds off announcing while ANY lower id races it for an
        overlapping range, so nodes sharing a range announce one at a time.
        With alongside, a node holds off only if, counting itself and every
        lower-id racer as gone, its half would drop below R: it announces
        alongside lower ids when there is room for all of them. The re-check
        is unchanged, so this cannot affect safety."""
        if not self.arm.alongside:
            return super()._yields(a, ilist)
        if a.level <= 0:
            return False
        cfg = self.cfg
        vs, ve = vacate_half(a.home, a.level, cfg.log2s)
        if not self._lower_racer(a, ilist, vs, ve):
            return False
        cov, lvl, _icov, _il = self._view(a)
        eff = cov[vs:ve].astype(np.int32)
        if int(lvl[a.aid]) >= a.level:
            eff -= 1
        for aid2, s2, e2 in ilist:
            if aid2 < a.aid:
                lo, hi = max(vs, s2), min(ve, e2)
                if lo < hi:
                    eff[lo - vs:hi - vs] -= 1
        return bool(eff.min() < cfg.redundancy)

    # -- multiwait leave re-check
    def _execute_intent(self, a):
        if not self.arm.multiwait:
            return super()._execute_intent(a)
        cfg = self.cfg
        cov, lvl, _icov, ilist = self._view(a)
        vs, ve = vacate_half(a.home, a.level, cfg.log2s)
        eff = cov[vs:ve].astype(np.int32)
        if int(lvl[a.aid]) >= a.level:
            eff -= 1
        low = eff.copy()
        higher = False
        for aid2, s2, e2 in ilist:
            if aid2 == a.aid:
                continue
            lo, hi = max(vs, s2), min(ve, e2)
            if lo < hi:
                eff[lo - vs:hi - vs] -= 1
                if aid2 < a.aid:
                    low[lo - vs:hi - vs] -= 1
                else:
                    higher = True
        if eff.min() >= cfg.redundancy:
            self._do_shrink(a)
        elif higher and low.min() >= cfg.redundancy:
            a.intent_at = self.t + 1          # would fit among the lower ones: wait
        else:
            a.intent_at = -1
            a.shrink_acc = 0
            self.cancels += 1

    def step(self):
        # due grow intents run before the parent's step (like shrink intents)
        for aid, (t, _ws, _we) in list(self.gint.items()):
            a = self.agents[aid]
            if not a.alive:
                self.gint.pop(aid)
            elif t <= self.t and a.sync_until < 0:
                self._execute_grow(a)
        super().step()


class BandSim(V7Mixin, Sim):
    def __init__(self, cfg, arm: Arm, ceiling: int, events, initial, joins):
        Sim.__init__(self, cfg, V6, events, initial, joins)
        self._init_v7(arm, ceiling)


def summarize(arm, sim, m, cfg, t_dist, C):
    S = cfg.sectors
    post = slice(t_dist, None)
    under = np.array(m.frac_under) * S
    st = settle_tick(m.resizes, t_dist)
    widths = np.array([1 << a.level for a in sim.agents if a.alive], dtype=float)
    cov = sim.cov_h[(sim.t - 1) % sim.H]
    return {
        "arm": arm.name,
        "loss": int(np.sum(m.zero_sectors[t_dist:])),
        "floor_min": int(np.min(m.floor[t_dist:])),
        "exposure": int(under[post].sum()),
        "sync_cost": int(m.cum_sync[-1]),
        "resizes": int(np.sum(m.resizes)),
        "settle": (st - t_dist) if st is not None else None,
        "final_copies_mean": float(cov.mean()),
        "final_over_C": int((cov > C).sum()),
        "top_decile": float(np.sort(widths)[-max(1, len(widths) // 10):].sum()
                            / widths.sum()) if widths.size else 0.0,
        "grow_announces": sim.grow_announces,
        "grow_withdrawn": sim.grow_withdrawn,
        "ceiling_refusals": sim.ceiling_refusals,
    }


def one(job):
    key, ticks, t_dist, kw, seed, C = job
    cfg = replace(Config(), seed=seed)
    initial, events, joins = make_world(cfg, ticks, **kw)
    out = []
    for arm in ARMS:
        sim = BandSim(cfg, arm, C, events, initial, joins)
        m = sim.run(ticks)
        out.append({"scenario": key, "seed": seed} | summarize(arm, sim, m, cfg, t_dist, C))
    return out


def main():
    argv = sys.argv
    seeds = int(argv[argv.index("--seeds") + 1]) if "--seeds" in argv else 12
    procs = int(argv[argv.index("--procs") + 1]) if "--procs" in argv else 3
    C = int(argv[argv.index("--ceiling") + 1]) if "--ceiling" in argv else 8
    base = 600_000
    jobs = [(key, ticks, t_dist, kw, base + i, C)
            for key, _title, ticks, t_dist, kw in SCENARIOS for i in range(seeds)]
    with Pool(procs) as pool:
        rows = [r for batch in pool.imap_unordered(one, jobs) for r in batch]

    def mean(xs):
        return float(np.mean(xs)) if xs else float("nan")

    lines = ["# V7 (V6 floor + StaleCap ceiling) in the simulator", "",
             f"{seeds} fresh seeds per scenario (from {base}), 200 agents, R = 5, "
             f"C = {C}. Means over seeds. loss = sector-ticks with no copy; "
             "exposure = sector-ticks below R; sync = sectors fetched in total; "
             "top decile = share of storage held by the 10% largest nodes.", "",
             "| scenario | arm | runs losing data | worst floor | mean exposure | "
             "mean sync | mean resizes | mean settle | mean copies at end | "
             "sectors over C at end | top decile | grows withdrawn | ceiling refusals |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for key, *_ in SCENARIOS:
        for arm in ARMS:
            rs = [r for r in rows if r["scenario"] == key and r["arm"] == arm.name]
            settle = [r["settle"] for r in rs if r["settle"] is not None]
            lines.append(
                f"| {key} | {arm.name} | {sum(r['loss'] > 0 for r in rs)}/{len(rs)} | "
                f"{min(r['floor_min'] for r in rs)} | {mean([r['exposure'] for r in rs]):.0f} | "
                f"{mean([r['sync_cost'] for r in rs]):.0f} | {mean([r['resizes'] for r in rs]):.0f} | "
                f"{mean(settle):.0f} ({len(rs) - len(settle)} never) | "
                f"{mean([r['final_copies_mean'] for r in rs]):.2f} | "
                f"{mean([r['final_over_C'] for r in rs]):.0f} | "
                f"{mean([r['top_decile'] for r in rs]):.1%} | "
                f"{mean([r['grow_withdrawn'] for r in rs]):.0f} | "
                f"{mean([r['ceiling_refusals'] for r in rs]):.0f} |")
    table = "\n".join(lines) + "\n"
    with open(f"results/v7_summary_C{C}.md", "w", encoding="utf-8") as f:
        f.write(table)
    with open(f"results/v7_C{C}.json", "w") as f:
        json.dump(rows, f)
    print(table)


if __name__ == "__main__":
    main()
