------------------------------ MODULE StaleBandNet ------------------------------
(***************************************************************************)
(* StaleBand (a floor R and a ceiling C, with joins and leaves on stale    *)
(* views) plus the two things a real network adds:                        *)
(*                                                                         *)
(*  - PARTITION: at most once, the nodes split into two sides for a while. *)
(*    During the split, what a node knows about the other side is frozen   *)
(*    at the moment of the split: holders, leavers and joiners as they     *)
(*    were then.  New intents, joins and leaves across the split are       *)
(*    unseen until it heals.                                               *)
(*  - DEATH: up to MaxDeaths holders vanish without announcing.  Others    *)
(*    keep believing a dead node holds until Det ticks after its death     *)
(*    (unresponsive marking), then drop it even from older views.          *)
(*                                                                         *)
(* Contact (the recent-contact rule): a node counts as SILENT to an        *)
(* observer once the observer has heard nothing from it for D ticks (the  *)
(* wait).  For the floor, silent nodes are not counted as holders; for     *)
(* the ceiling, silent nodes are counted as holders (one might have joined *)
(* unseen).  Each bound reads silence the cautious way for itself.         *)
(*                                                                         *)
(* Safety is about DECISIONS: Breach records a leave that left fewer than  *)
(* R holders or a join that left more than C.  A death alone can take the  *)
(* count below R; that is not a breach.                                    *)
(***************************************************************************)
EXTENDS Naturals, FiniteSets, Sequences

CONSTANTS Nodes, H0, R, C, L, D, Rule,
          Contact,     \* TRUE: the recent-contact rule is on
          Partition,   \* TRUE: one split may happen
          MaxDeaths,   \* 0 or more holders may die
          Det          \* ticks from a death until it is detected

ASSUME /\ Nodes \subseteq Nat /\ H0 \subseteq Nodes
       /\ R \in Nat /\ C \in Nat /\ R <= Cardinality(H0) /\ Cardinality(H0) <= C
       /\ L \in Nat \ {0} /\ D \in Nat \ {0}
       /\ Rule \in {"tb", "patient", "patient_k"}
       /\ Contact \in BOOLEAN /\ Partition \in BOOLEAN
       /\ MaxDeaths \in Nat /\ Det \in Nat

Span == D + 2 * L + 1
Horizon == Span + 2 * D + 2 * L + 2
           + (IF Rule = "tb" THEN 0 ELSE Cardinality(Nodes) * (D + 2 * L + 2))
None == Horizon + D + 1   \* "never" for pStart / pEnd / diedAt

VARIABLES now, holds, intent, kind, announced, snapshots,
          part,     \* one side of the split ({} = never split)
          pStart,   \* tick the split began (None if not)
          pEnd,     \* tick it healed (None while split or never)
          frozen,   \* <<holders, leavers, joiners>> at the split
          dead, diedAt,
          breach,   \* a decision crossed a bound
          breachOut \* ... with no death in the last D ticks

vars == <<now, holds, intent, kind, announced, snapshots,
          part, pStart, pEnd, frozen, dead, diedAt, breach, breachOut>>

Triple == (SUBSET Nodes) \X (SUBSET Nodes) \X (SUBSET Nodes)

TypeOK == /\ now \in 0..Horizon
          /\ holds \in SUBSET Nodes
          /\ intent \in [Nodes -> 0..(Horizon + D)]
          /\ kind \in [Nodes -> {"none", "leave", "join"}]
          /\ announced \in SUBSET Nodes
          /\ snapshots \in Seq(Triple) /\ Len(snapshots) <= L
          /\ part \in SUBSET Nodes
          /\ pStart \in 0..None /\ pEnd \in 0..None
          /\ frozen \in Triple
          /\ dead \in SUBSET Nodes
          /\ diedAt \in [Nodes -> 0..None]
          /\ breach \in BOOLEAN /\ breachOut \in BOOLEAN

