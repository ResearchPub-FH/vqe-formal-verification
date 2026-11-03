#!/usr/bin/env python3
"""Instrumented VQE evaluations for the Dafny/runtime verification artifact.

The default ``demo`` mode has no third-party dependencies and emits deterministic
term-level traces for the H2 and LiH case studies.  The optional
``qiskit-statevector`` mode runs the selected Hamiltonian with Qiskit's local
StatevectorEstimator when Qiskit and SciPy are installed.

The trace deliberately records the assumptions used by the Dafny proof:
complete term vectors, per-term energy contributions, bounded parameters,
shot accounting, convergence metadata, layout identities, and fresh optimizer
inputs.  The Qiskit execution paths submit all Hamiltonian term observables in
one Estimator PUB per optimizer evaluation and unpack the returned expectation
vector into the term-level trace.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


SCHEMA_VERSION = 2
ANGLE_LOWER = -math.pi
ANGLE_UPPER = math.pi


SYSTEMS: Dict[str, Dict[str, Any]] = {
    "h2": {
        "label": "H2 two-qubit Hamiltonian from the supplied Qiskit example",
        "kind": "explicit",
        "paulis": ["YZ", "ZI", "ZZ", "XX"],
        "coefficients": [0.3980, -0.3980, -0.0113, 0.1810],
        "reference_ground_energy": -0.7029,
        "convergence_tolerance": 1e-5,
        "statevector_maxiter": 80,
        "runtime_maxiter": 30,
        "min_iterations": 30,
        "convergence_patience": 5,
        "ansatz_su2_gates": ["h", "rz", "y"],
        "ansatz_entanglement": "circular",
        "ansatz_reps": 1,
        "shots": 10000,
        "theta": [
            [2.40, -1.70, 0.80, -2.20, 1.10, -0.40],
            [1.80, -1.20, 0.45, -1.60, 0.75, -0.25],
            [1.10, -0.75, 0.20, -1.05, 0.40, -0.10],
        ],
        "target_expectations": [
            [0.10, -0.20, 0.30, -0.10],
            [-0.30, 0.50, -0.20, -0.60],
            [-0.60, 0.70, 0.10, -0.80],
        ],
    },
    "lih": {
        "label": "LiH reduced active-space verification fixture",
        "kind": "explicit",
        "paulis": [
            "IIII",
            "ZIII",
            "IZII",
            "IIZI",
            "IIIZ",
            "ZZII",
            "IIZZ",
            "XXXX",
        ],
        "coefficients": [
            -7.4989469,
            0.1619948,
            0.1619948,
            -0.1244477,
            -0.1244477,
            0.0570634,
            0.0570634,
            0.0452328,
        ],
        "reference_ground_energy": -8.10,
        "convergence_tolerance": 1e-5,
        "statevector_maxiter": 80,
        "runtime_maxiter": 30,
        "min_iterations": 30,
        "convergence_patience": 5,
        "ansatz_su2_gates": ["ry"],
        "ansatz_entanglement": "linear",
        "ansatz_reps": 1,
        "shots": 4096,
        "theta": [
            [2.8, -2.2, 1.7, -1.3, 0.9, -0.7, 0.4, -0.2],
            [2.1, -1.7, 1.2, -0.9, 0.6, -0.5, 0.25, -0.1],
            [1.4, -1.1, 0.8, -0.6, 0.35, -0.25, 0.12, -0.04],
        ],
        "target_expectations": [
            [1.0, 0.20, 0.10, -0.30, -0.20, 0.10, 0.05, 0.0],
            [1.0, -0.40, -0.30, 0.50, 0.40, -0.20, -0.10, -0.50],
            [1.0, -0.70, -0.60, 0.70, 0.65, -0.40, -0.30, -0.80],
        ],
    },
    "heisenberg14": {
        "label": "14-qubit all-to-all Heisenberg benchmark",
        "kind": "heisenberg_all_to_all",
        "num_qubits": 14,
        "coupling": 1.0 / 13.0,
        "field": 0.3,
        "convergence_tolerance": 1e-4,
        "statevector_maxiter": 30,
        "runtime_maxiter": 10,
        "min_iterations": 10,
        "convergence_patience": 3,
        "ansatz_su2_gates": ["ry"],
        "ansatz_entanglement": "linear",
        "ansatz_reps": 1,
        "shots": 1024,
    },
}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_float(value: float) -> str:
    """Return the stable representation used by all trace hashes."""
    return format(float(value), ".17g")


def hash_vector(values: Sequence[float]) -> str:
    return _sha256(",".join(canonical_float(value) for value in values))


def hash_energy(energy: float) -> str:
    return _sha256(canonical_float(energy))


def normalize_angle(value: float) -> float:
    """Map an angle to the half-open interval [-pi, pi)."""
    normalized = (float(value) + math.pi) % (2.0 * math.pi) - math.pi
    return ANGLE_LOWER if normalized == ANGLE_UPPER else normalized


def counts_to_expectation(counts_ones: int, shots: int) -> float:
    if shots <= 0:
        raise ValueError("shots must be positive for count normalization")
    if not 0 <= counts_ones <= shots:
        raise ValueError("counts_ones must lie between zero and shots")
    return 1.0 - 2.0 * counts_ones / shots


def target_to_counts(expectation: float, shots: int) -> int:
    if not -1.0 <= expectation <= 1.0:
        raise ValueError("target expectation must lie in [-1, 1]")
    return int(round((1.0 - expectation) * shots / 2.0))


def pauli_label(num_qubits: int, assignments: Dict[int, str]) -> str:
    label = ["I"] * num_qubits
    for qubit, pauli in assignments.items():
        if not 0 <= qubit < num_qubits:
            raise ValueError("qubit index out of range")
        label[num_qubits - qubit - 1] = pauli
    return "".join(label)


def heisenberg_all_to_all_terms(
    num_qubits: int, coupling: float, field: float
) -> Tuple[List[str], List[float]]:
    paulis: List[str] = []
    coefficients: List[float] = []
    for left in range(num_qubits):
        for right in range(left + 1, num_qubits):
            for axis in ("X", "Y", "Z"):
                paulis.append(pauli_label(num_qubits, {left: axis, right: axis}))
                coefficients.append(float(coupling))
    for qubit in range(num_qubits):
        paulis.append(pauli_label(num_qubits, {qubit: "Z"}))
        coefficients.append(float(field))
    return paulis, coefficients


def materialize_system(system: str) -> Dict[str, Any]:
    if system not in SYSTEMS:
        raise ValueError("unknown system: {}".format(system))
    spec = dict(SYSTEMS[system])
    if spec.get("kind") == "heisenberg_all_to_all":
        paulis, coefficients = heisenberg_all_to_all_terms(
            int(spec["num_qubits"]),
            float(spec["coupling"]),
            float(spec["field"]),
        )
        spec["paulis"] = paulis
        spec["coefficients"] = coefficients
    return spec


def exact_ground_energy(paulis: Sequence[str], coefficients: Sequence[float]) -> float:
    try:
        from qiskit.quantum_info import SparsePauliOp
        from scipy.sparse.linalg import eigsh
    except ImportError as exc:
        raise SystemExit(
            "exact reference generation requires qiskit and scipy: {}".format(exc)
        )

    operator = SparsePauliOp.from_list(
        [(pauli, float(coefficient)) for pauli, coefficient in zip(paulis, coefficients)]
    )
    matrix = operator.to_matrix(sparse=True)
    value = eigsh(matrix, k=1, which="SA", return_eigenvectors=False)[0]
    return float(value.real)


def _aligned_lengths(vectors: Iterable[Sequence[Any]]) -> bool:
    lengths = {len(vector) for vector in vectors}
    return len(lengths) == 1


def build_record(
    *,
    run_id: str,
    system: str,
    iteration: int,
    theta: Sequence[float],
    paulis: Sequence[str],
    coefficients: Sequence[float],
    expectations: Sequence[float],
    shots: Sequence[int],
    counts_ones: Sequence[int],
    counts_available: Sequence[bool],
    layout_hash: str,
    shot_budget: int,
    budget_used_before: int,
    estimator_kind: str,
    reference_ground_energy: Optional[float],
    previous_energy: Optional[float],
    convergence_tolerance: float,
    min_iterations: int,
    convergence_patience: int,
    previous_stable_delta_count: int,
    max_iterations: int,
    final_iteration: bool,
) -> Dict[str, Any]:
    """Build one complete per-evaluation trace record."""
    vectors = [
        paulis,
        coefficients,
        expectations,
        shots,
        counts_ones,
        counts_available,
    ]
    if not _aligned_lengths(vectors):
        raise ValueError("term-level trace vectors must have identical lengths")
    if iteration < 0:
        raise ValueError("iteration must be non-negative")
    if max_iterations <= 0:
        raise ValueError("max_iterations must be positive")
    if convergence_tolerance < 0.0:
        raise ValueError("convergence_tolerance must be non-negative")
    if min_iterations <= 0:
        raise ValueError("min_iterations must be positive")
    if convergence_patience <= 0:
        raise ValueError("convergence_patience must be positive")
    if previous_stable_delta_count < 0:
        raise ValueError("previous_stable_delta_count must be non-negative")

    bounded_theta = [normalize_angle(value) for value in theta]
    theta_id = hash_vector(bounded_theta)
    per_term_energies = [
        float(coefficient) * float(expectation)
        for coefficient, expectation in zip(coefficients, expectations)
    ]
    energy = math.fsum(
        per_term_energies
    )
    energy_id = hash_energy(energy)
    energy_terms_id = hash_vector(per_term_energies)
    per_evaluation_shots = sum(shots)
    budget_used = budget_used_before + per_evaluation_shots
    previous_available = previous_energy is not None
    previous_value = float(previous_energy) if previous_available else 0.0
    energy_delta = abs(energy - previous_value) if previous_available else 0.0
    delta_within_tolerance = previous_available and energy_delta <= convergence_tolerance
    stable_delta_count = (
        previous_stable_delta_count + 1 if delta_within_tolerance else 0
    )
    converged = (
        delta_within_tolerance
        and iteration + 1 >= min_iterations
        and stable_delta_count >= convergence_patience
    )

    record: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "system": system,
        "hamiltonian_label": SYSTEMS.get(system, {}).get("label", system),
        "iter": iteration,
        "expected_term_count": len(paulis),
        "term_ids": list(range(len(paulis))),
        "paulis": list(paulis),
        "coefficients": [float(value) for value in coefficients],
        "expectations": [float(value) for value in expectations],
        "per_term_energies": [float(value) for value in per_term_energies],
        "terms_done": [True] * len(paulis),
        "shots": [int(value) for value in shots],
        "counts_ones": [int(value) for value in counts_ones],
        "counts_available": [bool(value) for value in counts_available],
        "total_shots_this_iter": int(per_evaluation_shots),
        "estimator_kind": estimator_kind,
        "theta": bounded_theta,
        "parameter_count": len(bounded_theta),
        "parameter_lower": ANGLE_LOWER,
        "parameter_upper": ANGLE_UPPER,
        "theta_hash": theta_id,
        "bound_theta_hash": theta_id,
        "energy_theta_hash": theta_id,
        "optimizer_input_theta_hash": theta_id,
        "energy_hash": energy_id,
        "energy_terms_hash": energy_terms_id,
        "optimizer_input_energy_hash": energy_id,
        "ansatz_layout_hash": layout_hash,
        "hamiltonian_layout_hash": layout_hash,
        "reported_energy": energy,
        "previous_energy": previous_value,
        "previous_energy_available": previous_available,
        "energy_delta": energy_delta,
        "convergence_tolerance": float(convergence_tolerance),
        "delta_within_tolerance": bool(delta_within_tolerance),
        "stable_delta_count": int(stable_delta_count),
        "min_iterations": int(min_iterations),
        "convergence_patience": int(convergence_patience),
        "converged": bool(converged),
        "final_iteration": bool(final_iteration),
        "max_iterations": int(max_iterations),
        "energy_ready": True,
        "params_ready": True,
        "shot_budget": int(shot_budget),
        "budget_used": int(budget_used),
    }
    if reference_ground_energy is not None:
        record["reference_ground_energy"] = float(reference_ground_energy)
    return record


def write_jsonl(path: Path, records: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")))
            stream.write("\n")


def _backend_display_name(backend: Any) -> str:
    name = getattr(backend, "name", None)
    if callable(name):
        return str(name())
    if name is not None:
        return str(name)
    return str(backend)


def _job_display_id(job: Any) -> Optional[str]:
    job_id = getattr(job, "job_id", None)
    if callable(job_id):
        return str(job_id())
    if job_id is not None:
        return str(job_id)
    return None


def print_iteration_finished(
    mode: str,
    record: Dict[str, Any],
    output: Path,
    *,
    backend_name: Optional[str] = None,
    job_id: Optional[str] = None,
) -> None:
    parts = [
        "finished {} iteration {}/{}".format(
            mode, int(record["iter"]) + 1, int(record["max_iterations"])
        ),
        "energy={:.12g}".format(float(record["reported_energy"])),
        "delta={:.12g}".format(float(record["energy_delta"])),
        "converged={}".format(record["converged"]),
        "stable={}/{}".format(
            record["stable_delta_count"], record["convergence_patience"]
        ),
        "shots={}/{}".format(record["budget_used"], record["shot_budget"]),
    ]
    if backend_name is not None:
        parts.append("backend={}".format(backend_name))
    if job_id is not None:
        parts.append("job={}".format(job_id))
    parts.append("trace={}".format(output))
    print(" | ".join(parts), flush=True)


def effective_cobyla_maxiter(requested: int, parameter_count: int) -> int:
    if requested <= 0:
        raise ValueError("maxiter must be positive")
    return max(requested, parameter_count + 2)


class ConvergenceStop(Exception):
    """Raised internally to stop SciPy after recording a converged trace row."""


def mark_final_if_stopping(record: Dict[str, Any], stop_on_convergence: bool) -> None:
    if stop_on_convergence and record["converged"]:
        record["final_iteration"] = True


def demo_records(system: str) -> List[Dict[str, Any]]:
    spec = materialize_system(system)
    if "target_expectations" not in spec:
        raise ValueError("{} does not define dependency-free demo records".format(system))
    paulis = spec["paulis"]
    coefficients = spec["coefficients"]
    per_term_shots = int(spec["shots"])
    target_expectations = spec["target_expectations"]
    max_iterations = len(target_expectations)
    shot_budget = len(paulis) * per_term_shots * max_iterations
    layout_hash = _sha256("{}:logical-layout-v1".format(system))
    run_id = "{}-verified-demo".format(system)
    records: List[Dict[str, Any]] = []
    budget_used = 0
    previous_energy: Optional[float] = None
    previous_stable_delta_count = 0

    for iteration, (theta, targets) in enumerate(
        zip(spec["theta"], target_expectations)
    ):
        counts = [
            target_to_counts(expectation, per_term_shots)
            for expectation in targets
        ]
        expectations = [
            counts_to_expectation(count, per_term_shots) for count in counts
        ]
        record = build_record(
            run_id=run_id,
            system=system,
            iteration=iteration,
            theta=theta,
            paulis=paulis,
            coefficients=coefficients,
            expectations=expectations,
            shots=[per_term_shots] * len(paulis),
            counts_ones=counts,
            counts_available=[True] * len(paulis),
            layout_hash=layout_hash,
            shot_budget=shot_budget,
            budget_used_before=budget_used,
            estimator_kind="shot",
            reference_ground_energy=spec["reference_ground_energy"],
            previous_energy=previous_energy,
            convergence_tolerance=spec["convergence_tolerance"],
            min_iterations=max_iterations,
            convergence_patience=1,
            previous_stable_delta_count=previous_stable_delta_count,
            max_iterations=max_iterations,
            final_iteration=iteration == max_iterations - 1,
        )
        budget_used = int(record["budget_used"])
        previous_energy = float(record["reported_energy"])
        previous_stable_delta_count = int(record["stable_delta_count"])
        records.append(record)
    return records


def missing_term_mutant() -> List[Dict[str, Any]]:
    """Seed a silent final-term omission with internally consistent arithmetic."""
    record = demo_records("h2")[0]
    original_count = int(record["expected_term_count"])
    term_fields = [
        "term_ids",
        "paulis",
        "coefficients",
        "expectations",
        "per_term_energies",
        "terms_done",
        "shots",
        "counts_ones",
        "counts_available",
    ]
    for field in term_fields:
        record[field] = record[field][:-1]

    energy = math.fsum(
        coefficient * expectation
        for coefficient, expectation in zip(
            record["coefficients"], record["expectations"]
        )
    )
    record["reported_energy"] = energy
    record["per_term_energies"] = [
        coefficient * expectation
        for coefficient, expectation in zip(
            record["coefficients"], record["expectations"]
        )
    ]
    record["energy_hash"] = hash_energy(energy)
    record["energy_terms_hash"] = hash_vector(record["per_term_energies"])
    record["optimizer_input_energy_hash"] = record["energy_hash"]
    record["total_shots_this_iter"] = sum(record["shots"])
    record["budget_used"] = record["total_shots_this_iter"]
    record["expected_term_count"] = original_count
    record["run_id"] = "h2-bug-missing-final-term"
    return [record]


def stale_energy_mutant() -> List[Dict[str, Any]]:
    """Seed an optimizer update that consumes the previous evaluation."""
    records = demo_records("h2")[:2]
    records[0]["run_id"] = "h2-bug-stale-energy"
    records[1]["run_id"] = "h2-bug-stale-energy"
    records[1]["optimizer_input_theta_hash"] = records[0]["theta_hash"]
    records[1]["optimizer_input_energy_hash"] = records[0]["energy_hash"]
    return records


def bad_energy_mutant() -> List[Dict[str, Any]]:
    """Seed a per-term contribution/aggregate energy mismatch."""
    record = demo_records("h2")[0]
    record["run_id"] = "h2-bug-bad-energy"
    record["per_term_energies"][0] += 0.125
    record["energy_terms_hash"] = hash_vector(record["per_term_energies"])
    return [record]


def shot_inconsistency_mutant() -> List[Dict[str, Any]]:
    """Seed a trace whose shot total does not match the term-level shots."""
    record = demo_records("h2")[0]
    record["run_id"] = "h2-bug-shot-inconsistency"
    record["total_shots_this_iter"] -= 1
    return [record]


def parameter_bounds_mutant() -> List[Dict[str, Any]]:
    """Seed a parameter vector outside its declared domain."""
    record = demo_records("h2")[0]
    record["run_id"] = "h2-bug-parameter-bounds"
    record["theta"][0] = record["parameter_upper"] + 0.5
    theta_id = hash_vector(record["theta"])
    record["theta_hash"] = theta_id
    record["bound_theta_hash"] = theta_id
    record["energy_theta_hash"] = theta_id
    record["optimizer_input_theta_hash"] = theta_id
    return [record]


def convergence_mutant() -> List[Dict[str, Any]]:
    """Seed a false convergence claim when the energy delta is too large."""
    records = demo_records("h2")[:2]
    for record in records:
        record["run_id"] = "h2-bug-convergence"
    records[1]["converged"] = True
    records[1]["final_iteration"] = True
    return records


def generate_fixtures(trace_dir: Path) -> None:
    write_jsonl(trace_dir / "h2_run.jsonl", demo_records("h2"))
    write_jsonl(trace_dir / "lih_run.jsonl", demo_records("lih"))
    write_jsonl(
        trace_dir / "bug_seeded_missing_term.jsonl", missing_term_mutant()
    )
    write_jsonl(
        trace_dir / "bug_seeded_stale_energy.jsonl", stale_energy_mutant()
    )
    write_jsonl(trace_dir / "bug_seeded_bad_energy.jsonl", bad_energy_mutant())
    write_jsonl(
        trace_dir / "bug_seeded_shot_inconsistency.jsonl",
        shot_inconsistency_mutant(),
    )
    write_jsonl(
        trace_dir / "bug_seeded_parameter_bounds.jsonl",
        parameter_bounds_mutant(),
    )
    write_jsonl(
        trace_dir / "bug_seeded_convergence.jsonl", convergence_mutant()
    )


def _flatten_numeric_values(value: Any) -> List[float]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, (list, tuple)):
        flattened: List[float] = []
        for item in value:
            flattened.extend(_flatten_numeric_values(item))
        return flattened
    return [float(value)]


def _extract_estimator_values(result: Any, expected_count: int) -> List[float]:
    values = _flatten_numeric_values(result[0].data.evs)
    if len(values) != expected_count:
        raise ValueError(
            "Estimator returned {} expectation values, expected {}".format(
                len(values), expected_count
            )
        )
    return values


def qiskit_system_data(system: str) -> Dict[str, Any]:
    spec = materialize_system(system)
    paulis = spec["paulis"]
    coefficients = spec["coefficients"]
    if "reference_ground_energy" not in spec:
        print(
            "computing sparse exact reference for {} ({} qubits, {} terms)".format(
                system, len(paulis[0]), len(paulis)
            ),
            flush=True,
        )
        spec["reference_ground_energy"] = exact_ground_energy(paulis, coefficients)
        print(
            "reference_ground_energy={:.12g}".format(
                float(spec["reference_ground_energy"])
            ),
            flush=True,
        )
    return spec


def build_ansatz(efficient_su2: Any, spec: Dict[str, Any], num_qubits: int) -> Any:
    return efficient_su2(
        num_qubits,
        su2_gates=spec.get("ansatz_su2_gates", ["ry"]),
        entanglement=spec.get("ansatz_entanglement", "linear"),
        reps=int(spec.get("ansatz_reps", 1)),
    )


def initial_parameters(parameter_count: int) -> List[float]:
    step = min(0.25, math.pi / (parameter_count + 1))
    return [step * (index + 1) for index in range(parameter_count)]


def run_qiskit_statevector(
    output: Path,
    system: str,
    maxiter: int,
    stop_on_convergence: bool,
    convergence_tolerance: Optional[float],
    min_iterations: int,
    convergence_patience: int,
) -> None:
    """Run selected VQE system locally with term-level observables."""
    try:
        from scipy.optimize import minimize
        from qiskit.circuit.library import efficient_su2
        from qiskit.primitives import StatevectorEstimator
        from qiskit.quantum_info import SparsePauliOp
    except ImportError as exc:
        raise SystemExit(
            "qiskit-statevector mode requires qiskit and scipy: {}".format(exc)
        )

    spec = qiskit_system_data(system)
    paulis = spec["paulis"]
    coefficients = spec["coefficients"]
    num_qubits = len(paulis[0])
    ansatz = build_ansatz(efficient_su2, spec, num_qubits)
    term_operators = [
        SparsePauliOp.from_list([(pauli, 1.0)]) for pauli in paulis
    ]
    estimator = StatevectorEstimator()
    layout_hash = _sha256("{}:statevector-logical-layout".format(system))
    run_id = "{}-qiskit-statevector".format(system)
    initial = initial_parameters(ansatz.num_parameters)
    effective_maxiter = effective_cobyla_maxiter(maxiter, len(initial))
    if effective_maxiter != maxiter:
        print(
            "requested maxiter={} is below COBYLA minimum {}; using {}".format(
                maxiter, effective_maxiter, effective_maxiter
            ),
            flush=True,
        )
    records: List[Dict[str, Any]] = []
    previous_energy: Optional[float] = None
    previous_stable_delta_count = 0
    effective_tolerance = (
        float(convergence_tolerance)
        if convergence_tolerance is not None
        else float(spec.get("convergence_tolerance", 1e-5))
    )

    def cost(params: Sequence[float]) -> float:
        nonlocal previous_energy, previous_stable_delta_count
        bounded_params = [normalize_angle(value) for value in params]
        pub = (ansatz, term_operators, [bounded_params])
        expectations = _extract_estimator_values(
            estimator.run([pub]).result(), len(term_operators)
        )
        record = build_record(
            run_id=run_id,
            system=system,
            iteration=len(records),
            theta=bounded_params,
            paulis=paulis,
            coefficients=coefficients,
            expectations=expectations,
            shots=[0] * len(paulis),
            counts_ones=[0] * len(paulis),
            counts_available=[False] * len(paulis),
            layout_hash=layout_hash,
            shot_budget=0,
            budget_used_before=0,
            estimator_kind="exact",
            reference_ground_energy=spec["reference_ground_energy"],
            previous_energy=previous_energy,
            convergence_tolerance=effective_tolerance,
            min_iterations=min_iterations,
            convergence_patience=convergence_patience,
            previous_stable_delta_count=previous_stable_delta_count,
            max_iterations=effective_maxiter,
            final_iteration=len(records) + 1 >= effective_maxiter,
        )
        mark_final_if_stopping(record, stop_on_convergence)
        records.append(record)
        previous_energy = float(record["reported_energy"])
        previous_stable_delta_count = int(record["stable_delta_count"])
        write_jsonl(output, records)
        print_iteration_finished("statevector", record, output)
        if stop_on_convergence and record["converged"]:
            raise ConvergenceStop
        return float(record["reported_energy"])

    try:
        minimize(cost, initial, method="COBYLA", options={"maxiter": effective_maxiter})
    except ConvergenceStop:
        pass


def run_qiskit_runtime(
    output: Path,
    system: str,
    maxiter: int,
    shots_per_term: int,
    backend_name: Optional[str],
    stop_on_convergence: bool,
    convergence_tolerance: Optional[float],
    min_iterations: int,
    convergence_patience: int,
) -> None:
    """Run selected VQE system through IBM Runtime in job mode.

    The ansatz is transpiled once, every Pauli term is transformed with the
    same layout, and EstimatorV2 receives one PUB containing all term
    observables. The returned expectation vector is preserved in the trace so
    the checker can validate completeness and coefficient/expectation pairing.
    """
    try:
        from scipy.optimize import minimize
        from qiskit.circuit.library import efficient_su2
        from qiskit.quantum_info import SparsePauliOp
        from qiskit.transpiler.preset_passmanagers import (
            generate_preset_pass_manager,
        )
        from qiskit_ibm_runtime import EstimatorV2 as Estimator
        from qiskit_ibm_runtime import QiskitRuntimeService
    except ImportError as exc:
        raise SystemExit(
            "qiskit-runtime mode requires qiskit, scipy, and "
            "qiskit-ibm-runtime: {}".format(exc)
        )
    if shots_per_term <= 0:
        raise SystemExit("--shots must be positive in qiskit-runtime mode")

    spec = qiskit_system_data(system)
    paulis = spec["paulis"]
    coefficients = spec["coefficients"]
    num_qubits = len(paulis[0])
    ansatz = build_ansatz(efficient_su2, spec, num_qubits)
    service = QiskitRuntimeService()
    backend = (
        service.backend(backend_name)
        if backend_name
        else service.least_busy(operational=True, simulator=False, min_num_qubits=num_qubits)
    )
    backend_label = _backend_display_name(backend)
    pass_manager = generate_preset_pass_manager(
        target=backend.target, optimization_level=3
    )
    ansatz_isa = pass_manager.run(ansatz)
    term_operators_isa = [
        SparsePauliOp.from_list([(pauli, 1.0)]).apply_layout(ansatz_isa.layout)
        for pauli in paulis
    ]
    layout_hash = _sha256(repr(ansatz_isa.layout))
    run_id = "{}-qiskit-runtime-{}".format(system, backend_label)
    initial = initial_parameters(ansatz_isa.num_parameters)
    effective_maxiter = effective_cobyla_maxiter(maxiter, len(initial))
    if effective_maxiter != maxiter:
        print(
            "requested maxiter={} is below COBYLA minimum {}; using {}".format(
                maxiter, effective_maxiter, effective_maxiter
            ),
            flush=True,
        )
    shot_budget = effective_maxiter * len(paulis) * shots_per_term
    records: List[Dict[str, Any]] = []
    budget_used = 0
    previous_energy: Optional[float] = None
    previous_stable_delta_count = 0
    effective_tolerance = (
        float(convergence_tolerance)
        if convergence_tolerance is not None
        else float(spec.get("convergence_tolerance", 1e-5))
    )
    estimator = Estimator(mode=backend)
    estimator.options.default_shots = shots_per_term

    def cost(params: Sequence[float]) -> float:
        nonlocal budget_used, previous_energy, previous_stable_delta_count
        bounded_params = [normalize_angle(value) for value in params]
        pub = (ansatz_isa, term_operators_isa, [bounded_params])
        job = estimator.run(pubs=[pub])
        job_id = _job_display_id(job)
        result = job.result()
        expectations = _extract_estimator_values(result, len(term_operators_isa))
        record = build_record(
            run_id=run_id,
            system=system,
            iteration=len(records),
            theta=bounded_params,
            paulis=paulis,
            coefficients=coefficients,
            expectations=expectations,
            shots=[shots_per_term] * len(paulis),
            counts_ones=[0] * len(paulis),
            counts_available=[False] * len(paulis),
            layout_hash=layout_hash,
            shot_budget=shot_budget,
            budget_used_before=budget_used,
            estimator_kind="shot",
            reference_ground_energy=spec["reference_ground_energy"],
            previous_energy=previous_energy,
            convergence_tolerance=effective_tolerance,
            min_iterations=min_iterations,
            convergence_patience=convergence_patience,
            previous_stable_delta_count=previous_stable_delta_count,
            max_iterations=effective_maxiter,
            final_iteration=len(records) + 1 >= effective_maxiter,
        )
        mark_final_if_stopping(record, stop_on_convergence)
        budget_used = int(record["budget_used"])
        previous_energy = float(record["reported_energy"])
        previous_stable_delta_count = int(record["stable_delta_count"])
        records.append(record)
        write_jsonl(output, records)
        print_iteration_finished(
            "qiskit-runtime",
            record,
            output,
            backend_name=backend_label,
            job_id=job_id,
        )
        if stop_on_convergence and record["converged"]:
            raise ConvergenceStop
        return float(record["reported_energy"])

    try:
        minimize(cost, initial, method="COBYLA", options={"maxiter": effective_maxiter})
    except ConvergenceStop:
        pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=["demo", "qiskit-statevector", "qiskit-runtime"],
        default="demo",
        help="execution backend",
    )
    parser.add_argument(
        "--system", choices=sorted(SYSTEMS), default="h2", help="demo system"
    )
    parser.add_argument(
        "--output", type=Path, help="output JSONL path for one run"
    )
    parser.add_argument(
        "--generate-fixtures",
        type=Path,
        metavar="TRACE_DIR",
        help="write all valid and bug-seeded traces",
    )
    parser.add_argument(
        "--maxiter",
        type=int,
        help="optimizer evaluation budget; defaults come from the selected system and mode",
    )
    parser.add_argument(
        "--shots", type=int, default=5000, help="shots per Pauli term"
    )
    parser.add_argument(
        "--backend", help="IBM backend name; default selects the least busy backend"
    )
    parser.add_argument(
        "--stop-on-convergence",
        action="store_true",
        help="stop after min-iterations and patience requirements are satisfied",
    )
    parser.add_argument(
        "--convergence-tolerance",
        type=float,
        help="absolute energy-delta tolerance for convergence; default comes from the system fixture",
    )
    parser.add_argument(
        "--min-iterations",
        type=int,
        help="minimum optimizer evaluations before convergence may stop the run",
    )
    parser.add_argument(
        "--convergence-patience",
        type=int,
        help="consecutive stable energy deltas required before convergence",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.generate_fixtures is not None:
        generate_fixtures(args.generate_fixtures)
        return 0

    output = args.output or Path("traces/myTests/{}_run.jsonl".format(args.system))
    if args.mode in ("qiskit-statevector", "qiskit-runtime"):
        system_spec = SYSTEMS[args.system]
        default_maxiter = int(
            system_spec[
                "statevector_maxiter"
                if args.mode == "qiskit-statevector"
                else "runtime_maxiter"
            ]
        )
        maxiter = args.maxiter if args.maxiter is not None else default_maxiter
        if maxiter <= 0:
            raise SystemExit("--maxiter must be positive")
        min_iterations = (
            args.min_iterations
            if args.min_iterations is not None
            else min(int(system_spec.get("min_iterations", 30)), maxiter)
        )
        convergence_patience = (
            args.convergence_patience
            if args.convergence_patience is not None
            else int(system_spec.get("convergence_patience", 5))
        )
        if min_iterations <= 0:
            raise SystemExit("--min-iterations must be positive")
        if convergence_patience <= 0:
            raise SystemExit("--convergence-patience must be positive")
        if args.convergence_tolerance is not None and args.convergence_tolerance < 0.0:
            raise SystemExit("--convergence-tolerance must be non-negative")
        if args.mode == "qiskit-statevector":
            run_qiskit_statevector(
                output,
                args.system,
                maxiter,
                args.stop_on_convergence,
                args.convergence_tolerance,
                min_iterations,
                convergence_patience,
            )
        else:
            run_qiskit_runtime(
                output,
                args.system,
                maxiter,
                args.shots,
                args.backend,
                args.stop_on_convergence,
                args.convergence_tolerance,
                min_iterations,
                convergence_patience,
            )
    else:
        write_jsonl(output, demo_records(args.system))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
