#!/usr/bin/env python3
"""H2 analytical Gaussian DTMC, PRISM exporter, and noisy FakeBackend study.

The analytical transition kernel is derived only from ideal Born probabilities
and the Gaussian finite-shot approximation.  The empirical branch executes the
same finite-grid optimizer directly on Qiskit's noisy FakeJakarta backend; it
does not estimate or construct an empirical DTMC.

Commands:
    python h2_prism_fakebackend_workflow.py build
    python h2_prism_fakebackend_workflow.py empirical
    python h2_prism_fakebackend_workflow.py all
    python h2_prism_fakebackend_workflow.py summarize-prism \
        --success-csv artifacts/h2_vqe/layer3_prism_results/prism_success_curve.csv
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np


SHOTS_PER_GROUP = 1024
RUNS = 400
MAX_STEPS = 50
HORIZONS = (10, 20, 30, 40, 50)
GRID_SIZE = 16
INITIAL_INDEX = (3, 11, 6, 14)
CONVERGENCE_TOLERANCE = 0.02
SEED = 20260721
GAUSS_HERMITE_POINTS = 24
TRANSPILE_SEED = SEED
FAKE_BACKEND_NAME = "FakeJakarta"
MAX_CIRCUITS_PER_FAKE_JOB = 900
DEFAULT_OUTPUT = Path("artifacts/h2_vqe")

I = np.eye(2, dtype=complex)
X = np.array([[0, 1], [1, 0]], dtype=complex)
Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
Z = np.diag([1, -1]).astype(complex)
H_GATE = np.array([[1, 1], [1, -1]], dtype=complex) / np.sqrt(2)
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


CX_0_1 = np.array(
    [[1, 0, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0], [0, 1, 0, 0]],
    dtype=complex,
)
Y_BASIS_Q1 = on_qubit(H_GATE, 1) @ on_qubit(SDG, 1)
X_BASIS_BOTH = on_qubit(H_GATE, 1) @ on_qubit(H_GATE, 0)

# Exact integer single-shot energy contributions, scaled by 10,000.
# Groups: {ZI, ZZ}, {YZ}, {XX}; outcomes are 00, 01, 10, 11.
GROUP_NAMES = ("zi_zz", "yz", "xx")
GROUP_VALUES = (
    np.array([-4093, -3867, 4093, 3867], dtype=np.int64),
    np.array([3980, -3980, -3980, 3980], dtype=np.int64),
    np.array([1810, -1810, -1810, 1810], dtype=np.int64),
)
SHOTS_PER_UPDATE = 3 * len(GROUP_VALUES) * SHOTS_PER_GROUP


def rz(angle):
    return np.diag([np.exp(-0.5j * angle), np.exp(0.5j * angle)])


def ansatz_state(index):
    """H2 EfficientSU2(['h', 'rz', 'y'], circular, reps=1) state."""
    theta = 2.0 * np.pi * np.asarray(index) / GRID_SIZE
    state = np.array([1, 0, 0, 0], dtype=complex)
    for offset in (0, 2):
        for qubit in (0, 1):
            state = on_qubit(H_GATE, qubit) @ state
        for qubit in (0, 1):
            state = on_qubit(rz(theta[offset + qubit]), qubit) @ state
        for qubit in (0, 1):
            state = on_qubit(Y, qubit) @ state
        if offset == 0:
            state = CX_0_1 @ state
    return state


@lru_cache(maxsize=None)
def state_data(index):
    """Return exact logical energy and ideal Born laws for the three groups."""
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
    if not np.isclose(energy, reconstructed, atol=1e-12):
        raise AssertionError("Hamiltonian and measurement groups disagree")
    return energy, probabilities


def candidate_indices(index, coordinate):
    """Current, minus, plus candidates in deterministic tie-priority order."""
    candidates = [np.asarray(index, dtype=int).copy() for _ in range(3)]
    candidates[1][coordinate] = (
        candidates[1][coordinate] - 1
    ) % GRID_SIZE
    candidates[2][coordinate] = (
        candidates[2][coordinate] + 1
    ) % GRID_SIZE
    return candidates


def normal_cdf(x):
    """Vectorized standard-normal CDF, with maximum error about 7.5e-8."""
    t = 1.0 / (1.0 + 0.2316419 * np.abs(x))
    polynomial = (
        ((((1.330274429 * t - 1.821255978) * t + 1.781477937) * t
          - 0.356563782) * t + 0.319381530) * t
    )
    positive = (
        1.0
        - np.exp(-0.5 * x * x) * polynomial / np.sqrt(2.0 * np.pi)
    )
    return np.where(x >= 0.0, positive, 1.0 - positive)


def energy_moments():
    """Born-derived Gaussian mean and variance at every parameter point."""
    shape = (GRID_SIZE,) * 4
    means = np.empty(shape)
    variances = np.empty(shape)
    for index in np.ndindex(shape):
        energy, probabilities = state_data(index)
        means[index] = energy
        single_shot_variance = sum(
            np.dot(probability, values * values)
            - np.dot(probability, values) ** 2
            for probability, values in zip(probabilities, GROUP_VALUES)
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
    candidate_variances = (
        variances,
        np.roll(variances, 1, axis=coordinate),
        np.roll(variances, -1, axis=coordinate),
    )
    standard_deviations = tuple(np.sqrt(array) for array in candidate_variances)
    nodes, weights = np.polynomial.hermite.hermgauss(GAUSS_HERMITE_POINTS)
    probabilities = []

    for chosen in range(3):
        sampled_energy = (
            candidate_means[chosen][..., None]
            + np.sqrt(2.0)
            * standard_deviations[chosen][..., None]
            * nodes
        )
        probability = np.ones_like(sampled_energy)
        for other in range(3):
            if other == chosen:
                continue
            scale = np.maximum(
                standard_deviations[other][..., None], 1e-15
            )
            probability *= normal_cdf(
                (candidate_means[other][..., None] - sampled_energy) / scale
            )
        probabilities.append(
            np.sum(probability * weights, axis=-1) / np.sqrt(np.pi)
        )

    probabilities = [np.clip(p, 0.0, 1.0) for p in probabilities]
    total = probabilities[0] + probabilities[1] + probabilities[2]
    if np.any(total <= 0.0):
        raise AssertionError("Gaussian selection kernel has a zero row")
    return tuple(probability / total for probability in probabilities)


def build_analytical_data():
    print("Layer 1: computing Born-derived Gaussian transition kernels...")
    means, variances = energy_moments()
    kernels = [
        selection_kernel(means, variances, coordinate)
        for coordinate in range(4)
    ]
    success = (
        means - GROUND_ENERGY <= CONVERGENCE_TOLERANCE
    )
    for coordinate, kernel in enumerate(kernels):
        row_sums = kernel[0] + kernel[1] + kernel[2]
        if not np.allclose(row_sums, 1.0, atol=2e-12):
            raise AssertionError(f"Kernel {coordinate} is not stochastic")
    return means, variances, kernels, success


def propagate_analytical(kernels, success):
    """Return bounded success and non-convergence probabilities through step 50."""
    shape = (GRID_SIZE,) * 4
    mass = np.zeros(shape)
    mass[INITIAL_INDEX] = 1.0
    success_cdf = [float(mass[success].sum())]
    mass[success] = 0.0
    not_converged = [float(mass.sum())]

    for step in range(MAX_STEPS):
        coordinate = step % 4
        current, minus, plus = kernels[coordinate]
        mass = (
            mass * current
            + np.roll(mass * minus, -1, axis=coordinate)
            + np.roll(mass * plus, 1, axis=coordinate)
        )
        success_cdf.append(
            success_cdf[-1] + float(mass[success].sum())
        )
        mass[success] = 0.0
        not_converged.append(float(mass.sum()))

    total = success_cdf[-1] + not_converged[-1]
    if not np.isclose(total, 1.0, atol=2e-10):
        raise AssertionError(f"Analytical mass is {total}, not 1")
    return {
        "success": np.asarray(success_cdf),
        "not_converged": np.asarray(not_converged),
    }


def conditional_success_metrics(success_cdf):
    """E[updates | success by 50] and its fixed-shot equivalent."""
    increments = np.diff(np.asarray(success_cdf, dtype=float))
    probability = float(success_cdf[MAX_STEPS])
    if probability <= 0.0:
        return math.nan, math.nan
    updates = float(
        np.dot(np.arange(1, MAX_STEPS + 1), increments) / probability
    )
    return updates, updates * SHOTS_PER_UPDATE


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def analytical_property_rows(curves):
    updates, shots = conditional_success_metrics(curves["success"])
    rows = []
    for horizon in HORIZONS:
        rows.append(
            {
                "property": f"success_by_{horizon}",
                "value": f"{curves['success'][horizon]:.12g}",
                "semantics": f"P(T_success <= {horizon})",
            }
        )
    rows.extend(
        [
            {
                "property": "expected_updates_given_success_by_50",
                "value": f"{updates:.12g}",
                "semantics": "E[T_success | T_success <= 50]",
            },
            {
                "property": "expected_shots_given_success_by_50",
                "value": f"{shots:.12g}",
                "semantics": "E[shots | T_success <= 50]",
            },
        ]
    )
    return rows


def configuration_dict():
    return {
        "hamiltonian": {
            "YZ": 0.3980,
            "ZI": -0.3980,
            "ZZ": -0.0113,
            "XX": 0.1810,
        },
        "ground_energy": GROUND_ENERGY,
        "ansatz": "EfficientSU2(['h','rz','y'], circular, reps=1), 2 qubits",
        "grid_size_per_parameter": GRID_SIZE,
        "initial_index": INITIAL_INDEX,
        "measurement_groups": [
            ["ZI", "ZZ"],
            ["YZ"],
            ["XX"],
        ],
        "shots_per_group": SHOTS_PER_GROUP,
        "candidates_per_update": 3,
        "shots_per_completed_update": SHOTS_PER_UPDATE,
        "candidate_order": ["current", "minus", "plus"],
        "coordinate_schedule": [0, 1, 2, 3],
        "empirical_tie_priority": ["current", "minus", "plus"],
        "convergence_tolerance": CONVERGENCE_TOLERANCE,
        "maximum_updates": MAX_STEPS,
        "horizons": HORIZONS,
        "empirical_runs": RUNS,
        "fake_backend": FAKE_BACKEND_NAME,
        "seed": SEED,
    }


def flush_lines(handle, lines):
    if lines:
        handle.write("".join(lines))
        lines.clear()


def export_prism(kernels, success, output_dir):
    """Export a phase-augmented homogeneous DTMC in PRISM explicit format."""
    prism_dir = output_dir / "layer2_prism"
    prism_dir.mkdir(parents=True, exist_ok=True)
    shape = (GRID_SIZE,) * 4
    grid_states = GRID_SIZE ** 4
    total_states = 4 * grid_states
    flat_grid = np.arange(grid_states, dtype=np.int64).reshape(shape)
    success_flat = success.ravel()
    indices = np.column_stack(
        np.unravel_index(np.arange(grid_states), shape)
    )
    destination_flats = []
    flat_kernels = []
    for coordinate in range(4):
        destination_flats.append(
            (
                flat_grid.ravel(),
                np.roll(flat_grid, 1, axis=coordinate).ravel(),
                np.roll(flat_grid, -1, axis=coordinate).ravel(),
            )
        )
        flat_kernels.append(
            tuple(array.ravel() for array in kernels[coordinate])
        )

    nonzero_candidates = 0
    transition_count = 0
    for phase in range(4):
        for flat in range(grid_states):
            if success_flat[flat]:
                transition_count += 1
                continue
            for probability in flat_kernels[phase]:
                if probability[flat] > 0.0:
                    transition_count += 1
                    nonzero_candidates += 1

    tra_path = prism_dir / "h2_gaussian.tra"
    print(
        f"Layer 2: exporting {total_states:,} states and "
        f"{transition_count:,} transitions..."
    )
    with tra_path.open("w", encoding="utf-8") as handle:
        handle.write(f"{total_states} {transition_count}\n")
        lines = []
        for phase in range(4):
            next_phase = (phase + 1) % 4
            for flat in range(grid_states):
                source = phase * grid_states + flat
                if success_flat[flat]:
                    lines.append(f"{source} {source} 1\n")
                else:
                    row_sum = 0.0
                    for choice in range(3):
                        probability = flat_kernels[phase][choice][flat]
                        if probability <= 0.0:
                            continue
                        destination = (
                            next_phase * grid_states
                            + int(destination_flats[phase][choice][flat])
                        )
                        lines.append(
                            f"{source} {destination} {probability:.17g}\n"
                        )
                        row_sum += probability
                    if not math.isclose(row_sum, 1.0, abs_tol=2e-12):
                        raise AssertionError(
                            f"PRISM row {source} sums to {row_sum}"
                        )
                if len(lines) >= 12000:
                    flush_lines(handle, lines)
        flush_lines(handle, lines)

    sta_path = prism_dir / "h2_gaussian.sta"
    with sta_path.open("w", encoding="utf-8") as handle:
        handle.write("(i0,i1,i2,i3,phase,status)\n")
        lines = []
        for phase in range(4):
            for flat, index in enumerate(indices):
                state = phase * grid_states + flat
                status = 1 if success_flat[flat] else 0
                values = ",".join(str(int(value)) for value in index)
                lines.append(
                    f"{state}:({values},{phase},{status})\n"
                )
                if len(lines) >= 12000:
                    flush_lines(handle, lines)
        flush_lines(handle, lines)

    initial_flat = int(np.ravel_multi_index(INITIAL_INDEX, shape))
    initial_state = initial_flat
    lab_path = prism_dir / "h2_gaussian.lab"
    with lab_path.open("w", encoding="utf-8") as handle:
        handle.write('0="init" 1="running" 2="success"\n')
        lines = []
        for phase in range(4):
            for flat in range(grid_states):
                state = phase * grid_states + flat
                labels = ["2"] if success_flat[flat] else ["1"]
                if state == initial_state:
                    labels.insert(0, "0")
                lines.append(f"{state}: {' '.join(labels)}\n")
                if len(lines) >= 12000:
                    flush_lines(handle, lines)
        flush_lines(handle, lines)

    reward_paths = {
        "updates": prism_dir / "h2_gaussian_updates.trew",
        "shots": prism_dir / "h2_gaussian_shots.trew",
    }
    reward_values = {"updates": 1, "shots": SHOTS_PER_UPDATE}
    for name, path in reward_paths.items():
        with path.open("w", encoding="utf-8") as handle:
            handle.write(f'# Reward structure "{name}"\n')
            handle.write("# Transition rewards\n")
            handle.write(f"{total_states} {nonzero_candidates}\n")
            lines = []
            for phase in range(4):
                next_phase = (phase + 1) % 4
                for flat in range(grid_states):
                    if success_flat[flat]:
                        continue
                    source = phase * grid_states + flat
                    for choice in range(3):
                        probability = flat_kernels[phase][choice][flat]
                        if probability <= 0.0:
                            continue
                        destination = (
                            next_phase * grid_states
                            + int(destination_flats[phase][choice][flat])
                        )
                        lines.append(
                            f"{source} {destination} {reward_values[name]}\n"
                        )
                    if len(lines) >= 12000:
                        flush_lines(handle, lines)
            flush_lines(handle, lines)

    props_path = prism_dir / "h2_gaussian.props"
    fixed_properties = "\n".join(
        f'"P_success_{horizon}": P=? [ F<={horizon} "success" ];'
        for horizon in HORIZONS
    )
    props_path.write_text(
        (
            "// Approved property family: bounded convergence.\n"
            "// H is swept from 0 through 50 to recover the first-hit law.\n"
            "const int H;\n\n"
            '"P_success_by_H": P=? [ F<=H "success" ];\n'
            f"\n{fixed_properties}\n"
        ),
        encoding="utf-8",
    )

    metadata = {
        "model_type": "DTMC",
        "analytical_semantics": "Born-derived Gaussian finite-shot approximation",
        "state_count": total_states,
        "transition_count": transition_count,
        "nonzero_rewarded_candidate_transitions": nonzero_candidates,
        "initial_state": initial_state,
        "state_variables": ["i0", "i1", "i2", "i3", "phase", "status"],
        "status_values": {"running": 0, "success": 1},
        "phase_semantics": "active coordinate for the next optimizer update",
        "transition_semantics": (
            "One transition is one complete optimizer update."
        ),
        "files": {},
    }
    for path in [
        tra_path,
        sta_path,
        lab_path,
        *reward_paths.values(),
        props_path,
    ]:
        metadata["files"][path.name] = {
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
    write_json(prism_dir / "model_metadata.json", metadata)
    write_prism_readme(prism_dir)
    return metadata


def write_prism_readme(prism_dir):
    text = f"""# Layer 2 — PRISM explicit Gaussian DTMC

