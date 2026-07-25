"""Lossy gossip under the AgentInfo-only encoding — closing §12's own caveat.

REPORT_stage3.md §12 measured polite shrink with each viewer's coverage picture
made incomplete *and* inconsistent (messages dropped, not merely stale), and
found the data-loss rate flat out to 90% drop. It carried one scope limit,
stated in `message_loss_sim.py`:

    "Intents (icov/ilist) stay on the base lag — lossy intent gossip is
     future work."

That gap closes itself under the AgentInfo-only encoding. There, the
announcement *is* the arc declaration, so the very channel §12 drops is the
channel the handshake depends on: an announcer's narrowed claim can be lost
exactly like any other coverage update. Nothing extra has to be modelled — the
loss model already covers intents once `_build_declared` reads `a.declared`.

So this run answers a question §12 could not: does the two-phase gate still
hold when the *intent* messages are the ones going missing?

Model is `message_loss_sim.MessageLossSim`'s, re-based on the plain `Sim` (that
one extends the mixed-population `MixedSim`, whose re-implemented `__init__` is
not needed here). At loss = 0 each viewer's rebuilt coverage equals the base
stale snapshot exactly, which is the correctness anchor.

Run:  python3 agentinfo_message_loss.py [--quick]
"""

from __future__ import annotations

import sys

import numpy as np

from polite_shrink import VARIANTS, Config, Sim, block, make_world

V3, V5 = VARIANTS[3], VARIANTS[4]

LOSSES = [0.0, 0.25, 0.5, 0.75, 0.9]
SEEDS = [42, 7, 99, 1234, 20260725]


class LossySim(Sim):
    """Per-viewer, per-peer lossy delivery of declared arcs."""

    def __init__(self, *args, loss: float = 0.0, **kw):
        super().__init__(*args, **kw)
        self.loss = float(loss)
        self.keep = 1.0 - self.loss
        N = len(self.agents)           # join-free scenarios only
        self.N = N
        self.homes = np.array([a.home for a in self.agents])
        self.lags = np.array([a.lag for a in self.agents])
        self._diag = (np.arange(N), np.arange(N))
        self.rng_loss = np.random.default_rng(self.cfg.seed + 17)
        init_lvl = self.lvl_h[0, :N].astype(np.int16)
        self.known = np.tile(init_lvl, (N, 1))            # N x N
        self.cov_view = np.tile(self.cov_h[0].astype(np.int32), (N, 1))

    def _deliver(self):
        N, cfg = self.N, self.cfg
        idxs = (self.t - self.lags) % self.H
        avail = self.lvl_h[idxs][:, :N].astype(np.int16)
        deliver = self.rng_loss.random((N, N)) < self.keep
        deliver[self._diag] = True                        # never lose your own
        change = deliver & (avail != self.known)
        if not change.any():
            return
        vs, ps = np.where(change)
        for a_i, p_i in zip(vs.tolist(), ps.tolist()):
            old, new = int(self.known[a_i, p_i]), int(avail[a_i, p_i])
            hp = int(self.homes[p_i])
            if old >= 0:
                s, e = block(hp, old, cfg.log2s)
                self.cov_view[a_i, s:e] -= 1
            if new >= 0:
                s, e = block(hp, new, cfg.log2s)
                self.cov_view[a_i, s:e] += 1
            self.known[a_i, p_i] = new

    def step(self):
        self._deliver()
        super().step()

    def _view(self, a):
        _cov, _lvl, icov, ilist = super()._view(a)
        # Under V5 the announcer has already narrowed its own declaration, so
        # a dropped delivery here IS a dropped intent — the case §12 deferred.
        return self.cov_view[a.aid], self.known[a.aid], icov, ilist


def run(variant, loss, seed, scen):
    cfg = Config(seed=seed)
    ticks, kw = ((2200, {}) if scen == "activation"
                 else (3000, dict(storm_at=1500, storm_frac=0.30)))
    initial, events, joins = make_world(cfg, ticks, **kw)
    m = LossySim(cfg, variant, events, initial, joins, loss=loss).run(ticks)
    return (int(np.sum(m.zero_sectors)), int(np.sum(m.held_zero)),
            int(np.min(m.floor)), int(np.min(m.held_floor)))


def main():
    quick = "--quick" in sys.argv
    seeds = SEEDS[:2] if quick else SEEDS
    scens = ["storm"] if quick else ["activation", "storm"]
    print(f"Lossy-gossip sweep: {len(seeds)} seeds x {len(LOSSES)} loss rates "
          f"x {len(scens)} scenarios, R = 5, N = 200.")
    print("held_* is the durability ground truth (bytes on disk); declared_* "
          "is what a reader could route to.\n")
    for scen in scens:
        print(f"--- {scen} ---")
        print(f"{'loss':>6} {'variant':>7} {'declared_loss':>14} "
              f"{'held_loss':>10} {'declared_floor':>15} {'held_floor':>11}")
        for loss in LOSSES:
            for v in (V3, V5):
                rs = [run(v, loss, s, scen) for s in seeds]
                print(f"{loss:6.2f} {v.name.split()[0]:>7} "
                      f"{sum(r[0] for r in rs):14d} {sum(r[1] for r in rs):10d} "
                      f"{min(r[2] for r in rs):15d} {min(r[3] for r in rs):11d}")
        print()


if __name__ == "__main__":
    main()
