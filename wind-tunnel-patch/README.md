# wind-tunnel scenario patch + results

Artefacts from the 2026-08-03 session, kept here because the working copies lived in
`/tmp` and do not survive a Codespace restart.

| file | what it is |
|---|---|
| `mixed_arc_selection_and_throttle.patch` | The fix, against `holochain/wind-tunnel` @ `e4861457`. Apply with `git apply` from the repo root. |
| `RESULTS_write_rate_sweep.txt` | Raw per-run output for all three write rates. **Quote numbers from here, not from memory.** |
| `visibility.py` | Computes visibility = observed seq ÷ (entries + 5). The `+5` is chain overhead — see the docstring; getting this wrong produced >100% figures. |
| `analyse_reads.py` | Which write peer each reader selected, and the arc of that peer. The `(?<!write_)` lookbehind is load-bearing: without it every reader identity is wrong. |
| `rebuild-env.sh` | Rebuilds the whole environment from scratch — clone + patch + both builds — and **verifies each step** rather than assuming. Measured 2026-08-04: ~20 min total (holochain 13m35s, scenario 5m58s), 4.5 GB. Usage: `./rebuild-env.sh [target-dir]`, defaults to `/tmp/wt-env`. |

## What the patch changes

1. `get_agents_with_write_behaviour` — returns all announced writers in a stable order.
2. Readers wait for the expected count before selecting, with a **bounded fallback**
   (`SELECTION_TIMEOUT_S`, default 90) so an announcement that never arrives cannot stall
   selection entirely.
3. Deterministic assignment by `ctx.agent_index() % n` — guarantees every writer is covered.
4. New metric `write_peers_visible_at_selection`, tagged `complete: true|false`.
5. Optional write throttle `WRITE_SLEEP_MS`, **default 0** so unmodified behaviour is preserved.

## Verification run — 2026-08-04, after the move to `/workspaces/wt-env`

One 300 s run at the documented local shape, default (unthrottled) write rate, to prove the
relocated environment works. It does, and it replicates the 08-03 results.

```
app_call_zome                     28,953 operations
entry_created_count                7,205 data points
write_peers_visible_at_selection   3 x  value: 3, complete: true
panics / happ-not-found            0
```

**The fix is doing its job.** Three readers drew three *different* peers, one each, including the
zero-arc author — against the stock behaviour where the candidate set is always exactly 1 and all
three readers land on the same full-arc peer.

| author | authored | max seq seen | visibility |
|---|---|---|---|
| full-arc | 2047 | 2043 | 99.6% |
| full-arc | 2028 | 1862 | 91.6% |
| ZERO-ARC | 3130 | 5 | **0.2%** |

Replicates all three 0 ms signals: zero-arc visibility collapses (0.2%, matching one of the two
08-03 values exactly), full-arc stays in the 85.2–99.6% band, and the zero-arc writer out-authors
both full-arc writers.

⚠️ **The 0.2% is LOAD, not a property of zero-arc nodes.** This run had no throttle. That is the
retracted §7.9 claim and it stays retracted — see `PLAN_0.7_conductor_run.md` §7.10.

⚠️ **Not posted upstream.** It adds a 4th 0 ms datapoint to a filed issue whose table already says
what it says, and the maintainers have asked for restraint on AI-assisted contributions. Recorded
here, not in the thread.

🆕 **Moving a built tree breaks the scenario binary — rebuild in place afterwards.** `happ_path!`
resolves via `env!("CARGO_MANIFEST_DIR")`, baked at compile time, with a nix-store fallback that
does not match this layout. After the `/tmp` -> `/workspaces/wt-env` move, both lookups failed and
the binary would have panicked at agent setup. ⚠️ **`--version` and `--help` both still worked**,
so a liveness check on the binary proves nothing here. A 49 s in-place rebuild fixed it and
re-packed the DNA/hApp, which also removes any stale-pack doubt. `rebuild-env.sh` builds in place
and never hits this.

## Node-count ceiling on this box — measured 2026-08-04

`clamp_min_peers` defaults to **25**, so a real polite-shrink test needs >=25 conductors. Whether
this machine could host that was unknown. It can.

8 cores, 31 GB RAM. Each run 120 s, proportional behaviour mix, `mixed_arc_get_agent_activity`.

