#!/usr/bin/env python3
"""Minimal 400-run finite-shot H2 coordinate-search experiment."""

from functools import lru_cache

import numpy as np


SHOTS_PER_GROUP = 1024
RUNS = 400
MAX_STEPS = 50
GRID_SIZE = 16
INITIAL_INDEX = (3, 11, 6, 14)
CONVERGENCE_TOLERANCE = 0.02
SEED = 20260721

I = np.eye(2, dtype=complex)
X = np.array([[0, 1], [1, 0]], dtype=complex)
Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
Z = np.diag([1, -1]).astype(complex)
H = np.array([[1, 1], [1, -1]], dtype=complex) / np.sqrt(2)
SDG = np.diag([1, -1j]).astype(complex)

# Qiskit basis order is |q1 q0>; Pauli labels are written q1 then q0.
HAMILTONIAN = (
    0.3980 * np.kron(Y, Z)
    - 0.3980 * np.kron(Z, I)
    - 0.0113 * np.kron(Z, Z)
    + 0.1810 * np.kron(X, X)
)
GROUND_ENERGY = float(np.linalg.eigvalsh(HAMILTONIAN)[0])


def on_qubit(gate, qubit):
    return np.kron(gate, I) if qubit == 1 else np.kron(I, gate)


# For two qubits, Qiskit's circular EfficientSU2 entangler is one CX(0, 1).
CX_0_1 = np.array(
    [[1, 0, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0], [0, 1, 0, 0]],
    dtype=complex,
)
Y_BASIS_Q1 = on_qubit(H, 1) @ on_qubit(SDG, 1)
X_BASIS_BOTH = on_qubit(H, 1) @ on_qubit(H, 0)

# Integer single-shot energy contributions, scaled by 10,000.
# Groups: {ZI, ZZ}, {YZ}, {XX}; outcomes are 00, 01, 10, 11.
GROUP_VALUES = (
    np.array([-4093, -3867, 4093, 3867], dtype=np.int64),
    np.array([3980, -3980, -3980, 3980], dtype=np.int64),
    np.array([1810, -1810, -1810, 1810], dtype=np.int64),
)


def rz(angle):
    return np.diag([np.exp(-0.5j * angle), np.exp(0.5j * angle)])


def ansatz_state(index):
    """H2 EfficientSU2(['h', 'rz', 'y'], circular, reps=1) state."""
    theta = 2.0 * np.pi * np.asarray(index) / GRID_SIZE
    state = np.array([1, 0, 0, 0], dtype=complex)
    for offset in (0, 2):
        for qubit in (0, 1):
            state = on_qubit(H, qubit) @ state
        for qubit in (0, 1):
            state = on_qubit(rz(theta[offset + qubit]), qubit) @ state
        for qubit in (0, 1):
            state = on_qubit(Y, qubit) @ state
        if offset == 0:
            state = CX_0_1 @ state
    return state


@lru_cache(maxsize=None)
def state_data(index):
    state = ansatz_state(index)
    energy = float(np.real(np.vdot(state, HAMILTONIAN @ state)))
    probabilities = []
    for rotated in (state, Y_BASIS_Q1 @ state, X_BASIS_BOTH @ state):
        probability = np.abs(rotated) ** 2
        probabilities.append(probability / probability.sum())

    reconstructed = sum(
        np.dot(probability, values)
        for probability, values in zip(probabilities, GROUP_VALUES)
    ) / 10000.0
    assert np.isclose(energy, reconstructed, atol=1e-12)
    return energy, probabilities


def measured_energy_numerator(index, rng):
    """Sample the configured shots for each group; return an exact integer score."""
    _, probabilities = state_data(tuple(index))
    return sum(
        int(np.dot(rng.multinomial(SHOTS_PER_GROUP, probability), values))
        for probability, values in zip(probabilities, GROUP_VALUES)
    )


def one_run(rng):
    index = np.array(INITIAL_INDEX, dtype=int)
    for step in range(MAX_STEPS):
        coordinate = step % 4
        candidates = [index.copy(), index.copy(), index.copy()]
        candidates[1][coordinate] = (candidates[1][coordinate] - 1) % GRID_SIZE
        candidates[2][coordinate] = (candidates[2][coordinate] + 1) % GRID_SIZE

        # np.argmin returns the first minimum: current, then minus, then plus.
        scores = [measured_energy_numerator(candidate, rng) for candidate in candidates]
        index = candidates[int(np.argmin(scores))]
        exact_energy, _ = state_data(tuple(index))
        if exact_energy - GROUND_ENERGY <= CONVERGENCE_TOLERANCE:
            return True, step + 1
    return False, MAX_STEPS


def wilson_interval(successes, runs, z=1.96):
    """Approximate two-sided binomial confidence interval (95% when z=1.96)."""
    rate = successes / runs
    denominator = 1.0 + z * z / runs
    center = (rate + z * z / (2.0 * runs)) / denominator
    half_width = (
        z
        * np.sqrt(rate * (1.0 - rate) / runs + z * z / (4.0 * runs * runs))
        / denominator
    )
    return center - half_width, center + half_width


def main():
    rng = np.random.default_rng(SEED)
    results = [one_run(rng) for _ in range(RUNS)]
    converged_steps = [step for converged, step in results if converged]
    successes = len(converged_steps)
    rate = successes / RUNS
    standard_error = np.sqrt(rate * (1.0 - rate) / RUNS)
    lower, upper = wilson_interval(successes, RUNS)

    print(f"Exact ground energy: {GROUND_ENERGY:.12f}")
    print(
        f"Configuration: {RUNS} runs, {MAX_STEPS} updates/run, "
        f"{SHOTS_PER_GROUP} shots/group, epsilon={CONVERGENCE_TOLERANCE}"
    )
    print(f"Converged: {successes}/{RUNS}")
    print(f"Observed convergence rate: {rate:.2%}")
    print(f"Estimated standard error: {standard_error:.2%}")
    print(f"Approximate 95% Wilson interval: [{lower:.2%}, {upper:.2%}]")
    if converged_steps:
        print(
            "Convergence-step summary: "
            f"mean={np.mean(converged_steps):.2f}, "
            f"median={np.median(converged_steps):.1f}, "
            f"range=[{min(converged_steps)}, {max(converged_steps)}]"
        )


if __name__ == "__main__":
    main()
