"""
Variational Quantum Eigensolver (VQE) — complete implementation.

Follows the Qiskit Patterns framework:
    1. Map problem to quantum circuits and operators
    2. Optimize for target hardware
    3. Execute on target hardware
    4. Post-process results
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import minimize

from qiskit.quantum_info import SparsePauliOp
from qiskit.circuit.library import efficient_su2
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
from qiskit_ibm_runtime import QiskitRuntimeService, Session
from qiskit_ibm_runtime import EstimatorV2 as Estimator


# ---------------------------------------------------------------------------
# Step 1: Map the problem to quantum circuits and operators
# ---------------------------------------------------------------------------

# Hamiltonian as a sum of weighted Pauli strings.
hamiltonian = SparsePauliOp.from_list(
    [("YZ", 0.3980), ("ZI", -0.3980), ("ZZ", -0.0113), ("XX", 0.1810)]
)

# Reference: exact ground-state energy via classical diagonalization
# (only feasible because the Hamiltonian is tiny — this is the target VQE aims to approach).
A = np.array(hamiltonian)
eigenvalues, _ = np.linalg.eigh(A)
print("Exact ground state energy:", min(eigenvalues))

# Ansatz: efficient_su2 with custom SU(2) gates and circular entanglement.
# Note: 'h' gates are usually placed outside the ansatz; included here intentionally
# to get this specific layer structure.
ansatz = efficient_su2(
    hamiltonian.num_qubits,
    su2_gates=["h", "rz", "y"],
    entanglement="circular",
    reps=1,
)
num_params = ansatz.num_parameters
print("This circuit has", num_params, "parameters")


# ---------------------------------------------------------------------------
# Step 2: Optimize for target hardware
# ---------------------------------------------------------------------------

# Pick the least busy real backend (not a simulator).
service = QiskitRuntimeService()
backend = service.least_busy(operational=True, simulator=False)
print(backend)

# Transpile the ansatz to the backend's native basis gates and qubit topology.
pm = generate_preset_pass_manager(target=backend.target, optimization_level=3)
ansatz_isa = pm.run(ansatz)

# The transpiler remaps abstract qubits to physical qubits, so the Hamiltonian
# must be remapped identically — otherwise expectation values are meaningless.
hamiltonian_isa = hamiltonian.apply_layout(layout=ansatz_isa.layout)


# ---------------------------------------------------------------------------
# Step 3: Execute on target hardware
# ---------------------------------------------------------------------------

# Tracks convergence across optimizer iterations.
cost_history_dict = {
    "prev_vector": None,
    "iters": 0,
    "cost_history": [],
}


def cost_func(params, ansatz, hamiltonian, estimator):
    """Return energy estimate <psi(params)|H|psi(params)> from the Estimator primitive."""
    pub = (ansatz, [hamiltonian], [params])
    result = estimator.run(pubs=[pub]).result()
    energy = result[0].data.evs[0]

    cost_history_dict["iters"] += 1
    cost_history_dict["prev_vector"] = params
    cost_history_dict["cost_history"].append(energy)
    print(f"Iters. done: {cost_history_dict['iters']} [Current cost: {energy}]")
    return energy


# Random initial parameters. In practice, problem-informed initializations
# (e.g. Hartree-Fock for chemistry) significantly help convergence.
x0 = 2 * np.pi * np.random.random(num_params)

# Run VQE inside a Session so all primitive calls share one backend reservation.
# Reference cost from the tutorial: ~13 min QPU / ~28 min wall time on an Eagle processor.
with Session(backend=backend) as session:
    estimator = Estimator(mode=session)
    estimator.options.default_shots = 10000

    res = minimize(
        cost_func,
        x0,
        args=(ansatz_isa, hamiltonian_isa, estimator),
        method="cobyla",  # gradient-free; robust to shot noise
        options={"maxiter": 50},
    )

print(res)


# ---------------------------------------------------------------------------
# Step 4: Post-process results
# ---------------------------------------------------------------------------

fig, ax = plt.subplots()

# Target line: the exact ground-state energy reported in the tutorial for this Hamiltonian.
target_energy = -0.7029
x = np.linspace(0, cost_history_dict["iters"], 50)
y_target = np.full_like(x, target_energy)

ax.plot(range(cost_history_dict["iters"]), cost_history_dict["cost_history"], label="VQE")
ax.plot(x, y_target, label="Target")
ax.set_xlabel("Iterations")
ax.set_ylabel("Cost")
plt.legend()
plt.show()
