---------------------------- MODULE AgentInfoOptimistic ----------------------------
(***************************************************************************)
(* NEGATIVE CONTROL for the AgentInfo-only encoding.                        *)
(*                                                                          *)
(* Same world as AgentInfoConservative: the vacate intent is carried by the *)
(* gossiped arc claim, so "announced but still holding" and "already gone"  *)
(* are indistinguishable -- both are simply absent from `declared`.         *)
(*                                                                          *)
(* This spec keeps the TCAS lower-id tie-break anyway, by making the        *)
(* assumption that recovers its input: treat every un-declared node as an   *)
(* intender that is STILL HOLDING, then subtract only the lower-id ones.    *)
(* That is the faithful optimistic port of the original rule -- not a       *)
(* strawman.  It is what you get if you take "reuse AgentInfo" literally    *)
(* and keep the rest of the gate as written.                                *)
(*                                                                          *)
(* It is unsound for one reason, and the counterexample shows it: a node    *)
(* that has genuinely departed is also absent from `declared`, so it is     *)
(* counted as a holder.  Counting a departed node as present is the one     *)
(* direction that loses data.                                               *)
(*                                                                          *)
(* EXPECTED RESULT: TLC reports "Invariant SafeCoverage is violated".       *)
(* The point of running it is to obtain that counterexample -- it is the    *)
(* argument, as a proof rather than an opinion, for why SOME bit            *)
(* distinguishing intent from departure has to exist.                       *)
(***************************************************************************)
EXTENDS Naturals, FiniteSets

CONSTANTS Nodes,        \* set of node ids, e.g. {1,2,3,4,5} (ordered naturals)
          R             \* redundancy target

ASSUME /\ R \in Nat
       /\ Nodes \subseteq Nat

VARIABLES holds,        \* nodes really storing the sector
          declared      \* nodes whose published arc claims the sector

vars == <<holds, declared>>

TypeOK == /\ holds    \subseteq Nodes
          /\ declared \subseteq holds

Init == /\ holds    = Nodes
        /\ declared = Nodes

Announce(n) ==
    /\ n \in declared
    /\ declared' = declared \ {n}
    /\ UNCHANGED holds

\* The optimistic reading: anyone not claiming the sector is assumed to be an
\* intender who is still holding it.  This is the assumption that gives the
\* tie-break its input -- and it is false for nodes that have already left.
PerceivedIntenders(n) == { m \in Nodes \ declared : m # n }

\* Perceived holders = everyone, because departures are invisible under this
\* reading.  Then discount every lower-id perceived intender, as the original
\* gate does.
EffCoverage(n) ==
    Cardinality( (Nodes \ {n}) \ { m \in PerceivedIntenders(n) : m < n } )

Execute(n) ==
    /\ n \in holds \ declared
    /\ \/ /\ EffCoverage(n) >= R
          /\ holds' = holds \ {n}
          /\ UNCHANGED declared
       \/ /\ EffCoverage(n) < R
          /\ declared' = declared \cup {n}
          /\ UNCHANGED holds

Next == \E n \in Nodes : Announce(n) \/ Execute(n)

Spec == Init /\ [][Next]_vars

------------------------------------------------------------------------------
SafeCoverage == Cardinality(holds) >= R
==============================================================================
