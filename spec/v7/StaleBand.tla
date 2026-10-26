------------------------------- MODULE StaleBand -------------------------------
(***************************************************************************)
(* A floor and a ceiling on stale views: between R and C nodes must hold  *)
(* the resource at all times, while any node may announce that it intends *)
(* to leave (if it holds) or to join (if it does not).  StaleShrink is the *)
(* floor alone, StaleCap the ceiling alone (the same model read through   *)
(* the complement); here both directions run at once.                     *)
(*                                                                         *)
(* Each check counts pessimistically for its own bound:                    *)
(*  - leave (floor R): holders other than n, minus every OTHER announced   *)
(*    leaver; announced joiners are not counted as holders yet.            *)
(*  - join (ceiling C): holders, plus n, plus every other announced        *)
(*    joiner; announced leavers still count as holders.                    *)
(* Rule, per direction:                                                    *)
(*  - "tb" (V3): count only LOWER-id announcers of the same direction.     *)
(*  - "patient" (V6): count all of them; if the check fails, the lowest    *)
(*    announcer of that direction waits a tick while higher ones are       *)
(*    racing, otherwise it withdraws.                                      *)
(*  - "patient_k" (V7): count all of them; if the check fails, an          *)
(*    announcer that would pass counting only itself and lower-id          *)
(*    announcers of its direction waits while higher ones are racing.      *)
(*                                                                         *)
(* Structure and timing as in StaleShrink: per-node Announce and Recheck  *)
(* steps read only their own variables and a snapshot 1..L ticks old;     *)
(* an explicit clock advances once every due re-check has happened.        *)
(***************************************************************************)
EXTENDS Naturals, FiniteSets, Sequences

CONSTANTS Nodes,  \* node ids, ordered naturals
          H0,     \* initial holders, R <= Cardinality(H0) <= C
          R,      \* floor
          C,      \* ceiling
          L,      \* maximum age of a view, in ticks
          D,      \* wait between announcing and re-checking, in ticks
          Rule    \* "tb", "patient" or "patient_k"

ASSUME /\ Nodes \subseteq Nat /\ H0 \subseteq Nodes
       /\ R \in Nat /\ C \in Nat /\ R <= Cardinality(H0) /\ Cardinality(H0) <= C
       /\ L \in Nat \ {0} /\ D \in Nat \ {0}
       /\ Rule \in {"tb", "patient", "patient_k"}

Span == D + 2 * L + 1
Horizon == Span + D + 2
           + (IF Rule = "tb" THEN 0 ELSE Cardinality(Nodes) * (D + 2 * L + 2))

VARIABLES now,       \* the clock (nodes never read it)
          holds,     \* current holders
          intent,    \* intent[n]: tick of n's next re-check; 0 = none
          kind,      \* kind[n]: "leave" or "join" once n has announced
          announced, \* nodes that have announced (each announces once)
          snapshots  \* last (up to) L published <<holders, leavers, joiners>>

vars == <<now, holds, intent, kind, announced, snapshots>>

TypeOK == /\ now \in 0..Horizon
          /\ holds \in SUBSET Nodes
          /\ intent \in [Nodes -> 0..(Horizon + D)]
          /\ kind \in [Nodes -> {"none", "leave", "join"}]
          /\ announced \in SUBSET Nodes
          /\ snapshots \in Seq((SUBSET Nodes) \X (SUBSET Nodes) \X (SUBSET Nodes))
          /\ Len(snapshots) <= L

