#!/usr/bin/env bash
# Self-relaunching driver for the robustness sweep. sweep.py checkpoints every
# completed cell and resumes on restart, so if the environment kills the run
# (this box SIGTERMs long jobs ~1.5h in), we just relaunch and continue.
cd "$(dirname "$0")"
SEEDS=312

for attempt in $(seq 1 30); do
  remaining=$(python3 -c "
import sweep
done = sweep.load_cells()
target = {(k, sweep.SEED_BASE + s) for (k, _, _, _) in sweep.SCENARIOS for s in range($SEEDS)}
print(len(target - set(done)))
")
  if [ "$remaining" -eq 0 ]; then
    echo "COMPLETE after $((attempt-1)) relaunch(es): all cells done"
    break
  fi
  echo "=== attempt $attempt: $remaining cells remaining, launching sweep ==="
  python3 -u sweep.py --seeds "$SEEDS" || echo "sweep exited non-zero (attempt $attempt)"
  sleep 3
done
echo "=== driver finished ==="
