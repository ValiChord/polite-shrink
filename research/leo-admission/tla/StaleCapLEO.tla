------------------------------ MODULE StaleCapLEO ------------------------------
(***************************************************************************)
(* Probe variant of ValiChord/polite-shrink spec/v7/StaleCap.tla.          *)
(* Derived from that file; the transitions are unchanged except for four   *)
(* switches, each of which exists to test ONE question an LEO reservation  *)
(* use would raise. With W = all 1, Slack = 0, Indep = FALSE, Linger = 0   *)
(* this is StaleCap.tla (same state counts expected).                      *)
(*                                                                         *)
(*  W      : per-node request weight (units of reserved capacity). The      *)
(*           upstream model is unit-weight: |active| <= C.                  *)
(*  Slack  : a view may be up to L+Slack ticks old. Slack > 0 breaks      *)
(*           assumption A1 on purpose (partition / queueing beyond L).      *)
(*  Indep  : the "active" half and the "announcers" half of a view age    *)
(*           independently (two messages, two delays). Upstream gives an    *)
(*           observer one consistent cut.                                   *)
(*  Linger : a committed node stays visible as an announcer for Linger    *)
(*           more ticks after it commits.                                   *)
(***************************************************************************)
EXTENDS Naturals, FiniteSets, Sequences

CONSTANTS Nodes, Prof, C, L, D, Rule, Slack, Indep, Linger

ASSUME /\ Nodes \subseteq Nat /\ Nodes # {}
       /\ Prof \in {"unit", "8_8_2", "5_4_3_2", "4_3_2_1", "2_1_1_1"}
       /\ C \in Nat \ {0} /\ L \in Nat \ {0} /\ D \in Nat \ {0}
       /\ Slack \in Nat /\ Linger \in Nat /\ Indep \in BOOLEAN
       /\ Rule \in {"patient", "patient_k"}

\* Weight profiles (cfg files cannot carry function literals). All hypothetical units.
W == CASE Prof = "unit"    -> <<1, 1, 1, 1>>
       [] Prof = "8_8_2"   -> <<8, 8, 2, 2>>   \* node1, node2 want 8; node3, node4 want 2
       [] Prof = "5_4_3_2" -> <<5, 4, 3, 2>>
       [] Prof = "4_3_2_1" -> <<4, 3, 2, 1>>
       [] Prof = "2_1_1_1" -> <<2, 1, 1, 1>>
ASSUME Len(W) >= Cardinality(Nodes) /\ \A i \in 1..Len(W) : W[i] > 0

LL == L + Slack
Span == D + 2 * LL + 1
Horizon == Span + D + 2 + Cardinality(Nodes) * (D + 2 * LL + 2) + Linger

VARIABLES now, active, intent, announced, snapshots, committedAt

vars == <<now, active, intent, announced, snapshots, committedAt>>

RECURSIVE SumW(_)
SumW(S) == IF S = {} THEN 0
           ELSE LET x == CHOOSE y \in S : TRUE IN W[x] + SumW(S \ {x})

Announcers == { n \in Nodes : intent[n] # 0 }
           \cup { n \in active : now < committedAt[n] + Linger }

Init == /\ now = 0
        /\ active = {}
        /\ intent = [n \in Nodes |-> 0]
        /\ announced = {}
        /\ snapshots = << >>
        /\ committedAt = [n \in Nodes |-> 0]

View(a, b) ==    \* a: age of the active half, b: age of the announcer half
    LET act == IF now >= a THEN snapshots[Len(snapshots) - a + 1][1] ELSE {}
        its == IF now >= b THEN snapshots[Len(snapshots) - b + 1][2] ELSE {}
    IN <<act, its>>

Decide(n, view) ==
    LET act    == view[1]
        its    == view[2]
        lower  == { m \in its : m < n }
        higher == { m \in its : m > n }
        eff    == SumW(act \cup {n} \cup its)
        effLo  == SumW(act \cup {n} \cup lower)
    IN CASE Rule = "patient" ->
            IF eff <= C THEN "go"
            ELSE IF higher # {} /\ lower = {} THEN "wait"
            ELSE "withdraw"
         [] Rule = "patient_k" ->
            IF eff <= C THEN "go"
            ELSE IF higher # {} /\ effLo <= C THEN "wait"
            ELSE "withdraw"

Announce(n) ==
    /\ now < Span
    /\ n \notin active /\ n \notin announced
    /\ intent' = [intent EXCEPT ![n] = now + D]
    /\ announced' = announced \cup {n}
    /\ UNCHANGED <<now, active, snapshots, committedAt>>

Recheck(n) ==
    /\ n \notin active
    /\ intent[n] = now /\ intent[n] # 0
    /\ \E a \in 1..LL : \E b \in (IF Indep THEN 1..LL ELSE {a}) :
         LET d == Decide(n, View(a, b))
         IN /\ active' = IF d = "go" THEN active \cup {n} ELSE active
            /\ committedAt' = IF d = "go" /\ Linger > 0 THEN [committedAt EXCEPT ![n] = now] ELSE committedAt
            /\ intent' = [intent EXCEPT ![n] = IF d = "wait" THEN now + 1 ELSE 0]
    /\ UNCHANGED <<now, announced, snapshots>>

AdvanceTime ==
    /\ now < Horizon
    /\ \A n \in Nodes \ active : intent[n] # now \/ intent[n] = 0
    /\ now' = now + 1
    /\ snapshots' = LET s == Append(snapshots, <<active, Announcers>>)
                    IN IF Len(s) > LL THEN Tail(s) ELSE s
    /\ UNCHANGED <<active, intent, announced, committedAt>>

Done == now = Horizon /\ UNCHANGED vars

Next == \/ \E n \in Nodes : Announce(n) \/ Recheck(n)
        \/ AdvanceTime
        \/ Done

Spec == Init /\ [][Next]_vars

TypeOK == /\ now \in 0..Horizon /\ active \in SUBSET Nodes
          /\ intent \in [Nodes -> 0..(Horizon + D)]
SafetyWeighted == SumW(active) <= C
\* Progress: if the node's own weight fits an empty pool, someone is admitted
Progress == (now = Horizon /\ announced # {} /\ \E n \in announced : W[n] <= C)
              => (active # {})
\* Starvation probe: every announcer that fits the pool alone is eventually either
\* active or blocked only because the pool is genuinely full for it
NoAvoidableRejection == (now = Horizon)
    => \A n \in announced : n \notin active => (SumW(active) + W[n] > C)
=============================================================================
