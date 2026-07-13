#!/usr/bin/env bash
# Stage-3 extension campaigns, run in order. Log: results/stage3_run.log
set -u
cd "$(dirname "$0")"
for study in partition_sim byzantine_sim scale_sim race_quantify repair_sim defense_sim fairness_sim; do
    echo "=== $study START $(date -u +%F' '%T) ==="
    if python3 "$study.py"; then
        echo "=== $study DONE $(date -u +%F' '%T) ==="
    else
        echo "=== $study FAILED (exit $?) $(date -u +%F' '%T) ==="
    fi
done
echo "=== STAGE3 ALL DONE $(date -u +%F' '%T) ==="
