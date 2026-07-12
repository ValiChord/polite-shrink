#!/usr/bin/env python3
"""Op-level reachability verdict for a kitsune_arc_sharding run.

The coverage analysis (analyze_run.py) scores *declared* arcs; this script
scores actual data: was every published op still held by at least one
surviving agent at run end? That is the claim Holochain ultimately cares
about — declared coverage without synced content is exactly the gap a
shrink-before-sync bug would hide in.

Inputs (written by the scenario when K2_OP_LOG_DIR is set):
- published_<agent>.jsonl — one line per publish: {"t_ms", "agent", "op_ids"}
- held_<agent>.json       — teardown dump: {"t_ms", "agent", "op_ids"}

Survivors are agents whose held dump lands within --survivor-window seconds
of the latest dump (the churn cohort tears down minutes earlier, at its own
process end). Ops published by a *non-survivor* within --grace seconds of
its final publish are reported separately as "grey": if nobody ever heard
them before the publisher died, that is publish-propagation latency, not an
arc-controller failure — but they are never silently dropped from the
report.

Stdlib only. Verdict lines mirror analyze_run.py.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def load(oplog_dir):
    oplog = Path(oplog_dir)
    published = []  # (t_ms, agent, op_id)
    for path in sorted(oplog.glob("published_*.jsonl")):
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            for op_id in rec["op_ids"]:
                published.append((rec["t_ms"], rec["agent"], op_id))
    held = {}  # agent -> (t_ms, set of op ids)
    for path in sorted(oplog.glob("held_*.json")):
        rec = json.loads(path.read_text())
        held[rec["agent"]] = (rec["t_ms"], set(rec["op_ids"]))
    return published, held


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("oplog_dir", help="K2_OP_LOG_DIR of the run")
    ap.add_argument(
        "--survivor-window",
        type=float,
        default=60.0,
        help="held dumps within this many seconds of the latest dump are survivors",
    )
    ap.add_argument(
        "--grace",
        type=float,
        default=30.0,
        help="ops published by a non-survivor within this many seconds of its "
        "final publish are reported as grey (propagation latency, not arc safety)",
    )
    ap.add_argument("--out", default=None, help="dir for op_summary.json")
    args = ap.parse_args()

    published, held = load(args.oplog_dir)
    if not published or not held:
        sys.exit(f"no op logs in {args.oplog_dir} — was K2_OP_LOG_DIR set for the run?")

    latest_dump = max(t for t, _ids in held.values())
    survivors = {
        agent
        for agent, (t, _ids) in held.items()
        if latest_dump - t <= args.survivor_window * 1000
    }
    dead = set(held) - survivors
    # Publishers with no held dump at all (hard-killed processes) are dead too.
    publishers = {agent for _t, agent, _op in published}
    dead |= publishers - set(held)

    last_publish = {}
    for t, agent, _op in published:
        last_publish[agent] = max(last_publish.get(agent, 0), t)

    survivor_union = set()
    for agent in survivors:
        survivor_union |= held[agent][1]
    replication = Counter()
    for agent in survivors:
        for op_id in held[agent][1]:
            replication[op_id] += 1

    total, grey, lost = 0, [], []
    rep_counts = []
    for t, agent, op_id in published:
        total += 1
        if op_id in survivor_union:
            rep_counts.append(replication[op_id])
            continue
        if agent in dead and last_publish[agent] - t <= args.grace * 1000:
            grey.append((t, agent, op_id))
        else:
            lost.append((t, agent, op_id))

    rep_counts.sort()
    n = len(rep_counts)
    rep_min = rep_counts[0] if n else 0
    rep_median = rep_counts[n // 2] if n else 0

    print(f"ops published: {total} by {len(publishers)} agents "
          f"({len(survivors)} survivors, {len(dead)} dead at run end)")
    print(f"reachable from survivors: {n}   "
          f"replication per op: min {rep_min}, median {rep_median}")
    print(f"grey (dead publisher, published within {args.grace:.0f}s of its last "
          f"publish — propagation latency, not arc safety): {len(grey)}")
    print(f"lost (published, propagated window elapsed, held by no survivor): "
          f"{len(lost)}")
    for t, agent, op_id in lost[:10]:
        print(f"  LOST {op_id} published by {agent[:12]}… at t_ms={t}")
    if len(lost) > 10:
        print(f"  … and {len(lost) - 10} more")
    print()
    print(f"VERDICT op reachability (zero non-grey ops lost):       "
          f"{'PASS' if not lost else 'FAIL'}")

    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "op_summary.json").write_text(json.dumps({
            "ops_published": total,
            "publishers": len(publishers),
            "survivors": len(survivors),
            "dead": len(dead),
            "reachable": n,
            "replication_min": rep_min,
            "replication_median": rep_median,
            "grey": len(grey),
            "grey_ops": [{"t_ms": t, "agent": a, "op_id": o} for t, a, o in grey],
            "lost": len(lost),
            "lost_ops": [{"t_ms": t, "agent": a, "op_id": o} for t, a, o in lost],
            "survivor_window_s": args.survivor_window,
            "grace_s": args.grace,
            "verdict_op_reachability": not lost,
        }, indent=2))
        print(f"wrote {out / 'op_summary.json'}")


if __name__ == "__main__":
    main()
