"""Cross-check the hand-written circuit/Hamiltonian against Qiskit's EfficientSU2 (h, rz, y; circular; reps=1).

Run after indep_physics.py. Needs qiskit-terra (tested with 0.21.2).
"""
from pathlib import Path
import numpy as np
from qiskit.circuit.library import EfficientSU2
from qiskit.quantum_info import SparsePauliOp, Statevector

OUT = Path(__file__).resolve().parent / "_out"
E = np.load(OUT / "indep_physics.npz")["energy"]
H = SparsePauliOp.from_list([("YZ", 0.3980), ("ZI", -0.3980), ("ZZ", -0.0113), ("XX", 0.1810)])
ans = EfficientSU2(2, su2_gates=["h", "rz", "y"], entanglement="circular", reps=1)
print(ans.decompose().draw(output="text"))
rng = np.random.default_rng(3); G = 16; mult = np.array([G**3, G**2, G, 1])
pts = [np.array([3, 11, 6, 14]), np.array([4, 2, 0, 12]), np.array([12, 14, 8, 12])] + [rng.integers(0, 16, 4) for _ in range(200)]
def qiskit_energy(z):
    return float(np.real(Statevector(ans.assign_parameters(2 * np.pi * z / 16)).expectation_value(H)))

worst = max(abs(qiskit_energy(z) - E[int(z @ mult)]) for z in pts)
print("max |Qiskit energy - independent numpy energy| over", len(pts), "grid points:", worst)
H_std = SparsePauliOp.from_list([("II", -1.052373245772859), ("IZ", 0.39793742484318045), ("ZI", -0.39793742484318045),
                                 ("ZZ", -0.01128010425623538), ("XX", 0.18093119978423156)])
print("benchmark operator spectrum:", np.round(np.linalg.eigvalsh(H.to_matrix()), 6), " max |Im H| =", np.abs(H.to_matrix().imag).max())
print("standard H2 STO-3G (0.735 A) parity-reduced spectrum:", np.round(np.linalg.eigvalsh(H_std.to_matrix()), 6))
