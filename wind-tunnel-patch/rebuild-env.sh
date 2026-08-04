#!/usr/bin/env bash
set -euo pipefail
export PATH="/home/codespace/.cargo/bin:$PATH"
TARGET="${1:-${TMPDIR:-/tmp}/wt-env}"
ENV="$TARGET"
mkdir -p "$ENV"; cd "$ENV"

echo "### [$(date +%T)] STEP 1/4  clone wind-tunnel @ e4861457"
rm -rf wt
git clone --quiet https://github.com/holochain/wind-tunnel wt
git -C wt checkout --quiet e48614573c246a1b468dcd16e94030da97d3f2e0
echo "    at $(git -C wt rev-parse --short HEAD)"

echo "### [$(date +%T)] STEP 2/4  apply the scenario patch"
git -C wt apply --verbose /workspaces/polite-shrink/wind-tunnel-patch/mixed_arc_selection_and_throttle.patch
echo "    get_agents_with_write_behaviour present: $(grep -c get_agents_with_write_behaviour wt/zomes/agent_activity/coordinator/src/lib.rs)"
echo "    WRITE_SLEEP_MS present:                  $(grep -c WRITE_SLEEP_MS wt/scenarios/mixed_arc_get_agent_activity/src/main.rs)"

echo "### [$(date +%T)] STEP 3/4  clone + build holochain 0.7.0 (release, unstable features) -- ~13 min"
rm -rf hc
git clone --quiet --depth 1 --branch holochain-0.7.0 https://github.com/holochain/holochain hc
cd hc
cargo build --release -p holochain --features unstable-functions,unstable-countersigning 2>&1 | tail -25
BIN="$ENV/hc/target/release/holochain"
echo "    built: $("$BIN" --version)"
echo "    countersigning host fn present: $(strings -n 8 "$BIN" | grep -c '__hc__accept_countersigning_preflight_request_1')  (must be >0)"

echo "### [$(date +%T)] STEP 4/4  build the patched scenario -- ~7 min"
cd "$ENV/wt"
cargo build --release -p mixed_arc_get_agent_activity 2>&1 | tail -20
echo "    scenario binary: $(ls -la "$ENV/wt/target/release/mixed_arc_get_agent_activity" | awk '{print $5" bytes"}')"

echo "### [$(date +%T)] DONE"
