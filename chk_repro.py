"""
chk_repro — is the mz_probe pipeline sensitive to the numpy version?

REPRODUCE.md pins numpy 2.5.1 for byte-reproducible results. The MZ studies
(`mz_probe.py`, `mz_attribution.py`, `detector_error_sim.py`) were developed on
a machine that could not install the pinned *Python* (3.12.1), so the question
is how much of the pin actually matters.

This prints a fingerprint of one run's collected records. Run it under two numpy
versions and compare: identical output means the simulation and the record
collection are insensitive across that range, and only the Python leg of the pin
remains unverified.

Result at the time of writing: **byte-identical between numpy 2.3.5 and 2.5.1**
at both `death_lag` settings. Cited in REPORT_mz_decomposition.md, Limitations.

Usage:  python3 chk_repro.py
"""

from __future__ import annotations

import hashlib

import numpy as np

from mz_probe import run_sim


def main():
    print("numpy", np.__version__)
    print(f"{'death_lag':>10} {'records':>8}  {'md5(y)':>16}  {'md5(features)':>16}"
          f"  {'unsafe':>6}")
    for dl in ("coupled", 96):
        r = run_sim((dl, 1.0, 900000))
        print(f"{str(dl):>10} {len(r['y']):8d}  "
              f"{hashlib.md5(r['y'].tobytes()).hexdigest()[:16]}  "
              f"{hashlib.md5(r['cur'].tobytes()).hexdigest()[:16]}  "
              f"{int(r['unsafe'].sum()):6d}")


if __name__ == "__main__":
    main()
