"""Independent reconstruction of the benchmark physics and Gaussian DTMC.

Written from the configuration only (no import of the experiment code).
Basis index convention: |q1 q0>, index = 2*b1 + b0 (q1 most significant),
matching Qiskit's little-endian Pauli labels where "YZ" = Y on q1, Z on q0.
"""
import json, sys, time
from pathlib import Path
EXP = Path(__file__).resolve().parents[1]          # the experiment folder
OUT = Path(__file__).resolve().parent / "_out"     # audit outputs (safe to delete)
OUT.mkdir(exist_ok=True)
import numpy as np
from scipy.special import ndtr
from scipy import integrate

ROOT = str(EXP)
cfg = json.load(open(f"{ROOT}/config/h2.json"))
G = cfg["grid_size"]; SHOTS = cfg["shots_per_group"]; GAP = cfg["success_gap"]; K = cfg["maximum_updates"]

I2 = np.eye(2, dtype=complex)
PX = np.array([[0, 1], [1, 0]], dtype=complex)
PY = np.array([[0, -1j], [1j, 0]], dtype=complex)
PZ = np.array([[1, 0], [0, -1]], dtype=complex)
HD = np.array([[1, 1], [1, -1]], dtype=complex) / np.sqrt(2)
SDG = np.array([[1, 0], [0, -1j]], dtype=complex)
PAULI = {"I": I2, "X": PX, "Y": PY, "Z": PZ}

def op2(a_q1, b_q0):
    return np.kron(a_q1, b_q0)

def rz(t):
    return np.array([[np.exp(-0.5j * t), 0], [0, np.exp(0.5j * t)]])

# CX with control q0 and target q1: |b1 b0> -> |b1 xor b0, b0>
CX01 = np.zeros((4, 4), dtype=complex)
for b1 in (0, 1):
    for b0 in (0, 1):
        CX01[2 * (b1 ^ b0) + b0, 2 * b1 + b0] = 1

terms = {k: v / cfg["hamiltonian"]["coefficient_scale"] for k, v in cfg["hamiltonian"]["terms"].items()}
Hm = sum(c * op2(PAULI[p[0]], PAULI[p[1]]) for p, c in terms.items())
eig = np.linalg.eigvalsh(Hm)
E0 = eig[0]

def unitary(theta):
    U = op2(HD, HD)
    U = op2(rz(theta[1]), rz(theta[0])) @ U
    U = op2(PY, PY) @ U
    U = CX01 @ U
    U = op2(HD, HD) @ U
    U = op2(rz(theta[3]), rz(theta[2])) @ U
    U = op2(PY, PY) @ U
    return U

psi0 = np.zeros(4, dtype=complex); psi0[0] = 1

# measurement bases: rotate so that each group's Paulis become Z-type
ROT = {0: op2(I2, I2), 1: op2(HD @ SDG, I2), 2: op2(HD, HD)}
GROUPS = cfg["measurement_groups"]

def eigval(pauli, outcome):
    # after rotation every non-identity factor is Z; eigenvalue = (-1)^(parity of measured bits on those qubits)
    b1, b0 = (outcome >> 1) & 1, outcome & 1
    v = 1
    if pauli[0] != "I": v *= (-1) ** b1
    if pauli[1] != "I": v *= (-1) ** b0
    return v

# group value per outcome = sum of coefficient * eigenvalue over terms in the group
GV = np.array([[sum(terms[t] * eigval(t, o) for t in grp) for o in range(4)] for grp in GROUPS])

idx = np.indices((G,) * 4).reshape(4, -1).T
n = idx.shape[0]
t0 = time.time()
energy = np.empty(n); probs = np.empty((n, 3, 4)); gmean = np.empty((n, 3)); gvar = np.empty((n, 3))
for k, z in enumerate(idx):
    th = 2 * np.pi * z / G
    psi = unitary(th) @ psi0
    energy[k] = np.real(np.vdot(psi, Hm @ psi))
    for g in range(3):
        p = np.abs(ROT[g] @ psi) ** 2
        probs[k, g] = p
        m = p @ GV[g]
        gmean[k, g] = m
        gvar[k, g] = p @ (GV[g] - m) ** 2
recon = gmean.sum(axis=1)
print(f"statevector sweep {time.time()-t0:.1f}s; max |E - sum group means| = {np.max(np.abs(energy-recon)):.3e}")
var_est = gvar.sum(axis=1) / SHOTS
print("ground energy (eigvalsh):", repr(E0), " spectrum:", eig)
gap = energy - E0
succ = gap <= GAP
print("success grid points:", int(succ.sum()), [tuple(map(int, z)) for z in idx[succ]])
print("gaps of success points:", np.sort(gap[succ]))
print("closest |gap-0.02| over all grid points:", np.min(np.abs(gap - GAP)), "at", tuple(map(int, idx[np.argmin(np.abs(gap - GAP))])))
print("energy range:", energy.min(), energy.max(), " initial point energy:", energy[np.ravel_multi_index((3, 11, 6, 14), (G,) * 4)])
print("estimator variance range:", var_est.min(), var_est.max())

