"""
mz_probe — is the §6.1 residual *really* irreducible by a local rule?

REPORT_stage3.md §11 concludes that the slow-detection residual race is
"irreducible by any local rule", and constraint 6 turns that into design advice
(size the shrink wait against death-detection latency, not gossip staleness).
That conclusion is stated qualitatively. This study tries to *falsify* it, and
reports a number either way.

The frame is the Mori-Zwanzig decomposition, which is the exact statement of
what happens to a dynamical system when you can only observe part of it. Project
out the unresolved variables and the dynamics of the resolved ones splits into
exactly three terms:

    1. Markovian  - a function of the CURRENT resolved state
    2. memory     - a convolution over the HISTORY of the resolved state; this
                    is where the unresolved variables' influence re-emerges
    3. orthogonal - depends on unresolved initial conditions. Irreducible.

Mapped onto an arc controller: the resolved variable is the agent's own stale
gossip view; the unresolved ones are the true global coverage and, decisively,
which peers have already died but are not yet marked unresponsive. The claim
under test is that the §6.1 residual lives *entirely* in term 3.

What is measured
----------------
At every execute-intent (the gate decision that matters), the agent's view
over-counts the half it wants to vacate by

    y = max over the vacate half of ( view coverage - true coverage )

y > 0 is exactly the condition that lets the gate pass when it should not. We
then ask how much of Var(y) is explained out-of-sample by

    M   : features of the agent's CURRENT view only          (Markovian term)
    M+H : the same, plus its own history of past views       (+ memory term)

    memory gain  = R2(M+H) - R2(M)          <- MZ term 2
    noise floor  = 1 - R2(M+H)              <- MZ term 3

and sweep death-detection latency, which is the knob that controls how much of
the truth is unresolved. MZ predicts the noise floor rises with `death_lag`
while the memory gain stays flat: undetected deaths are orthogonal dynamics, not
history. If instead the memory gain *grows* with `death_lag`, §11's claim is
wrong and there is signal a better local rule could use.

Two methodological guards, both deliberate:

  * **The learner must be strong enough for a negative result to mean
    anything.** A weak memory model would falsely confirm "irreducible" -- the
    exact failure mode McGreivy & Hakim (Nat. Mach. Intell. 2024) found in 79%
    of ML-for-PDE papers. So both feature sets are fitted with ridge *and* with
    gradient-boosted trees, and the better out-of-sample score is taken.
  * **A positive control.** The same learner, same features, is asked to predict
    a quantity that IS a function of recent history (next-epoch view coverage).
    If it scores well there and ~0 on y, the null result is about the physics,
    not about a broken estimator.

Train/test is split *by seed*, never by row: rows within one run are heavily
correlated and a random row split would leak.

A note on `H = cfg.lag_max + 2`
-------------------------------
The world-history ring buffer in polite_shrink holds only `lag_max + 2` ticks,
and each agent reads exactly one slot from it (`cov_h[(t - a.lag) % H]`). Any
attempt to build an agent's *memory* by indexing further back through that
buffer silently wraps around and reads the future once `a.lag + lookback >= H`.
This module therefore never looks back through `cov_h`. It records each agent's
view into per-agent storage AT THE MOMENT THE AGENT OBSERVES IT, which is both
immune to the buffer depth and the more faithful model anyway: a real node
remembers what it received, not what happened to be true.

Instrumentation only: this module records, it never alters a decision and never
draws from any RNG stream. `--validate` asserts the recorded run's metrics are
identical to the uninstrumented DecoupledSim on the same seed (the repo's
standard reduction guard).

Determinism: the published pins are Python 3.12.1 / numpy 2.5.1. Cell values
below were produced on a different interpreter; see the summary header.
"""

from __future__ import annotations

import argparse
import json
import os
from multiprocessing import Pool

import numpy as np

from polite_shrink import Config, make_world, vacate_half
from rolling_upgrade_sim import assign_initial_variants
from decoupled_sim import DecoupledSim

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
CELLS = os.path.join(RESULTS_DIR, "mz_cells.jsonl")

