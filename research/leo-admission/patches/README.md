# Patch for topeuph-ai/kitsune2 `feat/sharding-v7` (base `0cdcd8e`)

Apply: `git am research/leo-admission/patches/0001-kitsune2-v7-audit-items.patch`
(could not be pushed to the fork from the session that made it: the Claude GitHub App
is not installed for that organisation).

What it changes, after re-checking each reported item against source and `REPORT_v7.md`:

| Item | Verdict | Change |
|---|---|---|
| `grow_recheck` counts only lower-ID growers | **Not a bug.** Documented V7 design; the ceiling is deliberately soft because a hard one refused repairs | None |
| Storm brake cancels pending shrinks without telling peers | Real, liveness only (peers kept the ghost up to 2·wait) | Brake sends the withdrawal, under the same conditions as a stand-down |
| Intent expiry is the sender's absolute wall-clock time | Real, and unsafe in one direction: a receiver clock ahead of the sender's by more than the margin dropped a leaving node's intent on arrival | New `ttl_us` field; receiver counts the intent that long from arrival; sender expiry kept only as the withdrawal identity; lifetime capped at 1 h; zero from old senders falls back to the absolute expiry |
| Test `view_delay` skipped `live_grows` | Real test-coverage gap | Delay now covers grow intents |

Please run `cargo make proto`: the generated file was edited by hand to add `ttl_us`.

## Test status (2026-10-28, local)

- `cargo test -p kitsune2_gossip --features sharding --lib sharding`: 44 passed. Two new tests added; the relative-TTL one was seen to fail with the fix disabled.
- Integration: `sharding_race`, `sharding_stale`, `sharding_storm`, `sharding_upgrade`, `sharding_alongside`, `sharding_cascade` pass; `sharding_v7::growth_repairs_deaths_with_and_without_coordination` passes.
- **`sharding_v7::pinned_node_keeps_everything_while_others_shard` is intermittent** ("a sector fell to {min}", `tests/sharding_v7.rs:371`, the floor assertion). It also failed on the unpatched base `0cdcd8e` (at least 1 of 4 runs); with the patch it failed 2 of 4 runs and once in a full-suite run. Samples this small cannot show the patch is neutral. Treat it as a pre-existing floor dip worth its own investigation, and rerun it many times before merging.
- Not covered: the storm-brake withdrawal has no dedicated test (only the storm suite exercises that path); the ignored slow sweeps and the chaos soak were not run.