The transition matrix contains only the Born-derived Gaussian optimizer kernel.
No empirical FakeBackend transition frequency is used.

One DTMC transition is one complete optimizer update: 9 circuits are measured
(three candidates times three groups), the selected parameter point is entered,
and the coordinate phase advances.

## Run the approved PRISM properties

Install the command-line PRISM distribution from
https://www.prismmodelchecker.org/download.php and either add its `bin`
directory to `PATH` or replace `prism` below with the full path to that
executable.

From this directory:

```bash
prism -importmodel h2_gaussian.tra,sta,lab -dtmc -ex \\
  h2_gaussian.props -prop P_success_by_H -const H=0:1:50 \\
  -exportresults ../layer3_prism_results/prism_success_curve.csv:csv
```

The fixed-horizon convergence properties can also be checked together:

```bash
prism -importmodel h2_gaussian.tra,sta,lab -dtmc -ex \\
  h2_gaussian.props -const H=50 \\
  -prop P_success_10,P_success_20,P_success_30,P_success_40,P_success_50
```

## Conditional update and shot expectations

The requested expectation excludes runs that do not converge by iteration 50,
so it is derived from the PRISM bounded-success curve:

`P(T=t) = P(T<=t) - P(T<=t-1)`

`E[T | T<=50] = sum(t * P(T=t)) / P(T<=50)`