Live(k) == { n \in Nodes : intent[n] # 0 /\ kind[n] = k }
State == <<holds, Live("leave"), Live("join")>>

Init == /\ now = 0
        /\ holds = H0
        /\ intent = [n \in Nodes |-> 0]
        /\ kind = [n \in Nodes |-> "none"]
        /\ announced = {}
        /\ snapshots = << >>
        /\ part = {} /\ pStart = None /\ pEnd = None
        /\ frozen = <<H0, {}, {}>>
        /\ dead = {} /\ diedAt = [n \in Nodes |-> None]
        /\ breach = FALSE /\ breachOut = FALSE

Other(n) == IF n \in part THEN Nodes \ part ELSE part

\* Was tick s inside the split?
InSplit(s) == part # {} /\ s >= pStart /\ s < pEnd

\* Deaths as n sees them at the current tick.
Detected == { m \in dead : now >= diedAt[m] + Det }
Undetected == dead \ Detected

\* n's view of age a, as <<floor holders, ceiling holders, leavers, joiners>>.
ViewFor(n, a) ==
    LET s      == IF now >= a THEN now - a ELSE None
        base   == IF now >= a THEN snapshots[Len(snapshots) - a + 1]
                              ELSE <<H0, {}, {}>>
        oth    == Other(n)
        split  == now >= a /\ InSplit(s)
        Mix(i) == IF split THEN (base[i] \ oth) \cup (frozen[i] \cap oth)
                           ELSE base[i]
        hsRaw  == (Mix(1) \cup Undetected) \ Detected
        \* Silent: across a split for D ticks, or dead for D ticks.
        silent == ( (IF split /\ now - pStart >= D THEN oth ELSE {})
                    \cup { m \in dead : now - diedAt[m] >= D } ) \ Detected
        hsF    == IF Contact THEN hsRaw \ silent ELSE hsRaw
        hsC    == IF Contact THEN hsRaw \cup silent ELSE hsRaw
    IN <<hsF, hsC, Mix(2), Mix(3)>>

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
    /\ n \notin announced /\ n \notin dead
    /\ kind' = [kind EXCEPT ![n] = IF n \in holds THEN "leave" ELSE "join"]
    /\ intent' = [intent EXCEPT ![n] = now + D]
    /\ announced' = announced \cup {n}
    /\ UNCHANGED <<now, holds, snapshots, part, pStart, pEnd, frozen,
                   dead, diedAt, breach, breachOut>>

Recheck(n) ==
    /\ intent[n] # 0
    /\ intent[n] = now
    /\ \E a \in 1..L :
          LET v == ViewFor(n, a)
              d == IF kind[n] = "leave" THEN DecideLeave(n, v[1], v[3])
                                        ELSE DecideJoin(n, v[2], v[4])
              h == IF d # "go" THEN holds
                   ELSE IF kind[n] = "leave" THEN holds \ {n} ELSE holds \cup {n}
          IN /\ holds' = h
             /\ intent' = [intent EXCEPT ![n] = IF d = "wait" THEN now + 1 ELSE 0]
             /\ LET crossed == d = "go" /\ (Cardinality(h) < R \/ Cardinality(h) > C)
                    recent  == \E m \in dead : now - diedAt[m] < D
                IN /\ breach' = (breach \/ crossed)
                   /\ breachOut' = (breachOut \/ (crossed /\ ~recent))
    /\ UNCHANGED <<now, kind, announced, snapshots, part, pStart, pEnd,
                   frozen, dead, diedAt>>

\* The split: side `S` (containing node 1, to avoid counting mirror images
\* twice) and the rest.
Split(S) ==
    /\ Partition /\ part = {} /\ now < Span
    /\ 1 \in S /\ S # Nodes
    /\ part' = S /\ pStart' = now /\ frozen' = State
    /\ UNCHANGED <<now, holds, intent, kind, announced, snapshots, pEnd,
                   dead, diedAt, breach, breachOut>>

Heal ==
    /\ part # {} /\ pEnd = None /\ now > pStart
    /\ pEnd' = now
    /\ UNCHANGED <<now, holds, intent, kind, announced, snapshots, part,
                   pStart, frozen, dead, diedAt, breach, breachOut>>

Die(m) ==
    /\ Cardinality(dead) < MaxDeaths /\ now < Span + D
    /\ m \in holds
    /\ holds' = holds \ {m}
    /\ dead' = dead \cup {m}
    /\ diedAt' = [diedAt EXCEPT ![m] = now]
    /\ intent' = [intent EXCEPT ![m] = 0]
    /\ UNCHANGED <<now, kind, announced, snapshots, part, pStart, pEnd,
                   frozen, breach, breachOut>>

\* Time advances once every due re-check has happened; a split must have
\* healed with room to spare before the end.
AdvanceTime ==
    /\ now < Horizon
    /\ \A n \in Nodes : intent[n] # now \/ intent[n] = 0
    /\ (part # {} /\ pEnd = None) => now < Span + D
    /\ now' = now + 1
    /\ snapshots' = LET s == Append(snapshots, State)
                    IN IF Len(s) > L THEN Tail(s) ELSE s
    /\ UNCHANGED <<holds, intent, kind, announced, part, pStart, pEnd,
                   frozen, dead, diedAt, breach, breachOut>>

Done == now = Horizon /\ UNCHANGED vars

Next == \/ \E n \in Nodes : Announce(n) \/ Recheck(n) \/ Die(n)
        \/ \E S \in SUBSET Nodes : Split(S)
        \/ Heal
        \/ AdvanceTime
        \/ Done

Spec == Init /\ [][Next]_vars

NoBreach == ~breach

\* Breaches only in the window no local rule can close: a death less than
\* one wait before the decision.
NoBreachOutsideWindow == ~breachOut

\* Witnesses (expected to be VIOLATED): something does move.
NeverLeaves == H0 \subseteq holds
NeverJoins  == holds \subseteq H0
NeverLeavesInSplit == ~(part # {} /\ pEnd = None /\ ~(H0 \subseteq holds))
NeverJoinsInSplit  == ~(part # {} /\ pEnd = None /\ ~(holds \subseteq H0))
=============================================================================
