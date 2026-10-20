# V6 on the Rust fork — test evidence

Branch [`feat/sharding-v6`](https://github.com/topeuph-ai/kitsune2/tree/feat/sharding-v6)
of `topeuph-ai/kitsune2`, rebased onto kitsune2 `main` @ `1e44c65` (2026-10-16).
V6 ("patient lowest") is the default there (`patient_lowest: true`); `false`
gives the original V3 tie-break. Measured 2026-10-20 on one Windows machine. Sections 1–3 were measured before
intent withdrawal (section 5) was added; section 2's V3 figures are without it.

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

## 4. Stale views on a real network

`crates/gossip/tests/sharding_stale.rs`. The in-memory transport is near
instant, so section 2's views were fresh. A test-only switch
(`harness::set_sharding_view_delay`, compiled only in test builds) makes every
node act on the network as it was 2 seconds ago: peer arcs and "leaving"
notices both from that instant. Six nodes, one agent each, target 4, no
deaths. The model predicts that with a wait of 1.5× the staleness V6 is safe
and V3 need not be. A control arm runs V6 with a wait of 0.5× the staleness,
where no rule is safe.

Raw data: [rust_stale_compare.csv](rust_stale_compare.csv).

| arm (runs) | ever below target | re-grows per run | announcements (median) |
|---|---|---|---|
| V6, wait 1.5× (10) | **never** | **0** | 6 |
| V6 + withdrawal, wait 1.5× (4) | **never** | **0** | 6 |
| V3, wait 1.5× (10) | never | 5–20 (median 12) | 33 |
| V3 + withdrawal, wait 1.5× (4) | never | 4–11 (median 8.5) | 31.5 |
| **control:** V6, wait 0.5× (10) | **every run**, down to 1 copy, twice to 0 | 3–31 | 34.5 |

The control failing every time shows the test can catch a failure. **V3 was
not caught failing in these random runs.** The model puts V3's failures in a
narrow band of timings (6 of 159,984 schedules at N=4, R=1), so random runs
rarely hit it. Section 7 forces that timing, and there V3 fails.

## 5. Where V3's re-growing comes from, and the fix

Every grow decision is now logged with its cause: was the half the node would
grow into short of real copies, or did it only look short because of
"leaving" notices? In the forced race, **all 225 of V3's re-grows were of the
second kind**; none was a real shortage. When a node backs off, its notice
stayed live at other nodes until it expired. Growers count announced departures
as already gone, so they grew to cover departures that never came. The model
checks never saw this, because there a withdrawn notice is gone from the next
view.

**Fix: withdrawal** (`withdraw_on_stand_down`, now the default on the branch).
A node that backs off broadcasts a withdrawal naming its exact notice (agent and
expiry), and peers drop it at once. It is safe because a node that backs off
really does keep its data, so counting it as present again is correct.

Forced race (section 2's setup), 5 complete rounds per arm (raw data:
[rust_race_withdraw.csv](rust_race_withdraw.csv)):

| per run | V3 | **V3 + withdrawal** | V6 | **V6 + withdrawal** |
|---|---|---|---|---|
| announcements | 8–808 (median 470) | **8** | 6–8 | 6–8 |
| re-grows | 2–156 (median 90) | **0** | 0 | 0 |
| seconds to settle | 2.7–277 (median 225) | **2.2–2.4** | 2.3–3.2 | 2.2–2.4 |
| re-checks spent waiting | 0 | 0 | 1–10 | 1–2 |
| final copies (mean) | 3,482 | **3,072 every run** | 3,533 | 3,482 |

In a sixth round, V3 without withdrawal was still changing when the 5-minute
limit ran out.

With withdrawal, V3 settles as fast as V6 and ends the most sharded. Under stale
views (section 4) withdrawal helps V3 much less, because the withdrawal is seen
late too. V6 never re-grows with or without it. So V6 remains the recommended
rule, for its safety on stale views (section 1); withdrawal is worth having in
either rule.

## 6. A weakness in the intent channel, fixed

Building the withdrawal turned up an older problem. A new notice for an agent
simply replaced that agent's previous one, whoever sent it. So anyone could send
a short-lived forged notice in a leaving node's name. It would replace the
genuine notice, expire quickly, and leave other nodes counting a node that is
really leaving as staying. That is the unsafe direction.
[REPORT_stage3.md](../REPORT_stage3.md) §2a judged forged notices "fail-safe",
but it only considered forgeries *added* to the table, which can only make
coverage look lower. It listed checking the sender's identity as a defence;
the fork had not implemented it.

Now each notice is stored with the network address it came from, and a node
only counts the notice that came from the agent's own declared address. A
withdrawal is honoured only from that same address and only for the exact notice
it names, so a late or forged withdrawal cannot cancel a newer or genuine one.
Unit tests cover the displacement attack, forged withdrawals and out-of-order
withdrawals. The race test checks that genuine notices between nodes always pass
the address check. On real deployments this is only as strong as the
transport's peer authentication (kitsune2's iroh transport identifies peers by
key; the in-memory test transport does not).

