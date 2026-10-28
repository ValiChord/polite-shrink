"""Static quota vs escrow vs StaleCap (patient) on one shared pool of C unit slots.
HYPOTHETICAL parameters throughout; no satellite figures. Run: python3 baseline_compare.py
Delay model: each observation/message lag is uniform 1..L, but with probability p it is
spikeX*L (a violation of the bound L). StaleCap uses one lag per (observer, observed) pair,
i.e. a consistent cut, so the intent-linger issue (findings 3c) is NOT exercised here."""
import random, sys
from collections import defaultdict

def run(scheme, N, C, L, D, H, rho, skew, p, spikeX, T, P, seed, c=0.0, perm=0.0, Rc=40, Td=8, hb=10):
    rnd = random.Random(seed)
    w = [1 / (i + 1) ** skew for i in range(N)]; s = sum(w)
    lam = [rho * C / H * x / s for x in w]
    K = L * spikeX + 2
    held = [0] * N; rel = [[] for _ in range(N)]; queue = [[] for _ in range(N)]
    pend = [False] * N; execAt = [0] * N; backoff = [0] * N
    quota = [C // N + (1 if i < C % N else 0) for i in range(N)]
    rights = quota[:]; ask = [False] * N; events = defaultdict(list)
    hist = [([0] * N, [0] * N) for _ in range(K)]
    down = [0] * N; crashAt = [0] * N; frees = defaultdict(list); remints = defaultdict(list); BIG = 10 ** 9; ulast = 0
    acc = rej = 0; lat = 0; util = 0; breach = 0; over = 0
    lag = lambda: L * spikeX if rnd.random() < p else rnd.randint(1, L)

    def admit(n, t):
        nonlocal acc, lat
        held[n] += 1; rel[n].append(t + max(1, int(rnd.expovariate(1 / H))))
        lat += t - queue[n].pop(0); acc += 1

    for t in range(T):
        for n in frees.pop(t, []): held[n] = 0; rel[n] = []   # lease expiry of a crashed holder's units
        for n in range(N):
            if down[n] and t >= down[n]: down[n] = 0
            elif not down[n] and rnd.random() < c:
                crashAt[n] = t; down[n] = BIG if rnd.random() < perm else t + Rc
                frees[t + Rc].append(n); queue[n] = []; pend[n] = False; remints[t + Rc + Td].append(n)
        if scheme == "escrow_rec":
            def remint(n):
                live = [x for x in range(N) if x != n and not down[x]]
                for _ in range(rights[n]): rights[rnd.choice(live)] += 1
                rights[n] = 0
            for n in remints.pop(t, []):
                if down[n] == BIG: remint(n)          # still gone after lease + Td: declared dead
            for n in range(N):                        # false suspicion: a heartbeat lag spike > Td
                if not down[n] and rnd.random() < p / hb and rights[n] > 0: remint(n)
        for kind, a, b in events.pop(t, []):
            if kind == "ask":   # peer a decides whether to give a right to b
                if down[a]: events[t + lag()].append(("grant", b, 0))
                elif rights[a] - held[a] > (1 if queue[a] else 0):
                    rights[a] -= 1; events[t + lag()].append(("grant", b, 1))
                else:
                    events[t + lag()].append(("grant", b, 0))
            else:
                rights[a] += b; ask[a] = False
        for n in range(N):
            if down[n]: continue
            keep = [x for x in rel[n] if x > t]; held[n] -= len(rel[n]) - len(keep); rel[n] = keep
            if rnd.random() < lam[n]: queue[n].append(t)
            while queue[n] and t - queue[n][0] > P:
                queue[n].pop(0); rej += 1; pend[n] = False
        for n in rnd.sample(range(N), N):
            if down[n]: continue
            if not queue[n]: pend[n] = False; continue
            if scheme == "static":
                if held[n] < quota[n]: admit(n, t)
            elif scheme in ("escrow", "escrow_rec"):
                if held[n] < rights[n]: admit(n, t)
                elif not ask[n]:
                    ask[n] = True; j = rnd.choice([x for x in range(N) if x != n])
                    events[t + lag()].append(("ask", j, n))
            else:  # stalecap, rule "patient"
                if not pend[n]:
                    if t >= backoff[n]: pend[n] = True; execAt[n] = t + D
                elif t >= execAt[n]:
                    kmode = scheme in ("stalecap_k", "stalecap_kfc"); fc = scheme in ("stalecap_fc", "stalecap_kfc")
                    sumH = allP = lowP = 0; higher = blocked = False
                    for k in range(N):
                        if k == n: continue
                        a = lag()
                        if fc and (down[k] or a > L):          # recent-contact rule: this peer's view is not fresh
                            if down[k] and t - crashAt[k] >= Rc + Td: continue   # silent long enough: lease has freed its units
                            blocked = True; break
                        hs, ps = hist[(t - a) % K] if t - a >= 0 else ([0] * N, [0] * N)
                        sumH += hs[k]; allP += ps[k]
                        if ps[k]:
                            if k < n: lowP += 1
                            else: higher = True
                    if blocked: execAt[n] = t + 1; continue
                    eff = 1 + held[n] + sumH + allP; effLo = 1 + held[n] + sumH + lowP
                    v3 = scheme == "stalecap_v3"
                    if (effLo if v3 else eff) <= C: pend[n] = False; admit(n, t)
                    elif not v3 and higher and (effLo <= C if kmode else lowP == 0): execAt[n] = t + 1
                    else: pend[n] = False; backoff[n] = t + rnd.randint(1, 2 * D)
        hist[t % K] = (held[:], [1 if x else 0 for x in pend])
        tot = sum(held); util += tot
        if t >= 2 * T // 3: ulast += tot
        if tot > C: breach += 1; over = max(over, tot - C)
        if scheme == "escrow": assert sum(rights) + sum(1 for e in events.values() for x in e if x[0] == "grant" and x[2]) == C
    return dict(util=util / (T * C), acc=acc / max(1, acc + rej), lat=lat / max(1, acc), breach=breach, over=over, ulast=ulast / (T - 2 * T // 3) / C, strand=sum(rights[n] for n in range(N) if down[n] == BIG) / C if scheme != 'stalecap' else 0.0)

NAMES = {"escrow_rec": "escrow+recovery", "stalecap_v3": "V3 (tie-break, control)", "stalecap": "V6 patient",
         "stalecap_k": "V7 patient_k", "stalecap_fc": "V6 + recent-contact", "stalecap_kfc": "V7 + recent-contact"}
if __name__ == "__main__":
    N, C, L, D, H, P, T, X, skew = 8, 16, 3, 3, 30, 60, 9000, 4, 1
    print(f"N={N} C={C} L={L} D={D} T={T} skew={skew}, 6 seeds. V6 = patient, V7 = patient_k (multiwait), both as in polite-shrink spec/v7")
    print("rho  p     crash  perm  scheme                  util_last  accept  latency  breach_ticks  max_over")
    for rho in (0.8, 1.2):
        for p in (0, 0.05):
            for c, perm in ((0, 0), (0.0003, 0.25)):
                for sc in ("stalecap_v3", "stalecap", "stalecap_k", "stalecap_fc", "stalecap_kfc", "escrow_rec"):
                    rs = [run(sc, N, C, L, D, H, rho, skew, p, X, T, P, sd, c, perm) for sd in range(1, 7)]
                    m = lambda k: sum(r[k] for r in rs) / len(rs)
                    print(f"{rho:<4} {p:<5} {c:<6} {perm:<5} {NAMES[sc]:<23} {m('ulast'):.2f}       {m('acc'):.2f}    {m('lat'):5.1f}   {max(r['breach'] for r in rs):>6}        {max(r['over'] for r in rs)}")
