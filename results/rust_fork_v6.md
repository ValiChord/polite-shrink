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
| **Six nodes** (overnight, 2026-10-21) | V6: **0 failures and 0 stalls in 16,777,152 schedules** at each of R = 1, 2, 3 (lag 2, wait 1× lag); **0 failures in 905,966,208 schedules with one death at any tick** (R = 2). V3 fails 567,936 / 1,220,092 / 1,552,760 of the no-death schedules and 61,725,944 with a death |
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
[REPORT_stage3.md](../reports/REPORT_stage3.md) §2a judged forged notices "fail-safe",
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

## 8. The remaining risks, tested (2026-10-21)

Four open questions about the world around the rule, each tested on the real
Rust code or with the repo's simulator.

### 8.1 Deaths that are not noticed promptly

`stale_model::sweep_detection_delay`: every schedule for 4 nodes, R = 2, a
gossip lag of 2 ticks, a wait of 2 ticks, one death at any tick, noticed
`detect` ticks later (2,358,720 schedules per row).

| death noticed after | V6 schedules failing | V3 schedules failing |
|---|---|---|
| 0 ticks | **0%** | 4.6% |
| 1 tick | **0%** | 4.6% |
| 2 ticks (= the wait) | 6.5% | 10.6% |
| 3 ticks | 14.5% | 17.8% |
| 4 ticks | 22.5% | 25.5% |
| 6 ticks | 36.4% | 39.3% |

V6 is safe while a death is noticed within less than its wait, and degrades
steadily after that, always a little better than V3. The operational rule
follows: death detection has to be faster than V6's wait.

### 8.2 A wait shorter than the real staleness

`stale_model::sweep_wait_against_lag`: every schedule for 4 nodes, R = 2,
gossip lag up to 3 ticks, no deaths.

| wait | V6 schedules failing | V3 schedules failing |
|---|---|---|
| 1/3 of the lag | 20.5% | 35.1% |
| 2/3 of the lag | 1.9% | 19.2% |
| **= the lag** | **0%** | 7.5% |
| 4/3 | 0% | 1.9% |
| 5/3 | 0% | 0.16% |
| 2× | 0% | 0.02% |

V6 has a sharp edge exactly at wait = lag; V3 is not fully safe even at twice
the lag. On a real network (section 4) the too-short-wait control fell below
target in every run. The Rust controller scales its wait from the measured
gossip lag (90th percentile, clamped); a network that suddenly becomes slower
than that measurement is the case to watch.

### 8.3 Nodes that lie about what they store

[`byz_v6.py`](../sim/byz_v6.py) reruns the Stage-3 Byzantine studies
([REPORT_stage3.md §2](../reports/REPORT_stage3.md)) with V6 as well as V3: six seeds
each, N = 200, R = 5. Summary: [byz_v6_summary.md](byz_v6_summary.md).

- **Full-arc liars:** the same threshold for both rules. Below K = R liars, no
  sector loses its last real copy; from K = R (5) up, some do. V6 leaves
  slightly fewer uncovered sectors (93 against 120 at K = 5; 329 against 352 at
  K = 10), which is not a defence. No timing rule can see that a declaration is
  false. The defence is verified coverage (Stage 3 §6–7), which is simulated,
  not built into the fork.
