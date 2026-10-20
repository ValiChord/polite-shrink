"""
valkey_migration_sim — Valkey/Redis Cluster replica migration, against V6.

Valkey (and Redis) Cluster let a spare replica move, with no coordinator, to a
primary that has lost all its working replicas ("replica migration",
`clusterHandleReplicaMigration` in src/cluster_legacy.c). The rule is the
polite-shrink problem with a lowest-ID tie-break:

  * minimum to keep: a replica may leave only if its primary keeps more than
    `cluster-migration-barrier` working replicas;
  * who goes: among the replicas of the primaries with the most working
    replicas, the one with the smallest node ID;
  * when: once a target primary has been seen orphaned for 5 s;
  * on what: each node's own gossip view of the cluster.

The source says, in part: "There is a possible race condition causing multiple
replicas to migrate at the same time, but this is unlikely to happen and
relatively harmless when it does." This study asks whether that holds, and
what a V6-style gate would cost.

The Valkey rule is ported from `clusterCron` and `clusterHandleReplicaMigration`
(valkey-io/valkey, unstable, October 2026), including details that matter:

  * a node sees its own role fresh and everyone else's through gossip, `lag`
    ticks old (per node);
  * failure has two levels: PFAIL (local timeout) and FAIL (agreed, then
    broadcast); counts of "ok" replicas exclude FAIL only, while step 2 (the
    barrier check) also excludes PFAIL;
  * the candidate is the smallest name among ALL replicas (failed included) of
    the primaries with the most non-FAIL replicas;
  * the target is the first orphaned primary in the node's own dictionary
    order, which differs per node (siphash seeds are per process);
  * a primary's orphaned_time is updated only when the migration loop actually
    runs (after steps 1-2 pass), as in the source.

Three rules are compared:

  * "valkey": the rule as written. The candidate may be a FAILED replica (the
    source relies on failed nodes becoming reachable again), so a permanently
    dead replica with the smallest name, on a primary with the most working
    replicas, blocks every migration until an operator runs CLUSTER FORGET.
  * "skipfail": the obvious fix for that stall, skipping replicas this node
    sees as FAIL when choosing the candidate. It reintroduces the race: a live
    replica that others wrongly see as FAIL (a partition) is skipped by them
    and may still migrate itself, so two replicas leave the same primary.
  * "v6": skipfail plus the polite-shrink gate. Only the candidate announces
    (a gossiped flag); it waits `wait` ticks, then re-checks counting every
    other announcer from the same primary as gone; the lowest announcer waits
    rather than cancelling when only higher ones block it; no one announces
    while a lower-ID replica of the same primary is announcing; and of several
    announcers heading to the same orphan, only the lowest goes.

Scenario "deaths": every replica of one or two primaries dies (orphans), and
sometimes one spare elsewhere. Scenario "partition": as "deaths", plus one live
replica of the best-provided primary is cut off for a while: the others see it
PFAIL then FAIL, its own view of the cluster is frozen at the cut, and it keeps
running its cron.

One tick = 100 ms (Valkey's cron period).
"""

from __future__ import annotations

import argparse
import json
import os
import random
from dataclasses import dataclass, field, asdict
from multiprocessing import Pool

DELAY = 50            # CLUSTER_REPLICA_MIGRATION_DELAY, 5000 ms
RESULTS = os.path.join(os.path.dirname(__file__), "results")


@dataclass
class World:
    seed: int
    shape: list            # replicas per primary, e.g. [3, 3, 1]
    barrier: int = 1
    lag_max: int = 10      # gossip staleness, ticks (1 s)
    pfail: int = 150       # node timeout, 15 s
    fail_spread: int = 20  # FAIL reaches observers up to 2 s apart
    kill_at: int = 20
    horizon: int = 900     # 90 s
    wait: int = 0          # V6 wait after announcing (set from lag_max)
    scenario: str = "deaths"
    part_at: int = 205     # partition start: just after the orphan is FAIL everywhere
    part_len: int = 400    # partition length (40 s)


@dataclass
class Outcome:
    migrations: int = 0
    barrier_violations: int = 0      # a migration left its donor below the barrier
    orphaned_by_migration: int = 0   # ...with no live replica at all
    wasted: int = 0                  # migrated into a primary that already had one
    protect_ticks: int = -1          # orphan created -> every primary covered for good
    stalled: bool = False            # an orphan left while a donor could spare one
    announces: int = 0
    stand_downs: int = 0


