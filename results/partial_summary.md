# Partial liars vs verified coverage

K = 10 liars (= 2R) declare a full arc but truly store a fraction p of the ring. Audit = c-sample range-check; a liar passes with ~p^c and, once certified, is trusted over its whole declared arc.

## A. Static, declared vs verified (c=2 samples, R=5, seeds [42, 7, 99], tail-mean)

| policy | p (held) | true floor | true-zero sectors | ring 0-copy |
|---|---|---|---|---|
| declared | 0.00 | 0.0 | 352 | 68.8% |
| declared | 0.25 | 0.0 | 21 | 4.2% |
| declared | 0.50 | 1.0 | 0 | 0.0% |
| declared | 0.75 | 3.3 | 0 | 0.0% |
| declared | 0.90 | 5.3 | 0 | 0.0% |
| declared | 1.00 | 10.0 | 0 | 0.0% |
| verified | 0.00 | 6.7 | 0 | 0.0% |
| verified | 0.25 | 5.3 | 0 | 0.0% |
| verified | 0.50 | 3.7 | 0 | 0.0% |
| verified | 0.75 | 3.8 | 0 | 0.0% |
| verified | 0.90 | 5.3 | 0 | 0.0% |
| verified | 1.00 | 10.0 | 0 | 0.0% |

## B. Stringency — audit samples c at p=0.5 (verified)

| samples c | evade prob p^c | true floor | true-zero sectors | ring 0-copy |
|---|---|---|---|---|
| 1 | 0.500 | 1.8 | 0 | 0.0% |
| 2 | 0.250 | 3.7 | 0 | 0.0% |
| 3 | 0.125 | 5.6 | 0 | 0.0% |
| 4 | 0.062 | 6.4 | 0 | 0.0% |
| 6 | 0.016 | 7.4 | 0 | 0.0% |
