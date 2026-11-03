"""Fixed circuit, independent finite-shot execution, and Gaussian abstraction.

Pauli strings and outcomes use q1,q0 ordering. The two terms in the Z group
share each bitstring; their covariance is retained when forming group energy.
"""
from __future__ import annotations

from functools import lru_cache
import numpy as np

I = np.eye(2, dtype=complex)
X = np.array([[0, 1], [1, 0]], dtype=complex)
Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
Z = np.diag([1, -1]).astype(complex)
H = np.array([[1, 1], [1, -1]], dtype=complex) / np.sqrt(2)
SDG = np.diag([1, -1j])
CX = np.array([[1, 0, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0], [0, 1, 0, 0]], dtype=complex)
HAMILTONIAN = (3980 * np.kron(Y, Z) - 3980 * np.kron(Z, I) - 113 * np.kron(Z, Z) + 1810 * np.kron(X, X)) / 10000
GROUND_ENERGY = float(np.linalg.eigvalsh(HAMILTONIAN)[0])
GROUP_VALUES = np.array([[-4093, -3867, 4093, 3867], [3980, -3980, -3980, 3980], [1810, -1810, -1810, 1810]], dtype=np.int64)


def candidate_indices(index, coordinate, grid):
    result = [list(index) for _ in range(3)]
    result[1][coordinate] = (result[1][coordinate] - 1) % grid
    result[2][coordinate] = (result[2][coordinate] + 1) % grid
    return result


def states(indices, grid):
    indices = np.asarray(indices)
    theta = 2 * np.pi * indices / grid
    state = np.zeros((len(indices), 4), dtype=complex)
    state[:, 0] = 1
    for offset in (0, 2):
        state = state @ np.kron(H, H).T
        for q in (0, 1):
            signs = np.array([1 if not (b >> q) & 1 else -1 for b in range(4)])
            state *= np.exp(-0.5j * theta[:, offset + q, None] * signs)
        state = state @ np.kron(Y, Y).T
        if offset == 0:
            state = state @ CX.T
    return state


def measurement_data(indices, grid):
    state = states(indices, grid)
    energy = np.real(np.einsum("bi,ij,bj->b", state.conj(), HAMILTONIAN, state))
    bases = (np.eye(4), np.kron(H @ SDG, I), np.kron(H, H))
    probabilities = np.stack([np.abs(state @ basis.T) ** 2 for basis in bases], axis=1)
    probabilities = np.clip(probabilities, 0, 1)
    probabilities /= probabilities.sum(axis=2, keepdims=True)
    reconstructed = np.einsum("bgo,go->b", probabilities, GROUP_VALUES) / 10000
    if not np.allclose(energy, reconstructed, atol=1e-12, rtol=0):
        raise ValueError("circuit and measurement decomposition disagree")
    return energy, probabilities


@lru_cache(maxsize=65536)
def point(index, grid):
    energies, probabilities = measurement_data([index], grid)
    return float(energies[0]), probabilities[0]


def ideal_success(index, c):
    return point(tuple(index), c["grid_size"])[0] - GROUND_ENERGY <= c["success_gap"]


def normal_cdf(x):
    # Abramowitz-Stegun 26.2.17; same approximation as the existing artifact.
    t = 1.0 / (1.0 + 0.2316419 * np.abs(x))
    poly = ((((1.330274429 * t - 1.821255978) * t + 1.781477937) * t - 0.356563782) * t + 0.319381530) * t
    positive = 1 - np.exp(-0.5 * x * x) * poly / np.sqrt(2 * np.pi)
    return np.where(x >= 0, positive, 1 - positive)


