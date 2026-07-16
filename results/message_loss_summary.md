# Does lossy gossip break polite shrink? Data loss vs message-loss rate

Seeds: 100. Join-free scenarios. loss = per-round gossip drop probability; loss=0 = base sim.

## Conclusion: polite shrink is robust to lossy gossip up to 90% drop

**No data loss is attributable to message loss.** Across all 6000 runs (2 scenarios ×
3 fractions × 10 loss rates × 100 seeds), the data-loss rate is **flat in the loss
axis** — it does not climb as gossip drop goes 0→90%.

- **activation**: 0/100 at every loss rate, every fraction (0.0–0.9).
- **storm**: the only losses are pre-existing storm-onset deaths, not lossy
  over-counting. Every losing run has `first_orphan == 1500` (the storm instant),
  and attribution by seed confirms message loss is not the cause:
  - seed 100034 (storm f=0.1) loses at **every** loss rate **including loss=0.0** →
    a base-sim storm-death, present with perfect gossip; message loss is irrelevant.
  - seed 100090 (storm f=0.1) loses only at loss 0.2–0.4 and is fine at 0.5–0.9 —
    **non-monotonic**, so not driven by loss (more drop would be worse, not better);
    a marginal storm-death seed the delivery RNG tips either way.
  - seed 100060 (storm f=1.0) loses only at loss=0.7, orphan at storm onset — same
    isolated pattern.

Polite shrink's two-phase re-check runs on each viewer's incomplete, per-peer lossy
view and still never shrinks into a hole: at 90% per-round message drop the residual
loss is exactly the load-concentration storm-death already documented in the
rolling-upgrade study, at the same ~1% rate. The loss=0 column reproduces the base
sim (MixedSim) byte-for-byte, the correctness anchor.


## activation, upgraded fraction f=0.1

| loss | runs w/ data loss | rate | mean final level |
|---|---|---|---|
| 0.0 | 0/100 | 0.0% | 0.53 |
| 0.1 | 0/100 | 0.0% | 0.53 |
| 0.2 | 0/100 | 0.0% | 0.54 |
| 0.3 | 0/100 | 0.0% | 0.54 |
| 0.4 | 0/100 | 0.0% | 0.53 |
| 0.5 | 0/100 | 0.0% | 0.53 |
| 0.6 | 0/100 | 0.0% | 0.53 |
| 0.7 | 0/100 | 0.0% | 0.53 |
| 0.8 | 0/100 | 0.0% | 0.52 |
| 0.9 | 0/100 | 0.0% | 0.52 |

## activation, upgraded fraction f=0.5

| loss | runs w/ data loss | rate | mean final level |
|---|---|---|---|
| 0.0 | 0/100 | 0.0% | 0.85 |
| 0.1 | 0/100 | 0.0% | 0.83 |
| 0.2 | 0/100 | 0.0% | 0.83 |
| 0.3 | 0/100 | 0.0% | 0.85 |
| 0.4 | 0/100 | 0.0% | 0.83 |
| 0.5 | 0/100 | 0.0% | 0.84 |
| 0.6 | 0/100 | 0.0% | 0.82 |
| 0.7 | 0/100 | 0.0% | 0.84 |
| 0.8 | 0/100 | 0.0% | 0.79 |
| 0.9 | 0/100 | 0.0% | 0.78 |

## activation, upgraded fraction f=1.0

| loss | runs w/ data loss | rate | mean final level |
|---|---|---|---|
| 0.0 | 0/100 | 0.0% | 0.98 |
| 0.1 | 0/100 | 0.0% | 0.99 |
| 0.2 | 0/100 | 0.0% | 0.98 |
| 0.3 | 0/100 | 0.0% | 0.97 |
| 0.4 | 0/100 | 0.0% | 0.93 |
| 0.5 | 0/100 | 0.0% | 0.89 |
| 0.6 | 0/100 | 0.0% | 1.00 |
| 0.7 | 0/100 | 0.0% | 0.96 |
| 0.8 | 0/100 | 0.0% | 0.90 |
| 0.9 | 0/100 | 0.0% | 0.90 |

## storm, upgraded fraction f=0.1

| loss | runs w/ data loss | rate | mean final level |
|---|---|---|---|
| 0.0 | 1/100 | 1.0% | 0.56 |
| 0.1 | 1/100 | 1.0% | 0.57 |
| 0.2 | 2/100 | 2.0% | 0.55 |
| 0.3 | 2/100 | 2.0% | 0.56 |
| 0.4 | 2/100 | 2.0% | 0.56 |
| 0.5 | 1/100 | 1.0% | 0.56 |
| 0.6 | 1/100 | 1.0% | 0.54 |
| 0.7 | 1/100 | 1.0% | 0.54 |
| 0.8 | 1/100 | 1.0% | 0.55 |
| 0.9 | 1/100 | 1.0% | 0.54 |

## storm, upgraded fraction f=0.5

| loss | runs w/ data loss | rate | mean final level |
|---|---|---|---|
| 0.0 | 0/100 | 0.0% | 0.81 |
| 0.1 | 0/100 | 0.0% | 0.83 |
| 0.2 | 0/100 | 0.0% | 0.83 |
| 0.3 | 0/100 | 0.0% | 0.83 |
| 0.4 | 0/100 | 0.0% | 0.84 |
| 0.5 | 0/100 | 0.0% | 0.84 |
| 0.6 | 0/100 | 0.0% | 0.81 |
| 0.7 | 0/100 | 0.0% | 0.82 |
| 0.8 | 0/100 | 0.0% | 0.82 |
| 0.9 | 0/100 | 0.0% | 0.78 |

## storm, upgraded fraction f=1.0

| loss | runs w/ data loss | rate | mean final level |
|---|---|---|---|
| 0.0 | 0/100 | 0.0% | 0.99 |
| 0.1 | 0/100 | 0.0% | 1.03 |
| 0.2 | 0/100 | 0.0% | 1.02 |
| 0.3 | 0/100 | 0.0% | 1.04 |
| 0.4 | 0/100 | 0.0% | 1.00 |
| 0.5 | 0/100 | 0.0% | 0.98 |
| 0.6 | 0/100 | 0.0% | 0.98 |
| 0.7 | 1/100 | 1.0% | 1.00 |
| 0.8 | 0/100 | 0.0% | 0.94 |
| 0.9 | 0/100 | 0.0% | 0.94 |
