#!/usr/bin/env python3
"""Visibility of an author's chain to readers, split by the author's arc.

visibility = (highest action seq a reader observed) / (authored + CHAIN_OVERHEAD)

CHAIN_OVERHEAD = 5: the chain head sequence counts ALL actions, not just the
sample entries. Each writer has 6 actions before its first entry -- Dna,
AgentValidationPkg, agent key, InitZomesComplete, the cap grant from
admin_authorize_signing_credentials, and the announce_write_behaviour link --
so N entries put the head at seq N+5. Measured: the observed-minus-authored
difference is exactly +5 on every fully-tracked writer row. Dividing by the raw
entry count (the earlier mistake) produced visibilities above 100%.

~1.0 means the reader tracked the author's chain. Well below 1.0 means the
author's data had not become readable. The question is whether a ZERO-arc
author's visibility recovers as the write rate drops (=> the gap was load on
this machine) or stays low (=> structural).

Only runs with COMPLETE writer coverage give a zero-arc datapoint, so those are
marked; incomplete runs are still shown but must not be pooled into the claim.

Usage: visibility.py LABEL LOG [LOG ...]
"""
import re
import sys
from collections import defaultdict

CHAIN_OVERHEAD = 5

ansi = re.compile(r"\x1b\[[0-9;]*m|\[[0-9]+m")
hdr = re.compile(r"wt\.custom\.([a-z_]+)\s+\((\d+)\)")
val = re.compile(r"value:\s*(-?[\d.]+)")
beh = re.compile(r"behaviour:\s*(\w+)")
# `agent:` also appears inside `write_agent:`; the lookbehind keeps them apart.
agent = re.compile(r"(?<!write_)agent:\s*([A-Za-z0-9_-]+)")
wagent = re.compile(r"write_agent:\s*([A-Za-z0-9_-]+)")
complete = re.compile(r"complete:\s*(\w+)")


def parse(path):
    cur = None
    authored = {}        # agent -> max entries created
    behaviour = {}       # agent -> zero_write | full_write
    seq = defaultdict(float)   # write_agent -> max observed seq
    obs = defaultdict(int)     # write_agent -> observation count
    coverage = []              # (visible_count, complete_flag)
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
                authored[a.group(1)] = max(authored.get(a.group(1), 0), float(v.group(1)))
                behaviour[a.group(1)] = b.group(1)
        elif cur == "highest_observed_action_seq":
            wa = wagent.search(line)
            if wa:
                seq[wa.group(1)] = max(seq[wa.group(1)], float(v.group(1)))
                obs[wa.group(1)] += 1
        elif cur == "write_peers_visible_at_selection":
            c = complete.search(line)
            coverage.append((int(float(v.group(1))), c.group(1) if c else "?"))
    return authored, behaviour, seq, obs, coverage


label = sys.argv[1]
rows = []
print(f"\n{'='*86}\n{label}\n{'='*86}")
for path in sys.argv[2:]:
    authored, behaviour, seq, obs, coverage = parse(path)
    name = path.split("/")[-1]
    n_writers = len(authored)
    cov = f"{coverage[0][0]}/{len(authored)} complete={coverage[0][1]}" if coverage else "n/a"
    watched = set(seq)
    zero_watched = any(behaviour.get(w) == "zero_write" for w in watched)
    print(f"\n{name}   writers={n_writers}  selection_coverage={cov}  "
          f"zero-arc author read: {'YES' if zero_watched else 'no'}")
    for w in sorted(watched, key=lambda x: behaviour.get(x, "")):
        arc = behaviour.get(w, "?")
        auth = authored.get(w)
        if not auth:
            continue
        vis = seq[w] / (auth + CHAIN_OVERHEAD)
        tag = "ZERO-ARC" if arc == "zero_write" else "full-arc"
        print(f"    {tag:<9} {w[:14]}…  authored={int(auth):<6} "
              f"max_seq={int(seq[w]):<6} visibility={vis:6.1%}  (obs={obs[w]})")
        rows.append((tag, vis))

if rows:
    print(f"\n-- {label}: pooled by author arc --")
    for tag in ("ZERO-ARC", "full-arc"):
        vs = [v for t, v in rows if t == tag]
        if vs:
            print(f"   {tag:<9} n={len(vs)}  " + "  ".join(f"{v:.1%}" for v in sorted(vs)))
