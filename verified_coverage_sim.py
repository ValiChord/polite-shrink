"""
Stage-3 follow-up: verified coverage — the pessimistic shrink sensor.

The serve-audit (defense_sim.py) is *optimistic*: every declared peer counts
toward coverage, and a liar is only subtracted once an auditor has caught it.
Between a liar's arrival and its detection there is a window in which its
phantom copies inflate the sensor and an honest agent may shrink onto them.
REPORT_stage3.md §6 named the residual: "a *deployed* network's honest margin
today is still R - K."

This study inverts the trust default. Under **verified coverage** a peer
counts toward an agent's coverage *only while that agent holds a fresh
proof-of-serve from it* — a successful audit within `proof_ttl` ticks. A liar
can never produce a proof, so it contributes zero from the first tick: there
is no detection-lag window and no K = R threshold. The shrink safety re-check
(`_execute_intent`) then vacates only when *proven* coverage stays >= R, so a
shrinker never leans on a copy it has not verified.

The price is pessimism. An *honest* peer you have not re-audited inside the TTL
also stops counting, so the sensor undercounts and the controller
over-provisions unless the audit budget keeps enough peers fresh. The
safety-vs-efficiency trade is exactly what we measure:

  1. safety vs K liars: true coverage under {declared, reactive-exclusion,
     verified}, K in {0, R-1, R, 2R, 3R}. Expect declared to collapse at
     K >= R (Stage-3b), exclusion to recover with lag, verified to show no
     threshold at all.
  2. cost of pessimism (honest network, K = 0): how far verified coverage
     suppresses sharding vs declared coverage, and how audit budget
     (`audit_per_epoch`) and freshness (`proof_ttl`) buy the efficiency back.

Modelling granularity (stated, matching defense_sim.py): a liar stores nothing
and fails every audit; a successful audit certifies the peer's whole declared
arc for the TTL. Partial liars (store a strategic fraction, serve some
challenges) need per-sector proofs and are left as future work — the modelled
threat is the full-arc liar of §6.2, the one that is invisible to declared
coverage.

Usage:   python3 verified_coverage_sim.py [--quick]
Output:  results/verified_coverage.png, results/verified_summary.md,
         results/verified.json
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict

import numpy as np

from polite_shrink import Config, Sim, block, make_world
from byzantine_sim import ByzantineSim, V3, pick_byz
from defense_sim import DefenseSim
from ext_common import ALERT, BASELINE, INK, MUTED, SERIES, VARIANT_COLOR, plt


class VerifiedCoverageSim(DefenseSim):
    """DefenseSim with the coverage sensor inverted to proof-gated counting.

    A declared peer contributes to an agent's coverage view only while the
    agent holds a proof-of-serve for it minted within `proof_ttl` ticks.
    Proofs are minted by the same random audits DefenseSim already models
    (honest peers pass and are certified; liars fail and are never certified).
    DefenseSim's own optimistic audit loop is disabled (`audit_from=None`);
    this class runs its own minting loop instead, so the two policies never
    audit twice off the same RNG stream.
    """

    def __init__(self, cfg, variant, events, initial, joins, byz_ids, mode,
                 proof_ttl=600, audit_per_epoch=6, mint_from=0, **kw):
        super().__init__(cfg, variant, events, initial, joins, byz_ids, mode,
                         audit_from=None, audit_per_epoch=audit_per_epoch, **kw)
        self.proof_ttl = proof_ttl
        self.mint_from = mint_from
        # observer -> {peer: tick last certified}. Pruned lazily on read.
        self.proofs: dict[int, dict[int, int]] = defaultdict(dict)
        self.m.mean_proven = []

    # --- verified coverage: rebuild cov from self + fresh-proof peers -----
    def _view(self, a):
        # Take the raw stale declared snapshot (skip DefenseSim's exclusion,
        # which is empty here and superseded by proof-gating).
        cov, lvl, icov, ilist = Sim._view(self, a)
        vcov = np.zeros(self.cfg.sectors, dtype=np.int16)

        # self always counts — at the level peers saw me declare (same basis
        # as the declared snapshot, so _decide's own-copy subtraction holds).
        own = int(lvl[a.aid])
        if own >= 0:
            s_, e_ = block(a.home, own, self.cfg.log2s)
            vcov[s_:e_] += 1

        mine = self.proofs.get(a.aid)
        if mine:
            stale = []
            for x, pt in mine.items():
                if self.t - pt > self.proof_ttl:
                    stale.append(x)
                    continue
                xl = int(lvl[x])
                if xl < 0:
                    continue            # peer not declared in this stale view
                s_, e_ = block(self.agents[x].home, xl, self.cfg.log2s)
                vcov[s_:e_] += 1
            for x in stale:             # lazy prune keeps the dict fresh-sized
                del mine[x]
        return vcov, lvl, icov, ilist

    # --- minting: honest audits certify honest peers for the TTL ----------
    def step(self):
        if self.t >= self.mint_from:
            idx = (self.t - 1) % self.H if self.t else 0
            lvl_now = self.lvl_h[idx]
            declared = np.nonzero(lvl_now[:len(self.agents)] >= 0)[0]
            if len(declared):
                for a in self.agents:
                    if (not a.alive or a.aid in self.byz_ids
                            or self.t % self.cfg.eval_every != a.phase):
                        continue
                    for _ in range(self.audit_per_epoch):
                        x = int(declared[self._audit_rng.integers(
                            0, len(declared))])
                        if x == a.aid or x in self.byz_ids:
                            continue    # self / liar: no proof minted
                        self.proofs[a.aid][x] = self.t
        super().step()                  # DefenseSim.step (audit_from=None) -> world
        honest = [a for a in self.agents
                  if a.alive and a.aid not in self.byz_ids]
        fresh = sum(
            sum(1 for pt in self.proofs.get(a.aid, {}).values()
                if self.t - pt <= self.proof_ttl)
            for a in honest)
        self.m.mean_proven.append(fresh / max(1, len(honest)))


# ------------------------------------------------------------- studies
POLICIES = ("declared", "reactive-exclusion", "verified")


def make_policy_sim(policy, cfg, events, initial, joins, byz_ids, mode,
                    proof_ttl=600, audit_per_epoch=6, audit_from=0):
    if policy == "declared":
        return ByzantineSim(cfg, V3, events, initial, joins,
                            byz_ids=byz_ids, mode=mode)
    if policy == "reactive-exclusion":
        return DefenseSim(cfg, V3, events, initial, joins, byz_ids=byz_ids,
                          mode=mode, audit_from=audit_from,
                          audit_per_epoch=audit_per_epoch)
    if policy == "verified":
        return VerifiedCoverageSim(cfg, V3, events, initial, joins,
                                   byz_ids=byz_ids, mode=mode,
                                   proof_ttl=proof_ttl,
                                   audit_per_epoch=audit_per_epoch,
                                   mint_from=0)
    raise ValueError(policy)


def run_safety(cfg, ks, seeds, ticks=2600, audit_per_epoch=6):
    """True coverage vs number of full-arc liars K, one row per policy."""
    rows = []
    for policy in POLICIES:
        for k in ks:
            tf_end, tz_end, lvl_end, sync_end = [], [], [], []
            for seed in seeds:
                c = Config(seed=seed, log2s=cfg.log2s, n_agents=cfg.n_agents,
                           redundancy=cfg.redundancy)
                initial, events, joins = make_world(c, ticks)
                byz = set(pick_byz(c, k, c.n_agents)) if k else set()
                sim = make_policy_sim(policy, c, events, initial, joins, byz,
                                      "liar", audit_per_epoch=audit_per_epoch)
                m = sim.run(ticks)
                # average the tail so a single-tick wobble does not decide it
                tf_end.append(float(np.mean(m.true_floor[-200:])))
                tz_end.append(float(np.mean(m.true_zero[-200:])))
                lvl_end.append(m.mean_level[-1])
                sync_end.append(m.cum_sync[-1])
            row = {
                "policy": policy, "K": k,
                "true_floor_end": float(np.mean(tf_end)),
                "true_zero_end": float(np.mean(tz_end)),
                "true_zero_frac": float(np.mean(tz_end)) / cfg.sectors,
                "mean_level_end": float(np.mean(lvl_end)),
                "sync_end": float(np.mean(sync_end)),
            }
            rows.append(row)
            print(f"  safety {policy:20s} K={k:3d}  "
                  f"true_floor={row['true_floor_end']:.1f} "
                  f"true_zero={row['true_zero_end']:.0f} "
                  f"({row['true_zero_frac']:.1%}) "
                  f"level_end={row['mean_level_end']:.2f} "
                  f"sync={row['sync_end']:.0f}", flush=True)
    return rows


def run_overhead(cfg, budgets, ttls, seed=42, ticks=2600):
    """Honest network (K=0): the storage-efficiency price of verified
    coverage vs the declared-coverage baseline, over audit budget and TTL."""
    rows = []
    initial, events, joins = make_world(Config(seed=seed), ticks)
    base = ByzantineSim(Config(seed=seed), V3, events, initial, joins,
                        byz_ids=set(), mode="liar").run(ticks)
    base_row = {"policy": "declared", "audit_per_epoch": None, "proof_ttl": None,
                "mean_level_end": base.mean_level[-1], "sync_end": base.cum_sync[-1]}
    rows.append(base_row)
    print(f"  overhead declared (baseline)      "
          f"level_end={base_row['mean_level_end']:.2f} "
          f"sync={base_row['sync_end']:.0f}", flush=True)
    for ape in budgets:
        for ttl in ttls:
            c = Config(seed=seed)
            initial, events, joins = make_world(c, ticks)
            sim = VerifiedCoverageSim(c, V3, events, initial, joins,
                                      byz_ids=set(), mode="liar",
                                      proof_ttl=ttl, audit_per_epoch=ape)
            m = sim.run(ticks)
            row = {"policy": "verified", "audit_per_epoch": ape, "proof_ttl": ttl,
                   "mean_level_end": m.mean_level[-1], "sync_end": m.cum_sync[-1],
                   "mean_proven_end": m.mean_proven[-1]}
            rows.append(row)
            print(f"  overhead verified ape={ape} ttl={ttl:4d}   "
                  f"level_end={row['mean_level_end']:.2f} "
                  f"sync={row['sync_end']:.0f} "
                  f"proven_end={row['mean_proven_end']:.1f}", flush=True)
    return rows


# ------------------------------------------------------------- plot
def plot(safety, overhead, cfg, out):
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2))
    fig.suptitle("Verified coverage: proof-gated shrink sensor closes the "
                 "liar window", fontsize=12, fontweight="bold", color=INK)
    ax_floor, ax_zero, ax_cost = axes.flat
    colors = {"declared": SERIES[0], "reactive-exclusion": SERIES[1],
              "verified": VARIANT_COLOR[V3.name]}

    ks = sorted({r["K"] for r in safety})
    for policy in POLICIES:
        rs = sorted((r for r in safety if r["policy"] == policy),
                    key=lambda r: r["K"])
        ax_floor.plot(ks, [r["true_floor_end"] for r in rs], marker="o", ms=5,
                      lw=1.8, color=colors[policy], label=policy)
        ax_zero.plot(ks, [r["true_zero_frac"] for r in rs], marker="o", ms=5,
                     lw=1.8, color=colors[policy], label=policy)
    ax_floor.axhline(cfg.redundancy, color=BASELINE, lw=1, ls="--")
    ax_floor.axvline(cfg.redundancy, color=ALERT, lw=1, ls="--")
    ax_floor.text(cfg.redundancy + 0.2, 1, "K = R", color=ALERT, fontsize=8)
    ax_floor.set_title("True redundancy floor vs K liars")
    ax_floor.set_xlabel("K full-arc liars")
    ax_floor.set_ylabel("true copies (tail mean)")
    ax_floor.legend(fontsize=8, loc="center right")
    ax_zero.axvline(cfg.redundancy, color=ALERT, lw=1, ls="--")
    ax_zero.set_title("Fraction of ring with 0 true copies")
    ax_zero.set_xlabel("K full-arc liars")
    ax_zero.set_ylabel("fraction")
    ax_zero.legend(fontsize=8, loc="upper left")

    base = next(r for r in overhead if r["policy"] == "declared")
    ver = [r for r in overhead if r["policy"] == "verified"]
    ttls = sorted({r["proof_ttl"] for r in ver})
    budgets = sorted({r["audit_per_epoch"] for r in ver})
    for ttl in ttls:
        rs = sorted((r for r in ver if r["proof_ttl"] == ttl),
                    key=lambda r: r["audit_per_epoch"])
        ax_cost.plot([r["audit_per_epoch"] for r in rs],
                     [r["mean_level_end"] for r in rs], marker="s", ms=5,
                     lw=1.6, label=f"verified, TTL={ttl}")
    ax_cost.axhline(base["mean_level_end"], color=SERIES[0], lw=1.4, ls="--",
                    label="declared (no audit)")
    ax_cost.set_title(f"Honest-network cost (K=0): mean arc level\n"
                      f"({cfg.log2s} = full ring = sharding off)")
    ax_cost.set_xlabel("audits per agent-epoch")
    ax_cost.set_ylabel("mean level end")
    ax_cost.legend(fontsize=7, loc="upper right")
    for ax in axes.flat:
        ax.grid(True, axis="y")
        ax.margins(x=0.02)
    fig.tight_layout(rect=[0, 0, 1, 0.92])
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"wrote {out}")


def main():
    quick = "--quick" in sys.argv
    cfg = Config()
    R = cfg.redundancy
    ks = [0, R - 1, R, 2 * R, 3 * R]
    seeds = [42] if quick else [42, 7, 99]
    ticks = 2000 if quick else 2600
    budgets = [3, 6] if quick else [2, 4, 6, 10]
    ttls = [600] if quick else [300, 600]

    print("study: safety vs K liars")
    safety = run_safety(cfg, ks, seeds, ticks=ticks)
    print("study: cost of pessimism (honest network)")
    overhead = run_overhead(cfg, budgets, ttls, ticks=ticks)

    with open("results/verified.json", "w") as f:
        json.dump({"safety": safety, "overhead": overhead,
                   "R": R, "seeds": seeds, "ticks": ticks}, f, indent=1)

    with open("results/verified_summary.md", "w") as f:
        f.write("# Verified coverage — proof-gated shrink sensor\n\n"
                "A declared peer counts toward coverage only while a fresh "
                "proof-of-serve (successful audit within `proof_ttl`) backs "
                "it. Liars never earn a proof, so they never count.\n\n"
                f"## Safety vs K full-arc liars (R={R}, seeds {seeds}, tail-mean "
                "of true coverage)\n\n"
                "| policy | K | true floor | true-zero sectors | ring 0-copy | "
                "mean level end | sync |\n|---|---|---|---|---|---|---|\n")
        for r in safety:
            f.write(f"| {r['policy']} | {r['K']} | {r['true_floor_end']:.1f} | "
                    f"{r['true_zero_end']:.0f} | {r['true_zero_frac']:.1%} | "
                    f"{r['mean_level_end']:.2f} | {r['sync_end']:.0f} |\n")
        f.write("\n## Cost of pessimism — honest network, K=0 "
                "(mean arc level: lower = more sharding)\n\n"
                "| policy | audits/epoch | proof TTL | mean level end | sync | "
                "mean proven peers |\n|---|---|---|---|---|---|\n")
        for r in overhead:
            f.write(f"| {r['policy']} | {r.get('audit_per_epoch')} | "
                    f"{r.get('proof_ttl')} | {r['mean_level_end']:.2f} | "
                    f"{r['sync_end']:.0f} | "
                    f"{r.get('mean_proven_end', float('nan')):.1f} |\n")
    print("wrote results/verified_summary.md")
    plot(safety, overhead, cfg, "results/verified_coverage.png")


if __name__ == "__main__":
    main()
