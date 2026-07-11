"""
arc_sim — Stage-1 simulator for DHT storage-arc dynamics (kitsune2 issue #160).

Models N agents on a quantised ring of S sectors. Each agent claims an
*aligned power-of-two block* of sectors containing its fixed home sector
(faithful to kitsune's quantised-arc design: the only state is the block
"level"; level L = block of 2^L sectors; level log2(S) = full arc).

Every agent runs a local controller that decides, from a *stale* view of
peers' declared arcs (gossip lag), whether to grow (double) or shrink
(halve) its block to hold a redundancy target R. Four controller variants
isolate the ingredients under test:

  V0 naive        react immediately, synchronized epochs, instant drop
  V1 damped       + hysteresis scaled to the agent's own measured lag
                    (grow after 1x lag persistence, shrink after 4x)
  V2 +jitter      + desynchronised decision epochs (TCP-RED lesson)
  V3 polite       + two-phase shrink: announce intent, wait 2x max lag,
                    re-check, deterministic lowest-id-proceeds tie-break
                    (TCAS lesson); growers treat announced vacates as gone

Simplifications (documented in README.md): full peer visibility, one lag
per viewer (not per pair), honest agents, sync time linear in sectors,
no adversaries, no real network. This tests control-loop *dynamics* only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

BIG = np.int32(2**31 - 1)


@dataclass
class Config:
    log2s: int = 9          # ring has S = 2^log2s sectors
    n_agents: int = 200
    redundancy: int = 5     # R: target copies of every sector
    lag_min: int = 8        # gossip staleness, ticks (per-viewer, fixed)
    lag_max: int = 24
    eval_every: int = 6     # decision-epoch period E, ticks
    sync_per_sector: float = 0.05   # ticks to fetch+validate one sector
    grow_k: float = 1.0     # grow-persistence  = grow_k  * own lag (ticks)
    shrink_k: float = 4.0   # shrink-persistence = shrink_k * own lag
    intent_delay: int = 50  # two-phase shrink wait (> 2 * lag_max)
    clamp_min_peers: int = 25   # V3: below this visible-peer count, go full
    seed: int = 42

    @property
    def sectors(self) -> int:
        return 1 << self.log2s


@dataclass
class Variant:
    name: str
    hysteresis: bool
    jitter: bool
    polite: bool


VARIANTS = [
    Variant("V0 naive", hysteresis=False, jitter=False, polite=False),
    Variant("V1 damped", hysteresis=True, jitter=False, polite=False),
    Variant("V2 damped+jitter", hysteresis=True, jitter=True, polite=False),
    Variant("V3 full (polite shrink)", hysteresis=True, jitter=True, polite=True),
]


@dataclass
class Agent:
    aid: int
    home: int
    lag: int
    phase: int
    level: int                  # currently synced/declared block level
    alive: bool = True
    sync_until: int = -1        # tick when in-flight grow completes (-1 = none)
    sync_target: int = -1
    grow_acc: int = 0           # ticks the grow condition has persisted
    shrink_acc: int = 0
    intent_at: int = -1         # tick a pending vacate-intent executes (-1 = none)


def block(home: int, level: int, log2s: int) -> tuple[int, int]:
    """Aligned block [start, end) of 2^level sectors containing `home`."""
    if level >= log2s:
        return 0, 1 << log2s
    size = 1 << level
    start = (home >> level) << level
    return start, start + size


def sibling_half(home: int, level: int, log2s: int) -> tuple[int, int]:
    """Sectors gained by growing level -> level+1 (the sibling half of the
    parent block). Contiguous by construction."""
    ps, pe = block(home, level + 1, log2s)
    cs, ce = block(home, level, log2s)
    return (ce, pe) if ps == cs else (ps, cs)


def vacate_half(home: int, level: int, log2s: int) -> tuple[int, int]:
    """Sectors dropped by shrinking level -> level-1 (the half of the current
    block not containing home)."""
    cs, ce = block(home, level, log2s)
    ks, ke = block(home, level - 1, log2s)
    return (ke, ce) if cs == ks else (cs, ks)


@dataclass
class Metrics:
    floor: list = field(default_factory=list)        # min sector coverage
    frac_under: list = field(default_factory=list)   # fraction of sectors < R
    zero_sectors: list = field(default_factory=list) # sectors with 0 copies
    mean_level: list = field(default_factory=list)
    resizes: list = field(default_factory=list)      # arc changes this tick
    cum_sync: list = field(default_factory=list)     # cumulative sectors synced


class Sim:
    def __init__(self, cfg: Config, variant: Variant, events: dict,
                 initial: list[tuple[int, int]], joins: dict):
        """
        events:  tick -> list of agent ids that die at that tick
        initial: list of (home, lag) for the starting population
        joins:   tick -> list of (home, lag) joining at that tick
        (all pre-generated so every variant faces the identical world)
        """
        self.cfg = cfg
        self.v = variant
        self.events = events
        self.joins = joins
        self.t = 0
        self.m = Metrics()
        self.sync_cost = 0
        self.resize_events = 0

        S, H = cfg.sectors, cfg.lag_max + 2
        self.H = H
        max_agents = len(initial) + sum(len(j) for j in joins.values())
        self.agents: list[Agent] = []
        rng = np.random.default_rng(cfg.seed + 1)
        for home, lag in initial:
            phase = int(rng.integers(0, cfg.eval_every)) if variant.jitter else 0
            self.agents.append(Agent(len(self.agents), home, lag, phase,
                                     level=cfg.log2s))  # start full-arc
        self._join_rng = rng

        # Ring-buffer histories of the *declared* world, one slot per tick.
        self.cov_h = np.zeros((H, S), dtype=np.int16)
        self.lvl_h = np.full((H, max_agents), -1, dtype=np.int8)
        self.icov_h = np.zeros((H, S), dtype=np.int16)
        self.ilist_h: list[list[tuple[int, int, int]]] = [[] for _ in range(H)]
        snap_cov, snap_lvl = self._build_declared()
        for i in range(H):
            self.cov_h[i] = snap_cov
            self.lvl_h[i, :len(self.agents)] = snap_lvl

    # ---------------------------------------------------------- snapshots
    def _build_declared(self):
        cfg = self.cfg
        cov = np.zeros(cfg.sectors, dtype=np.int16)
        lvl = np.full(len(self.agents), -1, dtype=np.int8)
        for a in self.agents:
            if a.alive:
                s, e = block(a.home, a.level, cfg.log2s)
                cov[s:e] += 1
                lvl[a.aid] = a.level
        return cov, lvl

    def _store_snapshot(self):
        cfg = self.cfg
        idx = self.t % self.H
        cov, lvl = self._build_declared()
        self.cov_h[idx] = cov
        self.lvl_h[idx, :len(self.agents)] = lvl
        icov = np.zeros(cfg.sectors, dtype=np.int16)
        ilist = []
        for a in self.agents:
            if a.alive and a.intent_at > self.t:
                s, e = vacate_half(a.home, a.level, cfg.log2s)
                icov[s:e] += 1
                ilist.append((a.aid, s, e))
        self.icov_h[idx] = icov
        self.ilist_h[idx] = ilist

    def _view(self, a: Agent):
        """The stale snapshots agent `a` sees at time t."""
        idx = (self.t - a.lag) % self.H
        return (self.cov_h[idx], self.lvl_h[idx],
                self.icov_h[idx], self.ilist_h[idx])

    # ---------------------------------------------------------- decisions
    def _sync_ticks(self, sectors_added: int) -> int:
        return max(1, round(self.cfg.sync_per_sector * sectors_added))

    def _start_grow(self, a: Agent):
        added = (1 << a.level) if a.level < self.cfg.log2s - 1 else \
                (self.cfg.sectors - (1 << a.level))
        a.sync_target = a.level + 1
        a.sync_until = self.t + self._sync_ticks(added)
        a.grow_acc = a.shrink_acc = 0
        a.intent_at = -1
        self.sync_cost += added
        self.resize_events += 1

    def _do_shrink(self, a: Agent):
        a.level -= 1
        a.grow_acc = a.shrink_acc = 0
        a.intent_at = -1
        self.resize_events += 1

    def _decide(self, a: Agent):
        cfg = self.cfg
        cov, lvl, icov, _ilist = self._view(a)
        own_lvl_then = int(lvl[a.aid])  # my declaration as peers saw it then

        # V3 small-network clamp: too few visible peers -> full arc, always.
        if self.v.polite:
            visible = int((lvl[:len(self.agents)] >= 0).sum())
            if visible < cfg.clamp_min_peers:
                if a.level < cfg.log2s and a.sync_until < 0:
                    self._start_grow(a)
                return

        # Grow check: would the sibling half be under-covered?
        # (Polite variant treats announced vacates as already gone.)
        grow_cond = False
        if a.level < cfg.log2s:
            ws, we = sibling_half(a.home, a.level, cfg.log2s)
            eff = cov[ws:we] - icov[ws:we] if self.v.polite else cov[ws:we]
            grow_cond = bool(eff.min() < cfg.redundancy)

        # Shrink check: can the half I'd drop spare me?
        shrink_cond = False
        if a.level > 0:
            vs, ve = vacate_half(a.home, a.level, cfg.log2s)
            seg = cov[vs:ve].astype(np.int32)
            if own_lvl_then >= a.level:    # my old declaration covered it
                seg = seg - 1
            shrink_cond = bool(seg.min() >= cfg.redundancy + 1)

        # Hysteresis accumulators (in ticks; epochs advance them by E).
        E = cfg.eval_every
        a.grow_acc = a.grow_acc + E if grow_cond else 0
        a.shrink_acc = a.shrink_acc + E if shrink_cond else 0
        grow_need = math.ceil(cfg.grow_k * a.lag) if self.v.hysteresis else 0
        shrink_need = math.ceil(cfg.shrink_k * a.lag) if self.v.hysteresis else 0

        if grow_cond and a.grow_acc >= grow_need:
            self._start_grow(a)          # safety first: growing aborts intents
        elif shrink_cond and a.shrink_acc >= shrink_need and a.intent_at < 0:
            if self.v.polite:
                a.intent_at = self.t + cfg.intent_delay
            else:
                self._do_shrink(a)

    def _execute_intent(self, a: Agent):
        """Two-phase shrink, phase 2: proceed only if the vacated half keeps
        >= R copies after me AND every lower-priority (lower-id) announced
        intender have all left (TCAS tie-break: lower id proceeds first;
        higher-id intenders count me the same way and so defer to me)."""
        cfg = self.cfg
        cov, lvl, _icov, ilist = self._view(a)
        vs, ve = vacate_half(a.home, a.level, cfg.log2s)
        eff = cov[vs:ve].astype(np.int32)
        if int(lvl[a.aid]) >= a.level:      # my own stale declaration covers it
            eff -= 1
        for aid2, s2, e2 in ilist:
            if aid2 < a.aid:                # only lower ids outrank me
                lo, hi = max(vs, s2), min(ve, e2)
                if lo < hi:
                    eff[lo - vs:hi - vs] -= 1
        if bool(eff.min() >= cfg.redundancy):
            self._do_shrink(a)
        else:
            a.intent_at = -1
            a.shrink_acc = 0

    # ---------------------------------------------------------- main loop
    def step(self):
        cfg, t = self.cfg, self.t
        self.resize_events = 0

        # 1. Completed grows come online.
        for a in self.agents:
            if a.alive and 0 <= a.sync_until <= t:
                a.level = a.sync_target
                a.sync_until = a.sync_target = -1

        # 2. Due vacate-intents execute (polite variant only).
        for a in self.agents:
            if a.alive and a.intent_at == t:
                self._execute_intent(a)

        # 3. Decision epochs.
        for a in self.agents:
            if (a.alive and a.sync_until < 0
                    and t % cfg.eval_every == a.phase
                    and (a.intent_at < 0 or not self.v.polite)):
                self._decide(a)

        # 4. World events: deaths, joins.
        for aid in self.events.get(t, ()):
            self.agents[aid].alive = False
        for home, lag in self.joins.get(t, ()):
            phase = (int(self._join_rng.integers(0, cfg.eval_every))
                     if self.v.jitter else 0)
            a = Agent(len(self.agents), home, lag, phase, level=0)
            a.sync_until = t + 1   # tiny initial sync
            a.sync_target = 0
            self.agents.append(a)

        # 5. Publish declarations; 6. record ground truth.
        self._store_snapshot()
        cov = self.cov_h[t % self.H]
        alive_lv = [a.level for a in self.agents if a.alive]
        self.m.floor.append(int(cov.min()))
        self.m.frac_under.append(float((cov < cfg.redundancy).mean()))
        self.m.zero_sectors.append(int((cov == 0).sum()))
        self.m.mean_level.append(float(np.mean(alive_lv)) if alive_lv else 0.0)
        self.m.resizes.append(self.resize_events)
        self.m.cum_sync.append(self.sync_cost)
        self.t += 1

    def run(self, ticks: int):
        for _ in range(ticks):
            self.step()
        return self.m


# ------------------------------------------------------------- scenarios
def make_world(cfg: Config, ticks: int, storm_at: int | None = None,
               storm_frac: float = 0.0, crowd_at: int | None = None,
               crowd_frac: float = 0.0, churn_from: int | None = None,
               churn_death_p: float = 0.0):
    """Pre-generate the identical world (homes, lags, deaths, joins) that
    every controller variant will face."""
    rng = np.random.default_rng(cfg.seed)
    S = cfg.sectors
    initial = [(int(rng.integers(0, S)),
                int(rng.integers(cfg.lag_min, cfg.lag_max + 1)))
               for _ in range(cfg.n_agents)]
    events: dict[int, list[int]] = {}
    joins: dict[int, list[tuple[int, int]]] = {}

    if storm_at is not None:
        victims = rng.choice(cfg.n_agents, int(cfg.n_agents * storm_frac),
                             replace=False)
        events[storm_at] = [int(v) for v in victims]

    if crowd_at is not None:
        joins[crowd_at] = [(int(rng.integers(0, S)),
                            int(rng.integers(cfg.lag_min, cfg.lag_max + 1)))
                           for _ in range(int(cfg.n_agents * crowd_frac))]

    if churn_from is not None:
        alive = set(range(cfg.n_agents))
        next_id = cfg.n_agents
        for t in range(churn_from, ticks):
            # sorted(): iterate in a defined order so the RNG-consumption
            # sequence is identical across interpreters (set order is not
            # a portability guarantee) — keeps results byte-reproducible.
            dead = [a for a in sorted(alive) if rng.random() < churn_death_p]
            if dead:
                events.setdefault(t, []).extend(dead)
                alive -= set(dead)
            n_join = rng.poisson(churn_death_p * cfg.n_agents)
            if n_join:
                js = [(int(rng.integers(0, S)),
                       int(rng.integers(cfg.lag_min, cfg.lag_max + 1)))
                      for _ in range(n_join)]
                joins.setdefault(t, []).extend(js)
                alive |= set(range(next_id, next_id + n_join))
                next_id += n_join
    return initial, events, joins
