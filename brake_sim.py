"""Storm brake for the mixed-controller sim — the sim-side counterpart of the
kitsune2 port's brake (REPORT_stage1.md §6.1): *whenever a peer death is
detected, cancel all pending shrink intents and reset their dwell counters.*

Why a new parameter. In the single-clock Stage-1 model, a death only becomes
visible through the same stale view that drives shrink decisions (one `lag`
governs both). The port's brake works because death detection (unresponsive
marking) runs on a **separate, faster clock** than gossip staleness — the whole
§6.1 point. So the brake here takes a `detect_latency`: a death at tick D is
detected by every node at D + detect_latency, independent of gossip lag. The
brake fires once, at that tick, cancelling every pending intent.

This lets us answer "does the brake close the two §6.1-race storm losses?" and,
by sweeping detect_latency, show the residual the report says no local rule can
fully close: a death landing within detect_latency of an intent's execute still
slips through.
"""

from __future__ import annotations

from rolling_upgrade_sim import MixedSim


class BrakeMixedSim(MixedSim):
    def __init__(self, *args, detect_latency: int = 4, **kw):
        super().__init__(*args, **kw)
        self.detect_latency = detect_latency
        # ticks at which a death becomes detectable -> whether already braked
        self._brake_ticks = {d + detect_latency for d in self.events
                             if self.events[d]}
        self.brake_fires = 0

    def step(self):
        # Storm brake: on the tick a death becomes detectable, cancel every
        # pending shrink intent BEFORE this tick's intent-execute phase.
        if self.t in self._brake_ticks:
            for a in self.agents:
                if a.alive and a.intent_at >= 0:
                    a.intent_at = -1
                    a.shrink_acc = 0
                    self.brake_fires += 1
        super().step()