Run the workflow's `summarize-prism` command after exporting the CSV file.
The shot expectation is exactly `{SHOTS_PER_UPDATE}` times the update
expectation. The `.trew` files are supplied for auditing the resource mapping;
each non-terminal optimizer transition costs one update and
`{SHOTS_PER_UPDATE}` shots.
"""
    (prism_dir / "README.md").write_text(text, encoding="utf-8")


def write_layer1(output_dir, curves, variances):
    layer = output_dir / "layer1_analytical"
    layer.mkdir(parents=True, exist_ok=True)
    write_json(layer / "configuration.json", configuration_dict())
    curve_rows = [
        {
            "horizon": horizon,
            "success_probability": f"{curves['success'][horizon]:.12g}",
            "not_converged_probability": (
                f"{curves['not_converged'][horizon]:.12g}"
            ),
        }
        for horizon in range(MAX_STEPS + 1)
    ]
    write_csv(
        layer / "analytical_curve.csv",
        [
            "horizon",
            "success_probability",
            "not_converged_probability",
        ],
        curve_rows,
    )
    write_csv(
        layer / "analytical_properties.csv",
        ["property", "value", "semantics"],
        analytical_property_rows(curves),
    )
    readme = f"""# Layer 1 — Analytical Gaussian DTMC

Every current/minus/plus energy law is approximated by a Gaussian whose mean
and variance are calculated from the ideal H2 Born probabilities with
{SHOTS_PER_GROUP} shots per commuting group. Candidate measurements are
independent. Gaussian minimum probabilities define the optimizer transition
kernel.

