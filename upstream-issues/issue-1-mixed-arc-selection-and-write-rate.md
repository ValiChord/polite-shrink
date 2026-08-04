<!-- TITLE (paste into the GitHub title field, not the body): -->
<!-- `mixed_arc_get_agent_activity`: readers can commit to a single peer, and the unthrottled write rate saturates a single-machine run -->

I've been running `mixed_arc_get_agent_activity` on Holochain 0.7.0 and hit two things worth
passing on, both with a suggested fix I'm happy to turn into a PR or drop entirely. The first one
looks like it bears directly on #335, which is still open — in particular the part asking for *"the
delay between data being authored and first being available to the 0-arc nodes"*.

## 1. Readers can commit to a single peer, so the zero-arc author is never read

`get_random_agent_with_write_behaviour` shuffles whatever `get_links` returns on the first call and
takes the first element, with no lower bound on how much has propagated. I logged `links.len()`
inside the zome and ran the scenario's own documented local shape
(`--agents 6 --behaviour zero_read:3 --behaviour zero_write:1 --behaviour full_write:2 --duration 300`):

| run (300 s) | selection calls returning 0 candidates | returning 1 | returning 2 or 3 |
|---|---|---|---|
| A | 1618 | 3 (one per reader) | **0** |
| B | 1916 | 3 (one per reader) | **0** |

The candidate set is never larger than one, in either run. Each reader polls and sees nothing for its
first several hundred calls, then all three see the same single link at effectively the same moment,
select it, and stop calling. A shuffle over a one-element list is a no-op, so all three readers
commit to that one peer.

In both runs the one visible writer was a **full-arc** writer — neither the zero-arc writer nor the
second full-arc writer ever became a candidate.

The consequence is quiet: the scenario runs clean and reports plausible numbers while never
exercising a read against a zero-arc author — the case where the data can only be served by full-arc
nodes. Nothing fails, so nothing signals it. Two places where that looks like it matters:

- #335 asks for the delay between authoring and availability *to* 0-arc nodes, with both 0-arc and
  full-arc nodes creating data. As currently selected, the 0-arc author's data is not being read.
- The scenario README's `zero_read` bullet says *"Selects a single 'zero-write' agent for the
  duration of the scenario run"* — though the Description paragraph above it says *"a single
  'zero_write' or 'full_write' agent"*, so the two may just need reconciling either way.

The same selection idiom appears in five scenarios across two zomes (`write_get_agent_activity`,
`write_get_agent_activity_volatile`, `mixed_arc_get_agent_activity`,
`mixed_arc_must_get_agent_activity`, `write_validated_must_get_agent_activity`). I've only measured
the one, and in the non-mixed scenarios the consequence is milder — all readers watching one peer
rather than a whole behaviour going unexercised — but the race itself isn't specific to this
scenario.

This overlaps with #431 / #506 and I should be clear about what's different. #506 fixed the same
function timing out on the default websocket timeout, and its analysis notes that querying for the
write peer *"usually takes 3 minutes to complete, but it's not deterministic. Sometimes it takes
seconds, sometimes it takes 7 minutes."* That matches what I'm seeing from the other side. What
looks still open is the case where the call **succeeds** and returns a degenerate set: my runs are
on `e4861457`, so after that fix, and nothing was timing out — the calls returned promptly with zero
candidates ~1600 times, then exactly one. A shorter zome-call timeout doesn't help there, because
nothing is hanging.

(Incidentally, and I haven't measured whether it matters: #506's `call_zome_with_options` timeout
landed on `write_validated_must_get_agent_activity` only. The other four scenarios calling this
helper still use plain `call_zome`. Deliberate?)

**Caveat I should be straightforward about:** both instrumented runs were at the default write rate,
which section 2 shows is enough to saturate a single box — announcements propagate slowly under that
load. I haven't measured whether the race still bites at a lower write rate, because my throttled
runs all had the fix active and so can't answer it. The mechanism looks independent of load
(selection happens against whatever has arrived at that instant), but I haven't shown that.

## 2. The default write rate saturates a single-machine run

`agent_behaviour_write` here calls `create_sample_entry` once per iteration with no pause. The
sibling `mixed_arc_must_get_agent_activity` writes in batches of 10 and then sleeps 5 s
(`SLEEP_INTERVAL_WRITE_BEHAVIOUR_MS`) — ~2 entries/s. Measured on my box, this scenario's writers
average **6.8 entries/s** (full-arc, n=10) and **10.8 entries/s** (zero-arc, n=3), so roughly **3–5×**
the sibling's write pressure. I realise the sibling's sleep is partly there to serve its own
batch-delay measurement rather than as a general throttle — but the practical effect is that two
scenarios in the same family aren't directly comparable with each other.

Adding a pause between writes and changing nothing else:

