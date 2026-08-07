"""
detector_error_sweep — the safety/cost curve of a paranoid failure detector.

Tests the asymmetry argument stated in `detector_error_sim.py`: that a detector
should err toward *convicting the living* rather than *missing the dead*,
because the first costs storage and the second costs data.

Regime. The effect can only be measured where the race actually bites, which
§11 identifies as slow detection. A scan over storm severity x death_lag found
loss concentrated at **storm 50% with death_lag 96-192** (2-8x the gossip lag,
exactly §11's danger band); milder settings lose nothing at any p and are
uninformative either way. So this sweep runs the stress regime deliberately, and
the absolute loss rates below should NOT be read as expected operating figures.

Reported both ways, following §4.9's insistence that they can point in opposite
directions:
  * `P(any loss)` — fraction of runs losing any real data. Usually the binding
    exposure for an operator with a hard redundancy target.
  * `E[loss]`     — total held-loss sector-ticks.

Cost side: equilibrium arc level (storage) and cumulative sync (bandwidth).

Resumable; writes each cell as it completes. 4 processes by default — this is a
laptop-scale study and grabbing every core has caused a crash before.
"""

from __future__ import annotations

import argparse
import json
import os
from multiprocessing import Pool

import numpy as np

from polite_shrink import Config, make_world
from rolling_upgrade_sim import assign_initial_variants
from detector_error_sim import DetectorErrorSim

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
CELLS = os.path.join(RESULTS_DIR, "detector_error_cells.jsonl")

TICKS = 3000
STORM_FRAC = 0.50
P_VALUES = [0.0, 0.02, 0.05, 0.10, 0.20, 0.40]
DEATH_LAGS = [96, 192]
FRACTIONS = [1.0, 0.1]
SEED_BASE = 900000


def run_cell(args):
    p, dl, frac, seed = args
    cfg = Config(seed=seed)
    initial, events, joins = make_world(cfg, TICKS, storm_at=1500,
                                        storm_frac=STORM_FRAC)
    variants = assign_initial_variants(len(initial), frac, cfg.seed)
    sim = DetectorErrorSim(cfg, variants, events, initial, joins, frac,
                           death_lag=dl, false_convict_p=p)
    m = sim.run(TICKS)
    held = np.array(m.held_zero)
    decl = np.array(m.zero_sectors)
    under = np.array(m.frac_under)
    return {"p": p, "death_lag": dl, "fraction": frac, "seed": seed,
            "held_loss": int(held.sum()), "any_held_loss": bool(held.sum() > 0),
            "declared_loss": int(decl.sum()),
            "exposure": float(under.sum()),
            "eq_level": float(np.mean(m.mean_level[-300:])),
            "sync": int(m.cum_sync[-1]),
            "false_convictions": int(sim.false_convictions)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=48)
    ap.add_argument("--procs", type=int, default=4)
    args = ap.parse_args()
    seeds = [SEED_BASE + i for i in range(args.seeds)]
    work = [(p, dl, f, s) for f in FRACTIONS for dl in DEATH_LAGS
            for p in P_VALUES for s in seeds]
    os.makedirs(RESULTS_DIR, exist_ok=True)

    rows, done = [], set()
    if os.path.exists(CELLS):
        for line in open(CELLS, encoding="utf-8"):
            line = line.strip()
            if line:
                r = json.loads(line)
                k = (r["p"], r["death_lag"], r["fraction"], r["seed"])
                if k not in done:
                    done.add(k)
                    rows.append(r)
    todo = [w for w in work if w not in done]
    print(f"detector-error sweep: {len(work)} runs ({len(done)} done, "
          f"{len(todo)} to run) on {args.procs} procs", flush=True)

    with open(CELLS, "a", encoding="utf-8") as fh:
        with Pool(processes=args.procs) as pool:
            for i, row in enumerate(pool.imap_unordered(run_cell, todo), 1):
                fh.write(json.dumps(row) + "\n")
                fh.flush()
                rows.append(row)
                if i % 50 == 0 or i == len(todo):
                    print(f"  {i}/{len(todo)}", flush=True)
    summarise(rows, args.seeds)