Live(k) == { n \in Nodes : intent[n] # 0 /\ kind[n] = k }

Init == /\ now = 0
        /\ holds = H0
        /\ intent = [n \in Nodes |-> 0]
        /\ kind = [n \in Nodes |-> "none"]
        /\ announced = {}
        /\ snapshots = << >>

\* A view of age a: the state published at tick now - a; before tick a,
\* the initial state.
View(a) == IF now >= a
           THEN snapshots[Len(snapshots) - a + 1]
           ELSE <<H0, {}, {}>>

\* n's decision as a leaver, on holders hs and announced leavers lv.
DecideLeave(n, hs, lv) ==
    LET lower  == { m \in lv : m < n }
        higher == { m \in lv : m > n }
        others == hs \ {n}
        eff    == Cardinality(others \ (lv \ {n}))
        effLow == Cardinality(others \ lower)
    IN CASE Rule = "tb" -> IF effLow >= R THEN "go" ELSE "withdraw"
         [] Rule = "patient" ->
              IF eff >= R THEN "go"
              ELSE IF higher # {} /\ lower = {} THEN "wait" ELSE "withdraw"
         [] Rule = "patient_k" ->
              IF eff >= R THEN "go"
              ELSE IF higher # {} /\ effLow >= R THEN "wait" ELSE "withdraw"

\* n's decision as a joiner, on holders hs and announced joiners jn.
DecideJoin(n, hs, jn) ==
    LET lower  == { m \in jn : m < n }
        higher == { m \in jn : m > n }
        eff    == Cardinality(hs \cup {n} \cup jn)
        effLow == Cardinality(hs \cup {n} \cup lower)
    IN CASE Rule = "tb" -> IF effLow <= C THEN "go" ELSE "withdraw"
         [] Rule = "patient" ->
              IF eff <= C THEN "go"
              ELSE IF higher # {} /\ lower = {} THEN "wait" ELSE "withdraw"
         [] Rule = "patient_k" ->
              IF eff <= C THEN "go"
              ELSE IF higher # {} /\ effLow <= C THEN "wait" ELSE "withdraw"

Announce(n) ==
    /\ now < Span
    /\ n \notin announced
    /\ kind' = [kind EXCEPT ![n] = IF n \in holds THEN "leave" ELSE "join"]
    /\ intent' = [intent EXCEPT ![n] = now + D]
    /\ announced' = announced \cup {n}
    /\ UNCHANGED <<now, holds, snapshots>>

Recheck(n) ==
    /\ intent[n] # 0
    /\ intent[n] = now
    /\ \E a \in 1..L :
          LET v == View(a)
              d == IF kind[n] = "leave" THEN DecideLeave(n, v[1], v[2])
                                        ELSE DecideJoin(n, v[1], v[3])
          IN /\ holds' = IF d # "go" THEN holds
                         ELSE IF kind[n] = "leave" THEN holds \ {n}
                                                   ELSE holds \cup {n}
             /\ intent' = [intent EXCEPT ![n] = IF d = "wait" THEN now + 1 ELSE 0]
    /\ UNCHANGED <<now, kind, announced, snapshots>>

AdvanceTime ==
    /\ now < Horizon
    /\ \A n \in Nodes : intent[n] # now \/ intent[n] = 0
    /\ now' = now + 1
    /\ snapshots' = LET s == Append(snapshots, <<holds, Live("leave"), Live("join")>>)
                    IN IF Len(s) > L THEN Tail(s) ELSE s
    /\ UNCHANGED <<holds, intent, kind, announced>>

Done == now = Horizon /\ UNCHANGED vars

Next == \/ \E n \in Nodes : Announce(n) \/ Recheck(n)
        \/ AdvanceTime
        \/ Done

Spec == Init /\ [][Next]_vars

Floor   == Cardinality(holds) >= R
Ceiling == Cardinality(holds) <= C

\* No intent is left unresolved at the end.
Resolved == (now = Horizon) => (Live("leave") \cup Live("join")) = {}

\* If a leaver announced and a copy could be spared, someone left; if a
\* joiner announced and there was room, someone joined.
ProgressLeave == (now = Horizon /\ \E n \in announced : kind[n] = "leave"
                  /\ Cardinality(H0) > R) => H0 \ holds # {}
ProgressJoin  == (now = Horizon /\ \E n \in announced : kind[n] = "join"
                  /\ Cardinality(H0) < C) => holds \ H0 # {}
=============================================================================
