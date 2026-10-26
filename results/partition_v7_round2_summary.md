# Partitions against V7, across seeds

48 fresh seeds per scenario (from 500000, as for V6), 200 agents. Durability: live copies anywhere. Availability: copies reachable within each side during the split. stored = total sectors held at the end.

| scenario | rule | runs losing data | worst durability floor | worst availability floor in split | mean unreachable sector-ticks in split | mean after heal | mean settle after heal | mean stored | mean sync |
|---|---|---|---|---|---|---|---|---|---|
| split5050 | V6 | 0/48 | 5 | 1 | 0 | 0 | 50 (5 never) | 7538 | 9546 |
| split5050 | V7, R=8 | 0/48 | 8 | 0 | 262 | 0 | 183 (0 never) | 4768 | 6199 |
| split5050 | V7, R=9 | 0/48 | 9 | 0 | 52 | 0 | 154 (0 never) | 5281 | 6966 |
| split5050 | V7+critical, R=6 | 0/48 | 6 | 0 | 471 | 0 | 170 (0 never) | 3670 | 4510 |
| split5050 | V7+critical, R=8 | 0/48 | 8 | 0 | 98 | 0 | 162 (0 never) | 4782 | 6279 |
| split9010 | V6 | 0/48 | 5 | 0 | 1949 | 0 | 29 (0 never) | 6291 | 15035 |
| split9010 | V7, R=8 | 0/48 | 8 | 0 | 7070 | 0 | 280 (0 never) | 4640 | 9996 |
| split9010 | V7, R=9 | 0/48 | 9 | 0 | 5209 | 0 | 237 (0 never) | 5198 | 10775 |
| split9010 | V7+critical, R=6 | 0/48 | 6 | 0 | 7690 | 0 | 327 (0 never) | 3677 | 9428 |
| split9010 | V7+critical, R=8 | 0/48 | 8 | 0 | 6024 | 0 | 270 (0 never) | 4678 | 10086 |
| flapping | V6 | 0/48 | 5 | 0 | 63 | 0 | 57 (3 never) | 7902 | 11222 |
| flapping | V7, R=8 | 0/48 | 8 | 0 | 262 | 0 | 168 (0 never) | 4755 | 11179 |
| flapping | V7, R=9 | 0/48 | 9 | 0 | 52 | 0 | 123 (0 never) | 5382 | 12643 |
| flapping | V7+critical, R=6 | 0/48 | 6 | 0 | 474 | 0 | 101 (0 never) | 3754 | 8588 |
| flapping | V7+critical, R=8 | 0/48 | 8 | 0 | 98 | 0 | 145 (0 never) | 4777 | 11048 |