- **Forged leaving-notices:** neither rule lost a copy. V6 answers by keeping
  arcs wide (mean arc level 3.00 against V3's 2.11), but without churn: about
  9,900 sync units against V3's 80,000. On the fork, intents are also checked
  against their sender's own address (section 6), so a forged notice from
  another peer is not counted at all.
- **Trojan exit** (liars vanish after the network thins around them):
  identical for both rules.

### 8.4 A real network stack, at larger sizes

`tests/sharding_iroh.rs` runs the storm over kitsune2's **iroh** transport
(QUIC, with a local relay from the test bootstrap server) instead of the
in-memory one, using V6 with withdrawal. Each node starts at full arc and
shards down; a quarter of the nodes are then killed at once, chosen to push
sectors below target without killing the last holder of any sector.

| nodes | declared copies before the storm (of full replication) | killed | sectors pushed below target | ever orphaned | back to target |
|---|---|---|---|---|---|
| 8 | 2,048 of 4,096 (50%) | 2 | 256 | **never** | within ~2.4 s |
| 16 | 1,536 of 8,192 (19%) | 4 | 288 | **never** | ~2.4 s |
| 24 | 1,520 of 12,288 (12%) | 6 | 128 | **never** | ~2.4 s |
| 32 | 1,569 of 16,384 (10%) | 8 | 0 (no such kill existed) | **never** | not needed |

At 32 nodes the network had sharded so deeply that no set of 8 victims could
push a sector below target without orphaning it, so recovery was not exercised
there. Limits: one machine, so latency is local; the relay is local; 32 nodes
is about the most this PC runs comfortably. It tests V6 and its wiring over a
real network stack, not over a wide-area network.

## 9. Can the tests fail? Mutation testing (2026-10-21)

A test suite that passes proves little unless it would fail on broken code.
`mutate_v6.py` (in this repo) plants 18 realistic bugs in the fork's sharding
code, one at a time, and runs the tests against each: first the unit and
model-check tests, then, for any bug that survives, the forced race, the
forced cascade, the stale-view and storm tests.

**Round 1: 11 of 18 caught.** Every bug that breaks *safety* was caught:
counting only lower-ID announcers (V6 turned into V3), leaving one copy short,
a middle racer waiting, yielding to the wrong side, an intent that lapses
early, a forged sender, a withdrawal that removes the wrong intent.

The 7 that got through were all in glue code or defaults, not the safety rule:

| bug that survived round 1 | test added (fork commit `10af77e`) | round 2 |
|---|---|---|
| ranges that only touch counted as overlapping | unit test: adjacent ranges neither overlap nor block a re-check | caught |
| no yield at announce time | new cascade test: fresh views, lowest ID first; nobody else may announce while it is announcing | caught |
| waiting silently drops the shrink | race test: an agent that waited must go on to execute that intent | caught |
| no withdrawal sent on stand-down | race test: a stand-down must be applied by the other node (new log line on receipt) | caught |
| default rule is V3 | unit test on the defaults | caught |
| default has no withdrawal | unit test on the defaults | caught |
| intent still live at its exact expiry instant | unit test on expiry | caught* |

\*Round 2 ran before this unit test existed and the bug survived; the test
was then added and checked by hand against that bug (passes on the real code,
fails with the bug). This one is close to harmless in practice: it keeps an
intent alive a microsecond longer, which errs on the safe side.

**Result: 18 of 18 caught.** Limits: the bugs are hand-picked, not generated
by a tool such as `cargo-mutants`, so they cover what a reviewer would guess,
not every possible edit. Raw results: `results/mutation_round1.json`,
`results/mutation_round2.json`.

## 10. A real rollout (2026-10-21)

No live network runs an earlier version of this controller (V3 exists only
on our fork), so a real rollout does not start from V3. It starts from nodes
without dynamic sharding: they keep a fixed arc and never shrink. Such a
node does not have the sharding module at all, and kitsune2's transport
silently drops messages for a module that is not registered
(`crates/api/src/transport.rs`, the `K2WireType::Module` branch), so V6's
intent messages cost it nothing and cannot break its connections. In the
tests it is modelled as a node whose clamp is never reached: full arc,
never shrinks, never announces.

`tests/sharding_upgrade.rs` (fork commit `6dcb333`), in-memory transport,
each test run three times:

| scenario | what is asserted | result (3 runs) |
|---|---|---|
| 2 fixed-arc nodes + 6 V6 nodes, target 4, no deaths | once every sector reaches the target, none drops below it; fixed nodes keep a full arc and never announce; at the end no V6 agent could still shrink safely | pass every run; 6–8 shrinks, final 2,432–2,560 of 4,096 sector-copies |
| 6 fixed-arc nodes replaced one at a time by V6 nodes (join, 10 s side by side, then an old node goes away), target 3 | no sector ever without a declared holder (outside the 1 s death-detection window, as in the storm test); once only V6 remains every sector returns to the target and stays there | pass every run; no hole ever, even inside the detection window; 8–13 shrinks, at most 1 re-grow |
| 8 V6 nodes, half with the default timing, half with a slower set (check every 250 ms, persistence 2, wait 4x lag, lag ceiling 3 s), target 4, no deaths | as the first row | pass every run |

The first version of the mixed-settings test failed its progress check: it
declared the network settled after 15 s of no change, shorter than the slower
nodes' decision cycle (about 18 s), so two agents were still on their way.
The settle window is now computed from each configuration; it then passed
five runs out of five. Safety held in every run, including that one.

Not covered: different `target_redundancy` values on different nodes (a
policy mismatch; the network then only guarantees the smallest R any node
uses), a node restarting with its old agent and data rather than a new
node joining, and more than 8 nodes.

*Aside, not evidence for a rollout:* the exhaustive model check was also run
with every assignment of V3 or V6 to the nodes. A V6 node's shrink never
broke safety whatever its neighbours ran, and losses fell as more nodes ran
V6, but a mix is not strictly better than all-V3: V6's wait can move a
departure into a V3 node's blind window (520 of about a million N=4, R=2
cases). Since nobody runs V3, this test was dropped from the fork.

## 11. An hour of chaos (2026-10-21)

`tests/sharding_chaos.rs` (fork commit `e57d96d`) runs V6 on the in-memory
transport under random churn. Every 2–6 s one of these happens, chosen by a
seeded generator: a random node is killed (never one that is the last holder
of some sector, since no rule survives losing the last copy), a new node
joins with a full arc, every node's view becomes 0, 0.25, 0.5, 1 or 1.5 s
stale, or nothing. The wait is a fixed 2 s, so assumption A1 holds. Between
7 and 14 nodes, target 3.

Every 50 ms the test reads every node's true declared arc and fails if a
sector's count falls to below the target with no kill in the previous 5 s
(a shrink did it), or if any sector has no holder outside that window.
Inside the window such drops are counted rather than failed: a node cannot
discount a death it has not noticed yet (assumption A3).

