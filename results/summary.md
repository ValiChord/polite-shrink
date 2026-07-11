# Arc-controller simulation summary

settle = ticks after disruption until resize rate stays < 1/tick for 300 ticks; floor_min = worst redundancy floor after disruption; exposure = sector-ticks below R; loss = sector-ticks at zero copies (data loss); sync_cost = total sectors fetched+validated.

| scenario | variant | settle | floor_min | exposure | loss | resizes | sync_cost |
|---|---|---|---|---|---|---|---|
| activation | V0 naive | never | 0 | 334435 | 30439 | 44856 | 386689 |
| activation | V1 damped | 1258 | 2 | 12432 | 0 | 2835 | 23235 |
| activation | V2 damped+jitter | never | 0 | 35882 | 178 | 3767 | 31548 |
| activation | V3 full (polite shrink) | 1557 | 5 | 0 | 0 | 2893 | 23011 |
| storm | V0 naive | never | 0 | 277557 | 33314 | 56304 | 487370 |
| storm | V1 damped | 1090 | 0 | 55859 | 457 | 4211 | 40823 |
| storm | V2 damped+jitter | 315 | 3 | 13396 | 0 | 3642 | 21644 |
| storm | V3 full (polite shrink) | 406 | 4 | 7331 | 0 | 3265 | 27782 |
| flashcrowd | V0 naive | never | 0 | 187822 | 16891 | 72679 | 537660 |
| flashcrowd | V1 damped | 0 | 2 | 5704 | 0 | 3375 | 33073 |
| flashcrowd | V2 damped+jitter | never | 2 | 13186 | 0 | 4625 | 46264 |
| flashcrowd | V3 full (polite shrink) | 452 | 5 | 0 | 0 | 3709 | 34013 |
| churn | V0 naive | never | 0 | 245131 | 20766 | 54828 | 424629 |
| churn | V1 damped | never | 1 | 68486 | 0 | 4918 | 42261 |
| churn | V2 damped+jitter | never | 1 | 55219 | 0 | 4639 | 34209 |
| churn | V3 full (polite shrink) | 1157 | 4 | 7426 | 0 | 3990 | 34429 |
