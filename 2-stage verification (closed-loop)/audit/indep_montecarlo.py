"""Independent large-sample Monte Carlo of the exact finite-shot process.

Uses the independently reconstructed Born probabilities (indep_physics.npz),
exact multinomial counts, integer group scores, first-index tie priority,
coordinate schedule 0,1,2,3, success = ideal-energy gap <= 0.02 (absorbing),
budget 50 updates. No experiment code is imported.
"""
import json, sys, time
from pathlib import Path
EXP = Path(__file__).resolve().parents[1]          # the experiment folder
OUT = Path(__file__).resolve().parent / "_out"     # audit outputs (safe to delete)
OUT.mkdir(exist_ok=True)
import numpy as np

ROOT = str(EXP)
cfg = json.load(open(f"{ROOT}/config/h2.json"))
G = cfg["grid_size"]; SHOTS = cfg["shots_per_group"]; K = cfg["maximum_updates"]
d = np.load(OUT / "indep_physics.npz")
probs, succ = d["probs"], d["succ"]
coef = cfg["hamiltonian"]["terms"]

def eigval(p, o):
    b1, b0 = (o >> 1) & 1, o & 1
    v = 1
    if p[0] != "I": v *= (-1) ** b1
    if p[1] != "I": v *= (-1) ** b0
    return v

GVI = np.array([[sum(coef[t] * eigval(t, o) for t in grp) for o in range(4)] for grp in cfg["measurement_groups"]], dtype=np.int64)
print("integer group values:", GVI.tolist())
mult = np.array([G ** 3, G ** 2, G, 1])

def simulate(R, seed, shots=SHOTS):
    rng = np.random.default_rng(seed)
    z = np.tile(np.array(cfg["initial_index"]), (R, 1))
    T = np.full(R, -1)
    active = np.ones(R, bool)
    ties = 0
    for u in range(1, K + 1):
        a = np.nonzero(active)[0]
        if a.size == 0:
            break
        coord = cfg["coordinate_schedule"][(u - 1) % 4]
        cand = np.repeat(z[a][:, None, :], 3, axis=1)
        cand[:, 1, coord] = (cand[:, 1, coord] - 1) % G
        cand[:, 2, coord] = (cand[:, 2, coord] + 1) % G
        flat = cand @ mult                      # (A, 3)
        score = np.zeros((a.size, 3), dtype=np.int64)
        for c in range(3):
            for g in range(3):
                counts = rng.multinomial(shots, probs[flat[:, c], g])
                score[:, c] += counts @ GVI[g]
        m = score.min(axis=1)
        ties += int(((score == m[:, None]).sum(axis=1) > 1).sum())
        choice = np.argmin(score, axis=1)       # first minimal index = current/minus/plus priority
        z[a] = cand[np.arange(a.size), choice]
        hit = succ[z[a] @ mult]
        T[a[hit]] = u
        active[a[hit]] = False
    return T, ties

if __name__ == "__main__":
    R = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    shots = int(sys.argv[2]) if len(sys.argv) > 2 else SHOTS
    batches = []
    total_ties = 0
    t0 = time.time()
    for b in range(R // 50000):
        T, ties = simulate(50000, [987654321, shots, b], shots)
        batches.append(T); total_ties += ties
        print(f"batch {b} done {time.time()-t0:.1f}s", flush=True)
    T = np.concatenate(batches)
    np.save(OUT / f"mc_T_shots{shots}_R{R}.npy", T)
    n = T.size
    gauss = np.load(OUT / "cdf_indep_gauss.npy") if shots == SHOTS else None
    print(f"R={n}, shots/group={shots}, exact score ties (any pair at min) = {total_ties}")
    for k in (10, 20, 25, 27, 30, 35, 40, 45, 50):
        p = np.mean((T >= 0) & (T <= k)); se = np.sqrt(p * (1 - p) / n)
        g = gauss[k] if gauss is not None else float('nan')
        print(f"k={k:2d}: finite-shot MC P(T<=k) = {p:.5f} +/- {1.96*se:.5f} (95%)   Gaussian DTMC = {g:.5f}   diff = {p-g:+.5f}")
    s = T[T >= 0]
    print("MC conditional mean first-success update:", s.mean(), "+/-", 1.96 * s.std(ddof=1) / np.sqrt(s.size))
    print("MC unconditional E[min(T,K)]:", np.where(T >= 0, T, K).mean())
