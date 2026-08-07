# Is the §6.1 residual really irreducible? — a Mori–Zwanzig decomposition

**Question.** [REPORT_stage3.md §11](REPORT_stage3.md) concludes that the
slow-detection residual shrink race is *"irreducible by any local rule"*, and
[constraint 6](REPORT_stage3.md#constraints-on-any-sizing-policy) turns that into
design advice for #160: size the shrink wait against **death-detection latency**,
not gossip staleness. That conclusion is stated qualitatively, on the strength of
a mechanism argument. This study tries to **falsify** it and reports a number
either way.

**Answer, in one line:** the falsification attempt fails. Detection latency
drives the failure mode up **29×** while the fraction of it recoverable from an
agent's own history does not grow at all — so §11's claim survives, and it now
has a measurement behind it rather than an argument.

**Companion study:** [`mz_attribution.py`](mz_attribution.py) asks the next
question — of the information that *is* available locally, which observables
carry it (`results/mz_attribution_summary.md`).

---

## 1. Why Mori–Zwanzig is the right frame

Mori–Zwanzig is not a model. It is the exact statement of what happens to a
dynamical system when you can only observe part of it: project out the
unresolved variables and the dynamics of the resolved ones splits into exactly
three terms — a **Markovian** term (a function of the current resolved state), a
**memory** term (a convolution over the history of the resolved state, which is
where the unresolved variables' influence re-emerges), and an **orthogonal**
term that depends on unresolved initial conditions and is irreducible.

Mapped onto the arc controller: the resolved variable is an agent's own stale
gossip view; the unresolved ones are the true global coverage and — decisively —
which peers have already died but are not yet marked unresponsive. §11's claim,
restated in this language, is that the residual lives **entirely in term 3**.

That is a testable claim, because the simulator has something the real network
does not: ground truth on both sides of the projection.

## 2. What is measured

At every execute-intent — the gate decision that matters — the agent's view
over-counts the half it is about to vacate by

    y = max over the vacate half of ( view coverage − true coverage )

`y > 0` is exactly the condition that lets the gate pass when it should not. We
then ask how much of Var(y) is explained **out-of-sample** by

| arm | features |
|---|---|
| **M** | the agent's current view only (Markovian term) |
| **M+H** | the same, plus its own history of past views (+ memory term) |

    memory gain  =  R²(M+H) − R²(M)          ← MZ term 2
    noise floor  =  1 − R²(M+H)              ← MZ term 3

swept across `death_lag`, the knob that controls how much of the truth is
unresolved. **MZ predicts the noise floor rises with detection latency while the
memory gain stays flat** — undetected deaths are orthogonal dynamics, not
history. If instead the memory gain *grows* with `death_lag`, §11 is wrong and
there is signal a better local rule could use.

Every feature is something a real node could compute from gossip it has already
received: view floor and mean (global and over the vacate half), visible-peer
count, own arc level, visible announced intenders — plus, for the memory arm,
the deltas of those at 1, 2, 4, 8 and 16 epochs back.

## 3. Three methodological guards

These matter more than the headline, because a careless version of this study
would have confirmed §11 by accident.

1. **The learner has to be strong enough for a null to mean anything.** A weak
   memory model would falsely confirm "irreducible" — the exact failure mode
   McGreivy & Hakim (*Nat. Mach. Intell.* 2024) found in 79% of ML-for-PDE
   papers claiming to beat a numerical baseline. Both arms are therefore fitted
   with ridge (quadratic feature expansion) **and** gradient-boosted trees, and
   the better out-of-sample score is taken.
2. **A positive control.** The same learner and features are asked to predict a
   quantity that genuinely *is* a function of history — the forward change in
   the vacate-half view floor over the next epoch, which current state cannot
   supply. Memory must help there for a null on `y` to be interpretable. *(A
   first draft used the next-epoch level rather than its change; the Markov arm
   already predicted that at R² = 0.99 through autocorrelation, so the control
   could not have detected a working memory term. It was replaced.)*
3. **Splits are by seed, never by row.** Rows inside one run share a world and
   are heavily correlated; a random row split leaks and inflates every R².
   Cross-validation is 3-fold, grouped by seed.

Plus the repo's standard reduction guard: the instrumented sim's metrics are
asserted **identical** to the uninstrumented `DecoupledSim` on the same seed. The
probe records; it never alters a decision or draws from an RNG stream.

### The `H = cfg.lag_max + 2` trap

The world-history ring buffer in `polite_shrink.py` holds only `lag_max + 2`
ticks and each agent reads exactly one slot (`cov_h[(t − a.lag) % H]`). Building
an agent's *memory* by indexing further back through that buffer silently wraps
and reads the future as soon as `a.lag + lookback ≥ H`. This module therefore
**never looks back through `cov_h`**. It records each agent's view into
per-agent storage at the moment the agent observes it — immune to the buffer
depth, and the more faithful model anyway: a real node remembers what it
received, not what happened to be true.

## 4. Result — pure V3 (f = 1.0), 72 seeds, ~166,000 gate decisions per cell

| death_lag | R² Markov | R² Markov+mem | **memory gain** | residual Markov | residual +mem | **unsafe gates** |
|---|---|---|---|---|---|---|
| coupled | 0.899 | 0.914 | +0.0149 | 2.19 | 2.00 | 65 |
| 4 | 0.900 | 0.915 | +0.0145 | 2.18 | 1.99 | **22** |
| 8 | 0.900 | 0.915 | +0.0150 | 2.19 | 2.00 | 45 |
| 16 | 0.899 | 0.914 | +0.0150 | 2.19 | 1.99 | 71 |
| 24 | 0.899 | 0.913 | +0.0146 | 2.19 | 2.00 | 98 |
| 48 | 0.898 | 0.913 | +0.0151 | 2.20 | 2.01 | 249 |
| 96 | 0.896 | 0.911 | **+0.0150** | 2.22 | 2.04 | **635** |

`residual` is RMSE in **copies** — the unit R is measured in, and the number that
decides whether a corrected estimate could be trusted. R² alone is hostage to how
much variance a cell happens to contain.

**The headline is the two bold columns read together.** From `death_lag` 4 to 96
the unsafe-gate count rises **29×** (22 → 635). Over the same sweep the memory
gain does not move: +0.0145 → +0.0150, a spread of 0.0006 across the whole
sweep with no trend. The failure mode scales with detection latency exactly as
§11 says; the part of it that history can recover does not respond at all.

**Positive control, same cells:**

| death_lag | R² Markov | R² Markov+mem | memory gain |
|---|---|---|---|
| 4 | 0.639 | 0.761 | **+0.1218** |
| 24 | 0.639 | 0.760 | **+0.1214** |
| 96 | 0.634 | 0.760 | **+0.1258** |

Memory gain is **~8× larger on the control than on `y`**, at every latency. The
pipeline detects memory decisively where memory exists. The null on `y` is about
the physics, not a broken estimator.

### The f = 0.1 arm (where races actually occur)

| death_lag | R² Markov | memory gain | residual +mem | unsafe gates |
|---|---|---|---|---|
| 4 | 0.337 | +0.0894 | 1.04 | 4 |
| 24 | 0.345 | +0.0847 | 1.04 | 17 |
| 96 | 0.319 | +0.0837 | 1.13 | 116 |

Same shape: unsafe gates ×29, memory gain flat and if anything declining. Memory
is a *larger share* of what is learnable here (the Markov arm only reaches
R² ≈ 0.34), and this arm is less clean — its control has little headroom and n
is 11× smaller. It corroborates rather than carries the result.

### Seed robustness

An earlier 24-seed pass gave the same shape with slightly different digits
(memory gain ≈ +0.016 rather than +0.015; unsafe-gate growth 24× rather than
29×). The conclusion is unchanged and the memory gain moved *down* with more
seeds, which strengthens rather than weakens the null. Given §4.9 of the
AgentInfo report — where a durability answer flipped between 4 seeds and 100 —
the 72-seed figures are the ones to quote, and single-digit-seed variants of
this study should not be.

## 5. What "unsafe gate" is, and is not

An unsafe gate is a decision where the agent's view passed the R check but
perfect current information would not have. **It is a precursor, not a loss.**
Actual declared loss (`zero_sector_ticks`) was **0 at every latency**, including
the 96-tick cells with 217 precursors — consistent with §11's published f = 1.0
race counts, which are 0 almost everywhere.

That gap is the point of using it. The published race study had 0–2 events per
312 runs to reason from; this metric yields hundreds, which is what makes the
sweep well-powered. It should never be quoted as a data-loss figure.

## 6. The secondary finding, which cuts the other way

There is a **large Markov term**: R² ≈ 0.90. An agent can estimate its own
over-count well from what it currently sees, and the gate does not use this.

That is not a licence to build a bias correction, for a reason the repo already
proved. The residual after the best available predictor is **≈ 2.0 copies against
R = 5** — 40% of the redundancy target. And [`spec/AgentInfoAgeGated.tla`](spec/)
settles what happens next: recovering a missing bit by inference verifies at
`Budget = 0` (perfect classification) and is **violated at `Budget = 1`** — one
misclassification loses a copy. A predictor with ±2 copies of residual error is
not a candidate for the gate.

Where it *could* legitimately go is the policy layer: the announce trigger and
the wait, where being wrong costs bandwidth rather than data. Note also that
memory buys only **0.19 copies** of accuracy (2.19 → 2.00), which is small
against the effort of carrying history.

## 7. Limitations

- **The finding is about these features, and that is the binding limitation —
  more binding than "seven features" makes it sound.** The companion attribution
  study ([`mz_attribution.py`](mz_attribution.py)) measured how far each
  observable gets on its own, and the answer is: almost all the way. *Any one*
  of six observables scores R² ≈ 0.87–0.89 against 0.92 for all seven together.

  They are near-perfect **substitutes**, not seven independent probes. So this
  study did not test seven dimensions of observable space; it tested roughly
  one, sampled seven ways. The null is correspondingly weaker than the feature
  count suggests, and this should be read as a limitation the follow-up
  discovered rather than one it resolved.

  The positive control still holds — the pipeline detects memory where memory
  exists — so the result stands as *"no memory signal in this dimension of
  observable space."* It is a bound, and a narrower one than first stated.

  The MZ literature says exactly where to push. Tian, Lin, Anghel & Livescu
  (*Phys. Fluids* 33, 125118, 2021), extracting MZ operators from isotropic
  turbulence, report that *"prediction errors are strongly affected by the choice
  of observables and can be further reduced by including the past history of the
  observables."* Observable choice dominates memory depth. So the principled way
  to harden this null is **a systematic search over observables**, not more seeds
  and not longer lookbacks. `mz_attribution.py` is the first step: it ranks the
  seven current observables by exact Shapley value, which is what any wider
  search would have to beat.
- **The precise claim is narrower than "irreducible".** What is measured is that
  the recoverable-from-history fraction **does not grow with the mechanism that
  drives the race**. That is strong evidence for orthogonality; it is not a
  theorem.
- **Idealised model.** Full peer visibility, one lag per viewer, honest agents —
  the Stage-1 idealisations, which Stage 2 showed can hide real constraints.
- **72 seeds per cell**, with a 24-seed pass agreeing on the shape (§4).
- **Environment is partially off-pin.** Produced on **numpy 2.5.1 — the pinned
  version** — but Python 3.14.6 against a pin of 3.12.1, because 3.12.1 is not
  available on the machine used. Simulation output was checked to be
  **byte-identical** between numpy 2.3.5 and 2.5.1 (`chk_repro.py`: identical
  record counts and md5 of the target and feature arrays at
  `death_lag ∈ {coupled, 96}`), so the sim is not sensitive across that range.
  The Python-version leg is unverified; re-run under 3.12.1 before publishing.

## 8. What would change the conclusion

A memory gain that **rises with `death_lag`** in any feature set — that would
mean deaths leave a fingerprint in the view's history before detection, and a
better local rule exists. Nothing in seven scalars across five lookbacks does.

**Where to look, specifically.** The attribution result says the seven
observables collapse to roughly one dimension, so adding more summaries of the
coverage array will not help — they will be substitutes too. A real test needs
observables that are *structurally* different from "a statistic of the current
coverage vector". Candidates, in rough order of promise:

1. **Per-sector age** — time since each sector's coverage last changed. A peer
   that has died stops refreshing; the *absence* of change is a signal no
   snapshot statistic carries.
2. **Per-peer identity and staleness** — which specific declarations are going
   stale, rather than how many peers are visible. (See the caveat below on the
   peer count, which this model cannot currently answer.)
3. **Variance across sectors within the vacate half**, rather than its floor and
   mean, which are already shown to be substitutes.

Note that (1) is exactly the signal `spec/AgentInfoAgeGated.tla` model-checks —
and finds unsafe at `Budget = 1`. So even if it carried information, the proof
already bounds what could be done with it. That is the pattern this whole line
of work keeps returning to: information and safety are different questions.

## Reproduce

```bash
python3 mz_probe.py --seeds 72        # -> results/mz_summary.md, results/mz_cells.jsonl
python3 mz_attribution.py --seeds 24  # -> results/mz_attribution_summary.md
```

*Research directed by Ceri John; design, implementation, and analysis with AI
assistance (Claude, Anthropic); all results human-reviewed.*
