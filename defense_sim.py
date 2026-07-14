"""
Stage-3 follow-up: the two Byzantine defenses, simulated.

REPORT_stage3.md §2 identified two attack channels and named their
defenses; this study measures both defenses working.

1. INTENT RANGE-VALIDATION (vs forged intents). The forged-intent channel
   is fail-safe but a cost lever (§2a: 2.3x sync from whole-ring claims).
   The defense: receivers reject any ShrinkIntent whose range is not
   contained in the claimed sender's *declared arc* — local information
   every receiver already has. A forger is then limited to claiming the
   victim's real vacate-half, and only while the victim's declared level
   is > 0. Here: `forge_style="validated"` caps forged entries exactly
   so, and we measure the residual cost against the blatant attack and
   the clean baseline.

2. SERVE-AUDIT (vs false coverage / liars). §2b showed K >= R full-arc
   liars silently destroy true replication — a sensor-integrity gap no
   control law closes. The defense modelled: during its decision epoch,
   each honest agent audits `audit_per_epoch` randomly chosen declared
   peers (ask for one sector the peer declares; a liar cannot serve it).
   After `audit_threshold` failures the auditor *locally* excludes the
   liar's declared arc from its own coverage view — no gossip of
   verdicts, no reputation machinery, the most conservative variant.
   Scenario: K = 2R liars collapse the network (the 70%-destroyed case),
   auditing switches on at t=1500, and we measure true-coverage recovery.
   Detection scales as N * threshold / audit_rate; the point here is the
   dynamics (partial exclusion already re-triggers growth), not the
   constant.

Usage:   python3 defense_sim.py
Output:  results/defense.png, results/defense_summary.md,
         results/defense.json
"""

from __future__ import annotations

import json

import numpy as np

from polite_shrink import Sim, block, make_world, vacate_half
from byzantine_sim import ByzantineSim, V3, pick_byz
from ext_common import ALERT, BASELINE, INK, MUTED, SERIES, plt
from polite_shrink import Config


class DefenseSim(ByzantineSim):
    """ByzantineSim plus the two defenses.

    forge_style: "blatant" (whole-ring claims, as §2a) or "validated"
        (what survives receiver-side range-validation: the victim's real
        vacate-half, only while its declared level > 0).
    audit_from: tick at which serve-auditing starts (None = never).
    """

    def __init__(self, cfg, variant, events, initial, joins, byz_ids, mode,
                 attack_at=0, forge_k=10, forge_style="blatant",
                 audit_from=None, audit_per_epoch=2, audit_threshold=1):
        super().__init__(cfg, variant, events, initial, joins,
                         byz_ids, mode, attack_at, forge_k)
        self.forge_style = forge_style
        self.audit_from = audit_from
        self.audit_per_epoch = audit_per_epoch
        self.audit_threshold = audit_threshold
        self._audit_rng = np.random.default_rng(cfg.seed + 31)
        self._fails: dict[tuple[int, int], int] = {}
        self.excluded: dict[int, set[int]] = {}
        self.m.mean_excluded = []

    # --- defense 1: range-validation caps what forgery can inject -----
    def _store_snapshot(self):
        Sim._store_snapshot(self)          # skip ByzantineSim's forging
        if self.mode == "forge" and self.t >= self.attack_at:
            idx = self.t % self.H
            S = self.cfg.sectors
            for x in range(self.forge_k):
                lvl = int(self.lvl_h[idx, x])
                if lvl < 0:
                    continue
                if self.forge_style == "blatant":
                    s_, e_ = 0, S
                else:                       # "validated"
                    if lvl == 0:
                        continue            # no plausible vacate-half
                    s_, e_ = vacate_half(self.agents[x].home, lvl,
                                         self.cfg.log2s)
                self.icov_h[idx][s_:e_] += 1
                self.ilist_h[idx].append((x, s_, e_))

    # --- defense 2: per-observer exclusion of audited-out liars -------
    def _view(self, a):
        cov, lvl, icov, ilist = super()._view(a)
        exc = self.excluded.get(a.aid)
        if exc:
            idx = (self.t - a.lag) % self.H
            adj = None
            for x in exc:
                xl = int(self.lvl_h[idx, x])
                if xl < 0:
                    continue
                if adj is None:
                    adj = cov.astype(np.int32).copy()
                s_, e_ = block(self.agents[x].home, xl, self.cfg.log2s)
                adj[s_:e_] -= 1
            if adj is not None:
                cov = adj
        return cov, lvl, icov, ilist

    def step(self):
        if self.audit_from is not None and self.t >= self.audit_from:
            idx = (self.t - 1) % self.H if self.t else 0
            lvl_now = self.lvl_h[idx]
            declared = np.nonzero(lvl_now[:len(self.agents)] >= 0)[0]
            for a in self.agents:
                if (not a.alive or a.aid in self.byz_ids
                        or self.t % self.cfg.eval_every != a.phase):
                    continue
                for _ in range(self.audit_per_epoch):
                    x = int(declared[self._audit_rng.integers(
                        0, len(declared))])
                    if x == a.aid:
                        continue
                    if x in self.byz_ids:   # liar cannot serve the sample
                        k = (a.aid, x)
                        self._fails[k] = self._fails.get(k, 0) + 1
                        if self._fails[k] >= self.audit_threshold:
                            self.excluded.setdefault(a.aid, set()).add(x)
        super().step()
        if self.byz_ids:
            honest = [a for a in self.agents
                      if a.alive and a.aid not in self.byz_ids]
            tot = sum(len(self.excluded.get(a.aid, ())) for a in honest)
            self.m.mean_excluded.append(tot / max(1, len(honest)))
        else:
            self.m.mean_excluded.append(0.0)