The physical noise stored in FakeJakarta is intentionally absent from this
analytical kernel; it appears only in Layer 4. Both layers run for up to 50
optimizer updates and stop early only upon convergence.

The Gaussian abstraction has continuous energies and therefore zero tie
probability. The direct finite-shot experiment has discrete scores and applies
the declared current/minus/plus tie priority.

Minimum/maximum analytical energy variance on the grid:
`[{float(np.min(variances)):.12g}, {float(np.max(variances)):.12g}]`.
"""
    (layer / "README.md").write_text(readme, encoding="utf-8")


def write_layer3_scaffold(output_dir):
    layer = output_dir / "layer3_prism_results"
    layer.mkdir(parents=True, exist_ok=True)
    rows = [
        {"property": f"success_by_{h}", "prism_result": ""}
        for h in HORIZONS
    ]
    rows.extend(
        [
            {
                "property": "expected_updates_given_success_by_50",
                "prism_result": "",
            },
            {
                "property": "expected_shots_given_success_by_50",
                "prism_result": "",
            },
        ]
    )
    write_csv(
        layer / "prism_properties_template.csv",
        ["property", "prism_result"],
        rows,
    )
    (layer / "README.md").write_text(
        """# Layer 3 — PRISM results

Run the PRISM command in `../layer2_prism/README.md`, then run:

