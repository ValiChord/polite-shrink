-------------------------------- MODULE NaiveShrink --------------------------------
(***************************************************************************)
(* The pre-2021 behaviour, for contrast -- no announce, no wait, no        *)
(* tie-break.  Each node decides from a STALE coverage view: the count it   *)
(* last gossiped, before concurrent drops landed.  We hand every node the   *)
(* most permissive stale view, the initial full count, and let it drop as   *)
(* long as that view showed slack (> R).                                    *)
(*                                                                          *)
(* TLC finds a reachable state with fewer than R copies -- the "hallway     *)
(* dance" data loss that got dynamic sharding switched off.  Its purpose    *)
(* here is to show the model has teeth: the SAME setup as PoliteShrink,     *)
(* minus the two-phase discipline, and SafeCoverage fails.  So the safety   *)
(* PoliteShrink enjoys is bought by the two phases, not by the framing.     *)
(***************************************************************************)
EXTENDS Naturals, FiniteSets

CONSTANTS Nodes, R
ASSUME /\ R \in Nat
       /\ Nodes \subseteq Nat

VARIABLES holds,        \* nodes currently storing the sector
          staleView     \* staleView[n] = coverage n believes it saw

vars == <<holds, staleView>>

Init == /\ holds = Nodes
        /\ staleView = [n \in Nodes |-> Cardinality(Nodes)]  \* everyone saw "full"

\* n drops if its stale view showed more than R copies, blind to the fact
\* that other nodes may already have dropped on the same stale view.
Drop(n) ==
    /\ n \in holds
    /\ staleView[n] > R
    /\ holds' = holds \ {n}
    /\ UNCHANGED staleView

Next == \E n \in Nodes : Drop(n)

Spec == Init /\ [][Next]_vars

SafeCoverage == Cardinality(holds) >= R
==============================================================================
