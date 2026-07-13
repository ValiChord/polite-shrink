"""
Stage-3b: Byzantine agents against the arc controllers.

REPORT.md §7 flags Byzantine behaviour (lying declarations, forged
intents) as unmodelled. This study adds the two attack channels the
protocol actually exposes, and measures what each can and cannot do.

Attack channels
---------------
1. FORGED INTENTS (`forge`): the adversary broadcasts ShrinkIntent
   messages in honest agents' names. Tracing V3's consumption of intents
   shows both uses can only make coverage look *lower*: growers subtract
   announced vacates (cov - icov), and executing shrinkers count
   lower-priority intenders as already gone. Forgery therefore pushes
   honest agents toward growing and deferring — it can drive the network
   back to full replication (disable sharding = a resource/cost attack)
   but should never orphan a sector. This study measures that
   quantitatively rather than asserting it. We simulate the worst case:
   forged whole-ring vacate claims in the names of the lowest-id agents
   (who outrank everyone in the tie-break). Range-validating intents
   against the claimed agent's declared arc (cheap, local) and transport
   authentication (kitsune2 connections are peer-keyed; third-party
   forgery requires breaking that) both narrow this channel — noted in
   the report.

2. FALSE COVERAGE (`liar`): agents declare arcs they do not store.
   Declarations are the controller's *sensor*; every variant trusts them
   equally, so no control law can defend — the question is the damage
   curve. K full-arc liars add K phantom copies to every sector: honest
   agents shrink while declared coverage stays >= R, so true replication
   collapses once K approaches R. Threshold expected at K = R.
   `liar_exit` adds the trojan ending: the liars vanish at once after
   the network has thinned around them (compared against an honest storm
   of the same size).

Ground truth: `true_floor` / `true_zero` count only what honest agents
actually store. Declared metrics (Stage-1's) are kept for contrast —
the liar attack is invisible in declared coverage, which is the point.

Usage:   python3 byzantine_sim.py [--quick]
Output:  results/byz_forge.png, results/byz_liar.png,
         results/byz_summary.md, results/byzantine.json
"""

from __future__ import annotations

import json
import sys

import numpy as np

from arc_sim import VARIANTS, Config, Sim, block, make_world, vacate_half
from ext_common import (ALERT, BASELINE, INK, MUTED, SERIES, VARIANT_COLOR,
                        plt)

V3 = VARIANTS[3]


class ByzantineSim(Sim):
    """Sim with a set of Byzantine agents.

    mode "liar":  byz agents pin a full-arc declaration, never run the
                  controller, and store nothing (excluded from true
                  coverage). Optionally all die at `exit_at` (trojan).
    mode "forge": byz agents behave honestly with their own arcs (the
                  attack channel is isolated); from `attack_at` on, every
                  snapshot carries forged whole-ring vacate intents in
                  the names of agents 0..forge_k-1.
    """

    def __init__(self, cfg, variant, events, initial, joins,
                 byz_ids, mode, attack_at=0, forge_k=10):
        self.byz_ids = frozenset(byz_ids)
        self.mode = mode
        self.attack_at = attack_at
        self.forge_k = forge_k
        super().__init__(cfg, variant, events, initial, joins)
        # liars sit at full arc forever (initial agents start full anyway;
        # set explicitly so the intent is in the code, not an accident)
        if mode == "liar":
            for aid in self.byz_ids:
                self.agents[aid].level = cfg.log2s
        self.m.true_floor = []
        self.m.true_zero = []

    def _decide(self, a):
        if self.mode == "liar" and a.aid in self.byz_ids:
            return                      # liars never move
        super()._decide(a)

    def _store_snapshot(self):
        super()._store_snapshot()
        if self.mode == "forge" and self.t >= self.attack_at:
            idx = self.t % self.H
            S = self.cfg.sectors
            for x in range(self.forge_k):
                if self.lvl_h[idx, x] < 0:
                    continue            # can't credibly forge for the unseen
                self.icov_h[idx, :] += 1
                self.ilist_h[idx].append((x, 0, S))

    def step(self):
        super().step()
        cfg = self.cfg
        cov = np.zeros(cfg.sectors, dtype=np.int32)
        for a in self.agents:
            if a.alive and a.aid not in self.byz_ids:
                s, e = block(a.home, a.level, cfg.log2s)
                cov[s:e] += 1
        self.m.true_floor.append(int(cov.min()))
        self.m.true_zero.append(int((cov == 0).sum()))


