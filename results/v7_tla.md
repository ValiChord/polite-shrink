# V7 in TLA+: what TLC checked (October 2026)

TLC 2.19, exhaustive (every reachable state), models in [spec/v7/](../spec/v7/).
L = 2 ticks of staleness and D = the wait, unless stated. "Controls" are
configurations built to fail; if they passed, the check would have no teeth.

## StaleCap (the ceiling alone)

| configuration (4 nodes) | result |
|---|---|
| V6 rule, C = 1, 2, 3, wait 1x and 2x | no error |
| multiwait rule ("patient_k"), C = 2, 3 | no error |
| V3 rule, wait 1x (C = 1, 2), 1.5x (C = 2), 2x (C = 3) | **Safety violated** (control) |
| any rule, wait shorter than the staleness | **Safety violated** (control) |

StaleCap with ceiling C gives exactly the state counts of StaleShrink with floor
R = N − C (16,848 and 43,348 distinct states): the same model through the
complement.

## StaleBand (V7: floor and ceiling together)

| configuration | result |
|---|---|
| 4 nodes, roomy and tight bands, 1x and 2x waits, V6 and multiwait waiting | both bounds kept; progress in both directions (17–43k states each) |
| joiners competing for the last free place; leavers in a tight band | no error |
| 5 nodes, V6 and multiwait | no error (131–133k states) |
| V3 rule | **Floor** or **Ceiling violated** (control) |
| wait shorter than the staleness | **violated** (control) |

Mirror configurations (join and leave sides swapped) give identical state counts,
a check that the two halves of the rule are true mirror images.

## StaleBandNet (+ a split, deaths, recent contact)

| configuration (4 nodes unless stated) | without recent contact | with recent contact |
|---|---|---|
| one split, any sides, any timing | **breach** (both holders leave, each counting the other's frozen copy) | **no breach**, 13.3M states |
| split, tight band (R = 2, C = 3) | **breach** | **no breach**, 11.4M states |
| split, multiwait waiting | | **no breach**, 13.7M states |
| one death, detected at once | no breach, 155k states | |
| one death never detected | **breach** long after the death | breaches **only within one wait** of the death (166k states) |
| split **and** an undetected death, 3 nodes | **breach outside that window** | none outside the window, 8.7M states |
| the same, 4 nodes, L = D = 1 | | none outside the window, 15.1M states |
| witnesses: do leaves and joins happen during a split? | | **yes, both** |

The window just after a death cannot be closed by any local rule: a node cannot
tell a dead holder from a slow one sooner than one wait after its last message.
A split plus a death with L = D = 2 at 4 nodes exceeded this machine (64M
states and growing after an hour) and was replaced by the two smaller runs.