```bash
python h2_prism_fakebackend_workflow.py summarize-prism \\
  --success-csv artifacts/h2_vqe/layer3_prism_results/prism_success_curve.csv
```

This creates `prism_properties.csv` and inserts the PRISM values into the
Layer 4 comparison table. The conditional expectations are calculated from
the PRISM first-success distribution, so non-converged paths are not assigned
zero and do not enter the denominator.
""",
        encoding="utf-8",
    )


def build(output_dir):
    means, variances, kernels, success = build_analytical_data()
    curves = propagate_analytical(kernels, success)
    write_layer1(output_dir, curves, variances)
    metadata = export_prism(kernels, success, output_dir)
    write_layer3_scaffold(output_dir)
    write_manifest(output_dir, metadata)
    print_analytical_summary(curves)
    return curves


def print_analytical_summary(curves):
    updates, shots = conditional_success_metrics(curves["success"])
    print("Analytical Gaussian DTMC reference:")
    for horizon in HORIZONS:
        print(
            f"  P(success by {horizon:2d}) = "
            f"{curves['success'][horizon]:.6f}"
        )
    print(f"  E[updates | success by 50] = {updates:.6f}")
    print(f"  E[shots | success by 50]   = {shots:.2f}")
    print(
        f"  P(not converged by 50)     = "
        f"{curves['not_converged'][50]:.6f}"
    )


def build_fake_backend_circuits(output_dir):
    """Create and transpile the shared measurement circuits for FakeJakarta."""
    try:
        import qiskit
        from qiskit import QuantumCircuit, transpile
        from qiskit.circuit import ParameterVector
        from qiskit.providers.fake_provider import FakeJakarta
    except ImportError as error:
        raise RuntimeError(
            "The empirical command requires Qiskit with FakeJakarta and Aer. "
            "The validated local environment uses qiskit==0.38.0."
        ) from error

    theta = ParameterVector("theta", 4)
    state = QuantumCircuit(2)
    for offset in (0, 2):
        state.h(0)
        state.h(1)
        state.rz(theta[offset], 0)
        state.rz(theta[offset + 1], 1)
        state.y(0)
        state.y(1)
        if offset == 0:
            state.cx(0, 1)

    circuits = []
    for name in GROUP_NAMES:
        circuit = state.copy()
        circuit.name = name
        if name == "yz":
            circuit.sdg(1)
            circuit.h(1)
        elif name == "xx":
            circuit.h(0)
            circuit.h(1)
        circuit.measure_all()
        circuits.append(circuit)

    backend = FakeJakarta()
    backend.set_options(method="density_matrix")
    transpiled = transpile(
        circuits,
        backend=backend,
        optimization_level=3,
        seed_transpiler=TRANSPILE_SEED,
    )

    layer = output_dir / "layer4_empirical"
    layer.mkdir(parents=True, exist_ok=True)
    for name, circuit in zip(GROUP_NAMES, transpiled):
        qasm_method = getattr(circuit, "qasm", None)
        if callable(qasm_method):
            inspection_circuit = bind_circuit(
                circuit, theta, INITIAL_INDEX
            )
            (layer / f"transpiled_{name}_initial.qasm").write_text(
                inspection_circuit.qasm(), encoding="utf-8"
            )

    qiskit_versions_raw = getattr(qiskit, "__qiskit_version__", None)
    qiskit_versions = (
        {str(key): value for key, value in qiskit_versions_raw.items()}
        if hasattr(qiskit_versions_raw, "items")
        else str(qiskit_versions_raw)
    )
    metadata = {
        "backend": backend.name(),
        "backend_class": type(backend).__name__,
        "backend_properties_last_update": str(
            getattr(backend.properties(), "last_update_date", None)
        ),
        "qiskit_versions": qiskit_versions,
        "python": sys.version,
        "platform": platform.platform(),
        "transpile_seed": TRANSPILE_SEED,
        "optimization_level": 3,
        "simulation_method": "density_matrix",
        "transpiled_depths": [circuit.depth() for circuit in transpiled],
        "transpiled_operations": [
            {str(k): int(v) for k, v in circuit.count_ops().items()}
            for circuit in transpiled
        ],
    }
    write_json(layer / "fakebackend_metadata.json", metadata)
    return backend, tuple(theta), transpiled, metadata


def bind_circuit(circuit, parameters, index):
    angles = 2.0 * np.pi * np.asarray(index) / GRID_SIZE
    values = {
        parameter: float(angle)
        for parameter, angle in zip(parameters, angles)
    }
    assign = getattr(circuit, "assign_parameters", None)
    if callable(assign):
        return assign(values, inplace=False)
    return circuit.bind_parameters(values)


def score_counts(counts, values):
    if sum(counts.values()) != SHOTS_PER_GROUP:
        raise RuntimeError(
            f"Expected {SHOTS_PER_GROUP} shots, got {sum(counts.values())}"
        )
    score = 0
    for bitstring, count in counts.items():
        bits = bitstring.replace(" ", "")
        if len(bits) != 2:
            raise RuntimeError(f"Expected two-bit outcome, got {bitstring!r}")
        score += int(count) * int(values[int(bits, 2)])
    return score


def run_fakebackend_experiment(output_dir, runs=RUNS):
    """Execute direct finite-shot runs on noisy FakeJakarta; build no DTMC."""
    backend, parameters, circuits, backend_metadata = (
        build_fake_backend_circuits(output_dir)
    )
    simulator_rng = np.random.default_rng(SEED)
    records = [
        {
            "run": run + 1,
            "outcome": "running",
            "index": np.array(INITIAL_INDEX, dtype=int),
            "updates": 0,
            "shots": 0,
            "success_step": None,
            "history": [],
        }
        for run in range(runs)
    ]

    print(
        f"Layer 4: running {runs} direct noisy {FAKE_BACKEND_NAME} "
        f"experiments ({SHOTS_PER_GROUP} shots/group)..."
    )
    for step in range(MAX_STEPS):
        active = [record for record in records if record["outcome"] == "running"]
        if not active:
            break

        coordinate = step % 4
        work = []
        candidates_by_run = {}
        scores_by_run = {}
        for record in active:
            run_id = record["run"]
            candidates = candidate_indices(record["index"], coordinate)
            candidates_by_run[run_id] = candidates
            scores_by_run[run_id] = [0, 0, 0]
            for candidate_number, candidate in enumerate(candidates):
                for group_number, circuit in enumerate(circuits):
                    work.append(
                        (
                            run_id,
                            candidate_number,
                            group_number,
                            bind_circuit(circuit, parameters, candidate),
                        )
                    )

        for start in range(0, len(work), MAX_CIRCUITS_PER_FAKE_JOB):
            chunk = work[start:start + MAX_CIRCUITS_PER_FAKE_JOB]
            seed = int(
                simulator_rng.integers(1, np.iinfo(np.int32).max)
            )
            result = backend.run(
                [entry[3] for entry in chunk],
                shots=SHOTS_PER_GROUP,
                seed_simulator=seed,
            ).result()
            if not getattr(result, "success", True):
                raise RuntimeError("FakeBackend returned an unsuccessful job")
            for local_index, (
                run_id,
                candidate_number,
                group_number,
                _,
            ) in enumerate(chunk):
                counts = result.get_counts(local_index)
                scores_by_run[run_id][candidate_number] += score_counts(
                    counts, GROUP_VALUES[group_number]
                )

        for record in active:
            run_id = record["run"]
            before = record["index"].copy()
            scores = scores_by_run[run_id]
            choice = int(np.argmin(scores))
            record["index"] = candidates_by_run[run_id][choice]
            record["updates"] += 1
            record["shots"] += SHOTS_PER_UPDATE
            exact_energy, _ = state_data(tuple(record["index"]))
            record["history"].append(
                {
                    "attempt": step + 1,
                    "event": "optimizer_update",
                    "coordinate": coordinate,
                    "index_before": [int(x) for x in before],
                    "candidate_scores": [int(x) for x in scores],
                    "candidate_measured_energies": [
                        score / (SHOTS_PER_GROUP * 10000.0)
                        for score in scores
                    ],
                    "choice": choice,
                    "index_after": [int(x) for x in record["index"]],
                    "exact_logical_energy": exact_energy,
                }
            )
            if (
                exact_energy - GROUND_ENERGY
                <= CONVERGENCE_TOLERANCE
            ):
                record["outcome"] = "success"
                record["success_step"] = step + 1

        successes = sum(r["outcome"] == "success" for r in records)
        remaining = runs - successes
        print(
            f"  attempt {step + 1:2d}/{MAX_STEPS}: "
            f"success={successes}, running={remaining}",
            flush=True,
        )

    for record in records:
        if record["outcome"] == "running":
            record["outcome"] = "not_converged_by_50"

    layer = output_dir / "layer4_empirical"
    trace_path = layer / "fakebackend_runs.jsonl"
    with trace_path.open("w", encoding="utf-8") as handle:
        for record in records:
            serializable = dict(record)
            serializable["index"] = [
                int(value) for value in record["index"]
            ]
            handle.write(json.dumps(serializable, sort_keys=True) + "\n")

    result = write_empirical_results(output_dir, records, backend_metadata)
    return result


def wilson_interval(successes, total, z=1.96):
    if total <= 0:
        return math.nan, math.nan
    rate = successes / total
    denominator = 1.0 + z * z / total
    center = (rate + z * z / (2.0 * total)) / denominator
    half_width = (
        z
        * math.sqrt(
            rate * (1.0 - rate) / total
            + z * z / (4.0 * total * total)
        )
        / denominator
    )
    return center - half_width, center + half_width


def mean_interval(values, lower_bound, upper_bound, z=1.96):
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return math.nan, math.nan, math.nan
    mean = float(np.mean(values))
    if len(values) == 1:
        return mean, mean, mean
    half = z * float(np.std(values, ddof=1)) / math.sqrt(len(values))
    return mean, max(lower_bound, mean - half), min(upper_bound, mean + half)


def read_property_values(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return {
            row["property"]: float(row["value"])
            for row in csv.DictReader(handle)
        }


def write_empirical_results(output_dir, records, backend_metadata):
    layer = output_dir / "layer4_empirical"
    runs = len(records)
    rows = []
    empirical_values = {}
    empirical_intervals = {}
    for horizon in HORIZONS:
        count = sum(
            record["success_step"] is not None
            and record["success_step"] <= horizon
            for record in records
        )
        value = count / runs
        low, high = wilson_interval(count, runs)
        name = f"success_by_{horizon}"
        empirical_values[name] = value
        empirical_intervals[name] = (low, high)
        rows.append(
            {
                "property": name,
                "estimate": f"{value:.12g}",
                "ci95_low": f"{low:.12g}",
                "ci95_high": f"{high:.12g}",
                "sample_size": runs,
                "semantics": f"direct fraction with success_step <= {horizon}",
            }
        )

    successful = [r for r in records if r["outcome"] == "success"]
    update_values = [r["updates"] for r in successful]
    update_mean, update_low, update_high = mean_interval(
        update_values, 1, MAX_STEPS
    )
    shot_values = [r["shots"] for r in successful]
    shot_mean, shot_low, shot_high = mean_interval(
        shot_values, SHOTS_PER_UPDATE, SHOTS_PER_UPDATE * MAX_STEPS
    )
    for name, value, low, high, semantics in [
        (
            "expected_updates_given_success_by_50",
            update_mean,
            update_low,
            update_high,
            "sample mean over successful runs only",
        ),
        (
            "expected_shots_given_success_by_50",
            shot_mean,
            shot_low,
            shot_high,
            "sample mean over successful runs only",
        ),
    ]:
        empirical_values[name] = value
        empirical_intervals[name] = (low, high)
        rows.append(
            {
                "property": name,
                "estimate": f"{value:.12g}",
                "ci95_low": f"{low:.12g}",
                "ci95_high": f"{high:.12g}",
                "sample_size": len(successful),
                "semantics": semantics,
            }
        )

    write_csv(
        layer / "empirical_properties.csv",
        [
            "property",
            "estimate",
            "ci95_low",
            "ci95_high",
            "sample_size",
            "semantics",
        ],
        rows,
    )

    analytical = read_property_values(
        output_dir
        / "layer1_analytical"
        / "analytical_properties.csv"
    )
    comparison = []
    for property_name, analytical_value in analytical.items():
        empirical_value = empirical_values[property_name]
        low, high = empirical_intervals[property_name]
        comparison.append(
            {
                "property": property_name,
                "analytical_gaussian": f"{analytical_value:.12g}",
                "prism_result": "",
                "fakebackend_empirical": f"{empirical_value:.12g}",
                "empirical_ci95_low": f"{low:.12g}",
                "empirical_ci95_high": f"{high:.12g}",
                "absolute_difference": (
                    f"{abs(analytical_value - empirical_value):.12g}"
                ),
            }
        )
    write_csv(
        layer / "comparison.csv",
        [
            "property",
            "analytical_gaussian",
            "prism_result",
            "fakebackend_empirical",
            "empirical_ci95_low",
            "empirical_ci95_high",
            "absolute_difference",
        ],
        comparison,
    )

    outcomes = {
        outcome: sum(r["outcome"] == outcome for r in records)
        for outcome in ("success", "not_converged_by_50")
    }
    summary = {
        "runs": runs,
        "outcomes": outcomes,
        "backend": backend_metadata,
        "no_empirical_dtmc_constructed": True,
    }
    write_json(layer / "empirical_summary.json", summary)
    write_layer4_readme(layer, outcomes)
    print(
        "FakeBackend direct results: "
        f"success={outcomes['success']}/{runs}, "
        f"not_converged={outcomes['not_converged_by_50']}/{runs}"
    )
    return summary


def write_layer4_readme(layer, outcomes):
    text = f"""# Layer 4 — Direct noisy FakeBackend statistics

