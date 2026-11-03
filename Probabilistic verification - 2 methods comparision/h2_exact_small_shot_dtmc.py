#!/usr/bin/env python3
"""Exact small-shot analytical DTMC for the H2 VQE experiment.

"Exact" means that every optimizer-edge probability is obtained from the
finite multinomial measurement law.  There is no Gaussian approximation and
no Monte Carlo sampling in this model.
"""

from math import factorial

import numpy as np


SHOTS_PER_GROUP = 8
HORIZON = 50
GRID_SIZE = 16
INITIAL_INDEX = (3, 11, 6, 14)
CONVERGENCE_TOLERANCE = 0.02
SCALE = 10_000

I = np.eye(2, dtype=complex)
X = np.array([[0, 1], [1, 0]], dtype=complex)
Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
Z = np.diag([1, -1]).astype(complex)
H = np.array([[1, 1], [1, -1]], dtype=complex) / np.sqrt(2)
SDG = np.diag([1, -1j]).astype(complex)

# Qiskit ordering is |q1 q0>; Pauli labels are q1 then q0.
HAMILTONIAN = (
    0.3980 * np.kron(Y, Z)
    - 0.3980 * np.kron(Z, I)
    - 0.0113 * np.kron(Z, Z)
    + 0.1810 * np.kron(X, X)
)
GROUND_ENERGY = float(np.linalg.eigvalsh(HAMILTONIAN)[0])


def on_qubit(gate, qubit):
    return np.kron(gate, I) if qubit == 1 else np.kron(I, gate)


CX_0_1 = np.array(
    [[1, 0, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0], [0, 1, 0, 0]],
    dtype=complex,
)
Y_BASIS_Q1 = on_qubit(H, 1) @ on_qubit(SDG, 1)
X_BASIS_BOTH = on_qubit(H, 1) @ on_qubit(H, 0)

# Per-shot group contributions, scaled by 10,000, for outcomes 00,01,10,11.
GROUP_VALUES = (
    np.array([-4093, -3867, 4093, 3867]),  # {ZI, ZZ}
    np.array([3980, -3980, -3980, 3980]),  # {YZ}
    np.array([1810, -1810, -1810, 1810]),  # {XX}
)


def rz(angle):
    return np.diag([np.exp(-0.5j * angle), np.exp(0.5j * angle)])


def state_data(index):
    """Return exact-state energy and Born probabilities for the three groups."""
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

    energy = float(np.real(np.vdot(state, HAMILTONIAN @ state)))
    probabilities = np.stack(
        [np.abs(rotated) ** 2 for rotated in
         (state, Y_BASIS_Q1 @ state, X_BASIS_BOTH @ state)]
    )
    probabilities /= probabilities.sum(axis=1, keepdims=True)
    reconstructed = sum(
        probability @ values
        for probability, values in zip(probabilities, GROUP_VALUES)
    ) / SCALE
    assert np.isclose(energy, reconstructed, atol=1e-12)
    return energy, probabilities


def build_grid():
    """Evaluate the circuit and identify mathematically identical Born laws."""
    shape = (GRID_SIZE,) * 4
    energies = np.empty(shape)
    distribution_ids = np.empty(shape, dtype=np.int32)
    representatives = []
    cache = {}

    for index in np.ndindex(shape):
        energy, probabilities = state_data(index)
        energies[index] = energy

        # Rounding only removes <= 7e-16 trigonometric roundoff between
        # mathematically identical grid states; the stored probabilities are
        # the original Born probabilities.
        key_values = np.round(probabilities.ravel(), 12)
        key_values[np.abs(key_values) < 5e-13] = 0.0
        key = key_values.tobytes()
        if key not in cache:
            cache[key] = len(representatives)
            representatives.append(probabilities)
        distribution_ids[index] = cache[key]

    return energies, distribution_ids, np.asarray(representatives)


def group_distributions(born_probabilities):
    """Exact 8-shot laws for (sum ZI,sum ZZ), sum YZ, and sum XX."""
    count = len(born_probabilities)
    n = SHOTS_PER_GROUP
    joint = np.zeros((count, n + 1, n + 1))
    factorial_n = factorial(n)
    p = born_probabilities[:, 0, :]

    # Enumerate the C(n+3,3)=165 histograms of the four-outcome QWC group.
    for n0 in range(n + 1):
        for n1 in range(n - n0 + 1):
            for n2 in range(n - n0 - n1 + 1):
                n3 = n - n0 - n1 - n2
                counts = (n0, n1, n2, n3)
                denominator = 1
                probability = np.ones(count)
                for outcome, outcome_count in enumerate(counts):
                    denominator *= factorial(outcome_count)
                    probability *= p[:, outcome] ** outcome_count
                coefficient = factorial_n // denominator

                # A=sum ZI and B=sum ZZ, represented by indices 0,...,n.
                index_a = n0 + n1
                index_b = n0 + n3
                joint[:, index_a, index_b] += coefficient * probability

    binomials = []
    for group in (1, 2):
        positive = born_probabilities[:, group, 0] + born_probabilities[:, group, 3]
        law = np.empty((count, n + 1))
        for positive_count in range(n + 1):
            law[:, positive_count] = (
                factorial_n
                / (factorial(positive_count) * factorial(n - positive_count))
                * positive ** positive_count
                * (1.0 - positive) ** (n - positive_count)
            )
        binomials.append(law)

    assert np.allclose(joint.sum(axis=(1, 2)), 1.0, atol=2e-13)
    assert all(np.allclose(law.sum(axis=1), 1.0, atol=2e-13) for law in binomials)
    return joint, binomials[0], binomials[1]


