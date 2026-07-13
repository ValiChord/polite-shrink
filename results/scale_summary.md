# Scale study summary

settle criterion scaled to population (rate < N/200 per tick for 300 ticks). loss/exposure = sector-ticks after the disruption.

| n | sectors | series | scenario | variant | settle | floor_min | exposure | loss | resizes_per_agent | sync_per_agent | mean_level_end |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 500 | 1024 | density | activation | V1 damped | 868 | 1 | 9791 | 0 | 10.8 | 21.2 | 0.5 |
| 500 | 1024 | density | activation | V3 full (polite shrink) | 1465 | 5 | 0 | 0 | 18.4 | 135.2 | 0.6 |
| 1000 | 2048 | density | activation | V1 damped | 1096 | 1 | 60252 | 0 | 15.4 | 222.5 | 0.6 |
| 1000 | 2048 | density | activation | V3 full (polite shrink) | 1460 | 5 | 0 | 0 | 14.9 | 64.1 | 0.2 |
| 2000 | 4096 | density | activation | V1 damped | 2404 | 0 | 407594 | 1071 | 22.8 | 254.6 | 0.4 |
| 2000 | 4096 | density | activation | V3 full (polite shrink) | 1479 | 5 | 0 | 0 | 21.6 | 129.3 | 0.2 |
| 5000 | 16384 | density | activation | V1 damped | 1420 | 0 | 256840 | 1474 | 16.2 | 94.6 | 0.0 |
| 5000 | 16384 | density | activation | V3 full (polite shrink) | 1694 | 5 | 0 | 0 | 21.2 | 139.7 | 0.3 |
| 200 | 512 | fixed | activation | V1 damped | 1258 | 2 | 19296 | 0 | 19.4 | 243.4 | 1.1 |
| 200 | 512 | fixed | activation | V3 full (polite shrink) | 1557 | 5 | 0 | 0 | 22.9 | 248.0 | 0.9 |
| 500 | 512 | fixed | activation | V1 damped | 1174 | 0 | 32547 | 13 | 18.5 | 110.5 | 0.5 |
| 500 | 512 | fixed | activation | V3 full (polite shrink) | 1687 | 5 | 0 | 0 | 18.2 | 88.8 | 0.3 |
| 1000 | 512 | fixed | activation | V1 damped | 682 | 1 | 3536 | 0 | 10.0 | 12.7 | 0.1 |
| 1000 | 512 | fixed | activation | V3 full (polite shrink) | 1371 | 5 | 0 | 0 | 12.0 | 18.3 | 0.1 |
| 2000 | 512 | fixed | activation | V1 damped | 766 | 0 | 13945 | 19 | 12.3 | 34.8 | 0.2 |
| 2000 | 512 | fixed | activation | V3 full (polite shrink) | 1107 | 5 | 0 | 0 | 9.4 | 2.0 | 0.0 |
| 5000 | 512 | fixed | activation | V1 damped | 766 | 3 | 57 | 0 | 9.0 | 0.0 | 0.0 |
| 5000 | 512 | fixed | activation | V3 full (polite shrink) | 1104 | 5 | 0 | 0 | 9.7 | 0.3 | 0.0 |
| 500 | 1024 | density | storm | V1 damped | 0 | 4 | 285 | 0 | 11.0 | 22.9 | 0.3 |
| 500 | 1024 | density | storm | V3 full (polite shrink) | 494 | 3 | 15279 | 0 | 19.9 | 157.7 | 0.7 |
| 1000 | 2048 | density | storm | V1 damped | 120 | 2 | 34812 | 0 | 15.3 | 143.5 | 0.2 |
| 1000 | 2048 | density | storm | V3 full (polite shrink) | 119 | 4 | 19063 | 0 | 16.9 | 92.6 | 0.5 |
| 2000 | 4096 | density | storm | V1 damped | 126 | 2 | 192671 | 0 | 22.2 | 235.1 | 0.3 |
| 2000 | 4096 | density | storm | V3 full (polite shrink) | 451 | 4 | 80804 | 0 | 21.0 | 103.3 | 0.7 |
| 5000 | 16384 | density | storm | V1 damped | 0 | 5 | 0 | 0 | 16.2 | 94.6 | 0.0 |
| 5000 | 16384 | density | storm | V3 full (polite shrink) | 29 | 4 | 13292 | 0 | 20.2 | 117.2 | 0.7 |
| 200 | 512 | fixed | storm | V1 damped | never | 0 | 65909 | 249 | 26.4 | 340.3 | 1.4 |
| 200 | 512 | fixed | storm | V3 full (polite shrink) | 403 | 4 | 7552 | 0 | 22.2 | 200.8 | 0.7 |
| 500 | 512 | fixed | storm | V1 damped | 702 | 1 | 39540 | 0 | 21.6 | 141.9 | 0.6 |
| 500 | 512 | fixed | storm | V3 full (polite shrink) | 126 | 4 | 6293 | 0 | 17.6 | 75.1 | 0.5 |
| 1000 | 512 | fixed | storm | V1 damped | 0 | 2 | 10457 | 0 | 11.4 | 30.6 | 0.2 |
| 1000 | 512 | fixed | storm | V3 full (polite shrink) | 0 | 3 | 1971 | 0 | 13.4 | 30.8 | 0.2 |
| 2000 | 512 | fixed | storm | V1 damped | 0 | 1 | 8857 | 0 | 12.2 | 32.7 | 0.2 |
| 2000 | 512 | fixed | storm | V3 full (polite shrink) | 0 | 4 | 4325 | 0 | 9.6 | 2.1 | 0.1 |
| 5000 | 512 | fixed | storm | V1 damped | 0 | 1 | 11251 | 0 | 9.8 | 0.5 | 0.1 |
| 5000 | 512 | fixed | storm | V3 full (polite shrink) | 0 | 1 | 2274 | 0 | 10.1 | 0.7 | 0.1 |
