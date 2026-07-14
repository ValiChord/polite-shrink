"""
Stage-3 follow-up: partial liars against verified coverage.

verified_coverage_sim.py closed the *full-arc* liar (stores nothing, fails
every audit) and named the open edge: a **partial liar** that stores a
strategic fraction of its declared arc and can therefore serve *some*
challenges. This study models it and measures where the guarantee ends.

The audit is a *sampled range-check*, which is what a real one must be: a
peer's declared arc is unbounded (it covers content that doesn't exist yet),
so an auditor challenges `audit_samples` random sectors of it; serve them all
and you are certified for that arc for `proof_ttl` ticks. This is the honest
middle between the two extremes — whole-arc trust from one success (too
credulous) and per-sector proofs (so pessimistic the network never shards).

The consequence for a liar that truly holds a fraction p of its declared arc:
it passes a c-sample audit with probability p^c. So

  * a full-arc liar (p=0) is caught by any single sample (c>=1) — the
    verified_coverage_sim result;
  * an honest peer (p=1) always certifies, so honest networks shard normally;
  * a *partial* liar sits in between: with probability p^c it certifies and is
    then trusted over its whole declared arc, including the sectors it does NOT
    hold — which is exactly the coverage it can inflate, and the loss it can
    induce.

Two questions:

  A. STATIC sweep of held fraction p at fixed sample count c: how does the
     damage compare, declared vs verified? (Prediction: declared is fooled in
     proportion to what the liars withhold; verified degrades far more gently,
     worst at the *intermediate* p where a liar both certifies often and still
     withholds meaningful coverage.)

  B. STRINGENCY: at an evasion-prone p, sweep the sample count c. More samples
     = exponentially lower evasion (p^c) = the tunable knob that buys the
     partial-liar defense back, at more audit bandwidth.

Ground truth (`true_floor`/`true_zero`) counts honest holders **plus each
liar's real holdings**. Determinism holds (audit + holdings RNGs seeded). The
temporal "prove-then-drop" trojan (certify, then abandon within the TTL) is a
distinct, liveness-flavoured attack and is left as stated future work.

Usage:   python3 partial_liar_sim.py [--quick]
Output:  results/partial_liar.png, results/partial_summary.md,
         results/partial_liar.json
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict

import numpy as np

from polite_shrink import Config, Sim, block, make_world
from byzantine_sim import ByzantineSim, V3, pick_byz
from ext_common import ALERT, BASELINE, INK, MUTED, SERIES, VARIANT_COLOR, plt


class PartialLiarSim(ByzantineSim):
    """Liars that truly store a fraction of their declared full arc, audited
    by a c-sample range-check.

    policy "declared": trust declared arcs (the Stage-1 sensor).
    policy "verified": count a peer over its declared arc only while a fresh
        certification (passed a c-sample audit within proof_ttl) backs it.
    hold_frac p: fraction of the ring each liar actually stores.
    audit_samples c: sectors challenged per audit; a liar passes with ~p^c.
    """

    def __init__(self, cfg, variant, events, initial, joins, byz_ids,
                 policy="verified", hold_frac=0.5, audit_samples=2,
                 proof_ttl=600, audit_per_epoch=6, mint_from=0):
        super().__init__(cfg, variant, events, initial, joins,
                         byz_ids=byz_ids, mode="liar")
        self.policy = policy
        self.hold_frac = hold_frac
        self.audit_samples = audit_samples
        self.proof_ttl = proof_ttl
        self.audit_per_epoch = audit_per_epoch
        self.mint_from = mint_from
        self._audit_rng = np.random.default_rng(cfg.seed + 31)
        S = cfg.sectors

        # Each liar truly stores a random hold_frac of the ring (seeded per id
        # so the world is identical across policies and sample counts).
        self.holds: dict[int, np.ndarray] = {}
        hrng = np.random.default_rng(cfg.seed + 71)
        n_hold = int(round(hold_frac * S))
        for aid in sorted(self.byz_ids):
            h = np.zeros(S, dtype=bool)
            if n_hold:
                h[hrng.choice(S, n_hold, replace=False)] = True
            self.holds[aid] = h

        self.proofs: dict[int, dict[int, int]] = defaultdict(dict)  # obs->peer->tick
        self.m.true_floor = []
        self.m.true_zero = []
        self.m.mean_proven = []

    # ------- whole-arc verified coverage, gated on fresh certification ------
    def _view(self, a):
        cov, lvl, icov, ilist = Sim._view(self, a)
        if self.policy != "verified":
            return cov, lvl, icov, ilist
        vcov = np.zeros(self.cfg.sectors, dtype=np.int16)
        own = int(lvl[a.aid])
        if own >= 0:                                   # self always trusted
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
                    continue
                s_, e_ = block(self.agents[x].home, xl, self.cfg.log2s)
                vcov[s_:e_] += 1
            for x in stale:
                del mine[x]
        return vcov, lvl, icov, ilist

    def _passes_audit(self, x, s0, e0):
        """Peer x challenged on `audit_samples` sectors in [s0,e0). Honest x
        serves all; a liar serves each iff it holds it (~p^c overall)."""
        for _ in range(self.audit_samples):
            s = int(self._audit_rng.integers(s0, e0))
            if x in self.byz_ids and not self.holds[x][s]:
                return False
        return True

    def step(self):
        cfg = self.cfg
        if self.policy == "verified" and self.t >= self.mint_from:
            idx = (self.t - 1) % self.H if self.t else 0
            lvl_now = self.lvl_h[idx]
            declared = np.nonzero(lvl_now[:len(self.agents)] >= 0)[0]
            if len(declared):
                for a in self.agents:
                    if (not a.alive or a.aid in self.byz_ids
                            or self.t % cfg.eval_every != a.phase):
                        continue
                    for _ in range(self.audit_per_epoch):
                        x = int(declared[self._audit_rng.integers(
                            0, len(declared))])
                        if x == a.aid:
                            continue
                        s0, e0 = block(self.agents[x].home,
                                       int(lvl_now[x]), cfg.log2s)
                        if self._passes_audit(x, s0, e0):
                            self.proofs[a.aid][x] = self.t   # certify the arc

        Sim.step(self)      # advance world (liars never decide)

        cov = np.zeros(cfg.sectors, dtype=np.int32)
        for a in self.agents:
            if not a.alive:
                continue
            if a.aid in self.byz_ids:
                cov += self.holds[a.aid]                 # liar's REAL holdings
            else:
                s_, e_ = block(a.home, a.level, cfg.log2s)
                cov[s_:e_] += 1
        self.m.true_floor.append(int(cov.min()))
        self.m.true_zero.append(int((cov == 0).sum()))
        if self.policy == "verified":
            honest = [a for a in self.agents
                      if a.alive and a.aid not in self.byz_ids]
            fresh = sum(sum(1 for pt in self.proofs.get(a.aid, {}).values()
                            if self.t - pt <= self.proof_ttl) for a in honest)
            self.m.mean_proven.append(fresh / max(1, len(honest)))
        else:
            self.m.mean_proven.append(0.0)


# ------------------------------------------------------------- studies
def _one(policy, c, p, cfg, k, seed, ticks):
    conf = Config(seed=seed, log2s=cfg.log2s, n_agents=cfg.n_agents,
                  redundancy=cfg.redundancy)
    initial, events, joins = make_world(conf, ticks)
    byz = set(pick_byz(conf, k, conf.n_agents))
    sim = PartialLiarSim(conf, V3, events, initial, joins, byz,
                         policy=policy, hold_frac=p, audit_samples=c)
    m = sim.run(ticks)
    return (float(np.mean(m.true_floor[-200:])),
            float(np.mean(m.true_zero[-200:])))


def run_static(cfg, ps, k, seeds, c=2, ticks=2200):
    """Sweep held fraction p at fixed sample count c, declared vs verified."""
    rows = []
    for policy in ("declared", "verified"):
        for p in ps:
            res = [_one(policy, c, p, cfg, k, s, ticks) for s in seeds]
            tf = float(np.mean([r[0] for r in res]))
            tz = float(np.mean([r[1] for r in res]))
            rows.append({"policy": policy, "p": p, "true_floor_end": tf,
                         "true_zero_end": tz,
                         "true_zero_frac": tz / cfg.sectors})
            print(f"  static {policy:9s} p={p:.2f}  true_floor={tf:.1f} "
                  f"true_zero={tz:.0f} ({tz/cfg.sectors:.1%})", flush=True)
    return rows


def run_stringency(cfg, cs, p, k, seeds, ticks=2200):
    """At an evasion-prone p, sweep the audit sample count c (verified)."""
    rows = []
    for c in cs:
        res = [_one("verified", c, p, cfg, k, s, ticks) for s in seeds]
        tf = float(np.mean([r[0] for r in res]))
        tz = float(np.mean([r[1] for r in res]))
        rows.append({"audit_samples": c, "p": p, "evade_prob": p ** c,
                     "true_floor_end": tf, "true_zero_end": tz,
                     "true_zero_frac": tz / cfg.sectors})
        print(f"  stringency c={c} (evade~{p**c:.2f})  true_floor={tf:.1f} "
              f"true_zero={tz:.0f} ({tz/cfg.sectors:.1%})", flush=True)
    return rows


# ------------------------------------------------------------- plot
def plot(static, stringency, cfg, out):
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2))
    fig.suptitle("Partial liars vs verified coverage: graceful degradation, "
                 "and the sample-count knob", fontsize=12, fontweight="bold",
                 color=INK)
    ax_floor, ax_zero, ax_str = axes.flat
    colors = {"declared": SERIES[0], "verified": VARIANT_COLOR[V3.name]}

    ps = sorted({r["p"] for r in static})
    for policy in ("declared", "verified"):
        rs = sorted((r for r in static if r["policy"] == policy),
                    key=lambda r: r["p"])
        ax_floor.plot(ps, [r["true_floor_end"] for r in rs], marker="o", ms=5,
                      lw=1.8, color=colors[policy], label=policy)
        ax_zero.plot(ps, [r["true_zero_frac"] for r in rs], marker="o", ms=5,
                     lw=1.8, color=colors[policy], label=policy)
    ax_floor.axhline(cfg.redundancy, color=BASELINE, lw=1, ls="--")
    ax_floor.set_title("True floor vs liar's true-held fraction p (c=2 samples)")
    ax_floor.set_xlabel("fraction the liar actually stores (p)")
    ax_floor.set_ylabel("true copies (tail mean)")
    ax_floor.legend(fontsize=8, loc="upper left")
    ax_zero.set_title("Fraction of ring with 0 true copies")
    ax_zero.set_xlabel("held fraction p")
    ax_zero.set_ylabel("fraction")
    ax_zero.legend(fontsize=8, loc="upper right")

    cs = [r["audit_samples"] for r in stringency]
    ax_str.plot(cs, [r["true_zero_frac"] for r in stringency], marker="s",
                ms=6, lw=1.8, color=ALERT, label="ring 0-copy")
    ax_str.plot(cs, [r["evade_prob"] for r in stringency], marker="^", ms=6,
                lw=1.4, color=MUTED, ls="--", label="evade prob p^c")
    ax_str.set_title(f"Stringency: samples c vs damage (p={stringency[0]['p']})")
    ax_str.set_xlabel("audit samples per challenge (c)")
    ax_str.set_ylabel("fraction")
    ax_str.legend(fontsize=8, loc="upper right")
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
    k = 2 * R
    ps = [0.0, 0.5, 1.0] if quick else [0.0, 0.25, 0.5, 0.75, 0.9, 1.0]
    cs = [1, 2, 4] if quick else [1, 2, 3, 4, 6]
    seeds = [42] if quick else [42, 7, 99]
    ticks = 1800 if quick else 2200
    p_evade = 0.5                       # the danger zone: evades often AND withholds

    print("study A: static partial liars, declared vs verified (c=2)")
    static = run_static(cfg, ps, k, seeds, c=2, ticks=ticks)
    print("study B: stringency — sample count c at evasion-prone p")
    stringency = run_stringency(cfg, cs, p_evade, k, seeds, ticks=ticks)

    with open("results/partial_liar.json", "w") as f:
        json.dump({"static": static, "stringency": stringency,
                   "R": R, "K": k, "seeds": seeds}, f, indent=1)

    with open("results/partial_summary.md", "w") as f:
        f.write("# Partial liars vs verified coverage\n\n"
                f"K = {k} liars (= 2R) declare a full arc but truly store a "
                "fraction p of the ring. Audit = c-sample range-check; a liar "
                "passes with ~p^c and, once certified, is trusted over its "
                "whole declared arc.\n\n"
                f"## A. Static, declared vs verified (c=2 samples, R={R}, "
                f"seeds {seeds}, tail-mean)\n\n"
                "| policy | p (held) | true floor | true-zero sectors | "
                "ring 0-copy |\n|---|---|---|---|---|\n")
        for r in static:
            f.write(f"| {r['policy']} | {r['p']:.2f} | "
                    f"{r['true_floor_end']:.1f} | {r['true_zero_end']:.0f} | "
                    f"{r['true_zero_frac']:.1%} |\n")
        f.write(f"\n## B. Stringency — audit samples c at p={p_evade} "
                "(verified)\n\n"
                "| samples c | evade prob p^c | true floor | "
                "true-zero sectors | ring 0-copy |\n|---|---|---|---|---|\n")
        for r in stringency:
            f.write(f"| {r['audit_samples']} | {r['evade_prob']:.3f} | "
                    f"{r['true_floor_end']:.1f} | {r['true_zero_end']:.0f} | "
                    f"{r['true_zero_frac']:.1%} |\n")
    print("wrote results/partial_summary.md")
    plot(static, stringency, cfg, "results/partial_liar.png")


if __name__ == "__main__":
    main()
