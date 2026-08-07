"""
detector_error_sim — what does a *wrong* failure detector cost?

Every study so far treats death detection as a clock: `DecoupledSim` gives each
agent a `death_lag`, and a peer that dies at D is counted until D + death_lag.
Detection is late, but it is never *wrong* — no agent ever convicts a peer that
is still alive. Real failure detectors are not like that. In an asynchronous
network you cannot distinguish "crashed" from "slow", so any detector trades
detection speed against false accusations (Chandra & Toueg, 1996; the phi
accrual detector of Hayashibara et al. is the accrual form used in Cassandra and
Akka).

REPORT_stage3.md constraint 6 already says the shrink wait must be sized against
detection latency rather than gossip staleness. This study asks the question
that constraint leaves open: **which direction should a detector err in?**

The mechanism argument says the asymmetry is favourable:

  * **False positive** (convict a live peer) -> the viewer *under*-counts
    coverage -> its shrink condition `seg.min() >= R+1` gets harder and its grow
    condition `eff.min() < R` gets easier -> it holds MORE data. Costs bandwidth
    and storage.
  * **False negative** (miss a real death) -> the viewer *over*-counts -> it
    shrinks when it should not. Costs data.

If that holds, a detector should be tuned deliberately paranoid. But it is an
argument, not a measurement — exactly where §11's "irreducible" claim sat before
`mz_probe.py` measured it. This module measures it.

Model
-----
`DetectorErrorSim` adds one parameter to `DecoupledSim`: `false_convict_p`, the
per-(viewer, peer) probability that a *live* peer is wrongly excluded from the
viewer's coverage at the moment the viewer looks. Convictions are redrawn per
view, which models a memoryless detector with instantaneous false-positive rate
p — the simplest probe that isolates the cost of a false positive from any
particular detector's dynamics.

Only the coverage array is affected, matching how a real conviction works: an
unresponsive peer is excluded from coverage, not erased from the world. The
agent's own declaration is never self-convicted.

Deliberately *not* modelled (this is step 1 of three): heartbeat inter-arrival
distributions, per-peer heterogeneity, and detector memory. Those are what a phi
accrual detector needs in order to be more than a fixed timeout, and they are
worth building only if the asymmetry measured here holds.

Faithfulness guard
------------------
At `false_convict_p = 0.0` the draw is skipped entirely and the model is
**byte-identical to `DecoupledSim`** (`validate_detector_error.py`). A dedicated
RNG stream (`cfg.seed + 23`) is used so no existing stream is perturbed.

Determinism: pins as polite_shrink.py. See REPORT_mz_decomposition.md for the
environment caveat on locally produced digits.
"""

from __future__ import annotations

import numpy as np

from polite_shrink import block
from decoupled_sim import DecoupledSim


class DetectorErrorSim(DecoupledSim):
    def __init__(self, *args, false_convict_p: float = 0.0, **kw):
        super().__init__(*args, **kw)
        self.p_fc = float(false_convict_p)
        self.rng_fc = np.random.default_rng(self.cfg.seed + 23)
        self.false_convictions = 0
        # Scratch buffer for the difference-array trick below; one allocation
        # rather than one per view call.
        self._diff = np.zeros(self.cfg.sectors + 1, dtype=np.int32)

    def _homes_array(self, n: int) -> np.ndarray:
        """Home sectors, cached. Homes never change; the array only grows as
        agents join, so it is extended rather than rebuilt."""
        cached = getattr(self, "_homes", None)
        if cached is None or cached.size < n:
            self._homes = np.array([ag.home for ag in self.agents],
                                   dtype=np.int64)
        return self._homes

    def _p_for(self, a) -> float:
        """This viewer's false-conviction rate. One global rate here; the
        heterogeneous study (`hetero_detector_sim.py`) overrides this to give
        each agent its own, which is the only hook it needs."""
        return self.p_fc

    def _view(self, a):
        cov, lvl, icov, ilist = super()._view(a)
        p = self._p_for(a)
        if p <= 0.0:
            return cov, lvl, icov, ilist            # exact reduction to DecoupledSim

        n = len(self.agents)
        convicted = self.rng_fc.random(n) < p
        convicted[a.aid] = False                    # never self-convict

        # A viewer convicts on what it *sees*, so the coverage removed is the
        # peer's lagged declaration `lvl[p]` -- not the peer's current true
        # level. lvl < 0 means "not visible to me anyway", so nothing to remove.
        seen = np.asarray(lvl[:n], dtype=np.int64)
        target = np.flatnonzero(convicted & (seen >= 0))
        if target.size == 0:
            return cov, lvl, icov, ilist

        log2s, S = self.cfg.log2s, self.cfg.sectors
        homes = self._homes_array(n)[target]
        lv = seen[target]
        # Vectorised form of polite_shrink.block(): aligned power-of-two blocks,
        # with the full-arc case (level >= log2s) spanning the whole ring.
        full = lv >= log2s
        start = np.where(full, 0, (homes >> lv) << lv)
        end = np.where(full, S, start + (np.int64(1) << np.minimum(lv, log2s)))

        # Difference array + one cumsum: O(convicted) + O(sectors) per view,
        # with no Python-level loop. This runs in the hot path.
        diff = self._diff
        diff[:] = 0
        np.add.at(diff, start, -1)
        np.add.at(diff, end, 1)
        self.false_convictions += int(target.size)
        adj = np.cumsum(diff[:-1])
        # Coverage cannot go negative: a viewer that has convicted everyone
        # covering a sector simply sees zero there.
        out = np.maximum(cov.astype(np.int32) + adj, 0)
        return out.astype(cov.dtype), lvl, icov, ilist