# ------------------------------------------------------------- studies
def pick_byz(cfg, n_byz, n_agents):
    """Deterministic, spread-out Byzantine set — the highest ids, so the
    forged low-id names always belong to honest agents."""
    return list(range(n_agents - n_byz, n_agents))


def run_forge(cfg, ticks=3000, attack_at=1500):
    """Forged-intent flood vs clean baseline, V3 (V1 ignores intents by
    construction and is structurally immune to this channel)."""
    initial, events, joins = make_world(cfg, ticks)
    # Forgery is a message-layer attack: the forger needs no storage
    # presence in the network, so both runs have identical populations
    # and the only delta is the forged snapshot entries.
    out = {}
    clean = ByzantineSim(cfg, V3, events, initial, joins,
                         byz_ids=set(), mode="forge",
                         attack_at=ticks + 1)          # never fires
    out["clean"] = clean.run(ticks)
    attacked = ByzantineSim(cfg, V3, events, initial, joins,
                            byz_ids=set(), mode="forge",
                            attack_at=attack_at)
    out["forged intents"] = attacked.run(ticks)
    for k, m in out.items():
        print(f"  forge/{k:15s} floor_min(post)={min(m.floor[attack_at:])} "
              f"true_floor_min={min(m.true_floor[attack_at:])} "
              f"mean_level_end={m.mean_level[-1]:.2f} "
              f"sync={m.cum_sync[-1]}")
    return out


def run_liars(cfg, fracs, ticks=2600):
    """Liar sweep on V3: K full-arc liars from t=0; equilibrium true
    coverage vs K. Expect a threshold at K = R."""
    out = {}
    for f in fracs:
        k = round(f * cfg.n_agents)
        initial, events, joins = make_world(cfg, ticks)
        byz = pick_byz(cfg, k, cfg.n_agents)
        sim = ByzantineSim(cfg, V3, events, initial, joins,
                           byz_ids=set(byz), mode="liar")
        m = sim.run(ticks)
        out[k] = m
        print(f"  liar K={k:3d}  declared_floor_end={m.floor[-1]} "
              f"true_floor_end={m.true_floor[-1]} "
              f"true_zero_end={m.true_zero[-1]}/{cfg.sectors}")
    return out


def run_liar_exit(cfg, k, ticks=3400, exit_at=2200):
    """Trojan exit at K just below R, vs an honest storm of equal size."""
    initial, events, joins = make_world(cfg, ticks)
    byz = pick_byz(cfg, k, cfg.n_agents)

    ev_exit = {t: list(v) for t, v in events.items()}
    ev_exit.setdefault(exit_at, []).extend(byz)
    trojan = ByzantineSim(cfg, V3, ev_exit, initial, joins,
                          byz_ids=set(byz), mode="liar")
    m_trojan = trojan.run(ticks)

    # control: same-size storm of honest agents in an honest network
    rng = np.random.default_rng(cfg.seed + 11)
    victims = rng.choice(cfg.n_agents - k, k, replace=False)
    ev_storm = {t: list(v) for t, v in events.items()}
    ev_storm.setdefault(exit_at, []).extend(int(v) for v in victims)
    honest = ByzantineSim(cfg, V3, ev_storm, initial, joins,
                          byz_ids=set(), mode="liar")
    m_honest = honest.run(ticks)

    for name, m in (("trojan exit", m_trojan), ("honest storm", m_honest)):
        print(f"  exit/{name:13s} true_floor_min(post)="
              f"{min(m.true_floor[exit_at:])} "
              f"true_zero_ticks={sum(m.true_zero[exit_at:])}")
    return {"trojan exit": m_trojan, "honest storm": m_honest}


