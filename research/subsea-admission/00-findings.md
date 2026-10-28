# Subsea supervisory capacity admission: screening verdict

2026-10-28. Screening only: no new model or code was written, because nothing here changes the
protocol-level results already recorded in `../leo-admission/00-findings.md` (sections 2-4, 8-12).
External research was two web searches (below); everything not cited is **inference** or
**unknown** and is labelled so.

**Recommendation: STOP** (for the product framing); revisit only if the unknowns at the end are answered.

## Gate 1: what the LEO "failure" actually was

The briefs treat LEO as "StaleCap failed testing". That overstates it; the record shows three separate things:
1. **V3 (lowest-ID tie-break) breaches the ceiling** with no fault at all (TLC and simulation). General protocol flaw, already repaired by V6/V7. The Rust fork's `grow_recheck` still uses the V3 rule (opt-in path).
2. **V6/V7 hold the ceiling only while every delay is within L**, and with a consistent view or an intent that outlives its commit. Breaches of about one unit appear in simulation once delays exceed L. This is an assumption, not a defect, and it transfers to any domain.
3. **No advantage was found over escrow or static quotas** except in one regime (V7 plus recent-contact, overload, permanent node loss) that relies on an idealised stale-view detector.

So the failure was a failed *advantage* gate, not a broken ceiling. It applies to subsea unchanged,
because the dependence on a trustworthy delay bound is a property of the protocol. [T/sim; see LEO findings]

## Gate 3: is there a coordination gap in subsea allocation?

What the sources support, and what they do not:

| Question | Evidence | Label |
|---|---|---|
| Who commands chokes and valves? | A topside Master Control Station "controls and retrieves data from subsea equipment" and processes user commands for chokes and valves over the umbilical; Baker Hughes' Aptara MCS monitors control and communication health ([Baker Hughes Aptara MCS](https://www.bakerhughes.com/subsea/subsea-production-systems/subsea-production-control-systems/aptara-master-control-station), [US 12037864](https://patents.google.com/patent/US12037864)) | Documented (vendor page and patent) |
| What happens on loss of communication? | One patent proposes fail-as-is on loss of electrical power or communication, fail-closed on loss of hydraulic pressure ([US 9273536](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/9273536)). That is a proposal in a patent, not a statement of industry practice | Weak (patent) |
| Who optimises across wells? | Topside, model-based: a Cybernetica case adjusts a subsea choke and the topside choke together to hold separator pressure at a processing constraint ([Cybernetica case](https://cybernetica.no/cybe_case/topside-oil-and-gas-seperation-processes/)); FPSO guidance aligns topside setpoints with subsea chokes ([Rigzone](https://www.rigzone.com/insights/how-it-works-3/how-are-fpso-facilities-prepared-for-production-optimization-558)) | Documented (vendor case, trade article) |
| Is shared-capacity contention a real problem? | A summary of a paper on Norwegian gas says constraints often come from restricted *access* to processing and export capacity through allocation mechanisms ([SynapseSocial summary](https://www.synapsesocial.com/papers/69db380f4fe01fead37c6392)). That is inter-owner/commercial allocation, not SCM-to-SCM races, and I read only a summary | Weak; different layer |
| Do wells/SCMs independently authorise production increases? | Nothing found | **Unknown**; sources point the other way |

**Inference (not verified):** the resource owner already sits where the budget is. The shared
ceiling (separator, compression, export) is measured and known topside, and the entity that
commands the chokes is also topside. As in the single-satellite case, a resource with a local
owner needs no distributed admission. The brief's premise that wells hold their own export
allocations looks unsupported.

**Second problem, specific to this domain.** The protocol's selling point is continued admission
during a link outage. For production *increases*, the sensible behaviour on losing the host is the
reverse: stop increasing, because the true ceiling C can move (a compressor trip, a separator
constraint) and is only known topside. The protocol assumes a fixed C and has no response to C
falling below existing commitments. A quota-plus-"no increases without a fresh host grant" rule
is simpler, hard-ceiling, and fails closed. **[inference]**

## Gate 5: alternatives (reasoned, not simulated)

| Approach | Ceiling under comms loss | Fit |
|---|---|---|
| Central admission at the MCS | Holds; admissions stop when unreachable | Already where the authority is |
| Preallocated quotas, renewed by the host | Hard, no timing assumption; unused share idle | Simplest; matches fail-closed |
| Escrow-style rights transfer | Hard ceiling, but transfers need links and recovery needs agreement | Adds machinery without an owner problem |
| StaleCap V6/V7 | Holds only if delay is bounded by L | Needs a bound the umbilical may meet, acoustic fallback may not **[unknown]** |

## What was not done, and why

- No TLA+ or Rust for subsea: the protocol results are domain-independent, and no decentralised decision-maker exists to model.
- No safety-boundary claims beyond the briefs' own: the layer would have to sit entirely outside ESD/HIPPS; nothing here argues otherwise.
- No supplier, standards (IEC 61508/61511, API 17 series) or incident research, no outreach.

## Strongest argument for continuing

If a field has a genuinely decentralised arrangement (several operators' tiebacks into one host with
limited host connectivity, or autonomous subsea processing hubs), the topside-owner argument
weakens and a bounded-delay admission rule could matter. I found no evidence such an arrangement
exists or is wanted.

## Unknowns that would reopen this

1. A documented architecture where subsea units, not the host, grant production increments.
2. A measured upper bound on supervisory message delay (umbilical and acoustic fallback) with its exceedance rate.
3. A stated operator requirement to keep admitting increases while the host is unreachable.