KW = dict(storm_at=1500, storm_frac=0.30)
TICKS = 3000
DEATH_LAGS = ["coupled", 4, 8, 16, 24, 48, 96]
FRACTIONS = [1.0, 0.1]          # 1.0 = pure V3; 0.1 = the arm where races occur
SEED_BASE = 900000

# Lookbacks in *epochs* (an agent observes once per eval_every ticks). The wait
# is intent_delay=50 ticks ~ 8 epochs, so 1..16 spans the announce-to-execute
# window and a comparable stretch before it.
LOOKBACKS = (1, 2, 4, 8, 16)
N_OBS = 7                       # scalars recorded per observation


class MZProbeSim(DecoupledSim):
    """DecoupledSim + per-agent observation history + per-execute-intent records.

    Pure instrumentation. `_record_obs` and `_record_decision` read state and
    append to plain lists; neither mutates an agent, consumes an RNG draw, nor
    changes control flow.
    """

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.obs_hist: dict[int, list] = {}
        self.records: list[dict] = []

    # ------------------------------------------------------------ observation
    def _obs_vector(self, a) -> np.ndarray:
        """What agent `a` can compute from the gossip it has actually received.
        Every entry is local: no ground truth, no peer cooperation."""
        cfg = self.cfg
        cov, lvl, _icov, ilist = self._view(a)
        n_vis = int((lvl[:len(self.agents)] >= 0).sum())
        if a.level > 0:
            vs, ve = vacate_half(a.home, a.level, cfg.log2s)
            seg = cov[vs:ve]
            vh_min, vh_mean = float(seg.min()), float(seg.mean())
        else:
            vh_min = vh_mean = -1.0
        return np.array([
            float(cov.min()),        # 0 global view floor
            float(cov.mean()),       # 1 global view mean
            float(n_vis),            # 2 visible peers
            float(a.level),          # 3 own arc level
            vh_min,                  # 4 vacate-half view floor
            vh_mean,                 # 5 vacate-half view mean
            float(len(ilist)),       # 6 visible announced intenders
        ], dtype=np.float64)

    def _record_obs(self):
        """One observation per agent per decision epoch, on its own phase.

        Recorded regardless of whether `_decide` runs this tick: a node still
        receives gossip while an intent is pending, so its memory keeps filling.
        This is what the node could know, which is the question being asked.
        """
        cfg, t = self.cfg, self.t
        for a in self.agents:
            if a.alive and t % cfg.eval_every == a.phase:
                self.obs_hist.setdefault(a.aid, []).append(self._obs_vector(a))

    # ------------------------------------------------------------- the target
    def _record_decision(self, a):
        """Called immediately before the real `_execute_intent`, so the view and
        the truth are both read at the instant the gate decides."""
        cfg = self.cfg
        hist = self.obs_hist.get(a.aid)
        if hist is None or len(hist) <= max(LOOKBACKS):
            return                          # warm-up: not enough memory yet
        cov, lvl, _icov, ilist = self._view(a)
        true_cov, _true_lvl = self._build_declared()   # alive-only, zero lag
        vs, ve = vacate_half(a.home, a.level, cfg.log2s)
        seg_view = cov[vs:ve].astype(np.int32)
        seg_true = true_cov[vs:ve].astype(np.int32)

        # y: worst per-sector over-count over the half about to be vacated.
        overcount = int((seg_view - seg_true).max())

        # The gate as the agent computes it (mirrors Sim._execute_intent).
        eff = seg_view.copy()
        if int(lvl[a.aid]) >= a.level:
            eff -= 1
        for aid2, s2, e2 in ilist:
            if aid2 < a.aid:
                lo, hi = max(vs, s2), min(ve, e2)
                if lo < hi:
                    eff[lo - vs:hi - vs] -= 1
        view_pass = bool(eff.min() >= cfg.redundancy)

        # Truth side: would dropping now, on perfect CURRENT information, hold R?
        # Other intenders are deliberately not subtracted -- whether they go is
        # not yet determined, so this asks only about this agent's own drop.
        true_pass = bool((seg_true - 1).min() >= cfg.redundancy)

        cur = hist[-1]
        mem = np.concatenate([cur - hist[-1 - j] for j in LOOKBACKS])
        self.records.append({
            "cur": cur, "mem": mem,
            # two targets. `y` is the over-count (the MZ object: how wrong is
            # the resolved view). `y_true` is what the gate actually needs -- the
            # true floor of the half it is about to drop.
            "y": float(overcount),
            "y_true": float(seg_true.min()),
            "view_min": float(seg_view.min()),
            "unsafe": bool(view_pass and not true_pass),
            "view_pass": view_pass,
            # positive control, filled in after the run: the *change* in the
            # vacate-half view floor over the next epoch. Deliberately a
            # forward difference -- current state alone cannot give a trend, so
            # a pipeline that can detect memory must score above Markov here.
            "aid": a.aid, "hpos": len(hist) - 1,
        })

    def _execute_intent(self, a):
        self._record_decision(a)
        super()._execute_intent(a)

    def step(self):
        self._record_obs()      # before the tick: exactly the view decisions see
        super().step()

    # ------------------------------------------------- positive-control target
    def finalise_records(self):
        """Attach the control target: the FORWARD CHANGE in the vacate-half view
        floor over the next epoch.

        A forward difference is the right control because the current state
        carries no trend information -- to beat the Markov arm a learner must
        use the past deltas in `mem`. If memory measurably helps here and not on
        `y`, the null result on `y` is about the physics, not the estimator.
        (An earlier draft used the next-epoch *level*, which the Markov arm
        already predicted at R2=0.99 through autocorrelation; that control could
        not have detected a working memory term.)
        """
        out = []
        for r in self.records:
            hist = self.obs_hist.get(r["aid"])
            nxt = r["hpos"] + 1
            if hist is None or nxt >= len(hist):
                continue
            r["y_ctrl"] = float(hist[nxt][4] - hist[r["hpos"]][4])
            out.append(r)
        self.records = out
        return self.records