# ------------------------------------------------------------- plots
def plot_forge(res, cfg, attack_at, out):
    fig, axes = plt.subplots(2, 2, figsize=(11, 6.6))
    fig.suptitle("Forged shrink-intents (whole-ring, 10 lowest-id names) — V3",
                 fontsize=12, fontweight="bold", color=INK)
    ax_floor, ax_lvl, ax_rate, ax_cost = axes.flat
    colors = {"clean": VARIANT_COLOR[V3.name], "forged intents": SERIES[0]}
    from ext_common import rolling
    for name, m in res.items():
        c = colors[name]
        ax_floor.plot(m.true_floor, color=c, lw=1.6, label=name)
        ax_lvl.plot(m.mean_level, color=c, lw=1.6, label=name)
        ax_rate.plot(rolling(m.resizes), color=c, lw=1.6, label=name)
        ax_cost.plot(np.array(m.cum_sync) / 1000, color=c, lw=1.6, label=name)
    ax_floor.axhline(cfg.redundancy, color=BASELINE, lw=1, ls="--")
    ax_floor.axhline(0, color=ALERT, lw=0.8, alpha=0.5)
    ax_floor.set_ylim(-0.8, 25)
    ax_floor.set_title("True redundancy floor (y clipped at 25)")
    ax_floor.set_ylabel("copies")
    ax_lvl.set_title(f"Mean arc level ({cfg.log2s} = full ring = sharding disabled)")
    ax_lvl.set_ylabel("level")
    ax_rate.set_title("Arc-resize rate (rolling 100-tick mean)")
    ax_rate.set_ylabel("resizes / tick")
    ax_cost.set_title("Cumulative sync cost (k sector-fetches)")
    ax_cost.set_ylabel("k sectors")
    for ax in axes.flat:
        ax.grid(True, axis="y")
        ax.set_xlabel("tick")
        ax.margins(x=0.01)
        ax.axvline(attack_at, color=MUTED, lw=0.9, ls=":")
    ax_floor.legend(loc="upper right", fontsize=8)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  wrote {out}")


def plot_liars(res, res_exit, cfg, exit_at, out):
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2))
    fig.suptitle("False-coverage (liar) attack — V3, R = "
                 f"{cfg.redundancy}", fontsize=12, fontweight="bold", color=INK)
    ax_thr, ax_ts, ax_exit = axes.flat

    ks = sorted(res)
    true_zero_frac = [res[k].true_zero[-1] / cfg.sectors for k in ks]
    true_floor_end = [res[k].true_floor[-1] for k in ks]
    ax_thr.plot(ks, true_zero_frac, color=SERIES[0], lw=1.8, marker="o",
                ms=5, label="fraction of ring with 0 true copies")
    ax_thr.plot(ks, np.array(true_floor_end) / cfg.redundancy, color=SERIES[1],
                lw=1.8, marker="o", ms=5, label="true floor / R")
    ax_thr.axvline(cfg.redundancy, color=ALERT, lw=1, ls="--")
    ax_thr.text(cfg.redundancy + 0.3, 0.55, "K = R", color=ALERT, fontsize=8)
    ax_thr.set_title("Damage vs number of full-arc liars K (end state)")
    ax_thr.set_xlabel("K liars")
    ax_thr.set_ylabel("fraction")
    ax_thr.legend(loc="center right", fontsize=8)

    for k in ks:
        shade = 0.25 + 0.75 * (ks.index(k) / max(1, len(ks) - 1))
        ax_ts.plot(res[k].true_floor, color=SERIES[0], alpha=shade, lw=1.4,
                   label=f"K={k}")
    ax_ts.axhline(cfg.redundancy, color=BASELINE, lw=1, ls="--")
    ax_ts.axhline(0, color=ALERT, lw=0.8, alpha=0.5)
    ax_ts.set_ylim(-0.8, 25)
    ax_ts.set_title("True floor over time (declared floor stays ≥ R throughout)")
    ax_ts.set_xlabel("tick")
    ax_ts.set_ylabel("true copies")
    ax_ts.legend(loc="upper right", fontsize=7)

    colors = {"trojan exit": SERIES[0], "honest storm": VARIANT_COLOR[V3.name]}
    for name, m in res_exit.items():
        ax_exit.plot(m.true_floor, color=colors[name], lw=1.6, label=name)
    ax_exit.axvline(exit_at, color=MUTED, lw=0.9, ls=":")
    ax_exit.axhline(0, color=ALERT, lw=0.8, alpha=0.5)
    ax_exit.set_ylim(-0.8, 25)
    ax_exit.set_title(f"Trojan exit (K = R-1) vs honest storm of equal size")
    ax_exit.set_xlabel("tick")
    ax_exit.set_ylabel("true copies")
    ax_exit.legend(loc="upper right", fontsize=8)

    for ax in axes.flat:
        ax.grid(True, axis="y")
        ax.margins(x=0.01)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  wrote {out}")


