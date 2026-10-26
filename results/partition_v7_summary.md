# Partitions against V7, across seeds

48 fresh seeds per scenario (from 500000, as for V6), 200 agents. Durability: live copies anywhere. Availability: copies reachable within each side during the split. stored = total sectors held at the end.

| scenario | rule | runs losing data | worst durability floor | worst availability floor in split | mean unreachable sector-ticks in split | mean after heal | mean settle after heal | mean stored | mean sync |
|---|---|---|---|---|---|---|---|---|---|
| split5050 | V6 | 0/48 | 5 | 1 | 0 | 0 | 50 (5 never) | 7538 | 9546 |
| split5050 | V7, R=5 | 0/48 | 5 | 0 | 2114 | 0 | 203 (0 never) | 3086 | 3526 |
| split5050 | V7, R=6 | 0/48 | 6 | 0 | 1285 | 0 | 181 (0 never) | 3612 | 4377 |
| split5050 | V7+urgent, R=5 | 0/48 | 5 | 0 | 1062 | 0 | 115 (0 never) | 3718 | 12646 |
| split5050 | V7+urgent, R=6 | 0/48 | 6 | 0 | 125 | 0 | 160 (2 never) | 4508 | 16502 |
| split9010 | V6 | 0/48 | 5 | 0 | 1949 | 0 | 29 (0 never) | 6291 | 15035 |
| split9010 | V7, R=5 | 0/48 | 5 | 0 | 10808 | 0 | 329 (0 never) | 3101 | 8977 |
| split9010 | V7, R=6 | 0/48 | 6 | 0 | 9881 | 0 | 329 (0 never) | 3619 | 9287 |
| split9010 | V7+urgent, R=5 | 0/48 | 5 | 0 | 8927 | 0 | 89 (0 never) | 3272 | 14996 |
| split9010 | V7+urgent, R=6 | 0/48 | 6 | 0 | 8552 | 0 | 63 (0 never) | 4183 | 18517 |
| flapping | V6 | 0/48 | 5 | 0 | 63 | 0 | 57 (3 never) | 7902 | 11222 |
| flapping | V7, R=5 | 0/48 | 5 | 0 | 2135 | 0 | 134 (0 never) | 3177 | 7214 |
| flapping | V7, R=6 | 0/48 | 6 | 0 | 1281 | 0 | 159 (0 never) | 3669 | 8553 |
| flapping | V7+urgent, R=5 | 0/48 | 5 | 0 | 1213 | 0 | 252 (1 never) | 3518 | 19027 |
| flapping | V7+urgent, R=6 | 0/48 | 6 | 0 | 125 | 0 | 340 (2 never) | 4316 | 24613 |