# Standard H2 STO-3G (0.735 A) parity-reduced Hamiltonian for comparison (IZ instead of YZ, plus identity offset)
H2std = (-1.052373245772859 * op2(I2, I2) + 0.39793742484318045 * op2(I2, PZ) - 0.39793742484318045 * op2(PZ, I2)
         - 0.01128010425623538 * op2(PZ, PZ) + 0.18093119978423156 * op2(PX, PX))
print("standard H2 spectrum:", np.linalg.eigvalsh(H2std), " non-identity part ground:", np.linalg.eigvalsh(H2std + 1.052373245772859 * np.eye(4))[0])
print("benchmark Hamiltonian is real-symmetric?", np.allclose(Hm.imag, 0), " max |Im H| =", np.abs(Hm.imag).max())

np.savez_compressed(OUT / "indep_physics.npz", energy=energy, gap=gap, succ=succ, gmean=gmean, gvar=gvar, var_est=var_est, probs=probs, E0=E0)

# ---- Gaussian selection kernel, high-accuracy (exact ndtr, 160-node Gauss-Hermite) ----
shape = (G,) * 4
mu = energy.reshape(shape); sd = np.sqrt(var_est).reshape(shape)
nodes, weights = np.polynomial.hermite.hermgauss(160)
kern = np.empty((4, 3) + shape)
for coord in range(4):
    M = [mu, np.roll(mu, 1, axis=coord), np.roll(mu, -1, axis=coord)]
    S = [sd, np.roll(sd, 1, axis=coord), np.roll(sd, -1, axis=coord)]
    for j in range(3):
        x = M[j][..., None] + np.sqrt(2) * S[j][..., None] * nodes
        prod = np.ones_like(x)
        for o in range(3):
            if o != j:
                prod *= ndtr((M[o][..., None] - x) / S[o][..., None])
        kern[coord, j] = (prod * weights).sum(-1) / np.sqrt(np.pi)
rowsum = kern.sum(axis=1)
print("independent kernel: max |row sum - 1| =", np.abs(rowsum - 1).max())

saved = np.load(f"{ROOT}/artifacts/approved-experiment/stage1/gaussian-kernels.npz")
sk, ss = saved["kernels"], saved["success"]
print("saved kernels shape", sk.shape, " success shape", ss.shape)
print("success sets identical:", np.array_equal(ss.ravel(), succ))
diff = np.abs(sk - kern)
print("max |saved kernel - independent kernel| =", diff.max(), " mean =", diff.mean())
w = np.unravel_index(np.argmax(diff), diff.shape)
print("   worst entry", w, "saved", sk[w], "indep", kern[w])

# spot check a few rows with adaptive quadrature
rng = np.random.default_rng(5)
worst_q = 0
for _ in range(25):
    coord = int(rng.integers(4)); z = tuple(int(v) for v in rng.integers(0, G, 4))
    zm = list(z); zm[coord] = (zm[coord] - 1) % G; zp = list(z); zp[coord] = (zp[coord] + 1) % G
    cands = [z, tuple(zm), tuple(zp)]
    m = [mu[c] for c in cands]; s = [sd[c] for c in cands]
    for j in range(3):
        f = lambda x: np.exp(-0.5 * ((x - m[j]) / s[j]) ** 2) / (s[j] * np.sqrt(2 * np.pi)) * np.prod([ndtr((m[o] - x) / s[o]) for o in range(3) if o != j])
        val, err = integrate.quad(f, m[j] - 12 * s[j], m[j] + 12 * s[j], epsabs=1e-14, epsrel=1e-12, limit=400)
        worst_q = max(worst_q, abs(val - kern[(coord, j) + z]))
print("max |adaptive quad - 160-node GH| over 75 spot entries:", worst_q)

# ---- independent propagation of first-success CDF ----
def propagate(kernel, succ_mask, start=(3, 11, 6, 14)):
    mass = np.zeros(shape); mass[start] = 1.0
    sm = succ_mask.reshape(shape)
    cdf = [mass[sm].sum()]; mass[sm] = 0
    for u in range(K):
        c = cfg["coordinate_schedule"][u % 4]
        p = kernel[c]
        new = mass * p[0]
        new += np.roll(mass * p[1], -1, axis=c)   # move to index-1
        new += np.roll(mass * p[2], 1, axis=c)    # move to index+1
        mass = new
        cdf.append(cdf[-1] + mass[sm].sum()); mass[sm] = 0
    return np.array(cdf)

cdf_indep = propagate(kern / rowsum[:, None], succ)
cdf_saved = propagate(sk, ss.ravel())
storm = {10: 0.0, 20: 0.0, 30: 0.3839401891440446, 40: 0.7562529633830386, 50: 0.92802722250063}
for k in (10, 20, 25, 30, 40, 50):
    print(f"k={k}: indep-kernel CDF {cdf_indep[k]:.12f} | saved-kernel CDF {cdf_saved[k]:.12f} | storm {storm.get(k, float('nan'))}")
first = np.diff(np.concatenate([[0.0], cdf_indep]))
print("independent conditional mean first-success update:", (np.arange(K + 1) * first).sum() / cdf_indep[-1])
print("independent unconditional E[min(T,K)]:", sum(1 - cdf_indep[:-1]))
np.save(OUT / "cdf_indep_gauss.npy", cdf_indep)
np.save(OUT / "kern_indep.npy", kern)
