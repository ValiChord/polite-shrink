<!-- TITLE (paste into the GitHub title field, not the body): -->
<!-- Released `holochain` binaries can't run the scenario zomes — `WT_HOLOCHAIN_PATH` needs a build with `unstable-countersigning` -->

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
