#!/bin/bash
# usage: run.sh NAME   (expects NAME.cfg)  -> prints verdict line
J=${TLA2TOOLS:-/tmp/claude-0/-home-user-ValiChord/0662db71-8361-59ea-a562-724ba3d78e62/scratchpad/tlc/tla2tools.jar}
n=$1
out=$(java -XX:+UseParallelGC -cp $J tlc2.TLC -workers auto -metadir /tmp/claude-0/m_$n -config $n.cfg StaleCapLEO.tla 2>&1)
echo "$out" > logs/$n.log
v=$(echo "$out" | grep -E "No error has been found|Invariant .* is violated|Temporal properties were violated|Deadlock" | head -1)
s=$(echo "$out" | grep -E "distinct states found" | head -1)
printf "%-34s %s | %s\n" "$n" "$v" "$s"
