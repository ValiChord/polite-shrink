"""Hand-written mutation testing of the V6 sharding logic.

Each mutant is a realistic bug. It is applied, the tests are run, and the file
is restored. Stage 1: unit + model tests (`--lib sharding`). Stage 2, only for
mutants that survive stage 1: the functional tests that exercise the wiring.
"""
import pathlib, subprocess, sys, time, json

ROOT = pathlib.Path(sys.argv[1])
SRC = ROOT / "crates/gossip/src/sharding"
CTL, CFG, INT = SRC / "controller.rs", SRC / "config.rs", SRC / "intents.rs"

M = [
("count only lower-ID intenders (V6 becomes V3's count)", CTL,
 """        subtract_sectors(&mut eff, intent.vacate.0, intent.vacate.1);
        higher |= id > own_id;""",
 """        if id < own_id {
            subtract_sectors(&mut eff, intent.vacate.0, intent.vacate.1);
        }
        higher |= id > own_id;"""),
("proceed with one copy fewer than the target", CTL,
 """    if min_over(&eff, vacate.0, vacate.1) >= target_redundancy {
        Recheck::Proceed""",
 """    if min_over(&eff, vacate.0, vacate.1) >= target_redundancy.saturating_sub(1) {
        Recheck::Proceed"""),
("demand one copy more than the target", CTL,
 """    if min_over(&eff, vacate.0, vacate.1) >= target_redundancy {
        Recheck::Proceed""",
 """    if min_over(&eff, vacate.0, vacate.1) > target_redundancy {
        Recheck::Proceed"""),
("a middle racer waits too", CTL,
 """    } else if higher && !lower_racer(live_intents, own_id, vacate) {""",
 """    } else if higher {"""),
("wait even with no higher racer", CTL,
 """    } else if higher && !lower_racer(live_intents, own_id, vacate) {""",
 """    } else if !lower_racer(live_intents, own_id, vacate) {"""),
("adjacent ranges counted as overlapping", CTL,
 """    a.0.max(b.0) < a.1.min(b.1)""",
 """    a.0.max(b.0) <= a.1.min(b.1)"""),
("yield to HIGHER ids instead of lower", CTL,
 """        .any(|(id, i)| id < own_id && overlaps(i.vacate, vacate))""",
 """        .any(|(id, i)| id > own_id && overlaps(i.vacate, vacate))"""),
("refreshed intent expires too soon", CTL,
 """    (expires_at < next_check + wait).then(|| next_check + wait + wait)""",
 """    (expires_at < next_check + wait).then(|| next_check + wait)"""),
("refresh only after the intent has already lapsed", CTL,
 """    (expires_at < next_check + wait).then(|| next_check + wait + wait)""",
 """    (expires_at < next_check).then(|| next_check + wait + wait)"""),
("V3 re-check counts the agent's own intent", CTL,
 """        if id < own_id {
            subtract_sectors(&mut eff, intent.vacate.0, intent.vacate.1);
        }
    }
    min_over(&eff, vacate.0, vacate.1) >= target_redundancy""",
 """        if id <= own_id {
            subtract_sectors(&mut eff, intent.vacate.0, intent.vacate.1);
        }
    }
    min_over(&eff, vacate.0, vacate.1) >= target_redundancy"""),
("no announce-time yield", CTL,
 """                if lower_racer(live_intents, agent.agent(), (vs, ve)) {""",
 """                if false && lower_racer(live_intents, agent.agent(), (vs, ve)) {"""),
("waiting drops the pending shrink (wait becomes give-up)", CTL,
 """                    ctl.pending = Some(pending);
                    return;""",
 """                    let _ = pending;
                    return;"""),
("no withdrawal sent on stand-down", CTL,
 """                self.withdraw_intent(agent, pending.vacate, pending.expires_at)
                    .await;""",
 """"""),
("default re-check is V3", CFG,
 """            patient_lowest: true,""", """            patient_lowest: false,"""),
("default has no withdrawal", CFG,
 """            withdraw_on_stand_down: true,""", """            withdraw_on_stand_down: false,"""),
("sender address not checked", INT,
 """                && *url == intent.from
""", ""),
("withdrawal ignores which intent it names", INT,
 """is_some_and(|i| i.expires_at == expires_at)""", """is_some()"""),
("intent still live at its expiry instant", INT,
 """lock.retain(|_, i| i.expires_at > now);""", """lock.retain(|_, i| i.expires_at >= now);"""),
]

STAGE1 = ["cargo", "test", "-q", "-j", "3", "-p", "kitsune2_gossip", "--features", "sharding", "--lib", "sharding"]
STAGE2 = [
  ["cargo", "test", "-q", "-j", "3", "-p", "kitsune2_gossip", "--features", "sharding", "--test", "sharding_race", "forced_race_patient_lowest"],
  ["cargo", "test", "-q", "-j", "3", "-p", "kitsune2_gossip", "--features", "sharding", "--test", "sharding_cascade", "forced_cascade_spares_patient_lowest_v6"],
  ["cargo", "test", "-q", "-j", "3", "-p", "kitsune2_gossip", "--features", "sharding", "--test", "sharding_cascade", "higher_ids_yield"],
  ["cargo", "test", "-q", "-j", "3", "-p", "kitsune2_gossip", "--features", "sharding", "--test", "sharding_stale"],
  ["cargo", "test", "-q", "-j", "3", "-p", "kitsune2_gossip", "--features", "sharding", "--test", "sharding_storm"],
]

def run(cmd, timeout=1800):
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "timeout", ""
    out = r.stdout + r.stderr
    if "error[E" in out or "could not compile" in out and "test result" not in out:
        return "compile-error", out[-800:]
    return ("pass" if r.returncode == 0 else "fail"), out[-800:]

import os
ONLY = os.environ.get("ONLY")
if ONLY:
    keep = ONLY.split("|")
    M = [m for m in M if m[0] in keep]
results = []
for label, path, old, new in M:
    orig = path.read_text(encoding="utf-8")
    if old not in orig:
        results.append({"mutant": label, "stage1": "NOT APPLIED (text not found)"})
        print(f"!! {label}: text not found", flush=True)
        continue
    path.write_text(orig.replace(old, new, 1), encoding="utf-8", newline="\n")
    try:
        t0 = time.time()
        s1, tail = run(STAGE1)
        rec = {"mutant": label, "stage1": s1}
        if s1 == "pass":
            caught = None
            for cmd in STAGE2:
                s2, tail2 = run(cmd)
                if s2 != "pass":
                    caught = f"{cmd[-1]} ({s2})"
                    break
            rec["stage2"] = caught or "SURVIVED"
        rec["secs"] = round(time.time() - t0)
        results.append(rec)
        print(json.dumps(rec), flush=True)
    finally:
        path.write_text(orig, encoding="utf-8", newline="\n")

killed = sum(1 for r in results if r.get("stage1") == "fail" or (r.get("stage2") and r["stage2"] != "SURVIVED"))
applied = sum(1 for r in results if not r.get("stage1", "").startswith("NOT"))
print(f"\nkilled {killed} of {applied} applied mutants")
json.dump(results, open(ROOT.parent / os.environ.get("OUT", "mutation_results.json"), "w"), indent=1)