def main():
    quick = "--quick" in sys.argv
    cfg = Config()
    dump = {}

    print("study: forged intents")
    attack_at = 1500
    forge = run_forge(cfg, ticks=2200 if quick else 3000, attack_at=attack_at)
    plot_forge(forge, cfg, attack_at, "results/byz_forge.png")
    dump["forge"] = {k: {"true_floor": m.true_floor, "floor": m.floor,
                         "mean_level": m.mean_level, "resizes": m.resizes,
                         "cum_sync": m.cum_sync}
                     for k, m in forge.items()}

    print("study: liars")
    fracs = [0.01, 0.02, 0.025, 0.05, 0.10] if not quick else [0.02, 0.05]
    liars = run_liars(cfg, fracs, ticks=2600)
    print("study: trojan exit")
    exit_at = 2200
    trojan = run_liar_exit(cfg, k=cfg.redundancy - 1, exit_at=exit_at)
    plot_liars(liars, trojan, cfg, exit_at, "results/byz_liar.png")
    dump["liar"] = {str(k): {"true_floor": m.true_floor,
                             "true_zero": m.true_zero, "floor": m.floor}
                    for k, m in liars.items()}
    dump["liar_exit"] = {k: {"true_floor": m.true_floor,
                             "true_zero": m.true_zero}
                         for k, m in trojan.items()}

    with open("results/byzantine.json", "w") as f:
        json.dump(dump, f)

    rows = []
    for k in sorted(liars):
        m = liars[k]
        rows.append(f"| liar K={k} | {m.floor[-1]} | {m.true_floor[-1]} | "
                    f"{m.true_zero[-1]} | {m.true_zero[-1]/cfg.sectors:.1%} |")
    with open("results/byz_summary.md", "w") as f:
        f.write(
            "# Byzantine study summary\n\n"
            "## Forged intents (worst case: whole-ring claims, 10 lowest ids)\n\n"
            "| run | true floor min (post-attack) | mean level end | "
            "resizes | sync cost |\n|---|---|---|---|---|\n")
        for k, m in forge.items():
            f.write(f"| {k} | {min(m.true_floor[attack_at:])} | "
                    f"{m.mean_level[-1]:.2f} | {int(np.sum(m.resizes))} | "
                    f"{m.cum_sync[-1]} |\n")
        f.write(
            "\n## Full-arc liars (declared floor stays ≥ R in every run "
            "— the attack is invisible to declared coverage)\n\n"
            "| run | declared floor end | true floor end | true-zero "
            "sectors end | fraction of ring |\n|---|---|---|---|---|\n")
        f.write("\n".join(rows) + "\n")
        f.write("\n## Trojan exit (K = R-1) vs equal honest storm\n\n"
                "| run | true floor min post-exit | true-zero sector-ticks "
                "post-exit |\n|---|---|---|\n")
        for name, m in trojan.items():
            f.write(f"| {name} | {min(m.true_floor[exit_at:])} | "
                    f"{sum(m.true_zero[exit_at:])} |\n")
    print("wrote results/byz_summary.md")


if __name__ == "__main__":
    main()
