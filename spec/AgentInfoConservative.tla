--------------------------- MODULE AgentInfoConservative ---------------------------
(***************************************************************************)
(* Polite shrink with NO dedicated intent message: the vacate intent is     *)
(* carried by the arc claim that kitsune2 already gossips                   *)
(* (`AgentInfo.storage_arc`, crates/api/src/agent.rs).  Announcing means    *)
(* publishing the REDUCED arc while continuing to hold the data; executing  *)
(* means actually dropping it.                                              *)
(*                                                                          *)
(* Modelling the encoding:                                                  *)
(*  - `holds`    = nodes really storing the sector (ground truth).          *)
(*  - `declared` = nodes whose published arc claims the sector.             *)
(*  - An honest node never claims more than it holds, so declared \subseteq *)
(*    holds.  During the wait it claims LESS than it holds.                 *)
(*  - Announce   = leave `declared`, stay in `holds`.                       *)
(*  - Execute    = leave `holds` (proceed), or re-publish the wider arc     *)
(*                 (cancel).                                                *)
(*                                                                          *)
(* THE HARD PART this spec exists to test.  With a dedicated ShrinkIntent   *)
(* message a peer can tell "announced but still holding" from "already      *)
(* gone".  With the arc claim alone it CANNOT: both are simply absent from  *)
(* `declared`.  So the TCAS lower-id tie-break -- which needs to know who   *)
(* is an intender -- has no input.                                          *)
(*                                                                          *)
(* ENCODING A (this file) gives the tie-break up and reads only what is     *)
(* actually observable: proceed iff at least R OTHER nodes are still        *)
(* claiming the sector right now.  Every un-declared node is treated as     *)
(* already gone, which is the conservative direction.                       *)
(*                                                                          *)
(* SAFETY (checked exhaustively by TLC): the sector never holds < R real    *)
(* copies.  Note this holds for a structural reason -- declared \subseteq   *)
(* holds and n \notin declared, so the R survivors it counts are real ones. *)
(* The cost is liveness, not safety: if enough nodes announce at once,      *)
(* every one of them cancels and retries.  That retry cost is measured in   *)
(* the simulation, not here.                                                *)
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
          /\ declared \subseteq holds   \* never claim more than you hold

Init == /\ holds    = Nodes
        /\ declared = Nodes

\* Phase 1: publish the reduced arc.  Still holding.
Announce(n) ==
    /\ n \in declared
    /\ declared' = declared \ {n}
    /\ UNCHANGED holds

\* What an executing node can actually see: who is claiming the sector now.
\* n has already un-declared, so n is not in this set and needs no
\* self-subtraction -- the "discount your own stale declaration" step of the
\* original gate drops out of this encoding for free.
EffCoverage(n) == Cardinality(declared)

\* Phase 2: after the wait, re-check and either drop or re-publish.
Execute(n) ==
    /\ n \in holds \ declared
    /\ \/ /\ EffCoverage(n) >= R              \* safe: vacate
          /\ holds' = holds \ {n}
          /\ UNCHANGED declared
       \/ /\ EffCoverage(n) < R               \* not safe: re-publish, keep storing
          /\ declared' = declared \cup {n}
          /\ UNCHANGED holds

Next == \E n \in Nodes : Announce(n) \/ Execute(n)

Spec == Init /\ [][Next]_vars

------------------------------------------------------------------------------
\* The property under test: the sector never drops below R real copies.
SafeCoverage == Cardinality(holds) >= R
==============================================================================
