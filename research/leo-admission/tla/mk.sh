#!/bin/bash
# usage: mk.sh NAME "Nodes" "W-map" C L D Rule Slack Indep Linger INVARIANTS...
n=$1; shift
cat > $n.cfg <<CFG
SPECIFICATION Spec
CONSTANTS
    Nodes = $1
    Prof = "$2"
    C = $3
    L = $4
    D = $5
    Rule = "$6"
    Slack = $7
    Indep = $8
    Linger = $9
INVARIANTS
    TypeOK
CFG
shift 9
for i in "$@"; do echo "    $i" >> $n.cfg; done