## 7. The staggered cascade, forced on the real code

Section 4's random runs never hit V3's failure, because it needs one precise
timing. `crates/gossip/tests/sharding_cascade.rs` forces that timing, the one
the model check found:

- four nodes, one agent each, all with their home in the same half of the
  ring, so all four would vacate the *other* half;
- target 1, so that half may lose three of its four holders but not all four;
- every node acting on the network as it was 2 s ago;
- each agent announcing exactly once, in **descending ID order, 1 s apart**,
  then waiting 4 s before re-checking. A test-only schedule
  (`harness::set_sharding_announce_schedule`) dictates who announces when.

Every step has about a second of margin, so tick jitter cannot change the
outcome. In the model, this exact schedule loses the sector under V3 and not
under V6.

**A defence the model does not have.** The first time this ran, all four V3
nodes left, but coverage never fell below 2. The real controller's growers
count announced departures as already gone, so the first leavers saw the later
announcements and grew straight back. That rescues V3 only if growing back
finishes before the last holder leaves, about 3 s here. In this test, growing
back is near instant, because there are only a handful of tiny items to copy.
In a real network, taking on half the ring's data again is not. So the delay
before a leaver starts growing back was made a parameter and swept (raw data:
[rust_cascade_sweep.csv](rust_cascade_sweep.csv)):

| delay before a leaver grows back | V3: lowest copies left (3 runs) | V6: lowest copies left (3 runs) |
|---|---|---|
| 0.5 s | 2, 2, 2 | 2, 2, 2 |
| 1 s | 1, 1, 1 | 2, 3, 3 |
| **2 s** | **0, 0, 0** | 2, 2, 2 |
| **3 s** | **0, 0, 0** | 1, 2, 1 |
| **4 s** | **0, 0, 0** | 1, 2, 1 |
| **8 s** | **0, 0, 0** | 1, 1, 1 |

**On the real code, V3 loses every copy of the half in every run once growing
back takes 2 s or more (12 of 12). V6 keeps at least one copy at every delay
(18 of 18).** V6 does not rely on anyone growing back. Its lowest racer waits,
and the others back off. Controls, asserted in the test: on fresh views, V3
keeps a copy on the same schedule (so the cascade is a stale-view failure), and
with near-instant growth the grow rule masks it.

What "0 copies" means here: no node *declares* that half any more, so nobody
will serve it, and new data for it has nowhere to go. The nodes that left still
have the old data on disk; kitsune2 itself never deletes it, though the
application on top may. So this is a hole in what the network promises, which
the controller then has to repair, rather than proven permanent loss.

## Reproduce

In a checkout of the branch:
```
cargo test -p kitsune2_gossip --features sharding --lib sharding                    # unit + model-check tests
cargo test --release -p kitsune2_gossip --features sharding --lib stale_model -- --ignored  # the 14M-schedule case
cargo test -p kitsune2_gossip --features sharding --test sharding_race              # forced race, V6 and V3
cargo test -p kitsune2_gossip --features sharding --test sharding_stale             # 2 s stale views, V6
RACE_RUNS=6 cargo test -p kitsune2_gossip --features sharding --test sharding_race forced_race_compare -- --ignored --nocapture
STALE_RUNS=4 cargo test -p kitsune2_gossip --features sharding --test sharding_stale stale_views_compare -- --ignored --nocapture
cargo test -p kitsune2_gossip --features sharding --test sharding_cascade           # forced cascade: V3 fails, V6 holds, two controls
CASCADE_RUNS=3 cargo test -p kitsune2_gossip --features sharding --test sharding_cascade forced_cascade_regrow_sweep -- --ignored --nocapture
```
