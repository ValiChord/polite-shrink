"""
message_loss_sim — lossy-gossip model for the arc controller.

The base sim (and every study so far) gives each agent a *complete* view of the
declared world, merely stale by its gossip `lag`: `_view` returns the full
snapshot `cov_h[t-lag]`. Real gossip drops messages, so a viewer's picture is
not just stale but **incomplete and inconsistent across peers** — and it can
miss the very updates that matter most for safety: a peer's *shrink* or *death*.
Missing a coverage-*decrease* makes a viewer **over-count** and shrink into a
hole; missing a coverage-*increase* only makes it over-grow (cost, not loss).

Model. Each viewer a keeps a per-peer last-received level `known[a,p]`. Each
tick, peer p's lag-delayed declaration (`lvl_h[t-lag_a][p]`, exactly what the
base sim would deliver) reaches a with probability `1-loss`; otherwise a keeps
its previous `known[a,p]`. A viewer's coverage is rebuilt from `known` — kept
incrementally, so only actual level-change deliveries touch it. A viewer always
knows its own declaration (self-delivery never drops).

At **loss = 0** every update lands every tick, so `known[a,p] == lvl_h[t-lag_a][p]`
and the per-viewer coverage equals the base snapshot `cov_h[t-lag_a]` exactly —
the model is **byte-identical to MixedSim** (`validate_message_loss.py`). That
reduction is the correctness anchor; loss only ever *removes* information.

Scope (v1): join-free scenarios (activation, storm), so the viewer×peer matrix
has fixed N. Intents (icov/ilist) stay on the base lag — lossy intent gossip is
future work. Python 3.12.1, numpy 2.5.1.
"""

from __future__ import annotations

import numpy as np

from polite_shrink import block
from rolling_upgrade_sim import MixedSim


class MessageLossSim(MixedSim):
    def __init__(self, *args, loss: float = 0.0, **kw):
        super().__init__(*args, **kw)
        self.loss = float(loss)
        self.keep = 1.0 - self.loss
        N = len(self.agents)                       # fixed: v1 is join-free
        self.N = N
        self.homes = np.array([a.home for a in self.agents])
        self.lags = np.array([a.lag for a in self.agents])
        self._diag = (np.arange(N), np.arange(N))
        self.rng_loss = np.random.default_rng(self.cfg.seed + 17)
        # known[a,p] = viewer a's last-received declared level of peer p.
        # init = the initial snapshot (everyone at full arc), matching base init.
        init_lvl = self.lvl_h[0, :N].astype(np.int16)
        self.known = np.tile(init_lvl, (N, 1))     # N×N
        # per-viewer coverage, rebuilt from `known`; init = full snapshot per row.
        base_cov = self.cov_h[0].astype(np.int32)
        self.cov_view = np.tile(base_cov, (N, 1))  # N×S

    def _deliver(self):
        """One gossip round with loss: pull each peer's lag-delayed declaration
        into `known` w.p. keep, and fold every actual change into `cov_view`."""
        N, cfg = self.N, self.cfg
        idxs = (self.t - self.lags) % self.H
        avail = self.lvl_h[idxs][:, :N].astype(np.int16)   # N×N (viewer×peer)
        deliver = self.rng_loss.random((N, N)) < self.keep
        deliver[self._diag] = True                         # self-knowledge is exact
        change = deliver & (avail != self.known)
        if not change.any():
            return
        vs, ps = np.where(change)
        for a_i, p_i in zip(vs.tolist(), ps.tolist()):
            old = int(self.known[a_i, p_i])
            new = int(avail[a_i, p_i])
            hp = int(self.homes[p_i])
            if old >= 0:
                s, e = block(hp, old, cfg.log2s)
                self.cov_view[a_i, s:e] -= 1
            if new >= 0:
                s, e = block(hp, new, cfg.log2s)
                self.cov_view[a_i, s:e] += 1
            self.known[a_i, p_i] = new

    def step(self):
        self._deliver()          # refresh lossy views before this tick's decisions
        super().step()

    def _view(self, a):
        _cov, _lvl, icov, ilist = super()._view(a)
        # replace the complete stale snapshot with a's lossy, per-peer view
        return self.cov_view[a.aid], self.known[a.aid], icov, ilist
