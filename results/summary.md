# Arc-controller simulation summary

settle = ticks after disruption until resize rate stays < 1/tick for 300 ticks; floor_min = worst redundancy floor after disruption; exposure = sector-ticks below R; loss = sector-ticks at zero copies (data loss); sync_cost = total sectors fetched+validated.

All coverage columns are measured on **declared** arcs — what a reader can route to. `held_loss` is the same count over bytes actually on disk, and differs from `loss` only for the AgentInfo-only encoding (V5), where announcing means un-declaring a sector you are still serving. `cancels` = intents that stood down at the re-check; `publishes` = AgentInfo re-publishes that encoding costs.

| scenario | variant | settle | floor_min | exposure | loss | held_loss | resizes | sync_cost | cancels | publishes |
|---|---|---|---|---|---|---|---|---|---|---|
| activation | V0 naive | never | 0 | 334435 | 30439 | 30439 | 44856 | 386689 | 0 | 0 |
| activation | V1 damped | 1258 | 2 | 12432 | 0 | 0 | 2835 | 23235 | 0 | 0 |
| activation | V2 damped+jitter | never | 0 | 35882 | 178 | 178 | 3767 | 31548 | 0 | 0 |
| activation | V3 full (polite shrink) | 1557 | 5 | 0 | 0 | 0 | 2893 | 23011 | 78 | 0 |
| activation | V5 polite (AgentInfo-only) | 758 | 0 | 7167 | 44 | 0 | 1435 | 1308 | 182 | 1677 |
| storm | V0 naive | never | 0 | 277557 | 33314 | 33314 | 56304 | 487370 | 0 | 0 |
| storm | V1 damped | 1090 | 0 | 55859 | 457 | 457 | 4211 | 40823 | 0 | 0 |
| storm | V2 damped+jitter | 315 | 3 | 13396 | 0 | 0 | 3642 | 21644 | 0 | 0 |
| storm | V3 full (polite shrink) | 406 | 4 | 7331 | 0 | 0 | 3265 | 27782 | 88 | 0 |
| storm | V5 polite (AgentInfo-only) | 356 | 2 | 14735 | 0 | 0 | 1967 | 6174 | 166 | 1990 |
| flashcrowd | V0 naive | never | 0 | 187822 | 16891 | 16891 | 72679 | 537660 | 0 | 0 |
| flashcrowd | V1 damped | 0 | 2 | 5704 | 0 | 0 | 3375 | 33073 | 0 | 0 |
| flashcrowd | V2 damped+jitter | never | 2 | 13186 | 0 | 0 | 4625 | 46264 | 0 | 0 |
| flashcrowd | V3 full (polite shrink) | 452 | 5 | 0 | 0 | 0 | 3709 | 34013 | 169 | 0 |
| flashcrowd | V5 polite (AgentInfo-only) | 0 | 2 | 2593 | 0 | 0 | 1535 | 1387 | 211 | 1807 |
| churn | V0 naive | never | 0 | 245131 | 20766 | 20766 | 54828 | 424629 | 0 | 0 |
| churn | V1 damped | never | 1 | 68486 | 0 | 0 | 4918 | 42261 | 0 | 0 |
| churn | V2 damped+jitter | never | 1 | 55219 | 0 | 0 | 4639 | 34209 | 0 | 0 |
| churn | V3 full (polite shrink) | 1157 | 4 | 7426 | 0 | 0 | 3990 | 34429 | 149 | 0 |
| churn | V5 polite (AgentInfo-only) | 517 | 0 | 35681 | 44 | 0 | 2698 | 11700 | 124 | 2298 |
