#!/usr/bin/env python3
"""Test whether read-side instability tracks WHICH write peer a reader drew.

Readers call get_random_agent_with_write_behaviour once and keep that peer for
the whole run. With 1 zero-arc and 2 full-arc writers, the draw differs per run.

Hypothesis: querying the ZERO-arc writer behaves differently from querying a
FULL-arc writer, because a zero-arc author stores nothing itself -- its activity
can only be served by full-arc peers.

`highest_observed_action_seq` is tagged with both `agent` (the reader) and
`write_agent` (the peer queried), which is what makes this testable.
Note the scenario only emits these metrics when the observed head CHANGES
(n_jump != 0), so a low sample count means "the head rarely moved" = stale reads.
"""
import re
import sys
from collections import defaultdict

ansi = re.compile(r"\x1b\[[0-9;]*m|\[[0-9]+m")
hdr = re.compile(r"wt\.custom\.([a-z_]+)\s+\((\d+)\)")
val = re.compile(r"value:\s*(-?[\d.]+)")
beh = re.compile(r"behaviour:\s*(\w+)")
# Tag order is `write_agent: X, agent: Y`, so a bare `agent:` pattern matches
# INSIDE `write_agent:` and silently reports the reader as the peer. The
# lookbehind is load-bearing -- without it every reader identity is wrong.
agent = re.compile(r"(?<!write_)agent:\s*([A-Za-z0-9_-]+)")
wagent = re.compile(r"write_agent:\s*([A-Za-z0-9_-]+)")


def parse(path):
    cur = None
    seq = []          # (reader, write_agent, value)
    writers = {}      # agent -> behaviour, from entry_created_count
    for raw in open(path, encoding="utf-8", errors="replace"):
        line = ansi.sub("", raw)
        m = hdr.search(line)
        if m:
            cur = m.group(1)
            continue
        if not cur or "value:" not in line:
            continue
        v = val.search(line)
        if not v:
            continue
        if cur == "entry_created_count":
            a, b = agent.search(line), beh.search(line)
            if a and b:
                writers[a.group(1)] = b.group(1)
        elif cur == "highest_observed_action_seq":
            wa = wagent.search(line)
            a = agent.search(line)
            if wa and a:
                seq.append((a.group(1), wa.group(1), float(v.group(1))))
    return seq, writers


for path in sys.argv[1:]:
    seq, writers = parse(path)
    name = path.split("/")[-1]
    print(f"\n{'='*72}\n{name}   ({len(seq)} chain-head observations)")

    zero = [a for a, b in writers.items() if b == "zero_write"]
    full = [a for a, b in writers.items() if b == "full_write"]
    print(f"  writers: {len(zero)} zero-arc, {len(full)} full-arc")

    # Which peer did each reader draw, and how did it fare?
    per_reader = defaultdict(list)
    for reader, wa, v in seq:
        per_reader[(reader, wa)].append(v)

    by_arc = defaultdict(list)
    for (reader, wa), vals in sorted(per_reader.items()):
        arc = "ZERO-arc" if wa in zero else ("FULL-arc" if wa in full else "UNKNOWN")
        by_arc[arc].append((len(vals), max(vals)))
        print(f"    reader {reader[:14]}… -> {arc} peer {wa[:14]}… : "
              f"n={len(vals):<5} max_seq={max(vals):.0f}")

    print("  -- grouped by the ARC of the peer queried --")
    for arc in sorted(by_arc):
        ns = [n for n, _ in by_arc[arc]]
        mx = [m for _, m in by_arc[arc]]
        print(f"    {arc}: readers={len(ns)}  observations={ns}  max_seq_reached={[int(m) for m in mx]}")
