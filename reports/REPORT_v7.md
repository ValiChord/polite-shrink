# V7: a floor and a ceiling together

**October 2026. Status: tested in TLA+ and in the simulator; not yet implemented
on the kitsune2 fork.** V6 remains the rule on the fork until V7 has passed the
same Rust and real-network tests.

## What V7 is

V6 coordinates **leaving**: a node announces it intends to drop a range, waits
out the staleness of its information, and re-checks, counting every other
announced leaver as gone. **Growing** under V6 is uncoordinated: every node that
sees a short range grows on its own, so one gap can draw several growers.

V7 adds the ceiling side, from StaleCap (a model of "at most C at once" written
by Ceri John with other AI assistants), so that growing is coordinated too:

1. **Leaving:** V6's rule, with one repair (*alongside*, below).
2. **Growing:** announce the range you mean to take, wait, re-check, and grow
   only if the range is still short counting the lower-id announced growers as
   already there. One gap no longer draws a herd.
3. **Silent nodes** are read the cautious way for each bound: as gone for the
   floor, as possibly present for the ceiling.
4. **The floor always wins.** A short range may always regrow; the ceiling is
   *soft*. A range down to one copy or none is repaired at once, without
   coordination (*critical repair*). The small-network clamp also grows at once.

Run V7 with a spare copy: R one or two above the minimum needed (see below).

## The models (TLA+)

Three models, all checked exhaustively by TLC; full table in
[results/v7_tla.md](../results/v7_tla.md), models in [spec/v7/](../spec/v7/).

- **StaleCap** (the ceiling alone) turns out to be **StaleShrink read through the
  complement**: a ceiling C on "active" nodes is a floor R = N − C on the rest.
  TLC gives identical state counts (16,848 and 43,348 at 4 nodes).
- **StaleBand** (floor and ceiling at once, nodes joining and leaving
  concurrently): both bounds kept and progress in both directions, at 4 and 5
  nodes; the old V3 rule and a too-short wait break it, as they must.
- **StaleBandNet** (+ one network split, node deaths, the recent-contact rule):
  - a split, **with** recent contact: **no breach** of either bound in 11–14
    million states per configuration; **without** it, both holders of a range
    leave at once, each counting the other's frozen copy;
  - a death never detected: with recent contact, breaches occur **only within one
    wait of the death** (the window no local rule can close: dead and slow look
    the same until then); without it, breaches long after;
  - a split **and** an undetected death together: nothing outside that window
    (8.7 and 15.1 million states);
  - witnesses confirm that leaves and joins do happen during a split, so the
    safety is not bought by standing still.

## A problem in V6 found on the way

**V6 can shard down from full arcs far more slowly than V3**, and on some worlds
effectively stalls. V6 does not announce while a lower-id node is announcing for
an overlapping range (its *yield*). Starting from full arcs every node's first
shrink drops one of the same two halves, so those nodes queue and shrink one at
a time, each taking 50–100 ticks.

[results/activation_speed.md](../results/activation_speed.md), 24 fresh worlds,
6,000 ticks, no data lost by any rule:

| rule | median ticks to shard down | slowest world | copies at the end, worst world |
|---|---|---|---|
| V3 | 813 | 872 | 9.0 |
| **V6** | **1,346** | **3,004** | **38.8** (still stuck) |
| V6 + multiwait | 1,346 | 2,662 | 6.4 |
| V6 + multiwait + alongside | 809 | 873 | 9.4 |

