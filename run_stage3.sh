#!/usr/bin/env bash
# Stage-3 extension campaigns, run in order. Log: results/stage3_run.log
#
# Roughly 3 hours on 8 cores: ~80 min for the original nine studies, plus ~100
# min for the detection-side group added 2026-08-07 (mz_probe alone is ~50 min).
# Every study takes --seeds / --procs if you need to trim; bare invocation
# reproduces the published configuration.
set -u
cd "$(dirname "$0")"

# Reduction guards first: each asserts an extension model is byte-identical to
# the model it extends when its new parameter is off. A failure here means a
# modelling bug, and every result below it is suspect -- so run them at the top
# where the failure is visible rather than buried mid-log.
for guard in validate_decoupled validate_message_loss validate_rolling_upgrade \
             validate_detector_error validate_hetero_detector; do
    [ -f "$guard.py" ] || continue
    echo "=== GUARD $guard START $(date -u +%F' '%T) ==="
    if python3 "$guard.py"; then
        echo "=== GUARD $guard PASS $(date -u +%F' '%T) ==="
    else
        echo "=== GUARD $guard FAILED (exit $?) $(date -u +%F' '%T) ==="
    fi
done

# The original Stage-3 battery.
for study in partition_sim byzantine_sim scale_sim race_quantify repair_sim \
             defense_sim fairness_sim verified_coverage_sim partial_liar_sim; do
    echo "=== $study START $(date -u +%F' '%T) ==="
    if python3 "$study.py"; then
        echo "=== $study DONE $(date -u +%F' '%T) ==="
    else
        echo "=== $study FAILED (exit $?) $(date -u +%F' '%T) ==="
    fi
done

# Detection-side studies (REPORT_mz_decomposition.md; REPORT_stage3.md §11
# amendment and constraint 6b). Order matters: mz_probe collects the decisions
# mz_attribution ranks, and diag_detector_bias explains the curve
# detector_error_sweep produces.
for study in mz_probe mz_attribution detector_error_sweep diag_detector_bias \
             hetero_detector_sweep; do
    echo "=== $study START $(date -u +%F' '%T) ==="
    if python3 "$study.py"; then
        echo "=== $study DONE $(date -u +%F' '%T) ==="
    else
        echo "=== $study FAILED (exit $?) $(date -u +%F' '%T) ==="
    fi
done

echo "=== STAGE3 ALL DONE $(date -u +%F' '%T) ==="
