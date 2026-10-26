------------------------------- MODULE StaleCap -------------------------------
(***************************************************************************)
(* Safe capacity admission on stale views ("StaleViewCap"), the ceiling    *)
(* counterpart to StaleShrink.tla.                                         *)
(*                                                                         *)
(* N nodes start with no active claims (active = {}). Any node may decide  *)
(* to claim a slot, but at most C nodes may ever be active simultaneously. *)
(* A node announces its intent, waits D ticks, then re-checks against a    *)
(* view up to L ticks stale.                                               *)
(*                                                                         *)
(* Rules compared:                                                         *)
(*  - "tb" (V3): count active + self + lower-ID announcers <= C.           *)
(*  - "patient" (V6): count active + self + ALL announcers <= C. If > C,   *)
(*    only the single lowest-ID announcer (lower = {}) waits.              *)
(*  - "patient_k" (V7): count active + self + ALL announcers <= C. If > C, *)
(*    any announcer whose (active + self + lower) <= C waits while higher  *)
(*    excess announcers withdraw, filling up to C slots in one wave.       *)
(***************************************************************************)
EXTENDS Naturals, FiniteSets, Sequences

CONSTANTS Nodes, C, L, D, Rule

ASSUME /\ Nodes \subseteq Nat /\ Nodes # {}
       /\ C \in Nat \ {0} /\ L \in Nat \ {0} /\ D \in Nat \ {0}
       /\ Rule \in {"tb", "patient", "patient_k"}

Span == D + 2 * L + 1
Horizon == Span + D + 2
           + (IF Rule \in {"patient", "patient_k"}
              THEN Cardinality(Nodes) * (D + 2 * L + 2)
              ELSE 0)

VARIABLES now, active, intent, announced, snapshots

vars == <<now, active, intent, announced, snapshots>>

TypeOK == /\ now \in 0..Horizon
          /\ active \in SUBSET Nodes
          /\ intent \in [Nodes -> 0..(Horizon + D)]
          /\ announced \in SUBSET Nodes
          /\ snapshots \in Seq((SUBSET Nodes) \X (SUBSET Nodes))
          /\ Len(snapshots) <= L

Announcers == { n \in Nodes : intent[n] # 0 }

Init == /\ now = 0
        /\ active = {}
        /\ intent = [n \in Nodes |-> 0]
        /\ announced = {}
        /\ snapshots = << >>

View(a) == IF now >= a
           THEN snapshots[Len(snapshots) - a + 1]
           ELSE <<{}, {}>>

Decide(n, view) ==
    LET act    == view[1]
        its    == view[2]
        lower  == { m \in its : m < n }
        higher == { m \in its : m > n }
        eff    == Cardinality(act \cup {n} \cup its)
    IN CASE Rule = "tb" ->
            IF Cardinality(act \cup {n} \cup lower) <= C THEN "go" ELSE "withdraw"
         [] Rule = "patient" ->
            IF eff <= C THEN "go"
            ELSE IF higher # {} /\ lower = {} THEN "wait"
            ELSE "withdraw"
         [] Rule = "patient_k" ->
            IF eff <= C THEN "go"
            ELSE IF higher # {} /\ Cardinality(act \cup {n} \cup lower) <= C
                 THEN "wait"
            ELSE "withdraw"

Announce(n) ==
    /\ now < Span
    /\ n \notin active
    /\ n \notin announced
    /\ intent' = [intent EXCEPT ![n] = now + D]
    /\ announced' = announced \cup {n}
    /\ UNCHANGED <<now, active, snapshots>>

Recheck(n) ==
    /\ n \notin active
    /\ intent[n] = now
    /\ intent[n] # 0
    /\ \E a \in 1..L :
         LET d == Decide(n, View(a))
         IN /\ active' = IF d = "go" THEN active \cup {n} ELSE active
            /\ intent' = [intent EXCEPT ![n] = IF d = "wait" THEN now + 1 ELSE 0]
    /\ UNCHANGED <<now, announced, snapshots>>

AdvanceTime ==
    /\ now < Horizon
    /\ \A n \in Nodes \ active : intent[n] # now \/ intent[n] = 0
    /\ now' = now + 1
    /\ snapshots' = LET s == Append(snapshots, <<active, Announcers>>)
                    IN IF Len(s) > L THEN Tail(s) ELSE s
    /\ UNCHANGED <<active, intent, announced>>

Done == now = Horizon /\ UNCHANGED vars

Next == \/ \E n \in Nodes : Announce(n) \/ Recheck(n)
        \/ AdvanceTime
        \/ Done

Spec == Init /\ [][Next]_vars

Safety == Cardinality(active) <= C
ConditionalSafety == (D >= L /\ Rule \in {"patient", "patient_k"}) => (Cardinality(active) <= C)
NoPendingAtHorizon == (now = Horizon) => (Announcers = {})
Progress == (now = Horizon /\ announced # {} /\ C > 0) => (active # {})
=============================================================================
