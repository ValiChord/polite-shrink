# research/leo-admission

Findings: [00-findings.md](00-findings.md). Probe spec: [tla/StaleCapLEO.tla](tla/StaleCapLEO.tla),
derived from `spec/v7/StaleCap.tla` in this repo (Apache-2.0).

Reproduce (TLC jar from <https://github.com/tlaplus/tlaplus/releases>; set `TLA2TOOLS`):

```bash
cd research/leo-admission/tla
export TLA2TOOLS=/path/to/tla2tools.jar
./run.sh unit_patient_C2        # must print 20024 distinct states: the upstream count
./run.sh w882_prog_patient      # weighted 8,8,2,2 against C=10: safe
./run.sh slack1_D2_unit_C2      # staleness beyond L: Safety violated
./run.sh indep_L0_unit_C2       # independent message delays, no linger: Safety violated
./run.sh indep_L2_unit_C2       # same with linger = L: no error
```

`mk.sh` writes a `.cfg`; `run.sh` runs one and stores the log in `logs/`.
`w*_C*_patient*` configs that include `NoAvoidableRejection` are expected to fail: that
invariant measures needless one-shot rejection (findings §3a), not safety.