| agents | installed | signing-cred avg | zome calls | peak RSS | peak load | failures |
|---|---|---|---|---|---|---|
| 6 (300 s) | 6/6 | 10,495 ms | 28,953 | — | — | 0 |
| 12 | 12/12 | 18,637 ms | 16,847 | 3.7 GB | 38.5 | 0 |
| 20 | 20/20 | 28,803 ms | 16,419 | 6.5 GB | 66.0 | 0 |
| **25** | **25/25** | 39,234 ms | 14,014 | **7.9 GB** | **93.8** | **0** |

**Memory is not the constraint** — 7.9 GB of 31 GB, ~316 MB per conductor, headroom past 25.
**CPU is** — load 93.8 on 8 cores is ~12x oversubscribed.

🔴 **This splits what may and may not be claimed from a conductor-level run here.**

- ✅ **Structural claims are viable.** *Does the controller engage? Do arcs move? Does redundancy
  ever drop below the floor?* Those are discrete properties; a contended machine still answers them,
  and they are what the TLA+ proof and the simulator sweeps are about.
- ❌ **Performance claims are not.** *Does load fall, and by how much?* At load 93.8 that measures
  this Codespace. Publishing a throughput or latency number from here would repeat exactly the error
  wind-tunnel#679 section 2 documents — and that this repo retracted in §7.10.

🆕 **The throttle written for the upstream issue is what makes a 25-node run viable here.**
`WRITE_SLEEP_MS` cuts write pressure so the box keeps up; the 250 ms sweep resolved cleanly where
0 ms did not. The fix for upstream's scenario is directly reusable to keep our own test honest.

⚠️ **Two open problems the ceiling test does not solve.** These runs were 120 s, and arc convergence
plus shrink decisions likely need far longer windows. And the measurement question is unchanged: arc
sizes look obtainable, per-op redundancy does not.

## Rebuilding the environment

Everything below is gone after a restart and takes ~15 min:

```bash
git clone https://github.com/holochain/wind-tunnel && cd wind-tunnel
git checkout e48614573c246a1b468dcd16e94030da97d3f2e0
git apply /workspaces/polite-shrink/wind-tunnel-patch/mixed_arc_selection_and_throttle.patch
```

⚠️ **The released `holochain` binaries cannot run these zomes** — including the one named
`holochain-unstable-*`. Build from source (13 min):

```bash
git clone --depth 1 --branch holochain-0.7.0 https://github.com/holochain/holochain
cargo build --release -p holochain --features unstable-functions,unstable-countersigning
```

✅ **The environment now lives at `/workspaces/wt-env/`** — `hc/` (Holochain 0.7.0 source build)
and `wt/` (wind-tunnel @ `e4861457` + this patch). It is on the persistent volume, so it survives a
Codespace restart; only a full rebuild loses it, and `rebuild-env.sh` handles that.

Moved there 2026-08-04 after clearing ~26.8 GB of cargo `target/` dirs from `/workspaces/ValiChord`
(which had left just 3.4 GB free of 63 GB). Verified after the move: both binaries run from the new
path, the countersigning symbol is still present, and both are byte-identical to the originals.

⚠️ **Cargo bakes absolute paths into its fingerprints**, so the first `cargo build` inside
`/workspaces/wt-env` after the move may rebuild more than a true incremental would. The already-built
binaries are unaffected.

⚠️ **ValiChord's Rust builds are now cold** as a result of that clearing — WASM, sweettest,
wind-tunnel and the tripwire `target-test/` all rebuild from scratch on next use. Nothing was lost:
`valichord/workdir/*.dna` and `*.happ` live outside `target/` and were verified intact afterwards.

🆕 **The build's own positive control.** `rebuild-env.sh` greps the binary it just built for
`__hc__accept_countersigning_preflight_request_1` and fails loudly if absent. That matters because
wind-tunnel#678 rests on that symbol being **absent** from the released binaries — an absence is
weak evidence unless the same test is shown to detect the symbol when it *is* there. It does: our
source build reports 1, both release assets report 0.

Then, per run: `WT_METRICS_DIR` is **mandatory**, `WT_HOLOCHAIN_PATH` points at that binary,
and `--reporter in-memory-with-custom-metrics` is **required** or none of the custom metrics
are recorded. ⚠️ A totally failed run still **exits 0** — check for recorded operations, never `$?`.
