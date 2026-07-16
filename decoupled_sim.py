"""
decoupled_sim — the §6.1 "two clocks" model for the arc controller.

The base sim (and every study so far) uses ONE staleness parameter, `lag`, for
both (a) how stale an agent's *view* of peers' declared arcs is, and (b) how
quickly a peer *death* becomes visible. REPORT_stage1.md §6.1 is explicit that
in kitsune2 these are **independent clocks** — view staleness is peer-store
gossip propagation; death visibility is *unresponsive marking* — and that the
report's headline §6.1 race rate (0.002% at R=5) is therefore a *coupled-clock*
number, with the decoupled death-clock left unquantified.

This model decouples them. Each agent keeps its gossip `lag` (arc/coverage view
staleness) and gains a separate **death-detection latency** `death_lag`: a peer
that dies at tick D is still *counted in coverage* by an agent until D +
death_lag (its AgentInfo lingers in the peer store; unresponsive marking is what
removes it). The §6.1 race is exactly coverage over-counting not-yet-detected
deaths at an intent's execute re-check.

Coverage seen by agent a at time t, for a victim p that died at D_p:
    counted  ⟺  D_p > t − death_lag_a      (not yet detected)
base cov (`cov_h[t−lag_a]`) instead has:
    counted  ⟺  D_p > t − lag_a            (alive in the stale view)
so the decoupled coverage is the base snapshot adjusted for victims that fall in
the window between the two clocks (+ if slow detection still counts them, − if
fast detection has already dropped them). When death_lag_a == lag_a the two
agree for every victim and the model is **byte-identical to the base sim** — the
reduction guard (`validate_decoupled.py`).

Also here: `DecoupledBrakeSim`, the storm brake on the *detection* clock — when
agent a detects a peer death (at D + death_lag_a) it cancels its pending shrink
intents. This is the sim-faithful brake: it fires exactly as fast as detection,
so fast detection both keeps coverage honest *and* brakes early; slow detection
does neither (the report's irreducible residual).

Determinism: Python 3.12.1, numpy 2.5.1.
"""

from __future__ import annotations

import numpy as np

from polite_shrink import block
from rolling_upgrade_sim import MixedSim


class DecoupledSim(MixedSim):
    def __init__(self, *args, death_lag=None, **kw):
        """death_lag: None -> coupled (a.death_lag = a.lag, reduces to MixedSim);
        an int -> uniform detection latency for every agent."""
        super().__init__(*args, **kw)
        self._coupled = death_lag is None
        for a in self.agents:
            a.death_lag = a.lag if self._coupled else int(death_lag)
        self._uniform_death_lag = None if self._coupled else int(death_lag)
        # death tick -> summed coverage array of the peers that die at that tick
        self.victim_cov_by_tick: dict[int, np.ndarray] = {}

    # -- record each death's declared coverage as it happens (peer-store block) --
    def _record_deaths(self):
        cfg = self.cfg
        vids = self.events.get(self.t, ())
        if not vids:
            return
        vcov = np.zeros(cfg.sectors, dtype=np.int32)
        for aid in vids:
            a = self.agents[aid]
            if a.alive:                       # its last declared block
                s, e = block(a.home, a.level, cfg.log2s)
                vcov[s:e] += 1
        if vcov.any():
            self.victim_cov_by_tick[self.t] = (
                self.victim_cov_by_tick.get(self.t, 0) + vcov)

    def step(self):
        self._record_deaths()                 # before super() applies the deaths
        super().step()

    # -- coverage on the decoupled clock ---------------------------------------
    def _view(self, a):
        cov, lvl, icov, ilist = super()._view(a)
        if self._coupled or not self.victim_cov_by_tick:
            return cov, lvl, icov, ilist
        view_time = self.t - a.lag
        detect_time = self.t - a.death_lag
        if view_time == detect_time:
            return cov, lvl, icov, ilist
        lo, hi = (detect_time, view_time) if detect_time < view_time else (view_time, detect_time)
        adj = None
        for D, vcov in self.victim_cov_by_tick.items():
            if lo < D <= hi:
                if adj is None:
                    adj = np.zeros_like(vcov)
                # decoupled counts victim iff D > detect_time; base view iff D > view_time
                adj += vcov if D > detect_time else -vcov
        if adj is None:
            return cov, lvl, icov, ilist
        return (cov + adj).astype(cov.dtype), lvl, icov, ilist


class DecoupledBrakeSim(DecoupledSim):
    """DecoupledSim + storm brake on the detection clock: agent a cancels its
    pending shrink intents at the tick it detects a peer death (D + death_lag_a)."""

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.brake_fires = 0

    def step(self):
        self._record_deaths()
        # brake: cancel a's pending intents on the tick a detects any death.
        for D in self.events:
            if not self.events[D] or D >= self.t:
                continue
            for a in self.agents:
                if a.alive and a.intent_at >= 0 and D + a.death_lag == self.t:
                    a.intent_at = -1
                    a.shrink_acc = 0
                    self.brake_fires += 1
        # now run the tick (skip DecoupledSim.step's own _record_deaths re-call)
        MixedSim.step(self)