These are {RUNS} direct adaptive VQE executions on Qiskit's noisy
`{FAKE_BACKEND_NAME}` snapshot. No empirical transition matrix or empirical
DTMC is inferred.

The fixed protocol uses {SHOTS_PER_GROUP} shots for each of three commuting
groups and independently measures current, minus, and plus. FakeBackend gate,
relaxation, and readout noise affect the measured candidate scores. There is no
injected reliability event or artificial early termination.

Observed terminal counts:

- success: {outcomes['success']}
- not converged by 50: {outcomes['not_converged_by_50']}

`fakebackend_runs.jsonl` is the direct trace record. `empirical_properties.csv`
contains direct estimates and confidence intervals. `comparison.csv` compares
them with Layer 1 and has an empty PRISM column until `summarize-prism` is run.
"""
    (layer / "README.md").write_text(text, encoding="utf-8")


def write_manifest(output_dir, prism_metadata):
    text = f"""# H2 VQE probabilistic-verification artifact

This artifact is deliberately separated into four review layers:

1. `layer1_analytical`: Born-derived Gaussian DTMC assumptions and reference
   property values.
2. `layer2_prism`: explicit PRISM transition, state, label, reward, and
   property files.
3. `layer3_prism_results`: instructions and result-table scaffold. PRISM is
   not executed by this workflow.
