# Upstream drafts — NOT SENT. Two issues for `holochain/wind-tunnel`.

**Where:** <https://github.com/holochain/wind-tunnel/issues/new> — public, no issue template.
**Repo state (checked 2026-08-03):** public, issues enabled, not archived, last pushed the same day.
**Likely readers:** ThetaSinner (opened #214, #335 and kitsune2 #160), matthme (scoped #416), cdunster, jost-s, zippy.

**Suggested order: post ISSUE 2 first.** It is small, purely factual, costs them nothing to accept,
and is the thing that blocks a newcomer from running the harness at all. ISSUE 1 is the substantial
one and reads better as the second thing from someone who has already filed something useful.

**Everything below the `---` for each issue is the text to post.** Reword freely — it should sound
like you. Don't feel obliged to keep the tables if they feel heavy; the numbers matter more than
the formatting.

**When they reply:** bring the replies back rather than answering from these notes. Several claims
here have narrow caveats (one machine, one environment, fix-active runs) and the exact wording of
those caveats is doing real work.

**Deliberately NOT mentioned in either issue:** polite-shrink, sharding, kitsune2 #160. Both issues
stand on their own merits. Raising them together would make the fix look like a means to an end.

---

## ⚠️ Verification pass, 2026-08-04 — read this before posting

The previous version of this file contained four numbers that did not survive checking against
`wind-tunnel-patch/RESULTS_write_rate_sweep.txt`, plus two claims resting on logs that no longer
exist. All are corrected below. What changed and why:

| Was | Now | Why |
|---|---|---|
| `3 of 6` runs with complete coverage at 0 ms, caption "3 runs per rate" | **3 of 5**, caption states the real run counts | The results file holds **5** runs at 0 ms. The "6th" is §7.9's run where the **first version of my own patch** (no bounded fallback) made readers select nothing at all. That is my bug, not the write rate's — it cannot be counted against the scenario. |
| "roughly 10 entries/s versus 2 — about 5×" | **6.8/s full-arc, 10.8/s zero-arc → 3–5×** | 10/s is the top of the range. Means over the 0 ms runs: full-arc 2032 entries/300 s (n=10), zero-arc 3236/300 s (n=3). |
| "full-arc authors sit at 100%" | **99.8–100.0%** | Two full-arc rows at 250 ms are 99.8% and 99.9%. The separation is still clean (max zero-arc 99.1% < min full-arc 99.8%), but "100%" is not what was measured. |
| "Adding a pause and changing nothing else" | states that **all rows had the selection fix active**, and that two 0 ms rows used an earlier version of it | Not disclosing this leaves a hidden variable for a maintainer to find. The argument that it cannot affect any quoted number is now *in* the issue. |
| Error text ending `Expected Function(FunctionType { params: [I32, I32], results: [I64] })` | trimmed to the portion recorded in `PLAN_0.7_conductor_run.md` §7.1 while the log existed | That clause is not in the contemporaneous record and the logs are gone with `/tmp`. Do not quote reconstructed error text at maintainers. |
| "Across 9 earlier runs (27 reader draws)… a uniform draw would give about a third" | **removed** | Cannot be reconciled with §7.9's note that fresh-space 60 s runs found no peer at all, so some of those runs contributed zero draws. And "uniform draw" assumes the 27 draws are independent — which the very next clause ("all three readers picked the same peer") disproves. The direct `links.len()` measurement is a **mechanism** and is stronger than any statistic; it carries the section alone. |

**Verified correct and unchanged:** `BATCH_SIZE = 10` / `SLEEP_INTERVAL_WRITE_BEHAVIOUR_MS = 5_000`
in the sibling scenario; no sleep in `mixed_arc_get_agent_activity`; `create_sample_entry` writes one
entry per iteration; `shuffle`-then-`first` selection; `announce_write_behaviour` is a bare
`create_link` with no path anchor (which is what makes the `+5` chain-overhead arithmetic come out
right); the `hdk` workspace features; `flake.nix:62`; `WT_HOLOCHAIN_PATH` in the README; the
1618/3/0 and 1916/3/0 candidate-set counts; `ctx.agent_index()` is a real framework API.

**ISSUE 2 is now proved from the binaries, not from a failed run.** Reproducible in 30 seconds:

```bash
gh release download holochain-0.7.0 --repo holochain/holochain \
  -p 'holochain-x86_64-unknown-linux-gnu' -p 'holochain-unstable-x86_64-unknown-linux-gnu'
for b in holochain-x86_64-unknown-linux-gnu holochain-unstable-x86_64-unknown-linux-gnu; do
  echo "== $b"; strings -n 8 "$b" | grep -oE '__hc__(sleep|accept_countersigning_preflight_request)_1' | sort -u
done
# holochain-...          : (nothing)
# holochain-unstable-... : __hc__sleep_1
```

`__hc__sleep_1` is `#[cfg(feature = "unstable-functions")]` and
`__hc__accept_countersigning_preflight_request_1` is `#[cfg(feature = "unstable-countersigning")]`
— both at `crates/holochain/src/core/ribosome/real_ribosome.rs:509–516`, tag `holochain-0.7.0`.
So the "unstable" asset **was** built with `unstable-functions` and **was not** built with
`unstable-countersigning`. That is a symbol-table fact, not an anecdote.

**Anchoring changed.** #214 and #416 are both **closed**. **#335 is OPEN**, is the issue this
scenario was built to satisfy, asks in terms for *"the delay between data being authored and first
being available to the 0-arc nodes"*, and ThetaSinner's only comment on it is *"what remains to
complete this ticket?"* Both issues below now lead with #335.

---
---

# ISSUE 1 — the scenario

**Title:**

`mixed_arc_get_agent_activity`: readers can commit to a single peer, and the unthrottled write rate saturates a single-machine run

**Body:**

---

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

---
---

# ISSUE 2 — the released binaries (post this one first)

**Title:**

Released `holochain` binaries can't run the scenario zomes — `WT_HOLOCHAIN_PATH` needs a build with `unstable-countersigning`

**Body:**

---

The README documents `WT_HOLOCHAIN_PATH` for pointing Wind Tunnel at your own `holochain` binary,
which is a genuinely useful escape hatch if you aren't set up with Nix. What isn't documented is
that the binary has to be built with particular features, and the failure when it isn't is hard to
read.

Using the released `holochain-0.7.0` binaries, a scenario run fails at module build with:

```
ModuleBuild("agent_activity: Error while importing
  \"env\".\"__hc__accept_countersigning_preflight_request_1\": unknown import")
```

The cause makes sense once you find it: the workspace `Cargo.toml` enables `hdk` with
`unstable-functions` and `unstable-countersigning`, so every scenario's zome WASM declares the
countersigning host function, and the conductor has to provide it. `flake.nix:62` builds Holochain
with exactly those features (`cargoExtraArgs = "--features unstable-functions,unstable-countersigning"`),
so anyone using the Nix workflow never sees this. Because the `hdk` features are set at the
workspace level, this isn't specific to one scenario.

⚠️ The part that cost me the most time: **the `holochain-unstable-*` release asset fails the same
way.** Its name makes it look like the one to reach for, but it doesn't carry the countersigning
host function either. That's visible in the binaries without running anything:

```bash
gh release download holochain-0.7.0 --repo holochain/holochain \
  -p 'holochain-x86_64-unknown-linux-gnu' -p 'holochain-unstable-x86_64-unknown-linux-gnu'
for b in holochain-x86_64-unknown-linux-gnu holochain-unstable-x86_64-unknown-linux-gnu; do
  echo "== $b"
  strings -n 8 "$b" | grep -oE '__hc__(sleep|accept_countersigning_preflight_request)_1' | sort -u
done
```

```
== holochain-x86_64-unknown-linux-gnu
== holochain-unstable-x86_64-unknown-linux-gnu
__hc__sleep_1
```

`__hc__sleep_1` is registered under `#[cfg(feature = "unstable-functions")]` and
`__hc__accept_countersigning_preflight_request_1` under `#[cfg(feature = "unstable-countersigning")]`
(`crates/holochain/src/core/ribosome/real_ribosome.rs:509-516` at tag `holochain-0.7.0`). So the
"unstable" asset carries `unstable-functions` but not `unstable-countersigning` — which is exactly
the one Wind Tunnel's zomes need. Building from source with both features works; it took 13 minutes
on an 8-core box.

A sentence next to the `WT_HOLOCHAIN_PATH` documentation would have saved me a couple of hours —
something like "the binary must be built with `--features unstable-functions,unstable-countersigning`;
the released binaries, including `holochain-unstable-*`, are not." Happy to send that as a PR if
it's welcome.

(If the intent is that `holochain-unstable-*` should carry all unstable features, that'd be one for
the holochain repo rather than here — I've only checked the 0.7.0 assets.)

**Environment:** `wind-tunnel` @ `e4861457`, Holochain 0.7.0, Linux x86_64, not using Nix.
