----------------------------- MODULE AgentInfoAgeGated -----------------------------
(***************************************************************************)
(* The middle path for the AgentInfo-only encoding, and the spec that puts  *)
(* a number on how accurate it has to be.                                   *)
(*                                                                          *)
(* Encoding A (AgentInfoConservative) is safe but gives up the tie-break.   *)
(* Encoding B (AgentInfoOptimistic) keeps the tie-break by assuming every   *)
(* un-declared node is still holding, and loses data.  The gap between them *)
(* is one bit per un-declared node: is it an intender, or has it left?      *)
(*                                                                          *)
(* Encoding C tries to recover that bit from data AgentInfo already carries *)
(* -- `created_at` (crates/api/src/agent.rs) -- by age-gating: an arc claim *)
(* that shrank RECENTLY (inside the wait window) reads as an unexecuted     *)
(* intent; an older one reads as an executed departure.  No new fields, no  *)
(* new messages.                                                            *)
(*                                                                          *)
(* Modelling the heuristic without modelling clocks: the classification is  *)
(* an oracle that is correct except for at most `Budget` departed nodes,    *)
(* which are misread as intenders.  Budget is the knob:                     *)
(*                                                                          *)
(*   Budget = 0  -- the age gate never misclassifies.  The perceived        *)
(*                  intender set is exactly holds \ declared, so the gate   *)
(*                  reduces EXACTLY to the proven rule in PoliteShrink.tla. *)
(*                  Expected: no error.                                     *)
(*   Budget = 1  -- one departed node is misread as "still holding, merely  *)
(*                  intending".  Expected: violated.                        *)
(*                                                                          *)
(* Only that one direction of error is modelled, because only that one is   *)
(* dangerous.  The opposite mistake -- reading a live intender as departed  *)
(* -- subtracts a node that is really still there, which makes the gate     *)
(* stricter, and strictness is the safe direction.                          *)
(*                                                                          *)
(* WHAT THE RESULT MEANS.  If Budget = 1 falsifies safety, the age gate     *)
(* must be perfect to be usable -- a heuristic over gossip timestamps under *)
(* churn is not perfect, so the honest conclusion is that the distinguishing*)
(* bit has to be explicit.  That is an argument for one field on a struct   *)
(* that is already gossiped and already signed, which is a far smaller ask  *)
(* than a new wire message on a new module channel.                         *)
(***************************************************************************)
EXTENDS Naturals, FiniteSets

CONSTANTS Nodes,        \* set of node ids, e.g. {1,2,3,4,5} (ordered naturals)
          R,            \* redundancy target
          Budget        \* how many departed nodes may be misread as intenders

ASSUME /\ R \in Nat
       /\ Budget \in Nat
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

\* Ground truth, not directly observable by any node.
TrueIntenders == holds \ declared
Departed      == Nodes \ holds

\* The gate as computed from the age-gated classification.  `M` is the set of
\* departed nodes this evaluation misreads as intenders.
EffCoverage(n, M) ==
    LET PerceivedHolders   == holds \cup M
        PerceivedIntenders == TrueIntenders \cup M
    IN  Cardinality( (PerceivedHolders \ {n})
                       \ { m \in PerceivedIntenders : m < n } )

Execute(n) ==
    /\ n \in holds \ declared
    /\ \E M \in SUBSET Departed :
         /\ Cardinality(M) <= Budget
         /\ \/ /\ EffCoverage(n, M) >= R
               /\ holds' = holds \ {n}
               /\ UNCHANGED declared
            \/ /\ EffCoverage(n, M) < R
               /\ declared' = declared \cup {n}
               /\ UNCHANGED holds

Next == \E n \in Nodes : Announce(n) \/ Execute(n)

Spec == Init /\ [][Next]_vars

------------------------------------------------------------------------------
SafeCoverage == Cardinality(holds) >= R
==============================================================================
