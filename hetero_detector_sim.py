"""
hetero_detector_sim — does the detector optimum *move* across a mixed network?

`detector_error_sweep.py` established that a detector has an optimal error
direction, and that the optimum sits where its false-positive rate cancels the
over-count that slow detection produces. That optimum is therefore a function of
detection latency (constraint 6b).

Every run so far gave the whole network **one** detection latency. A real DHT
does not: a phone on a flaky link is marked unresponsive on a very different
timescale from a server on fibre. If the optimum moves with latency and the
network's latencies differ, then a single global threshold is wrong for most
peers — and adaptive, self-calibrating detection (the phi accrual family used in
Cassandra and Akka) would be buying something real.

**This study is deliberately a measurement, not a detector.** It does not
implement phi accrual, heartbeat inter-arrival distributions, or detector memory.
It asks the one question that decides whether any of that is worth building:

    In a network with two detection-latency classes, does tuning each class
    separately beat the best single global setting -- and by how much?

If the gap is large, adaptive detection is justified with a number attached. If
it is small, a fixed threshold is fine and the machinery would answer a question
nobody has. Either answer is a result.

Model
-----
Agents are split into two classes by a seeded permutation (uncorrelated with home
sector, so class is not confounded with geography):

  * **fast** — detection latency `dl_fast`, false-conviction rate `p_fast`
  * **slow** — detection latency `dl_slow`, false-conviction rate `p_slow`

Both knobs are per-agent. `DecoupledSim` already stores `death_lag` per agent, so
latency needs no new machinery; the conviction rate hooks into
`DetectorErrorSim._p_for`, which exists for exactly this.

Faithfulness guard
------------------
With `dl_fast == dl_slow` and `p_fast == p_slow` the model is **byte-identical to
`DetectorErrorSim`** at that setting (`validate_hetero_detector.py`), which in
turn reduces to `DecoupledSim` at p=0. No new RNG stream is introduced: the class
assignment uses a dedicated one (`cfg.seed + 29`) drawn once at construction, and
the conviction draws are the same sequence `DetectorErrorSim` already makes.

Determinism: pins as polite_shrink.py; see REPORT_mz_decomposition.md for the
environment caveat on locally produced digits.
"""

from __future__ import annotations

import numpy as np

from detector_error_sim import DetectorErrorSim

FAST, SLOW = 0, 1


class HeteroDetectorSim(DetectorErrorSim):
    def __init__(self, *args, dl_fast: int = 24, dl_slow: int = 192,
                 p_fast: float = 0.0, p_slow: float = 0.0,
                 frac_slow: float = 0.5, **kw):
        # death_lag is passed through to DecoupledSim only to put it in
        # decoupled (not coupled) mode; every agent's value is overwritten below.
        kw.setdefault("death_lag", dl_slow)
        kw.setdefault("false_convict_p", max(p_fast, p_slow))
        super().__init__(*args, **kw)
        self.dl = {FAST: int(dl_fast), SLOW: int(dl_slow)}
        self.p = {FAST: float(p_fast), SLOW: float(p_slow)}
        self.frac_slow = float(frac_slow)

        # Class assignment: a seeded permutation, so membership is uncorrelated
        # with home sector and with the agent-id tie-break.
        n = len(self.agents)
        k = round(n * self.frac_slow)
        rng = np.random.default_rng(self.cfg.seed + 29)
        order = rng.permutation(n)
        self._slow_ids = set(int(i) for i in order[:k])
        self._class_rng = rng
        for a in self.agents:
            self._assign(a)

    def _assign(self, a):
        cls = SLOW if a.aid in self._slow_ids else FAST
        a.det_class = cls
        a.death_lag = self.dl[cls]

    def _p_for(self, a) -> float:
        return self.p[getattr(a, "det_class", FAST)]

    def step(self):
        n_before = len(self.agents)
        super().step()
        # Joiners: assign a class from the same distribution. Storm scenarios
        # have no joins, so this path is unused there, but leaving it unhandled
        # is how DecoupledSim acquired the AttributeError bug this repo fixed.
        for a in self.agents[n_before:]:
            if self._class_rng.random() < self.frac_slow:
                self._slow_ids.add(a.aid)
            self._assign(a)

    # ---------------------------------------------------------------- reporting
    def class_levels(self):
        """Mean held arc level per class — the storage side of the trade, split
        by who is paying it."""
        out = {}
        for cls in (FAST, SLOW):
            lv = [a.level for a in self.agents
                  if a.alive and getattr(a, "det_class", FAST) == cls]
            out[cls] = float(np.mean(lv)) if lv else 0.0
        return out