# ------------------------------------------------------------- studies
def run_forge_validation(cfg, ticks=3000, attack_at=1500):
    out = {}
    for label, style, k in (("clean", "blatant", None),
                            ("forged (no validation)", "blatant", 10),
                            ("forged (range-validated)", "validated", 10)):
        initial, events, joins = make_world(cfg, ticks)
        sim = DefenseSim(cfg, V3, events, initial, joins, byz_ids=set(),
                         mode="forge",
                         attack_at=attack_at if k else ticks + 1,
                         forge_k=k or 0, forge_style=style)
        out[label] = sim.run(ticks)
        m = out[label]
        print(f"  forge/{label:26s} true_floor_min(post)="
              f"{min(m.true_floor[attack_at:])} "
              f"mean_level_end={m.mean_level[-1]:.2f} "
              f"resizes={int(np.sum(m.resizes))} sync={m.cum_sync[-1]}",
              flush=True)
    return out


def run_audit(cfg, k_liars=10, ticks=4200, audit_from=1500, seeds=(42, 7, 99)):
    out = {}
    for label, af in (("no audit", None), ("audit from t=1500", audit_from)):
        runs = []
        for seed in seeds:
            c = Config(seed=seed, **{f: getattr(cfg, f) for f in
                                     ("log2s", "n_agents", "redundancy")})
            initial, events, joins = make_world(c, ticks)
            byz = pick_byz(c, k_liars, c.n_agents)
            sim = DefenseSim(c, V3, events, initial, joins,
                             byz_ids=set(byz), mode="liar", audit_from=af)
            m = sim.run(ticks)
            rec = next((t for t in range(audit_from, ticks)
                        if m.true_zero[t] == 0), None)
            runs.append({"seed": seed, "true_zero_end": m.true_zero[-1],
                         "true_floor_end": m.true_floor[-1],
                         "recovered_at": rec,
                         "m": m})
            print(f"  audit/{label:20s} seed={seed:4d} "
                  f"true_zero_end={m.true_zero[-1]} "
                  f"true_floor_end={m.true_floor[-1]} recovered_at={rec}",
                  flush=True)
        out[label] = runs
    return out


