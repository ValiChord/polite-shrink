# Splits with realistic growth, and pinned nodes

48 seeds per scenario (from 500000), 200 agents. Growth completes only when every added sector has a live holder on the grower's side. 'pinned' = one node in the smaller group keeps everything. small-side gaps = sectors with no copy on the smaller side at the moment of the split.

| scenario | rule | pinned | runs losing data | mean small-side gaps | runs with any small-side gap | mean unreachable sector-ticks in split | mean after heal | mean stored | mean sync |
|---|---|---|---|---|---|---|---|---|---|
| split5050 | V6 | no | 0/48 | 0 | 0/48 | 0 | 0 | 7538 | 9546 |
| split5050 | V6 | yes | 0/48 | 0 | 0/48 | 1061 | 0 | 6937 | 8028 |
| split5050 | V7, R=6 | no | 0/48 | 9 | 19/48 | 8850 | 0 | 3656 | 5214 |
| split5050 | V7, R=6 | yes | 0/48 | 0 | 0/48 | 6300 | 0 | 3602 | 4753 |
| split5050 | V7, R=8 | no | 0/48 | 2 | 7/48 | 1950 | 0 | 4763 | 6494 |
| split5050 | V7, R=8 | yes | 0/48 | 0 | 0/48 | 1362 | 0 | 4720 | 6048 |
| split9010 | V6 | no | 0/48 | 57 | 10/48 | 34411 | 0 | 6327 | 14146 |
| split9010 | V6 | yes | 0/48 | 0 | 0/48 | 0 | 0 | 6049 | 13263 |
| split9010 | V7, R=6 | no | 0/48 | 262 | 47/48 | 157049 | 0 | 3751 | 6456 |
| split9010 | V7, R=6 | yes | 0/48 | 0 | 0/48 | 0 | 0 | 3604 | 9212 |
| split9010 | V7, R=8 | no | 0/48 | 217 | 45/48 | 130475 | 0 | 4775 | 7353 |
| split9010 | V7, R=8 | yes | 0/48 | 0 | 0/48 | 0 | 0 | 4658 | 9852 |
| flapping | V6 | no | 0/48 | 0 | 0/48 | 344 | 0 | 7925 | 11218 |
| flapping | V6 | yes | 0/48 | 0 | 0/48 | 1155 | 0 | 7107 | 9496 |
| flapping | V7, R=6 | no | 0/48 | 9 | 19/48 | 2365 | 0 | 3756 | 9201 |
| flapping | V7, R=6 | yes | 0/48 | 0 | 0/48 | 1772 | 0 | 3681 | 9043 |
| flapping | V7, R=8 | no | 0/48 | 2 | 7/48 | 488 | 0 | 4766 | 11252 |
| flapping | V7, R=8 | yes | 0/48 | 0 | 0/48 | 341 | 0 | 4740 | 11249 |
