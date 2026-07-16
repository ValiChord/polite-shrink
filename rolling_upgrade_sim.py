"""
rolling_upgrade_sim — mixed-controller ("rolling upgrade") extension of the
Stage-1 simulator (`polite_shrink.py`), for kitsune2 issue #160.

Motivation
----------
The Stage-1 sweep runs a *homogeneous* network: every agent runs the same
controller variant. A real network never upgrades atomically — during a
rollout some nodes run the new polite-shrink controller (V3) and some still
run the old naive one (V0). A maintainer's natural question is therefore:

    Is a *partially* upgraded network safe, or does a naive minority
    reintroduce the data loss the polite shrink was built to prevent?

Mechanism hazard being probed: a V0 agent shrinks *instantly* on its stale
view and **never announces a vacate intent**. Polite growers only ever see
announced intents (`icov`/`ilist` in polite_shrink are populated solely by agents
with a pending `intent_at`). So a naive agent is an *invisible-shrink*
hazard to its polite neighbours: they cannot pre-empt a hole they cannot see.

Design
------
`MixedSim` is a thin subclass of `polite_shrink.Sim`. The only change is that the
controller variant becomes a *per-agent* property (`Agent.variant`, set as an
ad-hoc attribute since polite_shrink's frozen `Agent` dataclass has no such field)
rather than one variant for the whole sim. Every method that consulted
`self.v` is overridden to consult the *deciding agent's own* variant. All the
snapshot / view / intent machinery is variant-agnostic and inherited
unchanged — `_execute_intent` is only ever reached by agents that set
`intent_at`, which only polite agents do, so it is naturally safe.

Faithfulness guard
------------------
The rng-consumption order is preserved exactly, so the mixed sim *reduces to*
the pure Stage-1 sim at the extremes:

    MixedSim(fraction_v3=0.0)  ==  Sim(V0 naive)          (byte-identical)
    MixedSim(fraction_v3=1.0)  ==  Sim(V3 polite shrink)  (byte-identical)

`validate_rolling_upgrade.py` asserts this on every scenario. It is the primary
defence against a modelling bug in the fork.

Determinism: Python 3.12.1, numpy 2.5.1 — same pins as polite_shrink.
"""

from __future__ import annotations

import math

import numpy as np

from polite_shrink import (VARIANTS, Agent, Config, Metrics, Sim, block,
                     sibling_half, vacate_half)

V0 = VARIANTS[0]   # naive
V3 = VARIANTS[3]   # full polite shrink


def assign_initial_variants(n: int, fraction_v3: float, seed: int) -> list:
    """Return a per-agent variant list of length n with exactly round(n*f)
    agents set to V3 (polite) and the rest V0 (naive). The upgraded subset is
    chosen by a seeded permutation so it is uncorrelated with home sector and
    reproducible. At f=0 -> all V0; at f=1 -> all V3 (exact, no draw noise)."""
    k = round(n * fraction_v3)
    rng = np.random.default_rng(seed + 7)      # dedicated stream (see module doc)
    order = rng.permutation(n)
    upgraded = set(int(i) for i in order[:k])
    return [V3 if i in upgraded else V0 for i in range(n)]


