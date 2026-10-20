# Valkey replica migration vs V6

Random clusters of 3-6 primaries with 1-4 replicas each; every replica of one or two primaries dies (creating orphans), sometimes plus one spare elsewhere. Gossip staleness up to `lag` ticks per node; PFAIL after 15 s, FAIL reaching observers up to 2 s apart; 1 tick = 100 ms; 90 s per run. V6 waits lag+1 ticks after announcing, on top of Valkey's own 5 s delay.

| scenario | barrier | lag (s) | rule | runs | migrations | barrier violations (runs) | orphaned by migration (runs) | wasted migrations | stalled runs | median time to cover all (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| deaths | 1 | 0.2 | valkey | 300 | 345 | 0 | 0 | 0 | 21 | 22.4 |
| deaths | 1 | 0.2 | skipfail | 300 | 374 | 0 | 0 | 0 | 0 | 22.4 |
| deaths | 1 | 0.2 | v6 | 300 | 374 | 0 | 0 | 0 | 0 | 22.8 |
| deaths | 1 | 1.0 | valkey | 300 | 352 | 0 | 0 | 0 | 16 | 22.4 |
| deaths | 1 | 1.0 | skipfail | 300 | 372 | 0 | 0 | 0 | 0 | 22.4 |
| deaths | 1 | 1.0 | v6 | 300 | 372 | 0 | 0 | 0 | 0 | 23.6 |
| deaths | 1 | 2.0 | valkey | 300 | 352 | 0 | 0 | 0 | 16 | 22.5 |
| deaths | 1 | 2.0 | skipfail | 300 | 372 | 0 | 0 | 0 | 0 | 22.5 |
| deaths | 1 | 2.0 | v6 | 300 | 372 | 0 | 0 | 0 | 0 | 24.6 |
| deaths | 2 | 0.2 | valkey | 300 | 315 | 0 | 0 | 0 | 8 | 22.5 |
| deaths | 2 | 0.2 | skipfail | 300 | 323 | 0 | 0 | 0 | 0 | 22.5 |
| deaths | 2 | 0.2 | v6 | 300 | 323 | 0 | 0 | 0 | 0 | 22.8 |
| deaths | 2 | 1.0 | valkey | 300 | 324 | 0 | 0 | 0 | 10 | 22.5 |
| deaths | 2 | 1.0 | skipfail | 300 | 334 | 0 | 0 | 0 | 0 | 22.5 |
| deaths | 2 | 1.0 | v6 | 300 | 334 | 0 | 0 | 0 | 0 | 23.6 |
| deaths | 2 | 2.0 | valkey | 300 | 324 | 0 | 0 | 0 | 10 | 22.5 |
| deaths | 2 | 2.0 | skipfail | 300 | 334 | 0 | 0 | 0 | 0 | 22.5 |
| deaths | 2 | 2.0 | v6 | 300 | 334 | 0 | 0 | 0 | 0 | 24.7 |
| partition | 1 | 0.2 | valkey | 300 | 521 | 0 | 0 | 170 | 19 | 22.4 |
| partition | 1 | 0.2 | skipfail | 300 | 560 | 0 | 0 | 186 | 0 | 22.4 |
| partition | 1 | 0.2 | v6 | 300 | 560 | 0 | 0 | 186 | 0 | 22.8 |
| partition | 1 | 1.0 | valkey | 300 | 534 | 0 | 0 | 177 | 14 | 22.4 |
| partition | 1 | 1.0 | skipfail | 300 | 562 | 0 | 0 | 190 | 0 | 22.5 |
| partition | 1 | 1.0 | v6 | 300 | 562 | 0 | 0 | 190 | 0 | 23.6 |
| partition | 1 | 2.0 | valkey | 300 | 534 | 0 | 0 | 177 | 14 | 22.5 |
| partition | 1 | 2.0 | skipfail | 300 | 562 | 0 | 0 | 190 | 0 | 22.5 |
| partition | 1 | 2.0 | v6 | 300 | 562 | 0 | 0 | 190 | 0 | 24.6 |
| partition | 2 | 0.2 | valkey | 300 | 460 | 0 | 0 | 145 | 8 | 22.5 |
| partition | 2 | 0.2 | skipfail | 300 | 475 | 0 | 0 | 152 | 0 | 22.5 |
| partition | 2 | 0.2 | v6 | 300 | 475 | 0 | 0 | 152 | 0 | 22.8 |
| partition | 2 | 1.0 | valkey | 300 | 469 | 0 | 0 | 145 | 10 | 22.5 |
| partition | 2 | 1.0 | skipfail | 300 | 486 | 0 | 0 | 152 | 0 | 22.5 |
| partition | 2 | 1.0 | v6 | 300 | 486 | 0 | 0 | 152 | 0 | 23.6 |
| partition | 2 | 2.0 | valkey | 300 | 469 | 0 | 0 | 145 | 10 | 22.5 |
| partition | 2 | 2.0 | skipfail | 300 | 486 | 0 | 0 | 152 | 0 | 22.5 |
| partition | 2 | 2.0 | v6 | 300 | 486 | 0 | 0 | 152 | 0 | 24.7 |
