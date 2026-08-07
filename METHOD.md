# How this research is conducted, and how to check it

This repository is AI-assisted. That is stated in every report footer, and it is
worth being precise about what it means, because "AI-assisted" currently covers
everything from a machine-checked proof to an unreviewed pull request.

Three commitments, each of which a reader can verify without trusting anyone.

---

## 1. The proposal may come from anywhere. The proof does not.

The load-bearing claim in this repository — that a node obeying the gate cannot
take a sector below R — is **model-checked by TLC over every reachable state**
for N ≤ 8 and R = 1–7 ([`spec/`](spec/)). The naive rule fails the same check
with a counterexample. So does the plausible-looking middle option of inferring
which un-declared peers have really left ([`spec/AgentInfoAgeGated.tla`](spec/):
verifies at `Budget = 0`, violated at `Budget = 1`).

Once a rule is machine-checked, the provenance of the *proposal* stops mattering.
A conjecture is not evidence regardless of who or what produced it; a TLC run is
evidence regardless of who or what ran it. Anyone can re-run these specs and get
the same verdict:

```bash
java -cp tla2tools.jar tlc2.TLC spec/PoliteShrink.tla        # -> No error
java -cp tla2tools.jar tlc2.TLC spec/NaiveShrink.tla         # -> violated
java -cp tla2tools.jar tlc2.TLC spec/AgentInfoOptimistic.tla # -> violated
```

**This is a recognised research method, not a workaround.** Jakhar et al.
(*Phys. Rev. Lett.*, Feb 2026) used AI equation discovery to find a subgrid
closure for geophysical turbulence and then **verified it by formal derivation**
— it turned out to be a 4th-order Taylor expansion, where earlier analytical and
AI work had reached only 2nd order and produced unstable simulations. Google
DeepMind and collaborators (2025) used physics-informed neural networks to
discover new families of unstable singularities in the Boussinesq and
Incompressible Porous Media equations, **to a precision suitable for
computer-assisted proof**. In both cases the machine searched and a rigorous
method certified. That is the shape used here.

What this does **not** claim: that AI involvement makes anything more likely to
be correct, or that the Navier–Stokes Millennium Problem has been touched (it has
not — no new singularity was found in Navier–Stokes itself).

## 2. Claims are graded, and the grades are kept separate

Every report separates three things, and the distinction is load-bearing:

| grade | meaning | example |
|---|---|---|
| **Proven** | machine-checked, exhaustive over the modelled state space | the gate cannot take a sector below R |
| **Evidenced by simulation** | measured, with seed counts stated per table | equilibrium arc, cancel rates, the §6.1 race quantification |
| **Known gap** | named, unfixed | liars past K = R are a sensor problem no controller can out-think |

Simulation results are **not** promoted to proofs by repetition, and the
idealisations are listed in each report's Limitations rather than in a footnote.
Stage 2 exists specifically because Stage 1's idealisations were suspected of
hiding real constraints — and it found some.

## 3. Baselines are strong on purpose, and negative results are published

McGreivy & Hakim (*Nature Machine Intelligence*, 2024) reviewed papers claiming
that machine learning beat a standard numerical method on a fluid-related PDE.
**79% (60 of 76) compared against a weak baseline**, and they found widespread
outcome-reporting and publication bias. Their diagnosis — researcher degrees of
freedom plus a bias toward positive results — applies to any simulation study,
including this one.

Two deliberate defences:

**The ablation ladder.** The headline result is not "polite shrink loses no
data." It is the ladder, which shows what each ingredient is actually worth:

| variant | runs with data loss |
|---|---|
| V0 naive | 95.9% |
| V1 damped (hysteresis) | 24.0% |
| V2 damped + jitter | 24.3% |
| V3 polite (the gate) | **0.0%** |

Reporting V3 against V0 alone would have supported a "96% improvement" headline.
The ladder instead shows that hysteresis does most of the work, that **jitter —
the textbook first remedy — buys nothing**, and that the gate closes a distinct
residual. That is a weaker-sounding claim and a truer one.

**Corrections are published in place, not quietly dropped.** Worked examples in
this repository:

- [`REPORT_agentinfo_encoding.md`](REPORT_agentinfo_encoding.md) §4.9 retracts
  its own §4.1: *"durability untouched" was an artefact of testing four seeds*.
  Going from 4 seeds to 100 changed the answer, and the section says so.
- §4.8 of the same report opens *"a hypothesis of mine that was wrong"* — the
  predicted effect went in the opposite direction.
- [`REPORT_mz_decomposition.md`](REPORT_mz_decomposition.md) §3 records that its
  first positive control was too weak to detect the effect it existed to detect,
  and was replaced before the result was taken.
- [`REPORT_stage3.md`](REPORT_stage3.md) constraint 7 reports that the intuitive
  culprit for storage skew was wrong and the fix built for it did not work.

A repository where nothing was ever wrong would be the less trustworthy one.

---

## What would falsify the central claim

Stated plainly so it can be aimed at:

- A TLC counterexample to [`spec/PoliteShrink.tla`](spec/) at any N ≤ 8, R ≤ 7.
- A run in which an agent obeying the gate drives a sector below R with all
  peers honest.
- A demonstration that the gate's precondition — that the wait outlasts the
  staleness — cannot be met on a real transport, which would move the result
  from "safe" to "unimplementable" without touching the proof.

The third is the live one, and it is why
[constraint 6](REPORT_stage3.md#constraints-on-any-sizing-policy) is stated in
terms of death-detection latency rather than gossip timing.

---

## References

- Karan Jakhar, Yifei Guan, Pedram Hassanzadeh, *An Analytical and AI-discovered
  Stable, Accurate, and Generalizable Subgrid-scale Closure for Geophysical
  Turbulence*, Phys. Rev. Lett. (published 10 Feb 2026). arXiv:2509.20365
- Google DeepMind et al., *Discovering new solutions to century-old problems in
  fluid dynamics* (2025) — unstable singularities in the Boussinesq and IPM
  equations via PINNs, at computer-assisted-proof precision.
- Nick McGreivy & Ammar Hakim, *Weak baselines and reporting biases lead to
  overoptimism in machine learning for fluid-related partial differential
  equations*, Nature Machine Intelligence (2024). arXiv:2407.07218
- Tian, Lin, Anghel & Livescu, *Data-driven learning of Mori–Zwanzig operators
  for isotropic turbulence*, Phys. Fluids 33, 125118 (2021). arXiv:2108.13288

*Research directed by Ceri John; design, implementation, and analysis with AI
assistance (Claude, Anthropic); all results human-reviewed.*
