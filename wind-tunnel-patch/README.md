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
