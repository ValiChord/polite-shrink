# Sharding down from full arcs: speed by rule

24 fresh seeds (from 600000), 200 agents, R = 5, 6000 ticks. settle = first tick after which the resize rate stays below 1/tick for 300 ticks; level<=3 = first tick the mean arc level is 3 or less.

| rule | runs losing data | lowest floor | median settle | worst settle | never settled | median ticks to level<=3 | worst | median final copies | worst final copies | runs with full-arc nodes left |
|---|---|---|---|---|---|---|---|---|---|---|
| V3 | 0/24 | 5 | 1632 | 2888 | 0/24 | 813 | 872 (0 never) | 6.1 | 9.0 | 24/24 |
| V6 | 0/24 | 5 | 993 | 1392 | 0/24 | 1346 | 3004 (0 never) | 6.3 | 38.8 | 24/24 |
| V6+multiwait | 0/24 | 5 | 993 | 1391 | 0/24 | 1346 | 2662 (0 never) | 6.0 | 6.4 | 23/24 |
| V6+multiwait+alongside | 0/24 | 5 | 1356 | 2932 | 0/24 | 809 | 873 (0 never) | 6.0 | 9.4 | 24/24 |
