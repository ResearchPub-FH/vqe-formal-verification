#!/usr/bin/env python3
"""Minimal analytical H2 model: 1024 shots/group, convergence by step 50.

The finite-shot energy at each candidate is approximated by a Gaussian whose
mean and variance are derived analytically from the ideal Born probabilities.
"""

import numpy as np

import h2_minimal_experiment as h2


SHOTS_PER_GROUP = 1024
HORIZON = 50
MONTE_CARLO_RUNS = 400
GAUSS_HERMITE_POINTS = 24


def normal_cdf(x):
    """Vectorized standard-normal CDF (maximum error about 7.5e-8)."""
    t = 1.0 / (1.0 + 0.2316419 * np.abs(x))
    polynomial = (
        ((((1.330274429 * t - 1.821255978) * t + 1.781477937) * t
           - 0.356563782) * t + 0.319381530) * t
    )
    positive = 1.0 - np.exp(-0.5 * x * x) * polynomial / np.sqrt(2.0 * np.pi)
    return np.where(x >= 0.0, positive, 1.0 - positive)


def energy_moments():
    """Exact finite-shot means and variances at every abstract parameter point."""
    shape = (h2.GRID_SIZE,) * 4
    means = np.empty(shape)
    variances = np.empty(shape)
    for index in np.ndindex(shape):
        energy, probabilities = h2.state_data(index)
        means[index] = energy
        single_shot_variance = sum(
            np.dot(probability, values * values)
            - np.dot(probability, values) ** 2
            for probability, values in zip(probabilities, h2.GROUP_VALUES)
        )
        variances[index] = single_shot_variance / (
            10000.0 ** 2 * SHOTS_PER_GROUP
        )
    return means, variances


def selection_kernel(means, variances, coordinate):
    """Probability of selecting current, minus, or plus at every grid point."""
    candidate_means = (
        means,
        np.roll(means, 1, axis=coordinate),
        np.roll(means, -1, axis=coordinate),
    )
    standard_deviations = tuple(
        np.sqrt(array)
        for array in (
            variances,
            np.roll(variances, 1, axis=coordinate),
            np.roll(variances, -1, axis=coordinate),
        )
    )
    nodes, weights = np.polynomial.hermite.hermgauss(GAUSS_HERMITE_POINTS)
    probabilities = []

    for chosen in range(3):
        sampled_energy = (
            candidate_means[chosen][..., None]
            + np.sqrt(2.0) * standard_deviations[chosen][..., None] * nodes
        )
        probability = np.ones_like(sampled_energy)
        for other in range(3):
            if other == chosen:
                continue
            scale = np.maximum(standard_deviations[other][..., None], 1e-15)
            probability *= normal_cdf(
                (candidate_means[other][..., None] - sampled_energy) / scale
            )
        probabilities.append(
            np.sum(probability * weights, axis=-1) / np.sqrt(np.pi)
        )

    total = probabilities[0] + probabilities[1] + probabilities[2]
    return tuple(np.clip(probability / total, 0.0, 1.0) for probability in probabilities)


def analytical_probability(means, variances):
    """Propagate the DTMC distribution and evaluate P(F<=50 success)."""
    kernels = [selection_kernel(means, variances, axis) for axis in range(4)]
    success = means - h2.GROUND_ENERGY <= h2.CONVERGENCE_TOLERANCE
    mass = np.zeros_like(means)
    mass[h2.INITIAL_INDEX] = 1.0
    converged = float(mass[success].sum())
    mass[success] = 0.0

    for step in range(HORIZON):
        current, minus, plus = kernels[step % 4]
        mass = (
            mass * current
            + np.roll(mass * minus, -1, axis=step % 4)
            + np.roll(mass * plus, 1, axis=step % 4)
        )
        converged += float(mass[success].sum())
        mass[success] = 0.0

    assert np.isclose(converged + mass.sum(), 1.0, atol=1e-10)
    return converged


def monte_carlo_check():
    """Controlled multinomial comparison using the same 1024-shot semantics."""
    h2.SHOTS_PER_GROUP = SHOTS_PER_GROUP
    rng = np.random.default_rng(h2.SEED)
    results = [h2.one_run(rng) for _ in range(MONTE_CARLO_RUNS)]
    return sum(converged for converged, _ in results)


def main():
    means, variances = energy_moments()
    probability = analytical_probability(means, variances)
    empirical_successes = monte_carlo_check()

    print(f'Property: P(F<={HORIZON} "success")')
    print(f"Analytical Gaussian-model probability: {probability:.6f} ({probability:.2%})")
    print(
        f"{MONTE_CARLO_RUNS}-run check: {empirical_successes}/{MONTE_CARLO_RUNS} "
        f"({empirical_successes / MONTE_CARLO_RUNS:.2%})"
    )


if __name__ == "__main__":
    main()