# ------------------------------------------------------------------ learners
def _r2(y_true, y_pred):
    ss_res = float(((y_true - y_pred) ** 2).sum())
    ss_tot = float(((y_true - y_true.mean()) ** 2).sum())
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0


def _standardise(Xtr, Xte):
    mu, sd = Xtr.mean(0), Xtr.std(0)
    sd = np.where(sd < 1e-12, 1.0, sd)
    return (Xtr - mu) / sd, (Xte - mu) / sd


def ridge_r2(Xtr, ytr, Xte, yte, lam=1.0):
    """Closed-form ridge, with quadratic feature expansion so the linear arm is
    not a straw man (squares + a capped set of pairwise products)."""
    def expand(X):
        cols = [X, X ** 2]
        k = min(X.shape[1], 12)
        for i in range(k):
            for j in range(i + 1, k):
                cols.append((X[:, i] * X[:, j])[:, None])
        return np.hstack(cols)
    Xtr, Xte = _standardise(Xtr, Xte)
    Xtr, Xte = expand(Xtr), expand(Xte)
    Xtr, Xte = _standardise(Xtr, Xte)
    Xtr = np.hstack([Xtr, np.ones((Xtr.shape[0], 1))])
    Xte = np.hstack([Xte, np.ones((Xte.shape[0], 1))])
    A = Xtr.T @ Xtr + lam * np.eye(Xtr.shape[1])
    w = np.linalg.solve(A, Xtr.T @ ytr)
    return _r2(yte, Xte @ w)