class Sim:
    def __init__(self, w: World, rule: str):
        self.w, self.rule = w, rule
        rng = random.Random(w.seed)
        self.rng = rng
        prim = []
        reps = []
        nid = 0
        self.primary_of = {}
        for p, k in enumerate(w.shape):
            prim.append(nid); pid = nid; nid += 1
            for _ in range(k):
                reps.append(nid); self.primary_of[nid] = pid; nid += 1
        self.n = nid
        self.primaries, self.replicas = prim, reps
        self.name = {i: rng.getrandbits(64) for i in range(self.n)}
        self.lag = {i: rng.randint(1, w.lag_max) for i in range(self.n)}
        self.order = {}
        for i in range(self.n):
            o = list(range(self.n)); rng.shuffle(o); self.order[i] = o
        # Kill every replica of one or two primaries (creating orphans), plus
        # possibly a spare elsewhere, at kill_at.
        victims = set()
        orph = rng.sample(prim, k=min(len(prim) - 1, rng.choice([1, 1, 2])))
        for p in orph:
            victims |= {r for r in reps if self.primary_of[r] == p}
        if rng.random() < 0.5:
            others = [r for r in reps if r not in victims]
            if others:
                victims.add(rng.choice(others))
        self.victims = victims
        self.alive = {i: True for i in range(self.n)}
        # Per-observer detection times for each victim.
        self.pfail_at = {}
        self.fail_at = {}
        for x in victims:
            base_fail = w.kill_at + w.pfail + rng.randint(0, 10)
            for i in range(self.n):
                self.pfail_at[(i, x)] = w.kill_at + w.pfail + rng.randint(-5, 5)
                self.fail_at[(i, x)] = base_fail + rng.randint(0, w.fail_spread)
        # Partition: one live replica of the best-provided primary, seen as
        # failed by everyone else while cut off.
        self.cut = None
        if w.scenario == "partition":
            best = max(prim, key=lambda p: sum(1 for r in reps
                                               if self.primary_of[r] == p and r not in victims))
            live = [r for r in reps if self.primary_of[r] == best and r not in victims]
            if live:
                self.cut = min(live, key=lambda r: self.name[r])  # the natural candidate
                for i in range(self.n):
                    self.pfail_at[(i, self.cut)] = w.part_at + w.pfail + rng.randint(-5, 5)
                    self.fail_at[(i, self.cut)] = (w.part_at + w.pfail + rng.randint(0, 10)
                                                   + rng.randint(0, w.fail_spread))
        self.hist = []              # per tick: (primary_of copy, intents copy)
        self.orphan_since = {i: {} for i in range(self.n)}
        self.intent = {}            # replica -> (donor, target, execute_at)
        self.out = Outcome()

    # -- views -------------------------------------------------------------
    def view(self, i, t):
        if i == self.cut and self.cut_active(t):
            t = self.w.part_at              # frozen at the cut
        s = t - self.lag[i]
        if s < 0 or not self.hist:
            pof, its = dict(self.primary_of_initial), {}
        else:
            pof, its = self.hist[min(s, len(self.hist) - 1)]
            pof = dict(pof)
        pof[i] = self.primary_of[i]          # own role is fresh
        return pof, its

    def cut_active(self, t):
        return self.cut is not None and self.w.part_at <= t < self.w.part_at + self.w.part_len

    def is_fail(self, i, x, t):
        if x == self.cut and i != x:
            return self.cut_active(t) and t >= self.fail_at[(i, x)]
        return x in self.victims and t >= self.fail_at[(i, x)]

    def is_pfail(self, i, x, t):
        if x == self.cut and i != x:
            return self.cut_active(t) and t >= self.pfail_at[(i, x)]
        return x in self.victims and t >= self.pfail_at[(i, x)]

    # -- the Valkey checks -------------------------------------------------
    def counts(self, i, t, pof):
        reps_of = {p: [] for p in self.primaries}
        for r, p in pof.items():
            reps_of[p].append(r)
        ok = {p: sum(1 for r in reps_of[p] if not self.is_fail(i, r, t))
              for p in self.primaries}
        return reps_of, ok

    def valkey_eligible(self, i, t, pof):
        """clusterCron trigger + steps 1-3; returns (target, candidate_is_me,
        reps_of) or None. Updates orphan_since as the loop does."""
        reps_of, ok = self.counts(i, t, pof)
        orphans = [p for p in self.primaries if ok[p] == 0]
        mx = max(ok.values())
        mine = pof[i]
        if not (orphans and mx >= 2 and ok[mine] == mx):
            return None
        # Step 2: barrier, counting neither FAIL nor PFAIL replicas.
        okstrict = sum(1 for r in reps_of[mine]
                       if not self.is_fail(i, r, t) and not self.is_pfail(i, r, t))
        if okstrict <= self.w.barrier:
            return None
        # Step 3: candidate and target; orphan timers updated here only.
        cand = i
        target = None
        since = self.orphan_since[i]
        for p in (x for x in self.order[i] if x in ok):
            if ok[p] == 0:
                if target is None:
                    target = p
                since.setdefault(p, t)
            else:
                since.pop(p, None)
            if ok[p] == mx:
                for r in reps_of[p]:
                    if self.rule != "valkey" and r != i and self.is_fail(i, r, t):
                        continue
                    if self.name[r] < self.name[cand]:
                        cand = r
        return target, cand == i, reps_of, okstrict

    def migrate(self, i, target, t):
        donor = self.primary_of[i]
        if any(self.alive[r] and self.primary_of[r] == target
               for r in self.replicas if r != i):
            self.out.wasted += 1
        self.primary_of[i] = target
        self.out.migrations += 1
        left = sum(1 for r in self.replicas
                   if self.alive[r] and self.primary_of[r] == donor)
        if left < self.w.barrier:
            self.out.barrier_violations += 1
        if left == 0:
            self.out.orphaned_by_migration += 1

    # -- one tick ----------------------------------------------------------
    def step(self, t):
        w = self.w
        if t == w.kill_at:
            for x in self.victims:
                self.alive[x] = False
                self.intent.pop(x, None)
        decisions = []
        for i in self.replicas:
            if not self.alive[i]:
                continue
            pof, its = self.view(i, t)
            if self.rule in ("valkey", "skipfail"):
                e = self.valkey_eligible(i, t, pof)
                if e and e[0] is not None and e[1] and \
                        t - self.orphan_since[i][e[0]] > DELAY:
                    decisions.append(("go", i, e[0]))
            else:
                decisions.append(("v6", i, (pof, its)))
        for kind, i, arg in decisions:
            if kind == "go":
                self.migrate(i, arg, t)
            else:
                self.v6_step(i, t, *arg)
        self.hist.append((dict(self.primary_of), dict(self.intent)))

    def v6_step(self, i, t, pof, its):
        w = self.w
        mine = self.primary_of[i]
        if i in self.intent:
            donor, target, ex = self.intent[i]
            if t < ex:
                return
            reps_of, ok = self.counts(i, t, pof)
            okstrict = sum(1 for r in reps_of[donor]
                           if not self.is_fail(i, r, t) and not self.is_pfail(i, r, t))
            others = [r for r, (d, _, _) in its.items() if r != i and d == donor]
            lower = [r for r in others if self.name[r] < self.name[i]]
            higher = [r for r in others if self.name[r] > self.name[i]]
            # Donor keeps more than the barrier with me and every other
            # announcer from it gone (V5's count, the barrier as R).
            donor_ok = okstrict - 1 - len(others) >= w.barrier
            rivals_to_target = [r for r, (_, tg, _) in its.items()
                                if r != i and tg == target and self.name[r] < self.name[i]]
            target_still_orphan = ok.get(target, 1) == 0
            if donor_ok and target_still_orphan and not rivals_to_target:
                del self.intent[i]
                self.migrate(i, target, t)
            elif (not donor_ok and higher and not lower and target_still_orphan
                  and not rivals_to_target):
                self.intent[i] = (donor, target, t + 1)      # lowest waits
            else:
                del self.intent[i]
                self.out.stand_downs += 1
            return
        e = self.valkey_eligible(i, t, pof)
        if not e or e[0] is None or not e[1]:
            return
        target = e[0]
        if t - self.orphan_since[i][target] <= DELAY:
            return
        # Yield to a lower-ID replica of the same primary that is announcing.
        if any(d == mine and self.name[r] < self.name[i]
               for r, (d, _, _) in its.items()):
            return
        self.intent[i] = (mine, target, t + w.wait)
        self.out.announces += 1

    def run(self):
        self.primary_of_initial = dict(self.primary_of)
        w = self.w
        uncovered_last = -1
        for t in range(w.horizon):
            self.step(t)
            if t >= w.kill_at:
                covered = all(
                    any(self.alive[r] and self.primary_of[r] == p for r in self.replicas)
                    for p in self.primaries)
                if not covered:
                    uncovered_last = t
        o = self.out
        o.protect_ticks = (uncovered_last - w.kill_at + 1) if uncovered_last >= 0 else 0
        alive_count = {p: sum(1 for r in self.replicas
                              if self.alive[r] and self.primary_of[r] == p)
                       for p in self.primaries}
        o.stalled = (min(alive_count.values()) == 0 and
                     max(alive_count.values()) > self.w.barrier)
        return o