**The fix (*alongside*):** a node may announce alongside lower-id racers when,
counting itself and all of them as gone, its range still keeps R copies. The
re-check is unchanged, so this cannot affect safety. *Multiwait* (several racers
may wait at a failed re-check, from StaleCap's "patient_k") helps only the last
stragglers.

**The published V6 results hid this.** [results/v6_summary.md](../results/v6_summary.md)
reports the mean arc level averaged across 48 worlds (1.17 for activation). A
stalled world, with a group of nodes still at full arc, reads about 3–4 on its
own; averaged with healthy worlds it disappears. In a sample, 1 of 6 of the
published worlds and 3 of 6 fresh ones were stalled. The averages stand as
published; this is the reading that was missing.

The same yield exists in the Rust code. The real-network tests used 14 nodes or
fewer, too few to show it.

## V7 in the simulator

200 nodes, the four standard scenarios, fresh worlds (from seed 600,000).
[results/v7_summary_C8.md](../results/v7_summary_C8.md),
[results/v7_summary_C6.md](../results/v7_summary_C6.md).

**Against V6 at the same R (= 5):**

| | V6 | V7 |
|---|---|---|
| copies per range at the end (target 5) | 12–29 | 5.6–5.9 |
| data transferred (activation / storm / churn) | 5,302 / 6,836 / 6,945 | 146 / 1,122 / 2,593 |
| storage held by the largest 10% of nodes (activation / churn) | 69% / 91% | 35% / 80% |
| runs losing data in a 30% storm | 0/24 | 2/24 |

Every V7 storm loss began **at the storm tick itself**: the die-off killed every
copy of a range at once, which V7's lean storage allows and V6's accidental
over-storage did not. No rule can save a range whose holders all die in the same
moment; only having more copies beforehand helps.

**A hard ceiling is ruled out.** A ceiling that can refuse growth refused
hundreds of repairs and lost data in 4–8 of 24 storm and churn runs. In sharding
the floor must win.

**At comparable storage** ([results/v7_equal_storage.md](../results/v7_equal_storage.md)),
V7 with a higher target against V6 at R = 5:

| | runs losing data (storm / churn) | storage (V6 = 100%) | data transferred (V6 = 100%) |
|---|---|---|---|
| V6, R = 5 | 0/24 / 0/24 | 100% | 100% |
| V7, R = 5 | 2/24 / 0/24 | 36% | 16% |
| **V7, R = 6** | **0/24 / 0/24** | **43%** | **21%** |
| V7, R = 7 | 0/24 / 0/24 | 49% | 28% |
| V7, R = 8 | 0/24 / 0/24 | 56% | 33% |
| V7, R = 9 | 0/24 / 0/24 | 62% | 40% |

With one spare copy V7 loses nothing in either scenario, at under half the
storage and a fifth of the bandwidth. Zero in 24 runs does not exclude a true
rate up to about 14%. The lesson matches an old one in this repo: V6's storm
safety, like V3's before it, came from accidental over-storage. **Provision R
explicitly.**

**Repair triggers tried:**
- *urgent* (grow at once when a range is two or more copies short): ordinary
  deaths trigger it constantly, so herding returns, worse than V6 (data
  transferred 9,936–9,970 against V6's 6,836–6,945 at R = 6). Ruled out.
- *critical* (grow at once when a range is down to one copy or none): costs
  nothing in normal running and helps a little in splits. Kept.

## Splits

**V6 had never been through the split study.** It now has
([results/partition_v6_summary.md](../results/partition_v6_summary.md), 48 seeds
per scenario): no data lost in 144 runs, never below 5 copies, far more data
reachable during a split than V3, and settling 4–8 times faster after the heal.

**V7 through the same scenarios**
([results/partition_v7_summary.md](../results/partition_v7_summary.md),
[round 2](../results/partition_v7_round2_summary.md)): no data lost in any run.
Data reachable within each side during a split was worse than V6 at R = 6, and
close to V6 at R = 8–9 in balanced and flapping splits, but still 2.7–3 times
worse in a 90/10 split. V7 also settles more slowly after the heal (120–360
ticks against 29–57).

**Those split figures flattered both rules.** The simulator let a node cut off
by the split "grow" and sync a range whose copies were all on the other side.
[sim/partition_real.py](../sim/partition_real.py) fixes that: a grow completes
only when every added sector has a live holder on the grower's own side.
At the moment of a 90/10 split, the **large side never lacked anything**, for
either rule; the whole effect is on the small side. V6's apparent advantage there
was luck: it leaves a few nodes storing everything, and when one of them happens
to be in the small group, that group has everything.

[results/partition_real_summary.md](../results/partition_real_summary.md), 90/10
split, 48 seeds:

| | small group has gaps | unreachable data in the split | storage |
|---|---|---|---|
| V6 | 10/48 | 34,411 | 6,327 |
| V7, R = 6 | 47/48 | 157,049 | 3,751 |
| V6, one pinned node in the small group | 0/48 | 0 | 6,049 |
| **V7, R = 6, one pinned node in the small group** | **0/48** | **0** | **3,604** |

A *pinned* node keeps everything and never shrinks. One in the small group gives
it full access for the whole split, under either rule, and under V7 adds nothing
to total storage (the others shrink a little to make room). A pin protects only
the group it is in. No data was lost in any of the 864 runs.

**What it means in practice.** A cut-off group can always read its own data and
write new data (it syncs on reconnection). What it loses is other people's data
that it does not hold, which, scattered by hash, is effectively random items.
Today's Holochain, where every node holds everything, avoids this entirely; any
sharding gives some of it up, V7 more than V6 because it saves more. Pinning is
satisfactory where a group's whole network fits on one machine; it does not scale
to a large network, which is when sharding matters. **For groups that must keep
working while cut off, the right fix is usually to give their essential data its
own small network** (Holochain already supports separate networks per group):
small networks sit under the clamp, every member holds everything, and the large
shared network can shard freely.

## Verdict, and what is not yet shown

For networks large enough to shard, V7 is better than V6 on storage, bandwidth,
fairness and start-up, with no data lost from R = 6 upwards in any storm, churn
or split run, provided R includes a spare copy. V6 is better at settling after a
split heals and leaves a cut-off group fewer gaps.

Not yet shown: V7 on the real kitsune2 code (unit and model checks of the real
decision functions, the forced race and cascade, stale views, storms over iroh,
the chaos soak, the rollout tests, mutation testing); V7 at more than 200 nodes;
a real wide-area network. Those are the next stage.

## Reproduce

From the top folder, with the pinned environment (`requirements.txt`):

```bash
python sim/activation_speed.py --seeds 24 --ticks 6000   # the V6 start-up slowdown
python sim/band_sim.py --seeds 24 --ceiling 8             # V7 against V6, four scenarios
python sim/v7_equal_storage.py --seeds 24                 # V7 at R = 5..9
python sim/partition_v6.py --seeds 48                     # V6 through splits
python sim/partition_v7.py --seeds 48                     # V7 through splits (add --round2)
python sim/partition_real.py --seeds 48                   # realistic splits, pinned nodes
```
TLA+: see [spec/v7/README.md](../spec/v7/README.md).