# ------------------------------------------------------------- plots
def plot(forge, audit, cfg, attack_at, audit_from, out):
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2))
    fig.suptitle("Byzantine defenses measured: intent range-validation and "
                 "the serve-audit", fontsize=12, fontweight="bold", color=INK)
    ax_lvl, ax_sync, ax_rec = axes.flat

    colors = {"clean": SERIES[3], "forged (no validation)": SERIES[0],
              "forged (range-validated)": SERIES[1]}
    for label, m in forge.items():
        ax_lvl.plot(m.mean_level, color=colors[label], lw=1.6, label=label)
        ax_sync.plot(np.array(m.cum_sync) / 1000, color=colors[label],
                     lw=1.6, label=label)
    ax_lvl.axvline(attack_at, color=MUTED, lw=0.9, ls=":")
    ax_lvl.set_title(f"Mean arc level under forgery ({cfg.log2s} = full ring)")
    ax_lvl.set_xlabel("tick")
    ax_lvl.set_ylabel("level")
    ax_lvl.legend(fontsize=7, loc="upper left")
    ax_sync.axvline(attack_at, color=MUTED, lw=0.9, ls=":")
    ax_sync.set_title("Cumulative sync cost (k sector-fetches)")
    ax_sync.set_xlabel("tick")
    ax_sync.set_ylabel("k sectors")

    a_colors = {"no audit": SERIES[0], "audit from t=1500": SERIES[3]}
    for label, runs in audit.items():
        m = runs[0]["m"]           # seed 42 shown; table carries the rest
        ax_rec.plot(m.true_floor, color=a_colors[label], lw=1.6, label=label)
    ax_rec.axvline(audit_from, color=MUTED, lw=0.9, ls=":")
    ax_rec.text(audit_from + 30, 0.93, "audits start",
                transform=ax_rec.get_xaxis_transform(), color=MUTED,
                fontsize=8)
    ax_rec.axhline(cfg.redundancy, color=BASELINE, lw=1, ls="--")
    ax_rec.axhline(0, color=ALERT, lw=0.8, alpha=0.5)
    ax_rec.set_ylim(-0.8, 25)
    ax_rec.set_title(f"True floor, K={2*cfg.redundancy} liars (seed 42)")
    ax_rec.set_xlabel("tick")
    ax_rec.set_ylabel("true copies")
    ax_rec.legend(fontsize=8, loc="upper right")

    for ax in axes.flat:
        ax.grid(True, axis="y")
        ax.margins(x=0.01)
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"wrote {out}")


def main():
    cfg = Config()
    attack_at, audit_from = 1500, 1500
    print("study: forge with range-validation")
    forge = run_forge_validation(cfg, attack_at=attack_at)
    print("study: serve-audit recovery")
    audit = run_audit(cfg, audit_from=audit_from)

    with open("results/defense.json", "w") as f:
        json.dump({
            "forge": {k: {"true_floor": m.true_floor,
                          "mean_level": m.mean_level,
                          "resizes": m.resizes, "cum_sync": m.cum_sync}
                      for k, m in forge.items()},
            "audit": {k: [{kk: vv for kk, vv in r.items() if kk != "m"}
                          | {"true_floor": r["m"].true_floor,
                             "mean_excluded": r["m"].mean_excluded}
                          for r in runs]
                      for k, runs in audit.items()},
        }, f)

    with open("results/defense_summary.md", "w") as f:
        f.write("# Byzantine defenses\n\n"
                "## Intent range-validation (V3, 10 forged names, attack "
                "from t=1500)\n\n"
                "| run | true floor min (post) | mean level end | resizes "
                "| sync |\n|---|---|---|---|---|\n")
        for k, m in forge.items():
            f.write(f"| {k} | {min(m.true_floor[attack_at:])} | "
                    f"{m.mean_level[-1]:.2f} | {int(np.sum(m.resizes))} | "
                    f"{m.cum_sync[-1]} |\n")
        f.write(f"\n## Serve-audit (K=10 liars, 2 audits/agent-epoch, "
                f"threshold 1, per-observer exclusion, no verdict gossip)\n\n"
                "| run | seed | true-zero sectors end | true floor end | "
                "ring fully re-covered at |\n|---|---|---|---|---|\n")
        for k, runs in audit.items():
            for r in runs:
                f.write(f"| {k} | {r['seed']} | {r['true_zero_end']} | "
                        f"{r['true_floor_end']} | {r['recovered_at']} |\n")
    print("wrote results/defense_summary.md")
    plot(forge, audit, cfg, attack_at, audit_from, "results/defense.png")


if __name__ == "__main__":
    main()