4. `layer4_empirical`: direct 400-run noisy FakeBackend traces, statistics,
   and comparison. No empirical DTMC is built.

PRISM model size: {prism_metadata['state_count']:,} states and
{prism_metadata['transition_count']:,} transitions.

The analytical and empirical layers share the Hamiltonian, ansatz, initial
parameters, optimizer semantics, measurement grouping, shots per group,
parameter grid, convergence definition, and iteration limit. They intentionally
differ in physical measurement noise: Layer 1 uses ideal Born probabilities
with a Gaussian finite-shot approximation; Layer 4 uses FakeJakarta's stored
noise model.
"""
    (output_dir / "MANIFEST.md").write_text(text, encoding="utf-8")


def read_prism_curve(path):
    """Read PRISM experiment CSV with columns H and Result."""
    values = {}
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for raw_row in reader:
            row = {
                str(key).strip(): value.strip()
                for key, value in raw_row.items()
                if key is not None and value is not None
            }
            horizon_key = next(
                (key for key in row if key.lower() == "h"), None
            )
            result_key = next(
                (key for key in row if key.lower() == "result"), None
            )
            if horizon_key is None or result_key is None:
                raise ValueError(
                    f"{path} must contain H and Result columns"
                )
            horizon = int(round(float(row[horizon_key])))
            values[horizon] = float(row[result_key])
    missing = set(range(MAX_STEPS + 1)) - set(values)
    if missing:
        raise ValueError(f"{path} is missing horizons: {sorted(missing)}")
    return np.asarray([values[h] for h in range(MAX_STEPS + 1)])


def summarize_prism(output_dir, success_csv):
    success = read_prism_curve(success_csv)
    updates, shots = conditional_success_metrics(success)
    values = {
        **{f"success_by_{h}": float(success[h]) for h in HORIZONS},
        "expected_updates_given_success_by_50": updates,
        "expected_shots_given_success_by_50": shots,
    }
    layer3 = output_dir / "layer3_prism_results"
    rows = [
        {"property": name, "prism_result": f"{value:.12g}"}
        for name, value in values.items()
    ]
    write_csv(
        layer3 / "prism_properties.csv",
        ["property", "prism_result"],
        rows,
    )

    analytical = read_property_values(
        output_dir
        / "layer1_analytical"
        / "analytical_properties.csv"
    )
    validation_rows = [
        {
            "property": name,
            "analytical_python": f"{analytical[name]:.12g}",
            "prism": f"{value:.12g}",
            "absolute_difference": f"{abs(analytical[name] - value):.12g}",
        }
        for name, value in values.items()
    ]
    write_csv(
        layer3 / "prism_vs_analytical.csv",
        [
            "property",
            "analytical_python",
            "prism",
            "absolute_difference",
        ],
        validation_rows,
    )

    comparison_path = output_dir / "layer4_empirical" / "comparison.csv"
    if comparison_path.exists():
        with comparison_path.open(newline="", encoding="utf-8") as handle:
            comparison = list(csv.DictReader(handle))
        for row in comparison:
            row["prism_result"] = f"{values[row['property']]:.12g}"
        write_csv(
            comparison_path,
            [
                "property",
                "analytical_gaussian",
                "prism_result",
                "fakebackend_empirical",
                "empirical_ci95_low",
                "empirical_ci95_high",
                "absolute_difference",
            ],
            comparison,
        )
    print(f"Wrote {layer3 / 'prism_properties.csv'}")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Artifact root (default: {DEFAULT_OUTPUT})",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("build", help="Build analytical and PRISM layers")
    empirical = subparsers.add_parser(
        "empirical", help="Run 400 direct noisy FakeBackend executions"
    )
    empirical.add_argument("--runs", type=int, default=RUNS)
    subparsers.add_parser("all", help="Build, then run empirical experiment")
    summarize = subparsers.add_parser(
        "summarize-prism", help="Post-process PRISM experiment CSV files"
    )
    summarize.add_argument("--success-csv", type=Path, required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    output_dir = args.output.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.command == "build":
        build(output_dir)
    elif args.command == "empirical":
        analytical_path = (
            output_dir
            / "layer1_analytical"
            / "analytical_properties.csv"
        )
        if not analytical_path.exists():
            raise SystemExit(
                "Run the build command before the empirical command."
            )
        run_fakebackend_experiment(output_dir, args.runs)
    elif args.command == "all":
        build(output_dir)
        run_fakebackend_experiment(output_dir, RUNS)
    elif args.command == "summarize-prism":
        summarize_prism(output_dir, args.success_csv)


if __name__ == "__main__":
    main()
