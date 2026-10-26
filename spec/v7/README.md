# V7 models: a floor and a ceiling on stale views

Work in progress (October 2026). Not submitted anywhere.

- `StaleCap.tla` — the ceiling alone (at most C active). Written by Ceri John with
  other AI assistants; checked here unchanged. Its rule names predate the
  current naming: its "patient_k" is now the *multiwait* option.
  **Finding:** StaleCap with ceiling C is StaleShrink with floor R = N − C read
  through the complement ("active" = "has left"): TLC gives identical state
  counts (16,848 and 43,348 at N = 4).
- `StaleBand.tla` — V7: the floor (V6) and the ceiling (StaleCap) at once, with
  nodes joining and leaving concurrently. Each check counts the cautious way for
  its own bound.
- `StaleBandNet.tla` — StaleBand plus one network split and node deaths with a
  detection delay, and the recent-contact rule (silent nodes count as gone for
  the floor, as possibly present for the ceiling).

The `*.cfg` files are the configurations checked; results are recorded in
`results/v7_tla.md`.