class _Tree:
    """Least-squares regression tree over pre-binned features."""

    def __init__(self, depth, min_leaf):
        self.depth, self.min_leaf = depth, min_leaf
        self.nodes = {}

    def fit(self, Xb, resid, n_bins):
        idx = np.arange(Xb.shape[0])
        self._build(Xb, resid, idx, 1, self.depth, n_bins)
        return self

    def _build(self, Xb, resid, idx, node, depth, n_bins):
        if depth == 0 or idx.size < 2 * self.min_leaf:
            self.nodes[node] = ("leaf", float(resid[idx].mean()) if idx.size else 0.0)
            return
        best_gain, best_j, best_b = -np.inf, -1, -1
        tot, n = float(resid[idx].sum()), idx.size
        for j in range(Xb.shape[1]):
            col = Xb[idx, j]
            s = np.bincount(col, weights=resid[idx], minlength=n_bins)
            c = np.bincount(col, minlength=n_bins).astype(np.float64)
            ls, lc = np.cumsum(s)[:-1], np.cumsum(c)[:-1]
            rs, rc = tot - ls, n - lc
            ok = (lc >= self.min_leaf) & (rc >= self.min_leaf)
            if not ok.any():
                continue
            gain = np.where(ok, ls ** 2 / np.maximum(lc, 1) + rs ** 2 / np.maximum(rc, 1), -np.inf)
            b = int(np.argmax(gain))
            if gain[b] > best_gain:
                best_gain, best_j, best_b = float(gain[b]), j, b
        if best_j < 0:
            self.nodes[node] = ("leaf", float(resid[idx].mean()))
            return
        mask = Xb[idx, best_j] <= best_b
        self.nodes[node] = ("split", best_j, best_b)
        self._build(Xb, resid, idx[mask], 2 * node, depth - 1, n_bins)
        self._build(Xb, resid, idx[~mask], 2 * node + 1, depth - 1, n_bins)

    def predict(self, Xb):
        out = np.zeros(Xb.shape[0])
        node = np.ones(Xb.shape[0], dtype=np.int64)
        for _ in range(self.depth + 1):
            for nid in np.unique(node):
                spec = self.nodes.get(int(nid))
                if spec is None:
                    continue
                sel = node == nid
                if spec[0] == "leaf":
                    out[sel] = spec[1]
                    node[sel] = -1
                else:
                    _, j, b = spec
                    left = sel & (Xb[:, j] <= b)
                    node[left] = 2 * nid
                    node[sel & ~left] = 2 * nid + 1
            if (node < 0).all():
                break
        return out


def gbt_r2(Xtr, ytr, Xte, yte, rounds=120, lr=0.1, depth=3, n_bins=32, min_leaf=40):
    """Histogram gradient boosting, numpy only. Bin edges from the TRAIN split."""
    edges = [np.quantile(Xtr[:, j], np.linspace(0, 1, n_bins + 1)[1:-1])
             for j in range(Xtr.shape[1])]
    def binify(X):
        return np.stack([np.searchsorted(edges[j], X[:, j]).astype(np.int64)
                         for j in range(X.shape[1])], axis=1)
    Btr, Bte = binify(Xtr), binify(Xte)
    base = float(ytr.mean())
    ptr = np.full(Xtr.shape[0], base)
    pte = np.full(Xte.shape[0], base)
    for _ in range(rounds):
        resid = ytr - ptr
        t = _Tree(depth, min_leaf).fit(Btr, resid, n_bins)
        ptr += lr * t.predict(Btr)
        pte += lr * t.predict(Bte)
    return _r2(yte, pte)


def best_r2(Xtr, ytr, Xte, yte):
    """Take the better of the two learners: a negative result then means the
    signal is absent, not that one model class was too weak."""
    return max(ridge_r2(Xtr, ytr, Xte, yte), gbt_r2(Xtr, ytr, Xte, yte))


# --------------------------------------------------------------- run one cell
def run_sim(args):
    dl, frac, seed = args
    cfg = Config(seed=seed)
    initial, events, joins = make_world(cfg, TICKS, **KW)
    variants = assign_initial_variants(len(initial), frac, cfg.seed)
    death_lag = None if dl == "coupled" else int(dl)
    sim = MZProbeSim(cfg, variants, events, initial, joins, frac,
                     death_lag=death_lag)
    m = sim.run(TICKS)
    recs = sim.finalise_records()
    if not recs:
        return None
    cur = np.stack([r["cur"] for r in recs])
    mem = np.stack([r["mem"] for r in recs])
    return {
        "death_lag": dl, "fraction": frac, "seed": seed,
        "cur": cur, "mem": mem,
        "y": np.array([r["y"] for r in recs]),
        "y_true": np.array([r["y_true"] for r in recs]),
        "view_min": np.array([r["view_min"] for r in recs]),
        "y_ctrl": np.array([r["y_ctrl"] for r in recs]),
        "unsafe": np.array([r["unsafe"] for r in recs]),
        "n_zero_sector_ticks": int(np.array(m.zero_sectors).sum()),
    }


