"""Exact finite-shot (multinomial) vs Gaussian candidate-selection probabilities for selected states.

Run after indep_physics.py. Python >= 3.8 + NumPy (>= 1.22 for broadcast multinomial).
"""
from pathlib import Path
import numpy as np

EXP = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "_out"
probs = np.load(OUT / "indep_physics.npz")["probs"]
K = np.load(EXP / "artifacts/approved-experiment/stage1/gaussian-kernels.npz")["kernels"]
GVI = np.array([[-4093, -3867, 4093, 3867], [3980, -3980, -3980, 3980], [1810, -1810, -1810, 1810]])
G = 16; mult = np.array([G**3, G**2, G, 1])
rng = np.random.default_rng(2026)
states = [((3, 11, 6, 14), c) for c in range(4)] + [((12, 2, 8, 5), 3), ((4, 3, 1, 12), 2), ((12, 14, 9, 12), 2),
                                                    ((8, 7, 11, 0), 0), ((5, 2, 0, 12), 0), ((7, 10, 4, 3), 1)]
N = 400000; worst = 0
for z, coord in states:
    cand = [list(z), list(z), list(z)]
    cand[1][coord] = (z[coord] - 1) % G; cand[2][coord] = (z[coord] + 1) % G
    score = np.zeros((N, 3), dtype=np.int64)
    for c in range(3):
        f = int(np.dot(cand[c], mult))
        for g in range(3):
            score[:, c] += rng.multinomial(1024, probs[f, g], size=N) @ GVI[g]
    emp = np.bincount(np.argmin(score, axis=1), minlength=3) / N
    gauss = np.array([K[coord, j][tuple(z)] for j in range(3)])
    se = np.sqrt(emp * (1 - emp) / N); d = np.max(np.abs(emp - gauss)); worst = max(worst, d)
    print(f"state {z} coord {coord}: exact-shot MC {np.round(emp, 4)}  Gaussian {np.round(gauss, 4)}  max|diff| {d:.4f} (MC 2se {2*se.max():.4f})")
print("worst per-transition |MC - Gaussian|:", round(worst, 4))