| run | kills | joins | staleness changes | shrinks | waits | stand-downs | re-grows | failures | drops inside the 5 s windows |
|---|---|---|---|---|---|---|---|---|---|
| seed 1, 1 hour, wait 2 s | 210 | 207 | 224 | 1,630 | 844 | 492 | 819 | **0** | **0** |
| control: wait 0.3 s, seeds 1–3 | | | | | | | | **fails each time**, after 5, 86 and 41 s | |

The control is what makes the clean run mean something: with the wait
shorter than the staleness, the same checker catches a shrink taking a
sector below target on every seed. At the end of the hour the churn stopped
and every sector returned to the target.

Limits: one seed for the full hour; one machine and the in-memory transport,
with staleness injected rather than real; at most 14 nodes; kills that would
remove a sector's last holder are excluded by design. Log:
`results/chaos_v6_seed1_1h.log`.

## 12. Enforcing the timing assumptions (2026-10-21; merged into `feat/sharding-v6`)

Sections 8–11 test V6 while its assumptions hold, and measure what happens
when they do not. The code itself trusted two of them:

- **A1, information no older than the wait.** The wait is 2.5 × the 90th
  percentile of the per-peer "last gossip" age, capped at `lag_ceiling_ms`.
  Nothing at decision time checked that what a node was relying on was
  actually that fresh.
- **A3, deaths noticed in time.** kitsune2 marks a peer unresponsive only
  on an event: a closed connection, a connect timeout, a failed send. A node
  that dies silently can be counted as a holder for as long as that takes.

A finding along the way: kitsune2's per-peer last-gossip timestamp is set
when a round is **attempted**, even if the peer never answers
(`crates/gossip/src/gossip.rs`: "Even if this fails, we should still record
that this peer has been selected"). So V6's measured "lag" is the time since
each peer was last *tried*, not the age of what is known about it.

**The change** (fork commit `2d57117`, setting `require_recent_contact`,
default on in the branch): for shrink decisions only, a remote holder counts
if this node has *heard from* it within the current wait. "Heard from" is
kitsune2's per-peer completed-rounds counter going up, which happens only
when a gossip message arrives from that peer, in either direction. A holder
gone silent stops counting within one wait of its last message, whatever the
transport does. A broken assumption then costs progress, not safety. Growth
is unchanged.

**Results** (chaos soak of §11; 5 min per seed unless stated;
`results/failsafe_runs.txt`):

| scenario | without the change | with it |
|---|---|---|
| existing suite (race, stale, cascade incl. V3 failing, storm, rollout, iroh) | pass | **pass**, progress checks included |
| deaths never detected (`CHAOS_UNDETECTED=1`), seeds 1–3 | **fails every seed**, after 76, 21 and 12 s: a shrink counted a dead holder | **no failure** on any seed (13–20 undetected kills, 117–178 shrinks each) |
| wait 0.3 s, far below the staleness (the old control), seeds 1–3 | fails every seed (§11) | **safe, but no shrink at all**: nothing is heard from within 0.3 s |
| normal chaos, 20 min, seed 1 | 595 shrinks by 20 min (the §11 run) | 577 shrinks: **no measurable progress cost** |

**What it does not close.** A holder that has died is still counted until
one wait after its last message, because nothing local can tell "dead" from
"slow" sooner. In the undetected-death runs, shrinks did take sectors below
target inside that window: 2 and 128 sector-samples (50 ms samples × sectors)
on seeds 1 and 3, all within 5 s of a kill, and never a sector with no
holder. In the normal 20-minute run, 8 such sector-samples, also inside the
post-kill windows. So A3 becomes "a death is noticed within one wait of the
dead node's last message", **enforced by the rule itself** instead of
depending on the transport, but not removed. Intents are not covered: a
missing intent still relies on delivery within the wait (A1 for intents).

Status: developed on `feat/sharding-v6-failsafe`, CI green, then merged into
`feat/sharding-v6` (fork commit `2d57117`), where it is on by default.

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
cargo test --release -p kitsune2_gossip --features sharding --lib sweep_ -- --ignored --nocapture --test-threads 1   # 8.1, 8.2
cargo test -p kitsune2_gossip --features sharding --test sharding_iroh               # 8.4, 8 nodes over iroh
IROH_SIZES=8,16,24,32 cargo test -p kitsune2_gossip --features sharding --test sharding_iroh storm_over_iroh_larger -- --ignored --nocapture
cargo test -p kitsune2_gossip --features sharding --test sharding_upgrade           # 10, rollout (about 2.5 min)
CHAOS_SECS=3600 cargo test -p kitsune2_gossip --features sharding --test sharding_chaos -- --ignored --nocapture   # 11 (CHAOS_WAIT_MS=300 for the control)
# 12: SHARDING_RECENT_CONTACT=0 turns the change off; CHAOS_UNDETECTED=1 simulates undetected deaths
```
For 8.3, in this repo: `python sim/byz_v6.py --seeds 6`.
For 9, in this repo: `python sim/mutate_v6.py <path to fork checkout>` (about 1–2 hours on 3 cores).
