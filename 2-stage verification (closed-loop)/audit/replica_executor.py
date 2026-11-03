"""Stripped-down replica of execute_run's RNG/decision sequence (no tracing, no checker).

Purpose: (a) confirm the saved 400 baseline success steps are exactly reproduced
by the declared algorithm under the recorded seeds; (b) estimate the executor's
own success curve over many more seeds, to compare with the independent Monte Carlo.
Run with the experiment's interpreter (Python 3.14 / NumPy 2.5.3).
"""
import json, sys
import numpy as np
from pathlib import Path
EXP = Path(__file__).resolve().parents[1]          # the experiment folder
OUT = Path(__file__).resolve().parent / "_out"     # audit outputs (safe to delete)
OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(EXP))
from closed_loop.physics import GROUP_VALUES, candidate_indices, ideal_success, point  # read-only use

ROOT = str(EXP)
c = json.load(open(f"{ROOT}/artifacts/approved-experiment/stage1/configuration.json"))

def run(seed_words):
    rng = np.random.default_rng(np.random.SeedSequence(seed_words))
    index = list(c["initial_index"])
    if ideal_success(index, c):
        return 0
    for u in range(1, c["maximum_updates"] + 1):
        coordinate = c["coordinate_schedule"][(u - 1) % 4]
        cands = candidate_indices(index, coordinate, c["grid_size"])
        scores = []
        for params in cands:
            _, probabilities = point(tuple(params), c["grid_size"])
            s = 0
            for group in range(3):
                counts = rng.multinomial(c["shots_per_group"], probabilities[group])
                s += int(np.dot(counts, GROUP_VALUES[group]))
            scores.append(s)
        choice = min(range(3), key=lambda j: scores[j])
        index = cands[choice]
        if ideal_success(index, c):
            return u
    return None

if __name__ == "__main__":
    saved = json.load(open(f"{ROOT}/artifacts/approved-experiment/stage2/baseline/results.json"))["results"]
    mismatches = 0
    for i, r in enumerate(saved):
        if run([c["seed"], 0, i]) != r["success_step"]:
            mismatches += 1
    print("replica vs saved success_step mismatches over 400 baseline seeds:", mismatches)
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    if N:
        T = np.array([(-1 if (t := run([c["seed"], 7, i])) is None else t) for i in range(N)])
        np.save(OUT / f"replica_T_{N}.npy", T)
        for k in (25, 30, 40, 50):
            p = np.mean((T >= 0) & (T <= k)); print(f"executor replica, {N} fresh seeds: P(T<={k}) = {p:.5f} +/- {1.96*np.sqrt(p*(1-p)/N):.5f}")
        s = T[T >= 0]; print("executor replica conditional mean:", s.mean(), "+/-", 1.96 * s.std(ddof=1) / np.sqrt(s.size))
