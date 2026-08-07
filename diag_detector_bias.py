"""
diag_detector_bias — why does a *little* false conviction reduce storage AND loss?

`results/detector_error_summary.md` reports an anomaly it declines to explain:
at p = 0.02-0.05 the equilibrium arc level *falls* (-14%, -16%) while data loss
also falls. Holding less and losing less at the same time is not what the
"paranoia makes you conservative" mechanism predicts, and the summary says so.

Hypothesis under test: **the two errors cancel.** Under slow detection a viewer
*over*-counts, because peers that have died are still in its coverage. A false
conviction *under*-counts. At some small p the two roughly annul and the viewer's
picture is simply more accurate — so the controller behaves as designed, which
means a tighter equilibrium (less storage) and fewer bad shrinks (less loss) at
the same time. Above that p, over-correction takes over and the arc grows again.

If true, mean view bias should cross zero near p = 0.02-0.05 and the arc-level
minimum should sit at the same place. If the bias is monotone and never crosses
zero, the hypothesis is wrong and the anomaly stays unexplained.

Measures, per decision epoch, the mean signed error of the viewer's coverage
against ground truth:

    bias = mean over sectors of ( view coverage - true coverage )

Instrumentation only; no decision is altered and no RNG stream is perturbed
beyond the sim's own conviction draws.

Usage:  python3 diag_detector_bias.py
"""

from __future__ import annotations

import numpy as np

from polite_shrink import Config, make_world
from rolling_upgrade_sim import assign_initial_variants
from detector_error_sim import DetectorErrorSim

TICKS = 3000
STORM_FRAC = 0.50
DEATH_LAG = 192
P_VALUES = [0.0, 0.01, 0.02, 0.05, 0.10, 0.20, 0.40]
SEEDS = 8


class BiasProbe(DetectorErrorSim):
    """Records the signed view error at each agent's decision epoch."""

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.bias_sum = 0.0
        self.bias_n = 0
        self.bias_post = 0.0        # post-storm only
        self.bias_post_n = 0

    def step(self):
        cfg, t = self.cfg, self.t
        due = [a for a in self.agents
               if a.alive and t % cfg.eval_every == a.phase]
        if due:
            true_cov, _ = self._build_declared()
            tc = true_cov.astype(np.int64)
            for a in due:
                cov, _lvl, _icov, _il = self._view(a)
                b = float((cov.astype(np.int64) - tc).mean())
                self.bias_sum += b
                self.bias_n += 1
                if t > 1500:
                    self.bias_post += b
                    self.bias_post_n += 1
        super().step()


def run(p, seed):
    cfg = Config(seed=seed)
    initial, events, joins = make_world(cfg, TICKS, storm_at=1500,
                                        storm_frac=STORM_FRAC)
    variants = assign_initial_variants(len(initial), 1.0, cfg.seed)
    sim = BiasProbe(cfg, variants, events, initial, joins, 1.0,
                    death_lag=DEATH_LAG, false_convict_p=p)
    m = sim.run(TICKS)
    lv = np.array(m.mean_level)
    return {
        "bias": sim.bias_sum / max(sim.bias_n, 1),
        "bias_post": sim.bias_post / max(sim.bias_post_n, 1),
        "lvl_last300": float(lv[-300:].mean()),
        "lvl_last1000": float(lv[-1000:].mean()),
        "lvl_prestorm": float(lv[1200:1500].mean()),
        "held": int(np.array(m.held_zero).sum()),
    }


def main():
    print(f"storm {int(STORM_FRAC*100)}%, death_lag={DEATH_LAG}, f=1.0, "
          f"{SEEDS} seeds\n")
    print(f"{'p':>5} {'view bias':>10} {'bias post':>10} {'lvl(-300)':>10} "
          f"{'lvl(-1000)':>11} {'lvl pre':>8} {'held loss':>10}")
    rows = []
    for p in P_VALUES:
        r = [run(p, 900000 + k) for k in range(SEEDS)]
        agg = {k: float(np.mean([x[k] for x in r])) for k in r[0]}
        rows.append((p, agg))
        print(f"{p:5} {agg['bias']:+10.4f} {agg['bias_post']:+10.4f} "
              f"{agg['lvl_last300']:10.3f} {agg['lvl_last1000']:11.3f} "
              f"{agg['lvl_prestorm']:8.3f} {agg['held']:10.0f}")

    b = [r[1]["bias_post"] for r in rows]
    cross = next((P_VALUES[i] for i in range(1, len(b))
                  if b[i - 1] > 0 >= b[i]), None)
    lvl_min = min(rows, key=lambda r: r[1]["lvl_last300"])[0]
    print()
    if cross is None:
        print("Post-storm bias never crosses zero -> cancellation hypothesis "
              "NOT supported; anomaly stays unexplained.")
    else:
        print(f"Post-storm view bias crosses zero between p={cross} and the "
              f"previous step; arc-level minimum at p={lvl_min}.")
        print("Cancellation hypothesis SUPPORTED."
              if abs(P_VALUES.index(cross) - P_VALUES.index(lvl_min)) <= 1
              else "Zero-crossing and level minimum do not coincide — partial "
                   "support only.")


if __name__ == "__main__":
    main()
