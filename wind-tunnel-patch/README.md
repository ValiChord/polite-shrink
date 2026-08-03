# wind-tunnel scenario patch + results

Artefacts from the 2026-08-03 session, kept here because the working copies lived in
`/tmp` and do not survive a Codespace restart.

| file | what it is |
|---|---|
| `mixed_arc_selection_and_throttle.patch` | The fix, against `holochain/wind-tunnel` @ `e4861457`. Apply with `git apply` from the repo root. |
| `RESULTS_write_rate_sweep.txt` | Raw per-run output for all three write rates. **Quote numbers from here, not from memory.** |
| `visibility.py` | Computes visibility = observed seq ÷ (entries + 5). The `+5` is chain overhead — see the docstring; getting this wrong produced >100% figures. |
| `analyse_reads.py` | Which write peer each reader selected, and the arc of that peer. The `(?<!write_)` lookbehind is load-bearing: without it every reader identity is wrong. |

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

Then, per run: `WT_METRICS_DIR` is **mandatory**, `WT_HOLOCHAIN_PATH` points at that binary,
and `--reporter in-memory-with-custom-metrics` is **required** or none of the custom metrics
are recorded. ⚠️ A totally failed run still **exits 0** — check for recorded operations, never `$?`.
