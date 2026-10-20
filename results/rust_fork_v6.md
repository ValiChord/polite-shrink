# V6 on the Rust fork — test evidence

Branch [`feat/sharding-v6`](https://github.com/topeuph-ai/kitsune2/tree/feat/sharding-v6)
of `topeuph-ai/kitsune2`, rebased onto kitsune2 `main` @ `1e44c65` (2026-10-16).
V6 ("patient lowest") is the default there (`patient_lowest: true`); `false`
gives the original V3 tie-break. Measured 2026-10-20 on one Windows machine.

## 1. The stale-view model check, run on the real Rust code

`crates/gossip/src/sharding/controller/stale_model.rs` ports
[`spec/timed_check.py`](../spec/timed_check.py) to Rust. The difference is that
the decision at execute time is made by the controller's own `shrink_recheck`
(V3) and `patient_recheck` (V6), not by a re-implementation of them. Every
schedule is enumerated: announce ticks, per-node lags, and a death at any tick.

| check | result |
|---|---|
| The staggered cascade (4 nodes announce in descending ID order, 2 ticks stale, wait 2× lag) | V3 loses the last copy at tick 7; V6 keeps it, and still lets a node leave |
| V3 failure counts against the Python checker | **identical**: 126 of 4,088 (N=3, R=1, 1× lag wait); 6 of 159,984 (N=4, R=1, 2×); 0 of 159,984 (N=4, R=2, 2×) |
| V6 at a 1× lag wait | safe in every schedule: 4,088 (N=3 R=1), 65,520 (N=4 R=1), 65,520 (N=4 R=2) |
| One death at any tick, detected at once | V3 fails 2,820 of 110,376; V6 fails none. Large case (N=4, R=2, wait 2.5× lag): **V6 safe in all 14,054,400 schedules**, V3 fails some |
| Progress | V6 always lets at least one node leave whenever anyone announced. Counting every announcer without waiting (V5) stalls in some schedules at every size tried |

With deaths, Python counts 2,856 V3 failures where the Rust code counts 2,820. The
36-schedule gap is one modelling difference. In Rust, a dead node's "leaving"
notice stays in the table after its death is noticed, so it is counted as gone
twice; the Python model counts it once. That is the cautious direction. A switch
in the test (`python_view`) gives the Python behaviour, and the counts then match
exactly.

## 2. A forced race on a real network

`crates/gossip/tests/sharding_race.rs`, in-memory transport, real gossip. Six
agents on one node and two on another. The controller takes one snapshot of the
intent table per tick and then decides for each local agent in turn. So agents
on the same node that decide in the same tick cannot see each other's new
intents: a genuinely simultaneous race, which the "don't announce while a lower
ID is racing you" rule cannot prevent. The target redundancy is 6 of 8, so the
margin is thin: only one of any three overlapping leavers can go. No node dies.

Asserted on every run, for both rules: no sector ever falls below the target
after first reaching it; the network settles; at the end no agent is left that
could still safely shrink (no stall); and, under V6, every agent that waited
later left.

**V6's wait has now been seen between real nodes.** Typical run: 3 agents race
for the same half; the lowest waits 1–10 re-checks; the others stand down; the
lowest then leaves.

Both rules, 12 runs each, alternating (raw data:
[rust_race_compare.csv](rust_race_compare.csv)):

| per run | V3 | V6 |
|---|---|---|
| shrink announcements | 8–120 (median 34) | 5–8 (median 7) |
| announcements withdrawn | 4–84 (median 23) | 3–6 (median 4.5) |
| re-checks spent waiting | 0 | 1–10 (median 1.5) |
| shrinks carried out | 2–45 (median 12) | 2–3 (median 2) |
| grow decisions after reaching target (6 runs each) | 2–32 (median 10.5) | **0 in every run** |
| seconds to settle | 2.1–57.6 (median 19) | 2.2–3.3 (median 2.4) |
| final declared sector-copies (of 4,096) | 3,072–3,585 (mean 3,371) | 3,328–3,584 (mean 3,499) |
| fell below target / stalled | never / never | never / never |

What this shows: in a thin, simultaneous race **V3 is safe here but churns**.
It shrinks and re-grows, often for tens of seconds, before it settles. V6
settles in about 2–3 seconds, carrying out only the shrinks it keeps. That is
the oscillation the project set out to remove, reappearing under V3 in a
different form. The likely mechanism: growers count announced vacates as
already gone, and V3 announces far more. Its withdrawn intents also stay live
at peers until they expire. So growers react to departures that never happen.
That mechanism is inferred, not measured.

In V3's favour: its churn sometimes ends more sharded (as low as 3,072 copies,
mean 3,371 against V6's 3,499). Both rules always end in a genuine resting
point where no agent can safely shrink further; which resting point is reached
depends on the path.

Limits: one machine, in-memory transport, 8 agents, 12 runs per rule. These are
fresh views (gossip here is fast), which is why V3 stays safe; V3's safety
failures need stale views, and section 1 covers those.

## 3. The waiting intent's refresh

While the lowest racer waits, its "leaving" notice must stay live at peers
through its next re-check and a grace period after it; otherwise a peer could
stop counting it as gone while it may still leave. `refreshed_expiry` is tested
over 1,000 consecutive waits at four interval/wait settings: the notice never
lapses, and it is re-broadcast at most once per wait.

## Reproduce

In a checkout of the branch:
```
cargo test -p kitsune2_gossip --features sharding --lib sharding                    # 29 unit + model-check tests
cargo test --release -p kitsune2_gossip --features sharding --lib stale_model -- --ignored  # the 14M-schedule case
cargo test -p kitsune2_gossip --features sharding --test sharding_race              # forced race, V6 and V3
RACE_RUNS=6 cargo test -p kitsune2_gossip --features sharding --test sharding_race forced_race_compare -- --ignored --nocapture
```