*visibility = highest action seq a reader observed for an author ÷ that author's expected chain
head, where expected head = entries written + 5. `announce_write_behaviour` is a bare `create_link`
with no path anchor, so a writer has exactly 6 actions before its first sample entry (Dna,
AgentValidationPkg, agent key, InitZomesComplete, the cap grant from
`admin_authorize_signing_credentials`, the announce link) and N entries put the head at seq N+5.
Confirmed empirically: on every writer row that reached full visibility, observed head =
entries + 5 exactly. All runs 300 s.*

| write pause | runs | zero-arc author visibility | full-arc author visibility | runs where all 3 writers became visible |
|---|---|---|---|---|
| **0 ms** (current) | 5 | 0.2%, 5.4%, 69.5% | 85.2–99.6% (n=10) | **3 of 5** |
| 250 ms | 3 | 96.4%, 98.4%, 99.1% | 99.8–100.0% (n=6) | 3 of 3 |
| 1000 ms | 3 | 98.6%, 98.6%, 98.9% | 100.0% ×6 | 3 of 3 |

At the default rate the scenario is largely measuring the test machine — in 2 of the 5 runs only two
of the three writers ever became visible to readers at all, which is why those runs yield no zero-arc
figure. At 250 ms everything resolves cleanly.

I'd suggest making the pause configurable with the current behaviour as the default, so nobody's
existing baselines move, and documenting that a single-machine run probably wants a non-zero value.

**Method note, since it affects how to read that table:** all three rows had my selection fix from
section 1 active — without it there is no zero-arc datapoint to compare at any rate. Two of the three
0 ms zero-arc rows came from an earlier version of that fix that lacked the bounded fallback. That
difference cannot affect any figure in the table: the fallback only fires when the writer set is
incomplete, and an incomplete set produces no zero-arc datapoint either way. A sixth 0 ms run is
excluded entirely — that earlier fix version made its readers select nothing at all, which is a bug
in my patch and not a property of the write rate.

## 3. A small residual gap, once the machine can keep up

Noting this in case the size of it is of interest for #335 rather than as a problem. At both
throttled rates the zero-arc author is read slightly less completely than every full-arc author in
the same run — 6 of 6 runs, no overlap between the two groups. In absolute terms, at the end of the
run:

*How far the best reader observation trailed the author's actual chain head, in actions:*

| | zero-arc author | full-arc authors |
|---|---|---|
| 250 ms | 9, 16, 36 | 0, 0, 0, 0, 1, 2 |
| 1000 ms | 3, 4, 4 | 0 ×6 |

That is consistent with the extra hop a zero-arc author's data has to make before anyone can read it,
and it is a lag of single-digit-to-tens of actions rather than a collapse. Both columns are end-of-run
snapshots, so the smallest values are partly just the boundary — the writer's last entry and the
reader's last successful poll aren't synchronised.

To be straightforward about it: I first read the 0 ms row as evidence that zero-arc authors' data was
slow to become readable, and that was wrong — it's contention, and the rate sweep is what showed me
so. Worth knowing if anyone has taken numbers off this scenario on a single box.

## Suggested fix

Small and additive; the existing function is untouched:

1. Add `get_agents_with_write_behaviour`, returning all announced writers in a stable order.
2. Readers wait for the expected number before selecting, with a **bounded fallback** so a writer
   whose announcement never arrives can't stall selection entirely. (My first attempt omitted the
   fallback and produced a run with healthy writers and no reader data at all.)
3. Assign by `ctx.agent_index() % n` instead of shuffling — guarantees coverage and removes a
   source of run-to-run variance.
4. Emit `write_peers_visible_at_selection`, tagged `complete: true|false`.
5. Make the write pause configurable, defaulting to the current unthrottled behaviour.

⚠️ Point 2 is the weakest part and you'll see the problem faster than I did: my version takes the
expected writer count from an env var defaulting to 3, which is fine for the documented local shape
but not for the distributed mode, where a reader has no way to know the global writer count. A
warm-up period or periodic re-selection might fit the harness better — you'll have a much better
sense of that than me.

**Point 4 is the one I'd argue for even if you take nothing else:** it turns "all readers silently
watched the same peer" into a number in the results, so a degraded run looks degraded instead of
looking fine.

## Environment

- `holochain` 0.7.0 built from source with `--features unstable-functions,unstable-countersigning`
  (see the companion issue about the released binaries)
- `wind-tunnel` @ `e4861457`, scenario `mixed_arc_get_agent_activity`
- 6 conductors on one 8-core / 32 GB machine
- Default `ConductorConfig` bootstrap and relay URLs, i.e. the public dev bootstrap. Since the space
  ID derives from the DNA hash, these runs shared a space with anyone else running the same scenario
  — I couldn't see a way to override that from the CLI, and I mention it because it is a
  reproducibility caveat on my absolute numbers.

One environment, one machine — which is where the write-rate effect will be most pronounced, and a
distributed run may not see it at all. The selection race should be independent of that.

Happy to open a PR, or to leave it if you'd rather solve it differently.
