#!/usr/bin/env bash
# Orchestrate one arc-sharding Wind Tunnel run: bootstrap+relay, main cohort,
# optional churn cohort (storm), then coverage/floor analysis.
#
#   ./run_experiment.sh settle          # main cohort only
#   ./run_experiment.sh storm           # + churn cohort that joins late and dies abruptly
#
# Everything is env-tunable; every knob is recorded in the run summary by the
# scenario's add_capture_env. Results land in runs/$RUN_ID/.
set -euo pipefail
cd "$(dirname "$0")"

MODE="${1:-settle}" # settle | storm
case "$MODE" in settle | storm) ;; *)
  echo "usage: $0 [settle|storm]" >&2
  exit 2
  ;;
esac

AGENTS="${AGENTS:-12}"
DURATION="${DURATION:-600}"
CHURN_AGENTS="${CHURN_AGENTS:-6}"
CHURN_DELAY="${CHURN_DELAY:-240}"       # seconds into the run when the churn cohort joins
CHURN_DURATION="${CHURN_DURATION:-120}" # how long it lives before dying abruptly
PORT="${PORT:-30744}"
PROFILE="${PROFILE:-release}" # release | debug (debug reuses the dev build for smoke tests)
RUN_ID="${RUN_ID:-arc-$MODE-$(date +%Y%m%d-%H%M%S)}"

# Controller knobs (defaults mirror the sim's headline configuration).
# CLAMP_MIN_PEERS must stay below the total agent count or the controller
# never engages and the run silently measures nothing.
export K2_SHARDING_TARGET_REDUNDANCY="${K2_SHARDING_TARGET_REDUNDANCY:-5}"
export K2_SHARDING_CLAMP_MIN_PEERS="${K2_SHARDING_CLAMP_MIN_PEERS:-8}"
export NUM_MESSAGES="${NUM_MESSAGES:-3}"
export PUBLISH_INTERVAL_MS="${PUBLISH_INTERVAL_MS:-1000}"

if [ "$K2_SHARDING_CLAMP_MIN_PEERS" -ge "$AGENTS" ]; then
  echo "ERROR: K2_SHARDING_CLAMP_MIN_PEERS ($K2_SHARDING_CLAMP_MIN_PEERS) must be" >&2
  echo "below the main-cohort agent count ($AGENTS) or the controller never engages." >&2
  exit 2
fi

RUN_DIR="runs/$RUN_ID"
mkdir -p "$RUN_DIR"
export WT_METRICS_DIR="$PWD/$RUN_DIR/metrics"

FLAGS=()
[ "$PROFILE" = release ] && FLAGS+=(--release)
BIN="target/$PROFILE"

echo "== building ($PROFILE) =="
cargo build --workspace "${FLAGS[@]+"${FLAGS[@]}"}"

echo "== starting bootstrap + iroh relay on 127.0.0.1:$PORT =="
"$BIN/bootstrap_relay" "127.0.0.1:$PORT" >"$RUN_DIR/bootstrap_relay.log" 2>&1 &
SRV_PID=$!
MAIN_PID=""
cleanup() {
  [ -n "$MAIN_PID" ] && kill "$MAIN_PID" 2>/dev/null || true
  kill "$SRV_PID" 2>/dev/null || true
}
trap cleanup EXIT
for _ in $(seq 1 30); do
  grep -q "ready at" "$RUN_DIR/bootstrap_relay.log" 2>/dev/null && break
  sleep 1
done
grep -q "ready at" "$RUN_DIR/bootstrap_relay.log" || {
  echo "bootstrap_relay failed to start:" >&2
  cat "$RUN_DIR/bootstrap_relay.log" >&2
  exit 1
}
URL="http://127.0.0.1:$PORT"

COMMON_ARGS=(
  --bootstrap-server-url "$URL" --relay-url "$URL"
  --run-id "$RUN_ID" --reporter influx-file --no-progress
)

echo "== main cohort: $AGENTS agents, ${DURATION}s (run id $RUN_ID) =="
"$BIN/kitsune_arc_sharding" "${COMMON_ARGS[@]}" \
  --agents "$AGENTS" --duration "$DURATION" \
  >"$RUN_DIR/main_cohort.log" 2>&1 &
MAIN_PID=$!

if [ "$MODE" = storm ]; then
  echo "== storm: churn cohort of $CHURN_AGENTS joins at t+${CHURN_DELAY}s, dies at t+$((CHURN_DELAY + CHURN_DURATION))s =="
  sleep "$CHURN_DELAY"
  # Same --run-id = same space. The cohort's exit is abrupt from the
  # network's point of view: no leave, no unregister — survivors must
  # detect the loss and react (storm brake, regrow, handoff).
  "$BIN/kitsune_arc_sharding" "${COMMON_ARGS[@]}" \
    --agents "$CHURN_AGENTS" --duration "$CHURN_DURATION" \
    >"$RUN_DIR/churn_cohort.log" 2>&1 || {
    echo "churn cohort exited non-zero (log: $RUN_DIR/churn_cohort.log)" >&2
  }
  echo "== churn cohort gone; main cohort continues =="
fi

wait "$MAIN_PID"
MAIN_PID=""
kill "$SRV_PID" 2>/dev/null || true
trap - EXIT

echo "== analysing =="
python3 analysis/analyze_run.py "$WT_METRICS_DIR" \
  --redundancy "$K2_SHARDING_TARGET_REDUNDANCY" \
  --out "$RUN_DIR" | tee "$RUN_DIR/analysis.txt"

echo
echo "run artifacts: $RUN_DIR/"
