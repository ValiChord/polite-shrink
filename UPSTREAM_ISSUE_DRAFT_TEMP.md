# Upstream drafts — NOT SENT. Two issues for `holochain/wind-tunnel`.

**Where:** <https://github.com/holochain/wind-tunnel/issues/new> — public, no issue template.
**Repo state (checked 2026-08-03):** public, issues enabled, not archived, last pushed the same day.
**Likely readers:** ThetaSinner (opened #214, #335 and kitsune2 #160), matthme (scoped #416), cdunster, jost-s, zippy.

**Suggested order: post ISSUE 2 first.** It is small, purely factual, costs them nothing to accept,
and is the thing that blocks a newcomer from running the harness at all. ISSUE 1 is the substantial
one and reads better as the second thing from someone who has already filed something useful.

**Everything below the `---` for each issue is the text to post.** Reword freely — it should sound
like you. Don't feel obliged to keep the tables if they feel heavy; the numbers matter more than
the formatting.

**When they reply:** bring the replies back rather than answering from these notes. Several claims
here have narrow caveats (one machine, one environment, fix-active runs) and the exact wording of
those caveats is doing real work.

**Deliberately NOT mentioned in either issue:** polite-shrink, sharding, kitsune2 #160. Both issues
stand on their own merits. Raising them together would make the fix look like a means to an end.

---

## ⚠️ Verification pass, 2026-08-04 — read this before posting

The previous version of this file contained four numbers that did not survive checking against
`wind-tunnel-patch/RESULTS_write_rate_sweep.txt`, plus two claims resting on logs that no longer
exist. All are corrected below. What changed and why:

| Was | Now | Why |
|---|---|---|
| `3 of 6` runs with complete coverage at 0 ms, caption "3 runs per rate" | **3 of 5**, caption states the real run counts | The results file holds **5** runs at 0 ms. The "6th" is §7.9's run where the **first version of my own patch** (no bounded fallback) made readers select nothing at all. That is my bug, not the write rate's — it cannot be counted against the scenario. |
| "roughly 10 entries/s versus 2 — about 5×" | **6.8/s full-arc, 10.8/s zero-arc → 3–5×** | 10/s is the top of the range. Means over the 0 ms runs: full-arc 2032 entries/300 s (n=10), zero-arc 3236/300 s (n=3). |
| "full-arc authors sit at 100%" | **99.8–100.0%** | Two full-arc rows at 250 ms are 99.8% and 99.9%. The separation is still clean (max zero-arc 99.1% < min full-arc 99.8%), but "100%" is not what was measured. |
| "Adding a pause and changing nothing else" | states that **all rows had the selection fix active**, and that two 0 ms rows used an earlier version of it | Not disclosing this leaves a hidden variable for a maintainer to find. The argument that it cannot affect any quoted number is now *in* the issue. |
| Error text ending `Expected Function(FunctionType { params: [I32, I32], results: [I64] })` | trimmed to the portion recorded in `PLAN_0.7_conductor_run.md` §7.1 while the log existed | That clause is not in the contemporaneous record and the logs are gone with `/tmp`. Do not quote reconstructed error text at maintainers. |
| "Across 9 earlier runs (27 reader draws)… a uniform draw would give about a third" | **removed** | Cannot be reconciled with §7.9's note that fresh-space 60 s runs found no peer at all, so some of those runs contributed zero draws. And "uniform draw" assumes the 27 draws are independent — which the very next clause ("all three readers picked the same peer") disproves. The direct `links.len()` measurement is a **mechanism** and is stronger than any statistic; it carries the section alone. |

**Verified correct and unchanged:** `BATCH_SIZE = 10` / `SLEEP_INTERVAL_WRITE_BEHAVIOUR_MS = 5_000`
in the sibling scenario; no sleep in `mixed_arc_get_agent_activity`; `create_sample_entry` writes one
entry per iteration; `shuffle`-then-`first` selection; `announce_write_behaviour` is a bare
`create_link` with no path anchor (which is what makes the `+5` chain-overhead arithmetic come out
right); the `hdk` workspace features; `flake.nix:62`; `WT_HOLOCHAIN_PATH` in the README; the
1618/3/0 and 1916/3/0 candidate-set counts; `ctx.agent_index()` is a real framework API.

**ISSUE 2 is now proved from the binaries, not from a failed run.** Reproducible in 30 seconds:

```bash
gh release download holochain-0.7.0 --repo holochain/holochain \
  -p 'holochain-x86_64-unknown-linux-gnu' -p 'holochain-unstable-x86_64-unknown-linux-gnu'
for b in holochain-x86_64-unknown-linux-gnu holochain-unstable-x86_64-unknown-linux-gnu; do
  echo "== $b"; strings -n 8 "$b" | grep -oE '__hc__(sleep|accept_countersigning_preflight_request)_1' | sort -u
done
# holochain-...          : (nothing)
# holochain-unstable-... : __hc__sleep_1
```

`__hc__sleep_1` is `#[cfg(feature = "unstable-functions")]` and
`__hc__accept_countersigning_preflight_request_1` is `#[cfg(feature = "unstable-countersigning")]`
— both at `crates/holochain/src/core/ribosome/real_ribosome.rs:509–516`, tag `holochain-0.7.0`.
So the "unstable" asset **was** built with `unstable-functions` and **was not** built with
`unstable-countersigning`. That is a symbol-table fact, not an anecdote.

**Anchoring changed.** #214 and #416 are both **closed**. **#335 is OPEN**, is the issue this
scenario was built to satisfy, asks in terms for *"the delay between data being authored and first
being available to the 0-arc nodes"*, and ThetaSinner's only comment on it is *"what remains to
complete this ticket?"* Both issues below now lead with #335.

🆕 **Near-duplicate found on their tracker — #431, fixed by PR #506 (merged Feb 2026).** Their
CONTRIBUTING says to search existing issues first; this is what that search turned up, and ISSUE 1
now cites it rather than walking into it.

- **It corroborates us, in their own words.** #506's analysis says querying for the write peer
  *"usually takes 3 minutes to complete, but it's not deterministic. Sometimes it takes seconds,
  sometimes it takes 7 minutes."* That is the same propagation race, observed from the other side.
  Citing it makes ISSUE 1 read as building on what they already found rather than as a discovery.
- **It does not pre-empt us.** Their model was "the zome call times out"; the fix was a 15 s
  `call_zome_with_options` timeout. Our runs are on `e4861457`, i.e. **after** that fix, and nothing
  was timing out — the calls returned promptly with **0** candidates ~1600 times, then exactly 1.
  A shorter timeout cannot help a call that succeeds and returns a degenerate set.
- ⚠️ **Without this citation the likely reply is "we fixed that in #506"** and the issue dies.
- 🆕 Also verified while checking: #506's timeout landed on `write_validated_must_get_agent_activity`
  **only**; `mixed_arc_get_agent_activity`, `mixed_arc_must_get_agent_activity`,
  `write_get_agent_activity` and `write_get_agent_activity_volatile` all still use plain `call_zome`.
  Raised in the issue as a question, not a finding — we did not measure whether it matters.

**Duplicate search, per their CONTRIBUTING** (`repo:holochain/wind-tunnel is:issue`): zero hits for
`unstable-countersigning`, `WT_HOLOCHAIN_PATH`, `unknown import`, `write_peer`, `throttle`; one hit
for `get_random_agent_with_write_behaviour` — #431, handled above. **Neither issue is a duplicate.**

---

## 📋 The text to post lives in `upstream-issues/` — not in this file

This file is the **working record**: why each number is what it is, what was corrected, what was
searched. The postable text was split out on 2026-08-04 so there is **one** copy of each issue and
it cannot drift from the record.

| file | post to | order |
|---|---|---|
| `upstream-issues/issue-2-released-binaries-unstable-countersigning.md` | <https://github.com/holochain/wind-tunnel/issues/new> | **first** |
| `upstream-issues/issue-1-mixed-arc-selection-and-write-rate.md` | same | second |

Each file is **select-all, paste-into-the-body**. The title sits in an HTML comment at the top —
GitHub does not render HTML comments, so pasting the whole file leaves nothing visible; copy the
title separately into the title field.

## Their CONTRIBUTING rules, checked 2026-08-04

**Issues** — three lines, all satisfied: use Issues for bugs/features; **search existing issues
first** (done, recorded above — #431 is the only near-hit and ISSUE 1 now cites it); **include
reproduction steps** (ISSUE 2 has the `strings` command, ISSUE 1 has their own documented scenario
invocation).

⚠️ **PRs are a much higher bar — read before acting on either issue's "happy to open a PR" line:**

- Conventional Commits, atomic commits, **rebase never merge**, `fixup!` commits during review.
- The PR template requires *"I ran the Nomad CI workflow successfully on my branch"* — **that is
  their infrastructure and we probably cannot.** Know this before volunteering.
- *"We will reject PRs that are purely cosmetic and appear to have been automated with tooling."*
- *"All AI-generated PRs must have been self-reviewed. If a PR is judged to be AI-generated, not
  checked by the author, and needs a lot of work… we will close the PR without comment."* This is
  not a ban on AI-assisted work — they explicitly accommodate it (*"AI tooling may add an in-depth
  summary below your description"*) provided the description itself is hand-written. The patch here
  was run six times and its numbers re-derived from raw logs, which meets that bar — but any PR
  description must be Ceri's own words.

**Recommendation: file the issues, do not offer a PR yet.** Let them ask. The Nomad checklist item
alone makes an unsolicited PR awkward, and both issues stand on their own.

## 🔴 One decision still open

Both issues end with an offer to open a PR, which is **inconsistent with the recommendation above**.
Either drop the line, or make it honest:

> Happy to open a PR if it'd help, though I can't run the Nomad CI workflow your PR template asks for.

Not changed unilaterally — it is the only sentence in either issue that commits Ceri to future work.

## Repo facts, verified 2026-08-04

- `holochain/wind-tunnel`: public, issues enabled, not archived, **no issue template**, **no
  Discussions tab**, default branch `main`, 46 open issues.
- Recent open issues are all filed by maintainers (ThetaSinner, cdunster, jost-s, zippy, mattyg).
  An outside report is unusual here — do not read a slow reply as a verdict.
