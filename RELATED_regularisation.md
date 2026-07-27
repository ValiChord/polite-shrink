# The shrink race, read as an L1 problem

*A reading aid, not a result. Nothing in this repo depends on it.*

For readers who work in statistics or machine learning, the failure this study is about has a
close structural analogue in **L1-regularised regression**. The analogy is worth stating because
it makes the problem legible in about thirty seconds to an audience that already has strong
intuitions for it — and because the two disciplines have arrived at the same corrective by
different routes, which is mild independent evidence that the corrective is the right one.

It is stated here in the same spirit as the wireless-sensor coverage-scheduling precedent noted
in the README (Tian & Georganas, 2002): **as convergence, not as prior art reinvented, and not as
a claim of contribution to statistics.** The safety property is established by the TLA+ model
check in [`spec/`](spec/), independently and completely. Delete this file and nothing is weakened.

---

## 1. The cost structure is L1-shaped

Minimum storage subject to *every sector holding at least R copies* is a **linear** cost in
sectors held. Linear cost plus a coverage floor is the same shape as a lasso objective: a fit
term, and a penalty that charges per unit of activity rather than per unit squared.

What makes the analogy sharp is not that costs are linear — it is **what the units are.** Two
nodes covering the same sector are not merely correlated. For the purposes of the coverage
constraint they are *exactly interchangeable*: a copy is a copy. In regression terms, the design
matrix has **identical columns**, not just collinear ones.

## 2. That puts the problem in lasso's provably degenerate regime

The lasso solution is unique when the columns are in general position — which holds with
probability one for predictors drawn from a continuous distribution. Identical columns violate
that condition exactly. And the classical result gives the consequence precisely:

> **The lasso *fit* is always unique, even when the coefficient vector is not.**
> (R. J. Tibshirani, *The Lasso Problem and Uniqueness*, EJS 7, 2013.)

Translated into this repo's terms:

| Regression | DHT |
|---|---|
| the fit `Xβ̂` — unique | **coverage** — determined |
| the coefficients `β̂` — not unique | **which nodes hold it** — undetermined |

This is the useful part, and it is not a metaphor. **The objective function cannot decide who
should drop.** Not because the optimiser is weak, or the policy insufficiently clever, but
because the answer is underdetermined by the cost. Any R of the K holders is optimal, at
identical cost.

It is the same conclusion [CORE_IDEA.md](CORE_IDEA.md) reaches from the other direction — that
the cost-optimal target `R/N` is nearly trivial and every hard part is elsewhere. The regression
framing explains *why* that has to be true, rather than merely observing it.

## 3. The algorithmic correspondence is the closest one

Lasso is solved in practice by **coordinate descent**: update one coefficient at a time against
the *partial residual*, so each coordinate sees the moves already made by the others
(Gauss–Seidel ordering). Update every coordinate simultaneously against the *same* residual
(Jacobi), and correlated coefficients each over-correct for a discrepancy the others are
correcting at the same instant.

That is the shrink race, exactly:

- **V0/V1/V2 (naive, damped, jittered)** — every node reads the same stale coverage snapshot and
  moves at once. Each node's arithmetic is correct *given the others hold still*
  (`polite_shrink.py`, `_decide`: `seg.min() >= R + 1`, discounting only itself), and wrong
  because they didn't.
- **V3 (polite)** — `_execute_intent` discounts every *lower-id* announced intender before
  computing its own move. That is a **Gauss–Seidel sweep order manufactured without a
  coordinator**: apply the updates of the coordinates ahead of you, then compute yours.
- **V5 (AgentInfo-only)** — the other classical trick. Make the announcement *be* the state
  change, so every reader's residual is already current and no ordering is required.

Hysteresis and jitter, in this light, are attempts to fix a Jacobi-ordering problem by adjusting
step size and timing. The ablation's central finding — that they take loss from 95.9% of runs to
24% and no further — is what one would expect of exactly that mistake.

## 4. Two further echoes, weaker but real