FINDINGS = """
## Findings

**1. The asymmetry holds in the realistic range — the direction was right.**
In the strongest-signal cell (f=1.0, death_lag=192) `P(any loss)` falls from
**40% to 2%** as `p` goes 0 -> 0.10, with E[loss] falling 148,240 -> 5,693. The
f=1.0/death_lag=96 cell agrees (8% -> 0%), as does f=0.1/death_lag=96
(12% -> 0%). Convicting the living really is cheaper than missing the dead.

**2. But it is NOT monotonic, and the reason is error cancellation — not
conservatism.** Past `p` ~ 0.2 the benefit reverses: f=1.0/death_lag=192 goes
back up to **10% at p=0.40**, five times its own optimum.

`diag_detector_bias.py` measures the viewer's mean signed coverage error against
ground truth and explains the whole curve (storm 50%, death_lag=192, 8 seeds):

| p | view bias (post-storm) | held loss |
|---|---|---|
| 0.00 | **+0.50** (over-counts) | 3,996 |
| 0.02 | +0.25 | 243 |
| 0.05 | **+0.10** (~balanced) | **0** |
| 0.10 | -0.24 | 3,119 |
| 0.20 | -1.14 | 0 |
| 0.40 | **-3.67** (under-counts) | 0 |

Under slow detection a viewer **over-counts**, because dead peers are still in
its coverage. A false conviction **under-counts**. The two annul near p ~ 0.05,
and that is exactly where loss is minimised. So the mechanism is not "paranoia
makes you conservative" — it is **one error source cancelling another**. Past the
crossing the viewer is simply wrong in the other direction, and at p=0.40 it is
under-counting by nearly four copies, which is a broken view rather than a
cautious one.

The practical consequence is sharper than "tune it paranoid": **the optimum sits
where the detector's false-positive rate offsets its false-negative rate, so it
is a function of detection latency and must be tuned against it** — the same
quantity constraint 6 already identifies.

**2b. This also explains the storage anomaly, which is real.** The equilibrium
arc dips at p=0.02 (1.387 -> 1.168 at death_lag=192) and the dip survives
testing: z = +3.01 across 48 seeds (z = +2.33 at death_lag=96). Holding *less*
while losing *less* looked contradictory, and it is not. At p=0 the viewer
over-counts, so it over-shrinks, opens holes, and then has to repair-grow; that
churn settles the network at a higher and much noisier level (seed std 0.40).
Cancel the bias and the controller shrinks correctly the first time, so it needs
no repair growth — less storage and less loss together. Seed variance collapses
monotonically with `p` (std 0.43 -> 0.14 at death_lag=96), which is the same
story: a less biased view produces a more repeatable equilibrium.

**3. Calibrate what `p` means before reading the right-hand rows.** `p` here is
a false-positive rate *per look*. A real accrual detector runs orders of
magnitude below this — Akka's default threshold of phi=8 corresponds to roughly
1e-8. Even a deliberately twitchy setting is p ~ 0.1. So the operating range is
the **left end** of these tables; p=0.40 is not a detector setting, it is a
broken view, and it is included only to locate the turn-over.

**4. The cost is storage, not bandwidth — the opposite of what was assumed.**
Equilibrium arc level rises (up to +52%), but sync cost *falls* across most of
the range (20,401 -> 9,165 at f=1.0/death_lag=192). Same mechanism as
REPORT_agentinfo_encoding.md 4.3: less shrinking means less re-growing, and
re-growing is what sync cost measures. Bandwidth only turns bad at p >= 0.4,
where thrash dominates. For phone-hosted nodes this is a *better* trade than
expected.

## Caveats

- **f=0.1 / death_lag=192 is non-monotonic throughout and should not be
  read as a curve.** 7/48 -> 7/48 -> 3/48 -> 7/48 -> 6/48 -> 10/48 is consistent
  with binomial noise at these counts. It neither supports nor contradicts;
  it is underpowered.
- **The storage dip was flagged as unexplained in the first version of this
  report and is now explained** (finding 2b). It was neither an averaging
  artefact nor noise. Recorded here because the first reading was wrong.
- **Stress regime.** Storm 50% at 4-8x the gossip lag. Chosen because nothing
  loses data at milder settings, which makes them useless for discriminating.
  These are not operating rates.
- **The detector is memoryless.** Convictions are redrawn per view, so this
  measures the cost of a false positive in isolation, not any real detector's
  dynamics. Heterogeneous per-peer responsiveness and detector memory are steps
  2 and 3 of this line of work, and are what a phi accrual detector would need
  in order to be more than a fixed timeout.
- 48 seeds per cell; single-digit counts carry the usual uncertainty.
""".splitlines()


def summarise(rows, n_seeds):
    import sys
    L = ["# Should a failure detector err toward paranoia?", "",
         "Constraint 6 says the shrink wait must be sized against "
         "death-detection latency. This asks the question it leaves open: which "
         "*direction* should a detector be wrong in?", "",
         f"`p` = per-(viewer, peer) probability that a **live** peer is wrongly "
         f"convicted and dropped from the viewer's coverage. Storm "
         f"{int(STORM_FRAC*100)}%, N=200, R=5, gossip lag [8,24], "
         f"{n_seeds} seeds/cell.", "",
         "**This is a deliberate stress regime.** Loss only occurs at slow "
         "detection (§11's 2-8x band); milder settings lose nothing at any `p` "
         "and cannot discriminate. Absolute rates here are not operating "
         "figures.", "",
         f"Environment: Python {sys.version.split()[0]}, numpy {np.__version__} "
         "— numpy matches the repo pin, Python does not (3.12.1). Re-run under "
         "the pins before publishing digits.", ""]
    for frac in FRACTIONS:
        for dl in DEATH_LAGS:
            sub = [r for r in rows if r["fraction"] == frac
                   and r["death_lag"] == dl]
            if not sub:
                continue
            label = "pure V3 (f=1.0)" if frac == 1.0 else f"f={frac}"
            L += [f"## {label}, death_lag = {dl}", "",
                  "| p | P(any loss) | E[loss] (sector-ticks) | exposure | "
                  "eq. arc level | sync cost |",
                  "|---|---|---|---|---|---|"]
            base_lvl = None
            for p in P_VALUES:
                c = [r for r in sub if r["p"] == p]
                if not c:
                    continue
                n = len(c)
                nl = sum(r["any_held_loss"] for r in c)
                hl = sum(r["held_loss"] for r in c)
                ex = np.mean([r["exposure"] for r in c])
                lv = np.mean([r["eq_level"] for r in c])
                sy = np.mean([r["sync"] for r in c])
                if base_lvl is None:
                    base_lvl = lv
                dlv = "" if p == 0 else f" ({100*(lv-base_lvl)/base_lvl:+.0f}%)"
                L.append(f"| {p} | {nl}/{n} ({100*nl/n:.0f}%) | {hl:,} | "
                         f"{ex:,.0f} | {lv:.2f}{dlv} | {sy:,.0f} |")
            L.append("")
    L += FINDINGS
    out = os.path.join(RESULTS_DIR, "detector_error_summary.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("\n".join(L))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
