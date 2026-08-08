#!/usr/bin/env bash
# Stage-3 extension campaigns, run in order. Log: results/stage3_run.log
#
# Picks a working Python 3 itself (PYTHON=... to override) and reports whether
# the environment matches the REPRODUCE.md pins before running anything.
#
# Roughly 3 hours on 8 cores: ~80 min for the original nine studies, plus ~100
# min for the detection-side group added 2026-08-07 (mz_probe alone is ~50 min).
# Every study takes --seeds / --procs if you need to trim; bare invocation
# reproduces the published configuration.
set -u
cd "$(dirname "$0")"

# ---------------------------------------------------------------- interpreter
# Resolve a working Python 3 rather than assuming `python3` is on PATH and
# usable. On Windows `python3` is commonly the Microsoft Store shim, which is on
# PATH, is not Python, and exits 49 — every study then dies instantly with
# "Python was not found". Candidates are therefore *executed*, not just located.
#
# Override with PYTHON=... to point at a virtualenv holding the pinned versions:
#   PYTHON=/path/to/venv/bin/python ./run_stage3.sh
PY=""
for cand in ${PYTHON:-} python3 python py; do
    [ -n "$cand" ] || continue
    if command -v "$cand" >/dev/null 2>&1 \
       && "$cand" -c 'import sys; sys.exit(0 if sys.version_info[0] == 3 else 1)' \
            >/dev/null 2>&1; then
        PY="$cand"; break
    fi
done
if [ -z "$PY" ]; then
    echo "FATAL: no working Python 3 found (tried \$PYTHON, python3, python, py)." >&2
    echo "       Set PYTHON=/path/to/python and re-run." >&2
    exit 1
fi

# Fail loudly on a missing dependency instead of watching every study die one by
# one, and say plainly when the environment is off-pin: results generated here
# are still useful, but they are not the byte-reproducible ones REPRODUCE.md
# describes, and the log should record which was which.
if ! "$PY" - <<'PYCHK'
import sys, re, pathlib
try:
    import numpy, matplotlib
except ImportError as e:
    sys.exit(f"FATAL: missing dependency: {e.name}. pip install -r requirements.txt")
have = {"numpy": numpy.__version__, "matplotlib": matplotlib.__version__}
want = dict(re.findall(r"^([A-Za-z0-9_-]+)==([\d.]+)\s*$",
                       pathlib.Path("requirements.txt").read_text(), re.M))
print(f"interpreter: {sys.executable}")
print(f"python {sys.version.split()[0]}  " +
      "  ".join(f"{k} {v}" for k, v in have.items()))
off = [f"{k} {have[k]} != pinned {want[k]}" for k in want if have.get(k) != want[k]]
pin_py = "3.12.1"
if sys.version.split()[0] != pin_py:
    off.append(f"python {sys.version.split()[0]} != pinned {pin_py}")
if off:
    print("WARNING: environment is OFF-PIN -- " + "; ".join(off))
    print("         Results will be indicative, not byte-reproducible.")
else:
    print("environment matches REPRODUCE.md pins exactly.")
PYCHK
then
    exit 1
fi
echo

# Reduction guards first: each asserts an extension model is byte-identical to
# the model it extends when its new parameter is off. A failure here means a
# modelling bug, and every result below it is suspect -- so run them at the top
# where the failure is visible rather than buried mid-log.
for guard in validate_decoupled validate_message_loss validate_rolling_upgrade \
             validate_detector_error validate_hetero_detector; do
    [ -f "$guard.py" ] || continue
    echo "=== GUARD $guard START $(date -u +%F' '%T) ==="
    if "$PY" "$guard.py"; then
        echo "=== GUARD $guard PASS $(date -u +%F' '%T) ==="
    else
        echo "=== GUARD $guard FAILED (exit $?) $(date -u +%F' '%T) ==="
    fi
done

# The original Stage-3 battery.
for study in partition_sim byzantine_sim scale_sim race_quantify repair_sim \
             defense_sim fairness_sim verified_coverage_sim partial_liar_sim; do
    echo "=== $study START $(date -u +%F' '%T) ==="
    if "$PY" "$study.py"; then
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
    if "$PY" "$study.py"; then
        echo "=== $study DONE $(date -u +%F' '%T) ==="
    else
        echo "=== $study FAILED (exit $?) $(date -u +%F' '%T) ==="
    fi
done

echo "=== STAGE3 ALL DONE $(date -u +%F' '%T) ==="
