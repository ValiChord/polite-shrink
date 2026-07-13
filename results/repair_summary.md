# §6.2 repair-rule study

V4 = V3 + expanding-ring repair (react to a hole in the level+g ancestor block after grow_need + (g-1)*2*lag).

## Sparse deadlock (kill to k survivors at t=1500; clustered = §6.2 geometry, survivors' homes in one half-ring)

| case | clamp | variant | recovered | stuck | median rec (ticks) | mean post-kill sync | worst floor |
|---|---|---|---|---|---|---|---|
| random-5 | 0 | V3 full (polite shrink) | 30/30 | 0 | 244.5 | 2444 | 0 |
| random-5 | 0 | V4 polite+repair | 30/30 | 0 | 245.0 | 2419 | 0 |
| random-5 | 25 | V3 full (polite shrink) | 30/30 | 0 | 83.5 | 2444 | 0 |
| random-5 | 25 | V4 polite+repair | 30/30 | 0 | 86.0 | 2419 | 0 |
| random-15 | 0 | V3 full (polite shrink) | 30/30 | 0 | 128.0 | 8155 | 0 |
| random-15 | 0 | V4 polite+repair | 30/30 | 0 | 128.5 | 7252 | 0 |
| random-15 | 25 | V3 full (polite shrink) | 30/30 | 0 | 63.0 | 7338 | 0 |
| random-15 | 25 | V4 polite+repair | 30/30 | 0 | 66.5 | 7408 | 0 |
| clustered-15 | 0 | V3 full (polite shrink) | 29/30 | 1 | 129.0 | 3825 | 0 |
| clustered-15 | 0 | V4 polite+repair | 30/30 | 0 | 130.0 | 3704 | 0 |
| clustered-15 | 25 | V3 full (polite shrink) | 30/30 | 0 | 72.0 | 7326 | 0 |
| clustered-15 | 25 | V4 polite+repair | 30/30 | 0 | 72.0 | 7219 | 0 |
| sparse-8@R2 | 0 | V3 full (polite shrink) | 85/90 | 5 | 39.0 | 1191 | 0 |
| sparse-8@R2 | 0 | V4 polite+repair | 90/90 | 0 | 36.5 | 1246 | 0 |
| sparse-8@R2 | 25 | V3 full (polite shrink) | 90/90 | 0 | 20.0 | 0 | 5 |
| sparse-8@R2 | 25 | V4 polite+repair | 90/90 | 0 | 20.0 | 0 | 5 |

## Dense overshoot probe (all holders of one sector killed at equilibrium; growers net of a matched no-kill control)

| variant | growers over baseline (mean) | (max) | median recovery | unrecovered | mean post-kill sync |
|---|---|---|---|---|---|
| V3 full (polite shrink) | 113.9 | 195 | 62.0 | 0 | 14680 |
| V4 polite+repair | 100.4 | 195 | 53.0 | 0 | 13420 |

## Regression battery (Stage-1 scenarios; V4 R=6 rows = the explicit-knob margin buy-back)

| scenario | seed | variant | R | loss | floor_min | exposure | resizes | sync | repair grows |
|---|---|---|---|---|---|---|---|---|---|
| activation | 42 | V3 full (polite shrink) | 5 | 0 | 5 | 0 | 2893 | 23011 | 0 |
| activation | 42 | V4 polite+repair | 5 | 0 | 5 | 0 | 2090 | 8191 | 25 |
| storm | 42 | V3 full (polite shrink) | 5 | 0 | 4 | 7331 | 3265 | 27782 | 0 |
| storm | 42 | V4 polite+repair | 5 | 0 | 2 | 21226 | 2770 | 11674 | 35 |
| storm | 42 | V4 polite+repair | 6 | 0 | 4 | 19815 | 2997 | 16757 | 39 |
| storm | 7 | V3 full (polite shrink) | 5 | 0 | 2 | 13839 | 2968 | 20692 | 0 |
| storm | 7 | V4 polite+repair | 5 | 0 | 5 | 0 | 3280 | 23576 | 98 |
| storm | 7 | V4 polite+repair | 6 | 0 | 5 | 7644 | 3632 | 33584 | 57 |
| storm | 99 | V3 full (polite shrink) | 5 | 0 | 4 | 7818 | 2564 | 9796 | 0 |
| storm | 99 | V4 polite+repair | 5 | 0 | 5 | 0 | 3244 | 26374 | 28 |
| storm | 99 | V4 polite+repair | 6 | 0 | 6 | 0 | 2577 | 15065 | 49 |
| storm | 1234 | V3 full (polite shrink) | 5 | 0 | 4 | 1877 | 3238 | 22963 | 0 |
| storm | 1234 | V4 polite+repair | 5 | 0 | 3 | 7290 | 3307 | 19701 | 102 |
| storm | 1234 | V4 polite+repair | 6 | 0 | 6 | 0 | 2402 | 9993 | 43 |
| flashcrowd | 42 | V3 full (polite shrink) | 5 | 0 | 5 | 0 | 3709 | 34013 | 0 |
| flashcrowd | 42 | V4 polite+repair | 5 | 0 | 5 | 0 | 2093 | 8191 | 25 |
| churn | 42 | V3 full (polite shrink) | 5 | 0 | 4 | 7426 | 3990 | 34429 | 0 |
| churn | 42 | V4 polite+repair | 5 | 0 | 3 | 24611 | 3700 | 24380 | 91 |
| churn | 42 | V4 polite+repair | 6 | 0 | 4 | 16195 | 4229 | 37244 | 79 |
| churn | 7 | V3 full (polite shrink) | 5 | 0 | 4 | 12792 | 3918 | 35664 | 0 |
| churn | 7 | V4 polite+repair | 5 | 0 | 4 | 3474 | 3182 | 18909 | 116 |
| churn | 7 | V4 polite+repair | 6 | 0 | 4 | 15094 | 4692 | 39819 | 125 |
| churn | 99 | V3 full (polite shrink) | 5 | 0 | 4 | 12548 | 3662 | 22060 | 0 |
| churn | 99 | V4 polite+repair | 5 | 0 | 5 | 0 | 3515 | 27988 | 33 |
| churn | 99 | V4 polite+repair | 6 | 0 | 5 | 10828 | 3460 | 22156 | 68 |
| churn | 1234 | V3 full (polite shrink) | 5 | 0 | 4 | 1579 | 3785 | 22990 | 0 |
| churn | 1234 | V4 polite+repair | 5 | 0 | 4 | 10514 | 3930 | 25390 | 74 |
| churn | 1234 | V4 polite+repair | 6 | 0 | 5 | 14067 | 3531 | 17341 | 147 |