TARGETS = ("y", "y_true", "y_ctrl")


def evaluate_cell(runs, n_folds=3):
    """Grouped cross-validation: folds are whole seeds, never rows.

    Rows inside one run share a world and are heavily correlated, so a random
    row split would leak the answer across the split and inflate every R2.
    """
    seeds = sorted({r["seed"] for r in runs})
    if len(seeds) < n_folds:
        return None
    sid = np.concatenate([np.full(len(r["y"]), r["seed"]) for r in runs])
    cur = np.vstack([r["cur"] for r in runs])
    mem = np.vstack([r["mem"] for r in runs])
    both = np.hstack([cur, mem])
    out = {}
    for tgt in TARGETS:
        Y = np.concatenate([r[tgt] for r in runs])
        m_scores, mh_scores, m_rmse, mh_rmse = [], [], [], []
        for f in range(n_folds):
            hold = {s for i, s in enumerate(seeds) if i % n_folds == f}
            te = np.isin(sid, list(hold))
            tr = ~te
            if te.sum() < 50 or tr.sum() < 200 or Y[te].std() == 0:
                continue
            sd = float(Y[te].std())
            r2m = best_r2(cur[tr], Y[tr], cur[te], Y[te])
            r2mh = best_r2(both[tr], Y[tr], both[te], Y[te])
            m_scores.append(r2m)
            mh_scores.append(r2mh)
            # RMSE follows from R2 by definition; reported in COPIES because R2
            # alone is hostage to how much variance the cell happens to contain.
            m_rmse.append(sd * np.sqrt(max(0.0, 1.0 - r2m)))
            mh_rmse.append(sd * np.sqrt(max(0.0, 1.0 - r2mh)))
        if not m_scores:
            continue
        m, mh = float(np.mean(m_scores)), float(np.mean(mh_scores))
        out[tgt] = {"r2_markov": m, "r2_markov_mem": mh,
                    "memory_gain": mh - m, "noise_floor": 1.0 - mh,
                    "rmse_markov": float(np.mean(m_rmse)),
                    "rmse_markov_mem": float(np.mean(mh_rmse)),
                    "rmse_gain": float(np.mean(m_rmse) - np.mean(mh_rmse))}
    y = np.concatenate([r["y"] for r in runs])
    out["n"] = int(len(y))
    out["y_std"] = float(y.std())
    out["true_std"] = float(np.concatenate([r["y_true"] for r in runs]).std())
    out["view_std"] = float(np.concatenate([r["view_min"] for r in runs]).std())
    out["unsafe"] = int(np.concatenate([r["unsafe"] for r in runs]).sum())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=24)
    ap.add_argument("--procs", type=int, default=min(os.cpu_count() or 4, 10))
    args = ap.parse_args()
    seeds = [SEED_BASE + i for i in range(args.seeds)]
    work = [(dl, f, s) for dl in DEATH_LAGS for f in FRACTIONS for s in seeds]
    os.makedirs(RESULTS_DIR, exist_ok=True)
    print(f"mz probe: {len(DEATH_LAGS)} death_lags x {len(FRACTIONS)} fractions "
          f"x {args.seeds} seeds = {len(work)} sims", flush=True)

    runs = []
    with Pool(processes=args.procs) as pool:
        for i, r in enumerate(pool.imap_unordered(run_sim, work), 1):
            if r is not None:
                runs.append(r)
            if i % 40 == 0 or i == len(work):
                print(f"  sims {i}/{len(work)}", flush=True)

    rows = []
    for frac in FRACTIONS:
        for dl in DEATH_LAGS:
            cell = [r for r in runs if r["fraction"] == frac and r["death_lag"] == dl]
            if not cell:
                continue
            res = evaluate_cell(cell)
            if res is None:
                continue
            res.update({"death_lag": dl, "fraction": frac,
                        "seeds": len({r['seed'] for r in cell})})
            rows.append(res)
            print(f"  fitted f={frac} death_lag={dl}", flush=True)

    with open(CELLS, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    summarise(rows, args.seeds)


def summarise(rows, n_seeds):
    import sys
    L = ["# Mori-Zwanzig decomposition of the §6.1 residual",
         "",
         "Is the shrink-race residual reducible by a *local* rule? Split the "
         "over-count an agent makes at its execute-intent into a Markovian term "
         "(current view), a memory term (its own past views) and an irreducible "
         "noise term, and sweep death-detection latency.",
         "",
         f"Storm scenario, N=200, R=5, gossip lag [8,24], {n_seeds} seeds/cell. "
         "R2 is out-of-sample under 3-fold cross-validation **grouped by seed**. "
         "Each arm is fitted with ridge (quadratic features) and gradient-boosted "
         "trees; the better score is reported, so a small memory gain means the "
         "signal is absent rather than the model too weak.",
         "",
         f"Environment: Python {sys.version.split()[0]}, numpy {np.__version__} "
         "— NOT the repo pins (3.12.1 / 2.5.1), so treat exact digits as "
         "indicative and re-run before publishing.",
         ""]
    for frac in FRACTIONS:
        sub = [r for r in rows if r["fraction"] == frac]
        if not sub:
            continue
        label = "pure V3 (f=1.0)" if frac == 1.0 else f"f={frac}"
        L += [f"## {label} — target y = view over-count at the gate", "",
              "`residual` columns are RMSE in **copies** — the units the "
              "redundancy target R is measured in, and the number that decides "
              "whether a corrected estimate could be trusted.", "",
              "| death_lag | n | y std | R2 Markov | R2 Markov+mem | memory gain | residual Markov | residual +mem | unsafe gates |",
              "|---|---|---|---|---|---|---|---|---|"]
        for r in sub:
            d = r.get("y")
            if not d:
                continue
            L.append(f"| {r['death_lag']} | {r['n']} | {r['y_std']:.2f} | "
                     f"{d['r2_markov']:.3f} | {d['r2_markov_mem']:.3f} | "
                     f"{d['memory_gain']:+.4f} | {d['rmse_markov']:.2f} | "
                     f"{d['rmse_markov_mem']:.2f} | {r['unsafe']} |")
        L += ["", f"### {label} — target y_true = TRUE floor of the vacated half "
              "(what the gate actually needs)", "",
              "| death_lag | R2 Markov | R2 Markov+mem | memory gain | residual Markov | residual +mem |",
              "|---|---|---|---|---|---|"]
        for r in sub:
            d = r.get("y_true")
            if not d:
                continue
            L.append(f"| {r['death_lag']} | {d['r2_markov']:.3f} | "
                     f"{d['r2_markov_mem']:.3f} | {d['memory_gain']:+.4f} | "
                     f"{d['rmse_markov']:.2f} | {d['rmse_markov_mem']:.2f} |")
        L += ["", f"### {label} — POSITIVE CONTROL (forward change in view floor)",
              "", "Memory *must* help here — a forward difference cannot be read "
              "off the current state. This is what makes a null result on y "
              "interpretable.", "",
              "| death_lag | R2 Markov | R2 Markov+mem | memory gain |",
              "|---|---|---|---|"]
        for r in sub:
            d = r.get("y_ctrl")
            if not d:
                continue
            L.append(f"| {r['death_lag']} | {d['r2_markov']:.3f} | "
                     f"{d['r2_markov_mem']:.3f} | {d['memory_gain']:+.4f} |")
        L.append("")
    out = os.path.join(RESULTS_DIR, "mz_summary.md")
    # explicit utf-8: the default locale encoding on Windows mangles the
    # section signs and em-dashes the rest of the repo's summaries use.
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("\n".join(L))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
