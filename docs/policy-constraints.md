# What any sizing policy must respect

> From the [history page](history.md); written for kitsune2 maintainers.


Issue #160 asks for a **policy** — *"recommend an appropriate target arc based on the
desired redundancy level."* The cost-optimal answer is nearly trivial: minimum storage
subject to *every sector ≥ R* is `R × ring`, so the ideal arc is `R/N` of it. Every
difficulty is elsewhere — measuring `N` under stale or dishonest views, reaching the
target without a race, not oscillating on the way, and arcs being quantised into
power-of-two halves.

**We deliberately don't propose the policy.** That needs facts this study doesn't have:
what Holochain apps store and how they read it, whether a node is a phone or a server,
what durability is worth against what bandwidth, and what validation requires a node to
hold. What the runs *do* establish is the weaker, defensible thing — the constraints any
policy has to respect, whoever writes it. (This is the *policy* half. The *gate* — the
~15 lines the model checks cover — is [REPORT_stage1.md §2.2](../reports/REPORT_stage1.md); the
recommended form of it is V6, see [REPORT_stale_views.md](../reports/REPORT_stale_views.md).)

| Constraint | Because |
|---|---|
| **Hysteresis, scaled to each agent's *own measured* lag** — grow readily, shrink reluctantly | takes data loss from **95.9% of runs to 24.0%**. Necessary, and *not* sufficient — the rest is the race, which only the gate closes |
| **Jitter buys nothing — don't reach for it first** | **24.3% vs 24.0%.** Desynchronising decision epochs is the textbook first response to control-loop oscillation, and it does not touch this failure mode |
| **The small-network clamp is a safety parameter, not a tuning knob** | below the visible-peer threshold, hold or grow to full arc. Tuning it as a performance dial removes a floor |
| **Ring granularity must scale with N** | a fixed 512-sector ring drives the coverage floor to **1 at N = 5,000** under storm — resolution is lost exactly when it matters |
| **Provision R explicitly** | V3's ~2R equilibrium was *accidental* — a by-product of the shrink cascade stalling. V4 removes it; **V4 at R+1** buys the headroom back deliberately, at comparable cost |
| **Size the shrink wait against death-detection latency, not gossip staleness** | they are independent clocks on a real transport. Detection *faster* than gossip drives the residual race to **zero**; the storm brake shares the detection clock, so it bounds but cannot close it |
| **Decide which way the failure detector should be *wrong*, and give it a ceiling** | convicting a live peer makes a node hold more (costs storage); missing a dead one makes it shrink wrongly (costs data). Erring toward conviction takes `P(any loss)` **40% → 2%** — but past the optimum it worsens again, because the mechanism is one error cancelling another, not caution. The optimum therefore moves with detection latency (constraint 6b) |
| **Don't spend effort on per-peer calibration before the global threshold is right** | one well-chosen global threshold is a **38 pp** effect; tuning per latency class adds ≤4 pp and is not distinguishable from selection noise. Self-calibrating detectors buy little until the first-order effect is already captured |
| **Don't treat a spread of detection speeds as a hazard** | it helps. Replicated on fresh seeds: uniformly slow detection loses data in **35%** of runs, a 50/50 mix with twice-as-fast nodes in **18%** — about what an all-fast network loses (15%). A mixed network tracks its *faster* half — so a policy that homogenises node behaviour may remove a margin it never knew it had (cf. the arc-distribution constraint below) |
| **Don't flatten the arc distribution** | the top decile holds **~91%** of stored sectors — and the skew is hysteresis path-dependence, not the tie-break (corr ≈ +0.08). Those big arcs are the emergent insurance behind sparse recovery's global reach, so **the textbook uniform `R/N` is probably the wrong policy** |

Each constraint traces to a run; sources and full detail in
[REPORT_stage3.md → *Constraints on any sizing policy*](../reports/REPORT_stage3.md).

**And what adopting the gate would actually cost.** Not a new wire message —
the announcement can ride on the `AgentInfo` arc claim kitsune2 already gossips
and signs. It does need **one bit** that claim cannot carry: whether a narrowed
arc means *intending to leave* or *already gone*. That is either one field on
an existing struct, or the ID tie-break on a dedicated signal; it cannot be
inferred from the claim's age (a single misclassification loses a copy —
model-checked). Mechanically, `update_storage_arcs` already moves the stored
arc toward a target hint; what is missing is the rule that sets the hint, and
the shrink direction `storage_arc.rs` explicitly leaves to "the host
implementation or some sharding logic". Full comparison of both encodings, and
the axes where the message-free one is *worse*, in
[REPORT_agentinfo_encoding.md](../reports/REPORT_agentinfo_encoding.md).

**And the question this study cannot answer: what should R be?** Every result above is
parameterised by it, and none of them decides it — that is a durability-versus-cost
judgement belonging to whoever knows what these networks carry.

**Every test on one page:** [TEST_LEDGER.md](../TEST_LEDGER.md) lists everything polite
shrink has been put through — simulation, adversarial, real transport, deployment
realism, and the formal checks — with the result and a link to each write-up.
