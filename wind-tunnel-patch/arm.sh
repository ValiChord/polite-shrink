#!/usr/bin/env bash
# Switch the holochain build between the STOCK conductor and the polite-shrink
# fork build, and keep a named binary for each so neither can be overwritten by
# building the other. (That mistake was made once, 2026-08-04.)
set -euo pipefail
export PATH="/home/codespace/.cargo/bin:$PATH"
HC=/workspaces/wt-env/hc
case "${1:-}" in
  stock)
    cp "$HC/Cargo.toml.orig" "$HC/Cargo.toml"
    git -C "$HC" checkout crates/holochain/Cargo.toml
    OUT=/workspaces/wt-env/holochain-stock ;;
  shrink)
    cp "$HC/Cargo.toml.polite-shrink" "$HC/Cargo.toml"
    cp "$HC/crates/holochain/Cargo.toml.polite-shrink" "$HC/crates/holochain/Cargo.toml"
    OUT=/workspaces/wt-env/holochain-polite-shrink ;;
  *) echo "usage: arm.sh stock|shrink"; exit 1 ;;
esac
cd "$HC"
cargo build --release -p holochain --features unstable-functions,unstable-countersigning 2>&1 | tail -5
cp target/release/holochain "$OUT"
echo "built $1 -> $OUT"
echo "  version:       $("$OUT" --version)"
echo "  K2Sharding:    $(strings -n 6 "$OUT" | grep -c K2Sharding)   (stock must be 0, shrink >0)"
echo "  countersigning:$(strings -n 8 "$OUT" | grep -c '__hc__accept_countersigning_preflight_request_1')   (both must be 1)"
