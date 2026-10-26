# Partitions against V6, across seeds

48 fresh seeds per scenario (from 500000), 200 agents, R = 5. Durability: live copies anywhere (held = bytes on disk). Availability: copies reachable within each side during the split.

| scenario | rule | runs losing data (declared) | runs losing data (held) | worst durability floor | worst availability floor in split | mean unreachable sector-ticks in split | mean after heal | mean ticks to settle after heal |
|---|---|---|---|---|---|---|---|---|
| split5050 | V3 full (polite shrink) | 0/48 | 0/48 | 5 | 0 | 607 | 0 | 315 (22 never) |
| split5050 | V5 polite (AgentInfo-only) | 2/48 | 0/48 | 0 | 0 | 616 | 8 | 301 (0 never) |
| split5050 | V6 polite shrink (patient lowest) | 0/48 | 0/48 | 5 | 1 | 0 | 0 | 50 (5 never) |
| split9010 | V3 full (polite shrink) | 0/48 | 0/48 | 5 | 0 | 9929 | 0 | 219 (18 never) |
| split9010 | V5 polite (AgentInfo-only) | 2/48 | 0/48 | 0 | 0 | 9184 | 2 | 211 (1 never) |
| split9010 | V6 polite shrink (patient lowest) | 0/48 | 0/48 | 5 | 0 | 1949 | 0 | 29 (0 never) |
| flapping | V3 full (polite shrink) | 0/48 | 0/48 | 5 | 0 | 684 | 0 | 459 (26 never) |
| flapping | V5 polite (AgentInfo-only) | 1/48 | 0/48 | 0 | 0 | 884 | 0 | 347 (1 never) |
| flapping | V6 polite shrink (patient lowest) | 0/48 | 0/48 | 5 | 0 | 63 | 0 | 57 (3 never) |