**Bounded parallelism.** Bradley, Kyrola, Bickson & Guestrin (*Shotgun: Parallel Coordinate
Descent for L1-Regularized Loss Minimization*, ICML 2011) show parallel coordinate descent
converges with near-linear speedup only up to a problem-dependent limit set by the correlation
structure of the design matrix — beyond it, the method can diverge. The silhouette matches the
gate: *bound the number of correlated units permitted to move at once.*

**The status is not the same, and the difference matters.** Theirs is a convergence bound on an
optimisation procedure; the R-invariant here is a hard safety property, enforced exactly and
locally rather than statistically. Similar shape, different kind of claim. It is cited as a
family resemblance, not as a theorem this work inherits.

**Stability under resampling.** The accepted statistical remedy for lasso's support flipping
between samples is *stability selection* (Meinshausen & Bühlmann, JRSS-B, 2010): resample
repeatedly and keep only variables selected above a threshold frequency. That is a redundancy
requirement across views. The 2021 "hallway dance" is recognisably support instability, with
temporal gossip staleness in the role of the resample.

## 5. Where the analogy breaks

Three ways, and each is load-bearing:

1. **There is no coordinator.** Coordinate descent presumes something sweeping the coordinates in
   order. This problem has nobody to do that, and manufacturing the order under stale, partial,
   adversarially-tinged views *is* the contribution. Lasso never has to ask the question.
2. **Failure here is irreversible.** A wrong zero is undone on the next iteration; a sector
   vacated to zero copies is gone, with no gradient back. Hence a safety invariant proven by
   model checking, rather than a convergence rate.
3. **The article's actual subject — the L1 corner versus the L2 curve — does not transfer.** Arcs
   are quantised into aligned power-of-two blocks (`block()`, level L = 2^L sectors), so the
   decision is already discrete and there is no smooth penalty to choose. Current Holochain
   practice (arcs clamped to full) corresponds to no penalty at all rather than to ridge; a
   hypothetical uniform partial-arc design would be the loosely ridge-like option, and
   quantisation puts it out of reach regardless. **The sparse regime is the only one on offer,
   which is precisely why its pathology has to be closed rather than avoided.**

## 6. What this is worth, stated plainly

**Nothing technically.** No result depends on it, no code follows from it, and the TLA+ proof
stands without it.

**Something rhetorically,** to one audience: readers who already reason fluently about correlated
predictors and unstable support, and for whom "the objective determines coverage but cannot
determine the holder set" lands immediately.

Guardrails, since the temptation runs one way:

- ✅ *"The failure mode has a well-studied analogue in L1 regularisation."*
- ✅ *"The DHT sits in the regime where the lasso solution is provably non-unique — the fit is
  determined, the coefficients are not."*
- ❌ *"Polite-shrink solves a known problem in statistics."* It does not, and claiming so in front
  of anyone who knows the field would be both false and embarrassing.
- ❌ Citing Shotgun as a proof of the gate. Different kind of claim; see §4.

---

## References

- Hoerl, A. E., & Kennard, R. W. (1970). Ridge Regression: Biased Estimation for Nonorthogonal
  Problems. *Technometrics*, 12(1), 55–67.
- Tibshirani, R. (1996). Regression Shrinkage and Selection via the Lasso. *JRSS-B*, 58(1),
  267–288.
- Tibshirani, R. J. (2013). The Lasso Problem and Uniqueness. *Electronic Journal of Statistics*,
  7. [arXiv:1206.0313](https://arxiv.org/abs/1206.0313)
- Bradley, J. K., Kyrola, A., Bickson, D., & Guestrin, C. (2011). Parallel Coordinate Descent for
  L1-Regularized Loss Minimization. *ICML*. [arXiv:1105.5379](https://arxiv.org/abs/1105.5379)
- Meinshausen, N., & Bühlmann, P. (2010). Stability Selection. *JRSS-B*.
  [arXiv:0809.2932](https://arxiv.org/abs/0809.2932)
- Tian, D., & Georganas, N. D. (2002). A coverage-preserving node scheduling scheme for large
  wireless sensor networks. *ACM WSNA*. (The precedent noted in the README; the same
  announce-then-defer structure, reached independently.)

*Research directed by Ceri John; design, implementation, and analysis with AI assistance (Claude,
Anthropic); all results human-reviewed.*
