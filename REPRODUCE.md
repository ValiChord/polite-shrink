# Reproducing this study

The point of this package is that you don't have to trust our numbers — you can
regenerate them. Results are **byte-deterministic** given the pinned environment,
so an independent run should match the tables below exactly.

## Environment

- **Python 3.12.1** (any CPython 3.11–3.12 should match; the RNG streams and the
  one set-iteration site are pinned for portability — see the `sorted()` note in
  `arc_sim.make_world`).
- Dependencies pinned in `requirements.txt`: `numpy==2.5.1`, `matplotlib==3.11.0`.
  numpy commits to stable `default_rng` streams across versions, so nearby numpy
  releases should also reproduce; pin exactly if you want a guaranteed match.

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
bash run_all.sh          # ~17 min total on 2 cores
```

Or piecemeal:

```bash
python3 check_determinism.py   # must print ALL DETERMINISTIC (~30 s)
python3 run_experiments.py     # scenario study -> results/*.png + summary.md (~1 min)
python3 check_seeds.py         # seed-robustness spot check
python3 adversary.py           # learning adversary -> results/adversary.* (~15 min)
```

## Expected results (confirm you match these)

### Scenario study (seed 42) — `results/summary.md`

`loss` = sector-ticks at zero copies (unrecoverable data loss). The invariant to
check: **V0 loses data in every scenario; V3 loses none.**

| scenario | variant | settle | worst floor | loss |
|---|---|---|---|---|
| activation | V0 naive | never | 0 | 30,439 |
| activation | V3 full  | 1557 | 5 | **0** |
| storm | V0 naive | never | 0 | 33,314 |
| storm | V3 full  | 406 | 4 | **0** |
| flashcrowd | V0 naive | never | 0 | 16,891 |
| flashcrowd | V3 full  | 452 | 5 | **0** |
| churn | V0 naive | never | 0 | 20,766 |
| churn | V3 full  | 1157 | 4 | **0** |

(V1/V2 rows are in the full `summary.md`; V1 is clean in most scenarios, V2
leaks small amounts under continuous churn.)

### Seed robustness — `check_seeds.py` (seeds 7 / 99 / 1234)

Invariant: **V0 loses data every run; V3 loses none.** V2 shows data loss in 3 of
4 storm runs (the jitter-without-handoff finding).

### Learning adversary — `adversary.py`

Evolutionary search, budget = 60 targeted kills (= the storm's 30%), search seed
2026. The headline invariant:

| variant | random storm loss | evolved-attack loss | distinct sectors lost |
|---|---|---|---|
| V1 damped | 391 | 5,994 | 134 |
| V2 damped+jitter | 0 | 2,938 | 23 |
| **V3 full (polite shrink)** | 0 | **0** | **0** |

If your run reproduces "adversary breaks V1 and V2 but scores 0 against V3 across
all 20 generations," you've reproduced the central result.

## If your numbers differ

- **Determinism check fails** → environment issue (interpreter or numpy stream);
  pin `requirements.txt` exactly and use CPython.
- **Scenario numbers differ but determinism passes** → different numpy version
  with a changed stream; the *ordering* of variants (V0 worst, V3 best) should
  still hold even if absolute counts shift.
- **Adversary numbers differ** → the search is stochastic in wall-clock only, not
  in result (fixed seed 2026); a difference means a code or environment change.

## What this does and does not show

This simulates control-loop **dynamics**, not kitsune2. See `README.md` →
"Honest limitations": full peer visibility, one gossip lag per viewer (not per
pair), honest agents, no eclipse/lying adversaries, abstract ticks. Reproducing
these numbers confirms *our claims about this model*; it does not by itself
establish behaviour on a real network. That is what a Stage-2 kitsune2 fork would
test.