def random_world(seed, barrier, lag_max, scenario="deaths"):
    rng = random.Random(seed * 7919 + 1)
    n_prim = rng.randint(3, 6)
    shape = [rng.randint(1, 4) for _ in range(n_prim)]
    # Guarantee at least one primary that can spare a replica.
    shape[rng.randrange(n_prim)] = max(barrier + 2, 3)
    w = World(seed=seed, shape=shape, barrier=barrier, lag_max=lag_max,
              scenario=scenario)
    w.wait = lag_max + 1
    return w


RULES = ("valkey", "skipfail", "v6")


def one(args):
    seed, barrier, lag_max, scenario = args
    res = {"seed": seed, "barrier": barrier, "lag_max": lag_max, "scenario": scenario}
    for rule in RULES:
        w = random_world(seed, barrier, lag_max, scenario)
        o = Sim(w, rule).run()
        res[rule] = asdict(o)
    return res


def summarise(rows):
    lines = ["# Valkey replica migration vs V6", "",
             "Random clusters of 3-6 primaries with 1-4 replicas each; every replica of "
             "one or two primaries dies (creating orphans), sometimes plus one spare "
             "elsewhere. Gossip staleness up to `lag` ticks per node; PFAIL after 15 s, "
             "FAIL reaching observers up to 2 s apart; 1 tick = 100 ms; 90 s per run. "
             "V6 waits lag+1 ticks after announcing, on top of Valkey's own 5 s delay.",
             "",
             "| scenario | barrier | lag (s) | rule | runs | migrations | barrier violations (runs) | "
             "orphaned by migration (runs) | wasted migrations | stalled runs | "
             "median time to cover all (s) |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    import statistics as st
    keys = sorted({(r["scenario"], r["barrier"], r["lag_max"]) for r in rows})
    for sc, b, lag in keys:
        sub = [r for r in rows if r["scenario"] == sc and r["barrier"] == b
               and r["lag_max"] == lag]
        for rule in RULES:
            o = [r[rule] for r in sub]
            pt = [x["protect_ticks"] / 10 for x in o if not x["stalled"]]
            lines.append(
                f"| {sc} | {b} | {lag/10:.1f} | {rule} | {len(o)} | {sum(x['migrations'] for x in o)} | "
                f"{sum(x['barrier_violations'] > 0 for x in o)} | "
                f"{sum(x['orphaned_by_migration'] > 0 for x in o)} | "
                f"{sum(x['wasted'] for x in o)} | {sum(x['stalled'] for x in o)} | "
                f"{st.median(pt) if pt else float('nan'):.1f} |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=2000)
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--lags", default="2,10,20")
    ap.add_argument("--barriers", default="1,2")
    ap.add_argument("--scenarios", default="deaths,partition")
    a = ap.parse_args()
    work = [(s, b, int(l), sc) for sc in a.scenarios.split(",")
            for b in map(int, a.barriers.split(","))
            for l in a.lags.split(",") for s in range(a.runs)]
    with Pool(a.procs) as pool:
        rows = pool.map(one, work, chunksize=50)
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "valkey_migration_cells.json"), "w") as fh:
        json.dump(rows, fh)
    text = summarise(rows)
    with open(os.path.join(RESULTS, "valkey_migration_summary.md"), "w",
              encoding="utf-8") as fh:
        fh.write(text)
    print(text)


if __name__ == "__main__":
    main()
