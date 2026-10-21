#!/usr/bin/env bash
# One-command reproduction of the full arc-controller study.
# Expected wall-clock: scenario study ~1 min, determinism check ~30 s,
# adversary search ~15 min (2 cores). See REPRODUCE.md for expected numbers.
set -euo pipefail
cd "$(dirname "$0")/.."   # run from the repository root; scripts are in sim/

echo "== 0. environment =="
python3 --version
python3 -c "import numpy, matplotlib; print('numpy', numpy.__version__, '| matplotlib', matplotlib.__version__)"

echo "== 1. determinism guard (must print ALL DETERMINISTIC) =="
python3 sim/check_determinism.py

echo "== 2. scenario study -> results/*.png, results/summary.md =="
python3 sim/run_experiments.py

echo "== 3. seed-robustness spot check =="
python3 sim/check_seeds.py

echo "== 4. learning-adversary search -> results/adversary.{json,png} =="
python3 sim/adversary.py

echo "== done. Compare results/summary.md and the adversary summary against REPRODUCE.md =="
