-------------------------------- MODULE PoliteShrink --------------------------------
(***************************************************************************)
(* Formal safety model of the "polite shrink" two-phase vacate rule, for a *)
(* single contested DHT sector.  N nodes each initially store the sector.   *)
(*                                                                          *)
(* Why one sector is enough: the safety property is per-sector.  For any    *)
(* given sector, the nodes covering it independently decide whether to drop *)
(* it; the arc geometry only decides *which* nodes contest *which* sector.  *)
(* Prove no sector is driven below R and you have proved it for the ring.   *)
(*                                                                          *)
(* Modelling the two phases:                                                *)
(*  - Announce is left UNCONSTRAINED.  A node's real trigger is an          *)
(*    optimistic, possibly-stale coverage estimate, so the worst case is    *)
(*    that every holder announces; the safety argument must not lean on the *)
(*    trigger being right.  A node still STORES while it intends.           *)
(*  - Execute reads the CURRENT holds and intend sets -- no staleness at    *)
(*    execute time.  This is exactly what the "wait 2x max gossip lag"      *)
(*    delay buys: by the time you act, every concurrent intent is visible.  *)
(*  - The TCAS-style tie-break: an executing node treats every LOWER-ID     *)
(*    intender as already gone, and proceeds only if >= R copies would      *)
(*    still remain.  So the lowest-id intender subtracts nobody and may go; *)
(*    higher ids subtract it and defer.  Departures serialise.              *)
(*                                                                          *)
(* SAFETY (checked exhaustively by TLC): the sector never holds < R real    *)
(* copies.  This is the per-sector form of the sweep's 0-loss-in-1248-runs  *)
(* result -- here a proof over every reachable state for small N, not a     *)
(* sample.                                                                   *)
(***************************************************************************)
EXTENDS Naturals, FiniteSets

CONSTANTS Nodes,        \* set of node ids, e.g. {1,2,3,4,5} (ordered naturals)
          R             \* redundancy target

ASSUME /\ R \in Nat
       /\ Nodes \subseteq Nat

VARIABLES holds,        \* nodes currently storing the sector
          intend        \* holders that have announced a vacate intent

vars == <<holds, intend>>

TypeOK == /\ holds  \subseteq Nodes
          /\ intend \subseteq holds

Init == /\ holds  = Nodes
        /\ intend = {}

Announce(n) ==
    /\ n \in holds
    /\ n \notin intend
    /\ intend' = intend \cup {n}
    /\ UNCHANGED holds

LowerIntenders(n) == { m \in intend : m < n }

\* Coverage the sector retains if n leaves and every lower-id intender leaves too.
EffCoverage(n) == Cardinality( (holds \ {n}) \ LowerIntenders(n) )

Execute(n) ==
    /\ n \in intend
    /\ \/ /\ EffCoverage(n) >= R              \* safe: vacate
          /\ holds'  = holds  \ {n}
          /\ intend' = intend \ {n}
       \/ /\ EffCoverage(n) < R               \* not safe: cancel, keep storing
          /\ intend' = intend \ {n}
          /\ UNCHANGED holds

Next == \E n \in Nodes : Announce(n) \/ Execute(n)

Spec == Init /\ [][Next]_vars

------------------------------------------------------------------------------
\* The property under test: the sector never drops below R real copies.
SafeCoverage == Cardinality(holds) >= R
==============================================================================
