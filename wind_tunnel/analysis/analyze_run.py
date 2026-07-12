#!/usr/bin/env python3
"""Coverage/floor analysis for a kitsune_arc_sharding Wind Tunnel run.

Reads the influx line-protocol files written by `--reporter influx-file`
(WT_METRICS_DIR) and applies the simulation's ground-truth checks
(research/arc_sim/arc_sim.py) to the real network's declared arcs:

- per-agent arc timeline from `wt.custom.arc_state` samples
- per-sector coverage over time on the real DHT's sector grid
  (SECTOR_SIZE = 2^23 -> 512 sectors, the same ring size the sim used)
- floor(t)        = min sector coverage        (sim: m.floor)
- zero_sectors(t) = sectors with no holder     (sim: m.zero_sectors)
- frac_under(t)   = fraction of sectors < R    (sim: m.frac_under)
- controller event timeline from `wt.custom.sharding_event`

A sector counts as covered by an agent only if the agent's declared arc
contains the whole sector — the same containment rule as the fork's storm
test (`sharding_storm.rs::declared_coverage`). An agent counts as live from
its first arc_state sample until `--grace` seconds after its last one;
abrupt death (churn cohort) = samples stop.

Output: human-readable report on stdout, summary.json (+ floor.png when
matplotlib is importable) in --out.

Stdlib only by design — runnable anywhere without a venv.
"""

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

