# Naming notes (exploratory — nothing decided)

**Working name: "polite shrink"** — the plain-English handle. Warm, and
non-technical readers get it immediately; keep it as the everyday name in code
and docs.

**Candidate formal name: VCAS — Vacate Collision Avoidance System.**

Why:

- The mechanism borrows its load-bearing idea from **TCAS** (aircraft *Traffic
  Collision Avoidance System*): when two agents with symmetric, stale
  information could conflict, a *deterministic tie-break* assigns complementary
  actions — one aircraft climbs, the other descends; here, the lowest-id node
  proceeds and the others defer. Echoing "…Collision Avoidance System" signals
  that lineage to anyone who knows it.
- But we can't reuse **TCAS** itself: it belongs to the aviation system and we
  would never rank for it in search.
- "**Vacate**" names what actually collides. TCAS prevents two aircraft from
  *arriving* at the same airspace; polite shrink prevents two custodians from
  *leaving* the same slice of the DHT at the same moment — overlapping
  departures that would leave data with zero copies. The colliding things are
  the vacate actions, so "Vacate" is the honest front word. (Note the neat
  inversion: TCAS prevents co-location; VCAS prevents co-*vacation*.)
- "V" is clean and uncontested — "VCAS" googles to almost nothing, so the
  pattern would own the term quickly.

Alternatives considered:

- **SCAS — Shard Collision Avoidance System** — hard-links to the well-known
  "sharding problem"; slightly looser literally (it is the *drops* that
  collide, not shards); note "SCAS" is also a UK ambulance service.
- **WCAS — Withdrawal Collision Avoidance System** — a node *withdraws*
  coverage; accurate, reads a touch more formal.
- **HCAS — Handoff Collision Avoidance System** — foregrounds the *cure*
  ("never leave before your replacement is confirmed") rather than the danger.

Letters avoided because of search collisions:

- **A**CAS — Airborne Collision Avoidance System (the international name for
  TCAS); and, to a UK audience, the Advisory, Conciliation and Arbitration
  Service.
- **D**CAS — NYC Department of Citywide Administrative Services.
- **E**CAS — the EU login / European Commission Authentication Service.
- **T**CAS — the aviation system itself.

**Status: exploratory.** "polite shrink" remains the working name until a
formal name is actually chosen.
