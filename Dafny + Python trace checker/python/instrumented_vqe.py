#!/usr/bin/env python3
"""Instrumented VQE evaluations for the Dafny/runtime verification artifact.

The default ``demo`` mode has no third-party dependencies and emits deterministic
term-level traces for the H2 and LiH case studies.  The optional
``qiskit-statevector`` mode runs the H2 example with Qiskit's local
StatevectorEstimator when Qiskit and SciPy are installed.

The trace deliberately records the assumptions used by the Dafny proof:
complete term vectors, per-term energy contributions, bounded parameters,
shot accounting, convergence metadata, layout identities, and fresh optimizer
inputs.
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
        "paulis": ["YZ", "ZI", "ZZ", "XX"],
        "coefficients": [0.3980, -0.3980, -0.0113, 0.1810],
        "reference_ground_energy": -0.7029,
        "convergence_tolerance": 0.25,
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
        "convergence_tolerance": 0.20,
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
    converged = previous_available and energy_delta <= convergence_tolerance

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


def demo_records(system: str) -> List[Dict[str, Any]]:
    if system not in SYSTEMS:
        raise ValueError("unknown system: {}".format(system))
    spec = SYSTEMS[system]
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
            max_iterations=max_iterations,
            final_iteration=iteration == max_iterations - 1,
        )
        budget_used = int(record["budget_used"])
        previous_energy = float(record["reported_energy"])
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


def _extract_estimator_value(result: Any) -> float:
    value = result[0].data.evs
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(value[0])


def run_qiskit_statevector(output: Path, maxiter: int) -> None:
    """Run the supplied H2-style VQE locally with term-level observables."""
    try:
        from scipy.optimize import minimize
        from qiskit.circuit.library import efficient_su2
        from qiskit.primitives import StatevectorEstimator
        from qiskit.quantum_info import SparsePauliOp
    except ImportError as exc:
        raise SystemExit(
            "qiskit-statevector mode requires qiskit and scipy: {}".format(exc)
        )

    spec = SYSTEMS["h2"]
    paulis = spec["paulis"]
    coefficients = spec["coefficients"]
    ansatz = efficient_su2(
        2, su2_gates=["h", "rz", "y"], entanglement="circular", reps=1
    )
    term_operators = [
        SparsePauliOp.from_list([(pauli, 1.0)]) for pauli in paulis
    ]
    estimator = StatevectorEstimator()
    layout_hash = _sha256("h2:statevector-logical-layout")
    run_id = "h2-qiskit-statevector"
    initial = [0.25 * (index + 1) for index in range(ansatz.num_parameters)]
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
    convergence_tolerance = float(spec.get("convergence_tolerance", 1e-6))

    def cost(params: Sequence[float]) -> float:
        nonlocal previous_energy
        expectations: List[float] = []
        for term_operator in term_operators:
            pub = (ansatz, term_operator, list(params))
            expectations.append(
                _extract_estimator_value(estimator.run([pub]).result())
            )
        record = build_record(
            run_id=run_id,
            system="h2",
            iteration=len(records),
            theta=list(params),
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
            convergence_tolerance=convergence_tolerance,
            max_iterations=effective_maxiter,
            final_iteration=len(records) + 1 >= effective_maxiter,
        )
        records.append(record)
        previous_energy = float(record["reported_energy"])
        write_jsonl(output, records)
        print_iteration_finished("statevector", record, output)
        return float(record["reported_energy"])

    minimize(cost, initial, method="COBYLA", options={"maxiter": effective_maxiter})


def run_qiskit_runtime(
    output: Path, maxiter: int, shots_per_term: int, backend_name: Optional[str]
) -> None:
    """Run H2 through IBM Runtime while retaining term-level observability.

    This is the instrumented counterpart of the supplied ``vqe_qiskit.py``.
    The ansatz is transpiled once, every Pauli term is transformed with the
    same layout, and EstimatorV2 is invoked in job mode with one PUB per term
    so the trace can check completeness and coefficient/expectation pairing.
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

    spec = SYSTEMS["h2"]
    paulis = spec["paulis"]
    coefficients = spec["coefficients"]
    ansatz = efficient_su2(
        2, su2_gates=["h", "rz", "y"], entanglement="circular", reps=1
    )
    service = QiskitRuntimeService()
    backend = (
        service.backend(backend_name)
        if backend_name
        else service.least_busy(operational=True, simulator=False)
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
    run_id = "h2-qiskit-runtime-{}".format(backend_label)
    initial = [
        0.25 * (index + 1) for index in range(ansatz_isa.num_parameters)
    ]
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
    convergence_tolerance = float(spec.get("convergence_tolerance", 1e-6))
    estimator = Estimator(mode=backend)
    estimator.options.default_shots = shots_per_term

    def cost(params: Sequence[float]) -> float:
        nonlocal budget_used, previous_energy
        pubs = [
            (ansatz_isa, [term_operator], [list(params)])
            for term_operator in term_operators_isa
        ]
        job = estimator.run(pubs=pubs)
        job_id = _job_display_id(job)
        result = job.result()
        expectations = [float(pub_result.data.evs[0]) for pub_result in result]
        record = build_record(
            run_id=run_id,
            system="h2",
            iteration=len(records),
            theta=list(params),
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
            convergence_tolerance=convergence_tolerance,
            max_iterations=effective_maxiter,
            final_iteration=len(records) + 1 >= effective_maxiter,
        )
        budget_used = int(record["budget_used"])
        previous_energy = float(record["reported_energy"])
        records.append(record)
        write_jsonl(output, records)
        print_iteration_finished(
            "qiskit-runtime",
            record,
            output,
            backend_name=backend_label,
            job_id=job_id,
        )
        return float(record["reported_energy"])

    minimize(cost, initial, method="COBYLA", options={"maxiter": effective_maxiter})


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
    parser.add_argument("--maxiter", type=int, default=30)
    parser.add_argument(
        "--shots", type=int, default=5000, help="shots per Pauli term"
    )
    parser.add_argument(
        "--backend", help="IBM backend name; default selects the least busy backend"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.generate_fixtures is not None:
        generate_fixtures(args.generate_fixtures)
        return 0

    output = args.output or Path("traces/myTests/{}_run.jsonl".format(args.system))
    if args.mode in ("qiskit-statevector", "qiskit-runtime"):
        if args.system != "h2":
            raise SystemExit("{} mode currently implements H2".format(args.mode))
        if args.mode == "qiskit-statevector":
            run_qiskit_statevector(output, args.maxiter)
        else:
            run_qiskit_runtime(output, args.maxiter, args.shots, args.backend)
    else:
        write_jsonl(output, demo_records(args.system))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