SECTOR_SIZE = 1 << 23  # kitsune2_dht::SECTOR_SIZE
NUM_SECTORS = (0xFFFFFFFF // SECTOR_SIZE) + 1  # 512
U32_MAX = 0xFFFFFFFF


# ---------------------------------------------------------------- parsing

def _split_unescaped(text, sep):
    """Split on `sep` outside double quotes, honouring backslash escapes."""
    parts, buf, in_quotes, escaped = [], [], False, False
    for ch in text:
        if escaped:
            buf.append(ch)
            escaped = False
        elif ch == "\\":
            buf.append(ch)
            escaped = True
        elif ch == '"':
            buf.append(ch)
            in_quotes = not in_quotes
        elif ch == sep and not in_quotes:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return parts


def _unescape(value):
    return (
        value.replace("\\ ", " ")
        .replace("\\,", ",")
        .replace("\\=", "=")
        .replace("\\\\", "\\")
    )


def _parse_field_value(raw):
    if raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if raw in ("t", "T", "true", "True"):
        return True
    if raw in ("f", "F", "false", "False"):
        return False
    if raw.endswith(("i", "u")):
        try:
            return int(raw[:-1])
        except ValueError:
            return raw
    try:
        return float(raw)
    except ValueError:
        return raw


def parse_line(line):
    """One influx line -> (measurement, tags, fields, t_seconds) or None."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    parts = _split_unescaped(line, " ")
    parts = [p for p in parts if p != ""]
    if len(parts) < 2:
        return None
    head = parts[0]
    if len(parts) >= 3:
        field_part, ts_part = parts[1], parts[-1]
        try:
            t = int(ts_part) / 1e9
        except ValueError:
            field_part, t = parts[1], None
    else:
        field_part, t = parts[1], None

    head_parts = _split_unescaped(head, ",")
    measurement = _unescape(head_parts[0])
    tags = {}
    for tag in head_parts[1:]:
        if "=" in tag:
            key, _, value = tag.partition("=")
            tags[_unescape(key)] = _unescape(value)
    fields = {}
    for field in _split_unescaped(field_part, ","):
        if "=" in field:
            key, _, value = field.partition("=")
            fields[_unescape(key)] = _parse_field_value(value)
    return measurement, tags, fields, t


def load_metrics(metrics_dir):
    arc_samples = defaultdict(list)  # agent -> [(t, start, end, empty)]
    events = []  # (t, kind, agent, fields)
    op_counts = defaultdict(lambda: {"said": 0, "heard": 0})
    files = sorted(Path(metrics_dir).glob("*.influx"))
    if not files:
        sys.exit(f"no .influx files in {metrics_dir}")
    for path in files:
        for line in path.read_text().splitlines():
            parsed = parse_line(line)
            if parsed is None:
                continue
            measurement, tags, fields, t = parsed
            if t is None:
                continue
            if measurement.endswith("arc_state"):
                arc_samples[tags.get("agent_id", "?")].append(
                    (
                        t,
                        int(fields.get("arc_start", 0)),
                        int(fields.get("arc_end", 0)),
                        bool(int(fields.get("is_empty", 0))),
                    )
                )
            elif measurement.endswith("sharding_event"):
                events.append(
                    (t, tags.get("event", "?"), tags.get("agent_id", "?"), fields)
                )
            elif measurement.endswith("said_messages"):
                op_counts[tags.get("agent_id", "?")]["said"] += int(
                    fields.get("num_messages", 0)
                )
            elif measurement.endswith("heard_messages"):
                op_counts[tags.get("agent_id", "?")]["heard"] += int(
                    fields.get("num_messages", 0)
                )
    for samples in arc_samples.values():
        samples.sort()
    events.sort()
    return dict(arc_samples), events, dict(op_counts), [str(f) for f in files]


# ---------------------------------------------------------------- coverage

def arc_to_sector_ranges(start, end):
    """Inclusive u32 arc -> list of (first_sector, last_sector) fully inside.

    Wrapping arcs (start > end) split into two segments, mirroring DhtArc
    semantics. Returns [] when no whole sector fits.
    """
    def contained(seg_start, seg_end):
        first = math.ceil(seg_start / SECTOR_SIZE)
        last = (seg_end + 1) // SECTOR_SIZE - 1
        return [(first, last)] if first <= last else []

    if start <= end:
        return contained(start, end)
    return contained(start, U32_MAX) + contained(0, end)


def coverage_timeline(arc_samples, grace, bucket):
    """Per-bucket sector coverage from declared arcs of live agents."""
    all_times = [t for samples in arc_samples.values() for (t, *_a) in samples]
    t0, t1 = min(all_times), max(all_times)
    n_buckets = int((t1 - t0) / bucket) + 1

    lifespans = {
        agent: (samples[0][0], samples[-1][0] + grace)
        for agent, samples in arc_samples.items()
    }

    timeline = []
    cursor = {agent: 0 for agent in arc_samples}
    for b in range(n_buckets):
        t = t0 + b * bucket
        diff = [0] * (NUM_SECTORS + 1)
        n_live = 0
        span_sum = 0
        for agent, samples in arc_samples.items():
            first, last = lifespans[agent]
            if not (first <= t <= last):
                continue
            i = cursor[agent]
            while i + 1 < len(samples) and samples[i + 1][0] <= t:
                i += 1
            cursor[agent] = i
            _st, start, end, empty = samples[i]
            n_live += 1
            if empty:
                continue
            span = (end - start if start <= end else U32_MAX - start + end) + 1
            span_sum += span
            for lo, hi in arc_to_sector_ranges(start, end):
                diff[lo] += 1
                diff[hi + 1] -= 1
        cov, acc = [], 0
        for s in range(NUM_SECTORS):
            acc += diff[s]
            cov.append(acc)
        timeline.append(
            {
                "t": t,
                "n_live": n_live,
                "floor": min(cov),
                "zero_sectors": sum(1 for c in cov if c == 0),
                "mean_cov": sum(cov) / NUM_SECTORS,
                "mean_span_frac": (span_sum / n_live / (U32_MAX + 1)) if n_live else 0.0,
                "cov": cov,
            }
        )
    return timeline, t0


# ---------------------------------------------------------------- report

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("metrics_dir", help="WT_METRICS_DIR of the run")
    ap.add_argument("--redundancy", type=int, default=5, help="target R")
    ap.add_argument("--bucket", type=float, default=1.0, help="bucket seconds")
    ap.add_argument(
        "--grace",
        type=float,
        default=3.0,
        help="agent counts as live this many seconds past its last sample",
    )
    ap.add_argument(
        "--warmup",
        type=float,
        default=30.0,
        help="exclude this many leading seconds from verdicts",
    )
    ap.add_argument("--out", default=None, help="dir for summary.json / floor.png")
    args = ap.parse_args()

    arc_samples, events, op_counts, files = load_metrics(args.metrics_dir)
    if not arc_samples:
        sys.exit("no arc_state samples found — was the run started with --reporter influx-file?")

    timeline, t0 = coverage_timeline(arc_samples, args.grace, args.bucket)
    settled = [row for row in timeline if row["t"] - t0 >= args.warmup]
    scored = settled if settled else timeline

    event_counts = defaultdict(int)
    for _t, kind, _agent, _fields in events:
        event_counts[kind] += 1

    floor_min = min(row["floor"] for row in scored)
    zero_max = max(row["zero_sectors"] for row in scored)
    final_window = [row for row in timeline if row["t"] >= timeline[-1]["t"] - 60]
    final_floor = min(row["floor"] for row in final_window)
    final_span = final_window[-1]["mean_span_frac"]
    # Post-warmup only: agents report an empty arc between create and join,
    # so early buckets legitimately contain span 0.
    spans = [row["mean_span_frac"] for row in scored if row["n_live"]]

    total_said = sum(c["said"] for c in op_counts.values())
    total_heard = sum(c["heard"] for c in op_counts.values())

    print(f"files: {len(files)}   agents seen: {len(arc_samples)}   "
          f"events: {len(events)}   duration: {timeline[-1]['t'] - t0:.0f}s")
    print(f"sector grid: {NUM_SECTORS} sectors (SECTOR_SIZE 2^23), R = {args.redundancy}, "
          f"warmup excluded: {args.warmup:.0f}s")
    print()
    print("controller events:")
    for kind in ("grow", "shrink_intent", "shrink_executed", "intent_cancelled",
                 "peer_loss_cancel", "intent_send_failed", "other"):
        if event_counts.get(kind):
            print(f"  {kind:18} {event_counts[kind]}")
    if not events:
        print("  (none — controller idle: check K2_SHARDING_CLAMP_MIN_PEERS vs agent count)")
    print()
    print(f"mean arc span (post-warmup): start {spans[0]:.3f} -> min {min(spans):.3f} "
          f"-> final {final_span:.3f} (1.000 = FULL)")
    if min(spans) > 0.999:
        print("  WARNING: arcs never shrank — the controller never engaged.")
    print()
    print(f"coverage floor (post-warmup): min {floor_min}   "
          f"orphaned sectors: max {zero_max}")
    print(f"final 60s: floor {final_floor} vs R={args.redundancy}")
    print()
    verdict_continuous = zero_max == 0
    verdict_redundant = final_floor >= args.redundancy
    print(f"VERDICT continuous coverage (no sector ever orphaned): "
          f"{'PASS' if verdict_continuous else 'FAIL'}")
    print(f"VERDICT final redundancy (floor >= R):                 "
          f"{'PASS' if verdict_redundant else 'FAIL'}")
    print(f"\nops: said {total_said}, heard {total_heard} "
          f"(context only — op-level loss is not measured here)")

    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        summary = {
            "files": files,
            "agents": len(arc_samples),
            "redundancy": args.redundancy,
            "warmup_s": args.warmup,
            "grace_s": args.grace,
            "bucket_s": args.bucket,
            "event_counts": dict(event_counts),
            "events": [
                {"t": t - t0, "kind": kind, "agent": agent}
                for t, kind, agent, _fields in events
            ],
            "floor_min_post_warmup": floor_min,
            "zero_sectors_max_post_warmup": zero_max,
            "final_60s_floor": final_floor,
            "final_mean_span_frac": final_span,
            "verdict_continuous_coverage": verdict_continuous,
            "verdict_final_redundancy": verdict_redundant,
            "ops_said_total": total_said,
            "ops_heard_total": total_heard,
            "timeline": [
                {k: row[k] for k in
                 ("t", "n_live", "floor", "zero_sectors", "mean_cov", "mean_span_frac")}
                for row in timeline
            ],
        }
        (out / "summary.json").write_text(json.dumps(summary, indent=2))
        print(f"\nwrote {out / 'summary.json'}")
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            ts = [row["t"] - t0 for row in timeline]
            fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(10, 6))
            ax1.plot(ts, [row["floor"] for row in timeline], label="floor")
            ax1.plot(ts, [row["mean_cov"] for row in timeline], label="mean cov")
            ax1.axhline(args.redundancy, ls="--", lw=1, label=f"R={args.redundancy}")
            ax1.set_ylabel("sector coverage")
            ax1.legend()
            ax2.plot(ts, [row["mean_span_frac"] for row in timeline], label="mean span")
            ax2.plot(ts, [row["n_live"] / max(len(arc_samples), 1) for row in timeline],
                     label="live frac")
            for t, kind, _agent, _fields in events:
                if kind == "shrink_executed":
                    ax2.axvline(t - t0, color="tab:green", alpha=0.15, lw=0.8)
                elif kind == "peer_loss_cancel":
                    ax2.axvline(t - t0, color="tab:red", alpha=0.3, lw=0.8)
            ax2.set_xlabel("seconds")
            ax2.set_ylabel("fraction")
            ax2.legend()
            fig.tight_layout()
            fig.savefig(out / "floor.png", dpi=120)
            print(f"wrote {out / 'floor.png'}")
        except ImportError:
            print("(matplotlib not available — skipped floor.png)")


if __name__ == "__main__":
    main()