def exact_energy_pmfs(born_probabilities):
    """Build each distinct exact finite-shot energy probability mass function."""
    joint, yz, xx = group_distributions(born_probabilities)
    count = len(born_probabilities)
    n = SHOTS_PER_GROUP

    # Combine -3980*A from {ZI,ZZ} with +3980*C from {YZ}.
    difference_and_zz = np.zeros((count, 2 * n + 1, n + 1))
    for index_a in range(n + 1):
        for index_c in range(n + 1):
            difference = index_c - index_a + n
            difference_and_zz[:, difference, :] += (
                joint[:, index_a, :] * yz[:, index_c, None]
            )

    pmfs = (
        difference_and_zz[:, :, :, None] * xx[:, None, None, :]
    ).reshape(count, -1)

    difference = np.arange(-n, n + 1)[:, None, None]
    zz_sum = (-n + 2 * np.arange(n + 1))[None, :, None]
    xx_sum = (-n + 2 * np.arange(n + 1))[None, None, :]
    scores = 7960 * difference - 113 * zz_sum + 1810 * xx_sum
    order = np.argsort(scores.ravel())
    assert len(np.unique(scores)) == scores.size
    pmfs = pmfs[:, order]
    pmfs /= pmfs.sum(axis=1, keepdims=True)
    return pmfs


def optimizer_kernel(distribution_ids, pmfs, coordinate):
    """Exact probabilities of selecting current, minus, and plus."""
    current = distribution_ids
    minus = np.roll(distribution_ids, 1, axis=coordinate)
    plus = np.roll(distribution_ids, -1, axis=coordinate)
    triples = np.stack((current, minus, plus), axis=-1).reshape(-1, 3)
    unique, inverse = np.unique(triples, axis=0, return_inverse=True)
    result = np.empty((len(unique), 3))

    # Process in chunks to keep peak memory small.
    for start in range(0, len(unique), 512):
        rows = unique[start:start + 512]
        p0, p1, p2 = (pmfs[rows[:, candidate]] for candidate in range(3))
        ge0 = np.cumsum(p0[:, ::-1], axis=1)[:, ::-1]
        ge1 = np.cumsum(p1[:, ::-1], axis=1)[:, ::-1]
        ge2 = np.cumsum(p2[:, ::-1], axis=1)[:, ::-1]

        # Tie priority is current, then minus, then plus.
        probabilities = np.column_stack((
            np.sum(p0 * ge1 * ge2, axis=1),
            np.sum(p1 * (ge0 - p0) * ge2, axis=1),
            np.sum(p2 * (ge0 - p0) * (ge1 - p1), axis=1),
        ))
        probabilities /= probabilities.sum(axis=1, keepdims=True)
        result[start:start + len(rows)] = probabilities

    shape = distribution_ids.shape
    expanded = result[inverse].reshape(shape + (3,))
    return expanded[..., 0], expanded[..., 1], expanded[..., 2]


def convergence_probability(energies, kernels):
    """Evaluate P(convergence within 50 optimizer updates)."""
    success = energies - GROUND_ENERGY <= CONVERGENCE_TOLERANCE
    mass = np.zeros_like(energies)
    mass[INITIAL_INDEX] = 1.0
    converged = 0.0

    for step in range(HORIZON):
        coordinate = step % 4
        current, minus, plus = kernels[coordinate]
        mass = (
            mass * current
            + np.roll(mass * minus, -1, axis=coordinate)
            + np.roll(mass * plus, 1, axis=coordinate)
        )
        converged += float(mass[success].sum())
        mass[success] = 0.0

    assert np.isclose(converged + mass.sum(), 1.0, atol=2e-12)
    return converged, float(mass.sum())


def main():
    energies, distribution_ids, born_probabilities = build_grid()
    pmfs = exact_energy_pmfs(born_probabilities)
    kernels = [
        optimizer_kernel(distribution_ids, pmfs, coordinate)
        for coordinate in range(4)
    ]
    probability, timeout_probability = convergence_probability(energies, kernels)

    print(f'Property: P(F<={HORIZON} "success")')
    print(f"Shots per commuting group: {SHOTS_PER_GROUP}")
    print(f"Distinct exact Born laws: {len(born_probabilities)}")
    print(f"Exact multinomial DTMC probability: {probability:.12f} ({probability:.4%})")
    print(f"Timeout probability: {timeout_probability:.12f}")
    print(f"Probability mass check: {probability + timeout_probability:.12f}")


if __name__ == "__main__":
    main()