class MixedSim(Sim):
    """Stage-1 Sim with a per-agent controller variant."""

    def __init__(self, cfg: Config, agent_variants: list, events: dict,
                 initial: list[tuple[int, int]], joins: dict,
                 fraction_v3: float):
        # --- faithful re-implementation of Sim.__init__, per-agent variant ---
        # (rewritten rather than super().__init__ so that phase draws are
        #  consumed in the same order and only for jittered agents, giving
        #  byte-identical reduction to the pure sim at f in {0,1}.)
        self.cfg = cfg
        self.events = events
        self.joins = joins
        self.fraction_v3 = fraction_v3
        self.t = 0
        self.m = Metrics()
        self.sync_cost = 0
        self.resize_events = 0

        S, H = cfg.sectors, cfg.lag_max + 2
        self.H = H
        max_agents = len(initial) + sum(len(j) for j in joins.values())
        self.agents: list[Agent] = []
        rng = np.random.default_rng(cfg.seed + 1)
        for (home, lag), var in zip(initial, agent_variants):
            phase = int(rng.integers(0, cfg.eval_every)) if var.jitter else 0
            a = Agent(len(self.agents), home, lag, phase, level=cfg.log2s)
            a.variant = var                    # ad-hoc per-agent controller
            self.agents.append(a)
        self._join_rng = rng
        # joiners get a variant from a dedicated stream; at f in {0,1} this is
        # constant (random() < 0 -> never; random() < 1 -> always) so extremes
        # stay exact without perturbing the world/join rng streams.
        self._upgrade_rng = np.random.default_rng(cfg.seed + 11)

        self.cov_h = np.zeros((H, S), dtype=np.int16)
        self.lvl_h = np.full((H, max_agents), -1, dtype=np.int8)
        self.icov_h = np.zeros((H, S), dtype=np.int16)
        self.ilist_h: list[list[tuple[int, int, int]]] = [[] for _ in range(H)]
        snap_cov, snap_lvl = self._build_declared()
        for i in range(H):
            self.cov_h[i] = snap_cov
            self.lvl_h[i, :len(self.agents)] = snap_lvl

    # -------------------------------------------------- decision (per-agent v)
    def _decide(self, a: Agent):
        cfg = self.cfg
        v = a.variant                          # <-- was self.v
        cov, lvl, icov, _ilist = self._view(a)
        own_lvl_then = int(lvl[a.aid])

        if v.polite:
            visible = int((lvl[:len(self.agents)] >= 0).sum())
            if visible < cfg.clamp_min_peers:
                if a.level < cfg.log2s and a.sync_until < 0:
                    self._start_grow(a)
                return

        grow_cond = False
        if a.level < cfg.log2s:
            ws, we = sibling_half(a.home, a.level, cfg.log2s)
            eff = cov[ws:we] - icov[ws:we] if v.polite else cov[ws:we]
            grow_cond = bool(eff.min() < cfg.redundancy)

        shrink_cond = False
        if a.level > 0:
            vs, ve = vacate_half(a.home, a.level, cfg.log2s)
            seg = cov[vs:ve].astype(np.int32)
            if own_lvl_then >= a.level:
                seg = seg - 1
            shrink_cond = bool(seg.min() >= cfg.redundancy + 1)

        E = cfg.eval_every
        a.grow_acc = a.grow_acc + E if grow_cond else 0
        a.shrink_acc = a.shrink_acc + E if shrink_cond else 0
        grow_need = math.ceil(cfg.grow_k * a.lag) if v.hysteresis else 0
        shrink_need = math.ceil(cfg.shrink_k * a.lag) if v.hysteresis else 0

        if grow_cond and a.grow_acc >= grow_need:
            self._start_grow(a)
        elif shrink_cond and a.shrink_acc >= shrink_need and a.intent_at < 0:
            if v.polite:
                a.intent_at = self.t + cfg.intent_delay
            else:
                self._do_shrink(a)

    # -------------------------------------------------- main loop (per-agent v)
    def step(self):
        cfg, t = self.cfg, self.t
        self.resize_events = 0

        for a in self.agents:
            if a.alive and 0 <= a.sync_until <= t:
                a.level = a.sync_target
                a.sync_until = a.sync_target = -1

        for a in self.agents:
            if a.alive and a.intent_at == t:
                self._execute_intent(a)

        for a in self.agents:
            if (a.alive and a.sync_until < 0
                    and t % cfg.eval_every == a.phase
                    and (a.intent_at < 0 or not a.variant.polite)):   # <-- per-agent
                self._decide(a)

        for aid in self.events.get(t, ()):
            self.agents[aid].alive = False
        for home, lag in self.joins.get(t, ()):
            jvar = V3 if self._upgrade_rng.random() < self.fraction_v3 else V0
            phase = (int(self._join_rng.integers(0, cfg.eval_every))
                     if jvar.jitter else 0)
            a = Agent(len(self.agents), home, lag, phase, level=0)
            a.variant = jvar
            a.sync_until = t + 1
            a.sync_target = 0
            self.agents.append(a)

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


def run_mixed(cfg: Config, ticks: int, world, fraction_v3: float) -> Metrics:
    """Run one mixed-controller world. `world` = (initial, events, joins)."""
    initial, events, joins = world
    variants = assign_initial_variants(len(initial), fraction_v3, cfg.seed)
    return MixedSim(cfg, variants, events, initial, joins, fraction_v3).run(ticks)