def build_gaussian(c):
    shape = (c["grid_size"],) * 4
    indices = np.indices(shape).reshape(4, -1).T
    means, probabilities = measurement_data(indices, c["grid_size"])
    group_means = np.einsum("bgo,go->bg", probabilities, GROUP_VALUES)
    group_second = np.einsum("bgo,go->bg", probabilities, GROUP_VALUES ** 2)
    variances = (group_second - group_means ** 2).sum(axis=1) / (10000 ** 2 * c["shots_per_group"])
    if np.any(variances <= 0):
        raise ValueError("degenerate Gaussian variance requires an explicit tie model")
    means, variances = means.reshape(shape), variances.reshape(shape)
    nodes, weights = np.polynomial.hermite.hermgauss(c["gauss_hermite_points"])
    kernels = []
    maximum_row_correction = 0.0
    for coord in range(4):
        mu = [means, np.roll(means, 1, axis=coord), np.roll(means, -1, axis=coord)]
        sigma = [np.sqrt(variances), np.sqrt(np.roll(variances, 1, axis=coord)), np.sqrt(np.roll(variances, -1, axis=coord))]
        choices = []
        for chosen in range(3):
            values = mu[chosen][..., None] + np.sqrt(2) * sigma[chosen][..., None] * nodes
            probability = np.ones_like(values)
            for other in range(3):
                if chosen != other:
                    probability *= normal_cdf((mu[other][..., None] - values) / sigma[other][..., None])
            choices.append(np.clip(np.sum(probability * weights, axis=-1) / np.sqrt(np.pi), 0, 1))
        total = sum(choices)
        if np.any(total <= 0) or not np.all(np.isfinite(total)):
            raise ValueError("invalid Gaussian transition row")
        maximum_row_correction = max(maximum_row_correction, float(np.max(np.abs(total - 1))))
        kernels.append(np.stack([p / total for p in choices]))
    kernels = np.stack(kernels)
    success = means - GROUND_ENERGY <= c["success_gap"]
    mass = np.zeros(shape)
    mass[tuple(c["initial_index"])] = 1
    cdf = [float(mass[success].sum())]
    mass[success] = 0
    for u in range(c["maximum_updates"]):
        coord = c["coordinate_schedule"][u % 4]
        p = kernels[coord]
        mass = mass * p[0] + np.roll(mass * p[1], -1, axis=coord) + np.roll(mass * p[2], 1, axis=coord)
        cdf.append(cdf[-1] + float(mass[success].sum()))
        mass[success] = 0
    if abs(cdf[-1] + mass.sum() - 1) > 1e-10:
        raise ValueError("probability mass was not conserved")
    first = np.diff(np.array([0.0] + cdf))
    conditional = float(np.dot(np.arange(len(cdf)), first) / cdf[-1]) if cdf[-1] > 0 else None
    return kernels, success, {
        "success_cdf": cdf,
        "expected_updates_given_success": conditional,
        "expected_shots_given_success": None if conditional is None else conditional * 9 * c["shots_per_group"],
        "expected_total_updates": float(sum(1 - p for p in cdf[:-1])),
        "minimum_energy_variance": float(variances.min()),
        "maximum_energy_variance": float(variances.max()),
        "maximum_quadrature_row_correction": maximum_row_correction,
        "ground_energy": GROUND_ENERGY,
        "grid_states": int(means.size),
        "dtmc_states": int(4 * means.size),
        "numeric_method": "24-node Gauss-Hermite (configured), normal CDF approximation, normalized rows; no certified approximation-error bound",
    }


def export_dtmc(directory, c, kernels, success):
    directory.mkdir(parents=True, exist_ok=True)
    shape = success.shape
    n = success.size
    flat = np.arange(n).reshape(shape)
    success_flat = success.ravel()
    transitions = directory / "gaussian.tra"
    labels = directory / "gaussian.lab"
    count = 0
    with transitions.open("w") as f:
        f.write("dtmc\n")
        for phase in range(4):
            coord = c["coordinate_schedule"][phase]
            targets = [flat.ravel(), np.roll(flat, 1, axis=coord).ravel(), np.roll(flat, -1, axis=coord).ravel()]
            probabilities = kernels[coord].reshape(3, n)
            for i in range(n):
                source = phase * n + i
                if success_flat[i]:
                    f.write(f"{source} {source} 1\n")
                    count += 1
                    continue
                edges = sorted(((phase + 1) % 4 * n + int(targets[j][i]), float(probabilities[j, i])) for j in range(3) if probabilities[j, i] > 0)
                for target, probability in edges:
                    f.write(f"{source} {target} {probability:.17g}\n")
                    count += 1
    initial = int(np.ravel_multi_index(c["initial_index"], shape))
    with labels.open("w") as f:
        f.write("#DECLARATION\ninit success\n#END\n")
        for phase in range(4):
            for i in range(n):
                tags = (["init"] if phase == 0 and i == initial else []) + (["success"] if success_flat[i] else [])
                if tags:
                    f.write(f"{phase * n + i} {' '.join(tags)}\n")
    return transitions, labels, count
