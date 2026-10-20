# V6 against other systems' own solutions (October 2026)

The question: where other projects face the same problem (members giving up a
shared duty while a minimum must remain, without a coordinator, on out-of-date
information), how do their solutions compare with V6 on their own terms? The
honest prior was that V6 would often be the slower one, because it deliberately
waits for gossip to catch up. That is what we found in two cases, and it was the
other way round in the third.

| system | their solution | result against V6 |
|---|---|---|
| **Valkey / Redis Cluster** replica migration | lowest node ID moves after a 5 s delay; no announcement | **V6 not needed.** Their admitted race never broke the barrier in the model. V6 only adds its wait. A **real stall bug** was found and confirmed on Valkey itself (below). |
| **One-at-a-time departures** (Cassandra's two-minute rule; self-paced random back-off) | serialise departures | **V6 much faster**: 9× to 180× quicker to shed spare copies, all safe. Cassandra itself is moving to a central metadata log (CEP-21), so this is evidence for coordinator-free systems, not a pitch to Cassandra. |
| **Swarm Bee** storage radius | lower radius under 50% full, raise it when over 100% | **Tie.** The polite-shrink-style rule and the bug reporter's first suggested fix both remove the flip. The reporter's second suggestion only halves it. |

## 1. Valkey replica migration

Model: [`valkey_migration_sim.py`](../valkey_migration_sim.py), a port of
`clusterCron` and `clusterHandleReplicaMigration` (valkey-io/valkey, unstable).
Summary: [valkey_migration_summary.md](valkey_migration_summary.md). 3,600 random
clusters, with orphaned primaries and with a live replica wrongly seen as failed:

- **No rule ever left a primary below the migration barrier.** The source calls
  its race "relatively harmless"; the model agrees. A replica only thinks it is
  the candidate when its stale view leaves out a lower-ID replica, and that kind
  of staleness errs on the safe side.
- **V6 adds 0.4–2 s** to covering every orphaned primary, and buys nothing here.
- **Valkey as written stalls in 3–6% of runs.** The candidate is the
  smallest-named replica of the primaries with the most working replicas, *and
  failed replicas are not skipped*. The source relies on failed replicas
  becoming reachable again. If that replica is gone for good, no replica ever
  migrates to the orphaned primary until an operator runs `CLUSTER FORGET`.
  (Valkey only deletes nodes on reset, on FORGET, or on a handshake timeout.)
- **Skipping replicas seen as FAIL removes every stall**, with no barrier
  violation in the model.

**Confirmed on real Valkey** (fork `topeuph-ai/valkey`, branch
`replica-migration-stall-test`, run on GitHub's Linux runners): a test in
Valkey's own framework, three primaries with 3, 1 and 1 replicas, run five times
on an unpatched and a patched build.

| case | unpatched | patched (skip FAIL replicas: one line) |
|---|---|---|
| control: live smallest-ID replica | migrates in ~6.3 s (5/5) | migrates in ~6.3 s (5/5) |
| failed smallest-ID replica | **never migrates, 30 s timeout (5/5)** | **migrates in ~6.3 s (5/5)** |

## 2. One-at-a-time departures

[`spacing_vs_v6.py`](../spacing_vs_v6.py), results in
[spacing_vs_v6.md](spacing_vs_v6.md). One sector; every holder wants to leave
while a copy can be spared; view lag up to 0.2 or 1 s; 40 runs per cell. All
rules stayed at or above R in every run.

| cluster | V6 | self-paced back-off | operator, 2 min apart |
|---|---|---|---|
| 8 nodes, R=2, 0.2 s lag | **3.3 s** | 29 s | 10 min |
| 20 nodes, R=5, 1 s lag | **22 s** | 11 min | 28 min |
| 50 nodes, R=5, 1 s lag | **41 s** | 83 min | 88 min |

A first attempt let every node try at once, and they cancelled each other for
ever. Self-paced back-off only works with a waiting window that widens with the
number of contenders; that is what is reported here.

## 3. Swarm Bee storage radius

[`bee_radius_sim.py`](../bee_radius_sim.py), results in
[bee_radius_sim.md](bee_radius_sim.md). One node, modelling the mechanism
described in ethersphere/bee#5659 (radius flipping every wakeup). Bee lowers the
radius when the chunks within it are under 50% of capacity, and raises it when
over 100%, evicting only as many chunks as needed to fit. One radius step roughly
doubles responsibility, so the two thresholds leave no margin. When the content
just below the radius is larger than the content within it, both conditions hold
at once.

| scenario | Bee | don't lower while full | evict out-of-radius first | polite-shrink style |
|---|---|---|---|---|
| dead zone (#5659's shape) | **671 changes/week** | 0 | 335 | 0 |
| neighbourhood outgrew radius 8 | **672 changes/week** | 1 | 336 | 1 |
| ordinary halving (should move once) | 1 | 1 | 1 | 1 |

Limits: one node, no batch values or expiry, no peers' radii. It reproduces the
mechanism, not Bee's whole storer.

## What this means for V6

V6 wins where the alternative is to queue departures. It loses, slightly, where
an existing rule's race turns out to be harmless (Valkey). It is not the right
tool where the problem is a controller's own thresholds (Swarm), though
polite-shrink's hysteresis lesson is. The two concrete things to offer other
projects are bug-level: Valkey's stall and its one-line fix, and the evidence
that Swarm's second suggested fix is not enough.
