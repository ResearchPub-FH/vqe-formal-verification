"""Independent statistics for the probabilistic comparison.

Wilson (mpmath, 40 digits) and Clopper-Pearson intervals, score-test p-values,
power / minimum detectable deviation, P2 test and Holm adjustment, unconditional
resource means, distributional comparison with the executor replica, and the
family-wise false-alarm rate of the marginal checks when the model is correct.
Needs _out/mc_T_shots1024_R100000.npy (indep_montecarlo.py 100000) and
_out/replica_T_20000.npy (replica_executor.py 20000). Python >= 3.8 + NumPy + SciPy + mpmath.
"""
import json
from pathlib import Path
import numpy as np
from scipy import stats
from mpmath import mp, mpf, sqrt as msqrt

mp.dps = 40
EXP = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "_out"
RUN = EXP / "artifacts/approved-experiment"
va = json.load(open(RUN / "comparison/verdict_agreement.json"))
b = json.load(open(RUN / "stage2/baseline/results.json"))["results"]
T = np.array([r["success_step"] if r["success_step"] is not None else -1 for r in b]); n = len(T)
mc = np.load(OUT / "mc_T_shots1024_R100000.npy"); rep = np.load(OUT / "replica_T_20000.npy")

def wilson_mp(s, n):
    z = mpf("1.959963984540054235524594430520551527955550")
    p = mpf(s) / n; den = 1 + z * z / n; cen = (p + z * z / (2 * n)) / den
    rad = z * msqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return float(max(0, cen - rad)), float(min(1, cen + rad))

def clopper_pearson(s, n):
    lo = 0.0 if s == 0 else stats.beta.ppf(0.025, s, n - s + 1)
    hi = 1.0 if s == n else stats.beta.ppf(0.975, s + 1, n - s)
    return lo, hi

print("k | model | succ/n | p_emp | Wilson(report) | Wilson(mpmath) | Clopper-Pearson | score-test p | |dp| | indep MC 100k | executor 20k")
pvals = []
for row in va["probability_comparison"]:
    k = row["update_bound"]; s = int(((T >= 0) & (T <= k)).sum()); assert s == row["runtime_successes"]
    w = wilson_mp(s, n); c = clopper_pearson(s, n); p0 = row["model_probability"]
    pv = 2 * stats.norm.sf(abs((s / n - p0) / np.sqrt(p0 * (1 - p0) / n))) if 0 < p0 < 1 else float("nan")
    pvals.append((k, pv))
    print(f"{k} | {p0:.6f} | {s}/{n} | {s/n:.4f} | [{row['wilson_95'][0]:.6f},{row['wilson_95'][1]:.6f}] | [{w[0]:.6f},{w[1]:.6f}] | "
          f"[{c[0]:.4f},{c[1]:.4f}] | {pv:.4f} | {abs(p0 - s/n):.4f} | {np.mean((mc >= 0) & (mc <= k)):.4f} | {np.mean((rep >= 0) & (rep <= k)):.4f}")
print("max |Wilson(report) - Wilson(mpmath)|:", max(max(abs(a - b) for a, b in zip(r["wilson_95"], wilson_mp(r["runtime_successes"], n))) for r in va["probability_comparison"]))
print("MAD (recomputed):", np.mean([abs(r["model_probability"] - r["runtime_probability"]) for r in va["probability_comparison"]]), "report:", va["mean_absolute_probability_difference"])
p0 = va["probability_comparison"][-1]["model_probability"]; se0 = np.sqrt(p0 * (1 - p0) / n)
print(f"k=50: rejection when |p_hat - p0| > {1.96*se0:.4f}; 80%-power detectable deviation ~ {(1.96+0.8416)*se0:.4f}")
for d in (0.01, 0.02, 0.03, 0.04, 0.05):
    p1 = p0 - d; se1 = np.sqrt(p1 * (1 - p1) / n)
    print(f"   true p = p0 - {d:.2f}: power {stats.norm.cdf((-1.96*se0 + d)/se1) + stats.norm.sf((1.96*se0 + d)/se1):.2f}")
s = T[T >= 0].astype(float)
model_m = va["conditional_means"][0]["model_mean"]
z = (s.mean() - model_m) / (s.std(ddof=1) / np.sqrt(s.size))
print("P2: empirical", s.mean(), "sd", round(s.std(ddof=1), 3), "n", s.size, "t-CI", stats.t.interval(0.95, s.size - 1, s.mean(), s.std(ddof=1) / np.sqrt(s.size)),
      "| report bootstrap", va["conditional_means"][0]["bootstrap_95"], f"| z vs model {z:.2f}, p={2*stats.norm.sf(abs(z)):.4f}")
mcs, reps = mc[mc >= 0], rep[rep >= 0]
print("P2 truth: indep MC", round(mcs.mean(), 4), "+/-", round(1.96 * mcs.std(ddof=1) / np.sqrt(mcs.size), 4), "| executor replica", round(reps.mean(), 4), "+/-", round(1.96 * reps.std(ddof=1) / np.sqrt(reps.size), 4))
U = np.where(T >= 0, T, 50).astype(float); Umc = np.where(mc >= 0, mc, 50)
print("unconditional E[min(T,50)]: campaign", U.mean(), stats.t.interval(0.95, U.size - 1, U.mean(), U.std(ddof=1) / np.sqrt(U.size)), "| indep MC", Umc.mean())
print("KS (400-run success steps vs executor replica):", stats.ks_2samp(s, reps))
cat = lambda a: np.where(a >= 0, a, 99); bins = [0, 25.5, 27.5, 30.5, 35.5, 40.5, 45.5, 50.5, 100]
o = np.histogram(cat(T), bins)[0]; e = np.histogram(cat(rep), bins)[0] / rep.size * n
chi = ((o - e) ** 2 / e).sum(); print("binned chi-square:", o.tolist(), np.round(e, 1).tolist(), f"chi2={chi:.2f} df={len(o)-1} p={stats.chi2.sf(chi, len(o)-1):.3f}")
tests = sorted([(f"P1@{k}", p) for k, p in pvals if k >= 30] + [("P2", 2 * stats.norm.sf(abs(z)))], key=lambda t: t[1])
running = 0; adj = []
for i, (name, p) in enumerate(tests):
    running = max(running, min(1, p * (len(tests) - i))); adj.append((name, round(p, 4), round(running, 4)))
print("Holm (raw, adjusted):", adj)
rng = np.random.default_rng(11); hits = 0; B = 4000
checks = [(r["update_bound"], r["model_probability"]) for r in va["probability_comparison"] if r["update_bound"] >= 30]
for _ in range(B):
    smp = rep[rng.integers(0, rep.size, n)]
    rej = any(abs(np.sum((smp >= 0) & (smp <= k)) / n - pr) > 1.96 * np.sqrt(pr * (1 - pr) / n) for k, pr in checks)
    ss = smp[smp >= 0]
    rej = rej or abs(ss.mean() - model_m) > 1.96 * ss.std(ddof=1) / np.sqrt(ss.size)
    hits += rej
print(f"family-wise false-alarm rate of the 4 informative marginal checks under the executor's true law: {hits/B:.3f}")
