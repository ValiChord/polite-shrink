# Polite Shrink — safe dynamic sharding for Holochain's DHT

Every node in a Holochain network stores every piece of data, because sizing
each node's share safely has been an open problem since Holochain switched
dynamic sharding off in 2021 ([kitsune2 issue #160](https://github.com/holochain/kitsune2/issues/160)).
Full storage caps how large a network can grow.

Polite shrink is a rule for when a node may stop storing part of the data
without any part ever dropping below **R** copies. There is no coordinator,
and every node decides from its own view of the network, which may be out of
date.

## The rule: V6, "patient lowest"

1. **Announce** that you intend to drop a range, unless a lower-ID node is
   already announcing an overlapping one.
2. **Wait** at least as long as your information can be out of date.
3. **Re-check**, counting every other announcer as already gone, and only
   holders you have heard from within the wait. If at least R copies remain,
   drop the range.
4. If not, and only higher-ID announcers stand in the way, **keep your
   announcement up and re-check shortly**; otherwise withdraw it.

The ID order decides only who waits, never who is assumed to stay, so several
nodes can drop at once when the margin allows. The rule, its assumptions and
what backs each claim are on one page: **[SPEC_V6.md](SPEC_V6.md)**.

## Status

- **Implemented** in Rust on a kitsune2 fork, branch
  [`feat/sharding-v6`](https://github.com/topeuph-ai/kitsune2/tree/feat/sharding-v6),
  behind kitsune2's existing `sharding` feature flag. V6 is the default there.
  CI runs every sharding test on each change.
- **Formally specified** in TLA+ ([`spec/StaleShrink.tla`](spec/StaleShrink.tla)),
  submitted to the TLA+ examples collection
  ([tlaplus/Examples#243](https://github.com/tlaplus/Examples/pull/243)).
- **Not merged upstream.** It is offered to the kitsune2 maintainers on
  [#160](https://github.com/holochain/kitsune2/issues/160).

## Try it

```bash
git clone -b feat/sharding-v6 https://github.com/topeuph-ai/kitsune2.git && cd kitsune2   # needs git + rustup
cargo test -p kitsune2_gossip --features sharding --lib sharding           # unit tests + exhaustive model check of the real code
cargo test -p kitsune2_gossip --features sharding --test sharding_cascade  # the staggered cascade: V3 loses a copy, V6 keeps one
cargo test -p kitsune2_gossip --features sharding --test sharding_upgrade  # rollout alongside nodes that never shrink
```

What each test checks, and what a pass means:
[SHARDING_V6.md](https://github.com/topeuph-ai/kitsune2/blob/feat/sharding-v6/SHARDING_V6.md)
on the fork.

## Evidence

| claim | evidence |
|---|---|
| No shrink takes a sector below R, in every schedule | Exhaustive model check of the real Rust decision code: no failure in any schedule up to 6 nodes, and none in 906 million with a death at any moment. TLC agrees on the TLA+ spec ([results/rust_fork_v6.md](results/rust_fork_v6.md), [spec/](spec/)) |
| It holds on a real network stack | Node-death storms over kitsune2's in-memory and iroh transports, 8–32 nodes: no sector ever left without a holder. The staggered cascade forced on the real code: the old rule (V3) loses a copy, V6 does not |
| It holds under churn | One hour of random kills, joins and stale views: 210 kills, 1,630 shrinks, no failure ([§11](results/rust_fork_v6.md)) |
| It holds when deaths go unnoticed | With deaths never detected, the rule without the recent-contact check fails on every seed; with it, none does ([§12](results/rust_fork_v6.md)) |
| The tests can fail | 18 deliberately planted bugs, all caught; and a control with too short a wait fails every time ([§9](results/rust_fork_v6.md)) |
| It does not cost much | At 200 simulated nodes: storage close to V3's, about 3× less sync traffic, and 2–8× less time below R ([results/v6_summary.md](results/v6_summary.md)) |

Every test and its result: **[TEST_LEDGER.md](TEST_LEDGER.md)**.

## Limits

- **Nodes that lie** about what they store defeat any rule that trusts
  declarations, once there are R of them. The defence (checking that nodes
  can actually serve what they claim) is simulated, not built.
- **A brief dip is possible right after a death:** a node can still count a
  holder that died within the last wait, because nothing can tell "dead" from
  "slow" sooner. It never removes data; kitsune2 does not delete stored data
  when a node shrinks.
- **Scale:** exhaustive checks stop at 6 nodes, and network tests at 32 nodes
  on one machine. There is no wide-area test.
- **The policy is not decided here.** How many copies R a network needs, and
  the tuning around it, belong to whoever knows what the network carries.
  What any policy must respect: [docs/policy-constraints.md](docs/policy-constraints.md).

## What's in this repository

| | |
|---|---|
| [SPEC_V6.md](SPEC_V6.md) | the rule, assumptions and guarantees on one page |
| [TEST_LEDGER.md](TEST_LEDGER.md) | every test and its result |
| [results/](results/) | measured results; [rust_fork_v6.md](results/rust_fork_v6.md) covers the Rust implementation |
| [reports/](reports/) | the full write-ups; [REPORT_stale_views.md](reports/REPORT_stale_views.md) explains how V6 was reached |
| [spec/](spec/) | the TLA+ specifications and the Python model checkers |
| [sim/](sim/) | the Python simulator ([`polite_shrink.py`](sim/polite_shrink.py)) and every study script. Run them from the top folder, e.g. `python sim/run_experiments.py` |
| [wind_tunnel/](wind_tunnel/) | measurements of the earlier V3 port over real iroh transport |
| [docs/](docs/) | the idea in one page ([CORE_IDEA.md](docs/CORE_IDEA.md)), how claims are graded ([METHOD.md](docs/METHOD.md)), [related work](docs/RELATED_WORK.md), [how to reproduce](docs/REPRODUCE.md), and the [history and full record](docs/history.md) |

## Background

In Holochain's 2021 sharding tests, nodes reacting to each other's storage
changes from slightly stale information oscillated: the
["hallway dance"](https://blog.holochain.org/testing-sharding/). This study
found that damping the oscillation does not stop the losses: what loses data
is two nodes dropping the same range at once, each on stale information.
Announcing first and re-checking after a wait closes that race. The first
version of the rule (V3, a lowest-ID tie-break) turned out to fail a
staggered cascade once views were genuinely stale; V6 is the version that
passed every check for safety, progress and concurrency. The whole story,
with the earlier studies and their numbers, is in
[docs/history.md](docs/history.md).

---

Research directed by Ceri John (topeuph-ai); design, implementation and
analysis with AI assistance (Claude, Anthropic); all results human-reviewed.
Apache-2.0. Citation: [CITATION.cff](CITATION.cff). This work began on the
[ValiChord repository's research branch](https://github.com/ValiChord/ValiChord/tree/research/dht-arc-sharding-sim/research/arc_sim);
this repository is its home since 13 July 2026.
