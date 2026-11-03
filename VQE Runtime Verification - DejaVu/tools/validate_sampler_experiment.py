#!/usr/bin/env python3
"""Executable local preflight for the fixed H2 SamplerV2 experiment.

This program intentionally exercises the same ``vqe_runtime.sampling`` path
used by the experiment runner.  It validates the fixed configuration, runs a
1-qubit Hadamard shot-total check, samples the four independent H2 Pauli PUBs,
compares their count-derived expectations with exact StatevectorEstimator
values, verifies Qiskit's bit/Pauli ordering, and proves that representative
evidence mutations are rejected.

The acceptance interval for the sampled H2 expectations is deliberately not
an exact-equality check.  For m simultaneous comparisons of n independent
outcomes in {-1, +1}, Hoeffding's inequality and a union bound give

    P(any |sample_mean - exact_mean| >= epsilon)
        <= 2*m*exp(-n*epsilon**2/2).

The report uses the resulting two-sided family-wise bound at alpha=0.01.
"""

from __future__ import annotations

import argparse
from base64 import b64decode, b64encode
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from importlib import metadata as importlib_metadata
from io import BytesIO
import json
import math
from pathlib import Path
import platform
import random
import sys
import traceback
from typing import Any


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = WORKSPACE_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from vqe_runtime.config import RuntimeConfig, load_config, vector_digest
from vqe_runtime.sampling import (
    SamplingEvidenceError,
    build_measurement_circuit,
    evidence_from_pub_result,
    expectation_from_negative_count,
    measurement_basis_plan,
    negative_eigenvalue_count,
    raw_evidence_sha256,
    validate_evidence_record,
)


EXPECTED_QISKIT_VERSION = "2.5.2"
FIXED_SHOTS = 1024
FIXED_PAULIS = ("YZ", "ZI", "ZZ", "XX")
FIXED_MAX_EVALUATIONS = 50
FIXED_PUBS_PER_EVALUATION = 4
FIXED_SHOT_BUDGET = 204_800
FAMILY_ALPHA = 0.01
REPORT_SCHEMA_VERSION = 1


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _distribution_version(name: str) -> str | None:
    try:
        return importlib_metadata.version(name)
    except importlib_metadata.PackageNotFoundError:
        return None


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else repr(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "tolist"):
        try:
            return _json_safe(value.tolist())
        except Exception:
            pass
    return repr(value)


def _qpy_sha256(circuit: Any) -> str:
    from qiskit import qpy

    stream = BytesIO()
    qpy.dump(circuit, stream)
    return hashlib.sha256(stream.getvalue()).hexdigest()


def simultaneous_hoeffding_bound(
    shots: int,
    comparisons: int,
    *,
    family_alpha: float = FAMILY_ALPHA,
) -> float:
    """Return a two-sided simultaneous absolute-error bound for +/-1 means."""

    if isinstance(shots, bool) or not isinstance(shots, int) or shots <= 0:
        raise ValueError("shots must be a positive integer")
    if (
        isinstance(comparisons, bool)
        or not isinstance(comparisons, int)
        or comparisons <= 0
    ):
        raise ValueError("comparisons must be a positive integer")
    if (
        isinstance(family_alpha, bool)
        or not isinstance(family_alpha, (int, float))
        or not math.isfinite(float(family_alpha))
        or not 0.0 < float(family_alpha) < 1.0
    ):
        raise ValueError("family_alpha must lie strictly between zero and one")
    value = math.sqrt(
        2.0 * math.log((2.0 * comparisons) / float(family_alpha)) / shots
    )
    return min(2.0, value)


def _add_check(
    checks: list[dict[str, Any]],
    check_id: str,
    passed: bool,
    detail: str,
    *,
    observed: Any = None,
    expected: Any = None,
) -> bool:
    record: dict[str, Any] = {
        "id": check_id,
        "status": "PASS" if passed else "FAIL",
        "detail": detail,
    }
    if observed is not None:
        record["observed"] = _json_safe(observed)
    if expected is not None:
        record["expected"] = _json_safe(expected)
    checks.append(record)
    return passed


def _scalar_float(value: Any) -> float:
    if hasattr(value, "item"):
        value = value.item()
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Estimator returned a non-finite expectation")
    return result


def _basis_plan_json(pauli: str) -> list[dict[str, Any]]:
    return [
        {"qubit": item.qubit, "pauli": item.pauli, "gates": list(item.gates)}
        for item in measurement_basis_plan(pauli)
    ]


def validate_h2_record_sequence(
    records: Sequence[Mapping[str, Any]],
    config: RuntimeConfig,
) -> tuple[dict[str, Any], ...]:
    """Bind each raw record to its fixed PUB index, term, Pauli, and shot count."""

    if len(records) != len(config.hamiltonian.terms):
        raise SamplingEvidenceError(
            f"received {len(records)} PUB records; expected "
            f"{len(config.hamiltonian.terms)}"
        )
    validated: list[dict[str, Any]] = []
    for record, term in zip(records, config.hamiltonian.terms):
        validated.append(
            validate_evidence_record(
                record,
                expected_term_id=term.term_id,
                expected_pauli=term.pauli,
                expected_shots=config.shots_per_term,
            )
        )
    term_ids = [record["term_id"] for record in validated]
    if len(set(term_ids)) != len(term_ids):
        raise SamplingEvidenceError("PUB record sequence contains duplicate term IDs")
    hashes = [record["raw_evidence_sha256"] for record in validated]
    if len(set(hashes)) != len(hashes):
        raise SamplingEvidenceError("PUB record sequence contains duplicate evidence hashes")
    return tuple(validated)


def _mutate_one_count(record: Mapping[str, Any]) -> dict[str, Any]:
    mutated = deepcopy(dict(record))
    counts = dict(mutated["counts"])
    source = mutated["ordered_bitstrings"][0]
    target = source[:-1] + ("1" if source[-1] == "0" else "0")
    counts[source] -= 1
    if counts[source] == 0:
        del counts[source]
    counts[target] = counts.get(target, 0) + 1
    mutated["counts"] = dict(sorted(counts.items()))
    # Rehash to demonstrate that internal consistency, not merely an old hash,
    # rejects the corruption.
    mutated["raw_evidence_sha256"] = raw_evidence_sha256(mutated)
    return mutated


def _negative_test(
    checks: list[dict[str, Any]],
    test_id: str,
    operation: Callable[[], Any],
) -> dict[str, Any]:
    try:
        operation()
    except SamplingEvidenceError as exc:
        _add_check(
            checks,
            test_id,
            True,
            "The invalid evidence was rejected by the production validator.",
            observed=str(exc),
            expected="SamplingEvidenceError",
        )
        return {
            "id": test_id,
            "status": "PASS",
            "rejection_type": type(exc).__name__,
            "rejection_message": str(exc),
        }
    except Exception as exc:
        _add_check(
            checks,
            test_id,
            False,
            "The case failed outside the expected evidence-validation boundary.",
            observed=f"{type(exc).__name__}: {exc}",
            expected="SamplingEvidenceError",
        )
        return {
            "id": test_id,
            "status": "FAIL",
            "rejection_type": type(exc).__name__,
            "rejection_message": str(exc),
        }
    _add_check(
        checks,
        test_id,
        False,
        "The production validator incorrectly accepted invalid evidence.",
        observed="accepted",
        expected="rejected",
    )
    return {"id": test_id, "status": "FAIL", "rejection_type": None}


def _exact_expectations(
    estimator: Any,
    pubs: Sequence[tuple[Any, Any, Sequence[float]]],
) -> list[float]:
    result = estimator.run(pubs, precision=0.0).result()
    if len(result) != len(pubs):
        raise RuntimeError(
            f"StatevectorEstimator returned {len(result)} PUBs; expected {len(pubs)}"
        )
    return [_scalar_float(pub_result.data.evs) for pub_result in result]


def _ordering_case(
    *,
    name: str,
    prepared_x_qubit: int,
    pauli: str,
    cross_pauli: str,
    expected_bitstring: str,
    shots: int,
    seed: int,
    sampler_type: type,
    estimator: Any,
    sparse_pauli_op_type: type,
    quantum_circuit_type: type,
) -> dict[str, Any]:
    state = quantum_circuit_type(2)
    state.x(prepared_x_qubit)
    measured = build_measurement_circuit(state, pauli)
    sampled = sampler_type(default_shots=shots, seed=seed).run(
        [measured], shots=shots
    ).result()
    if len(sampled) != 1:
        raise RuntimeError("ordering check did not return exactly one PUB")
    record = evidence_from_pub_result(
        sampled[0],
        term_id=name,
        pauli=pauli,
        requested_shots=shots,
    )
    exact, cross_exact = _exact_expectations(
        estimator,
        [
            (state, sparse_pauli_op_type(pauli), ()),
            (state, sparse_pauli_op_type(cross_pauli), ()),
        ],
    )
    passed = (
        record["counts"] == {expected_bitstring: shots}
        and record["negative_eigenvalue_count"] == shots
        and math.isclose(record["expectation"], -1.0, rel_tol=0.0, abs_tol=1e-15)
        and math.isclose(exact, -1.0, rel_tol=0.0, abs_tol=1e-15)
        and math.isclose(cross_exact, 1.0, rel_tol=0.0, abs_tol=1e-15)
    )
    return {
        "id": name,
        "status": "PASS" if passed else "FAIL",
        "prepared_state": f"X(q{prepared_x_qubit})|00>",
        "measured_pauli": pauli,
        "cross_pauli": cross_pauli,
        "expected_displayed_bitstring": expected_bitstring,
        "counts": record["counts"],
        "negative_eigenvalue_count": record["negative_eigenvalue_count"],
        "count_derived_expectation": record["expectation"],
        "exact_expectation": exact,
        "cross_exact_expectation": cross_exact,
        "raw_evidence_sha256": record["raw_evidence_sha256"],
        "interpretation": (
            "Qiskit displays two-qubit bits as q1q0 and maps the right-most "
            "Pauli character to q0."
        ),
    }


def run_validation(config_path: str | Path) -> dict[str, Any]:
    """Run the complete local validation and return a JSON-compatible report."""

    resolved_config = Path(config_path).resolve()
    config = load_config(resolved_config)
    checks: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_type": "h2-samplerv2-local-validation",
        "generated_at_utc": _utc_now(),
        "overall_status": "FAIL",
        "environment": {
            "python_executable": sys.executable,
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "qiskit": _distribution_version("qiskit"),
            "qiskit_ibm_runtime": _distribution_version("qiskit-ibm-runtime"),
            "numpy": _distribution_version("numpy"),
            "scipy": _distribution_version("scipy"),
        },
        "inputs": {
            "config_path": str(resolved_config),
            "config_hash": config.digest,
            "config": config.as_dict(include_source=False),
            "fixed_experiment": {
                "shots_per_term": FIXED_SHOTS,
                "hamiltonian_pauli_order": list(FIXED_PAULIS),
                "pubs_per_evaluation": FIXED_PUBS_PER_EVALUATION,
                "max_evaluations": FIXED_MAX_EVALUATIONS,
                "maximum_physical_shots": FIXED_SHOT_BUDGET,
            },
        },
        "checks": checks,
    }

    try:
        import qiskit
        from qiskit import ClassicalRegister, QuantumCircuit
        from qiskit.circuit.library import efficient_su2
        from qiskit.primitives import StatevectorEstimator, StatevectorSampler
        from qiskit.quantum_info import SparsePauliOp
    except ImportError as exc:
        _add_check(
            checks,
            "qiskit_importable",
            False,
            "The Qiskit validation dependencies could not be imported.",
            observed=str(exc),
            expected=f"Qiskit {EXPECTED_QISKIT_VERSION}",
        )
        report["check_summary"] = {"passed": 0, "failed": 1, "total": 1}
        return report

    qiskit_version = str(qiskit.__version__)
    fixed_requirements = [
        (
            "qiskit_exact_version",
            qiskit_version == EXPECTED_QISKIT_VERSION,
            "The validation API surface is pinned to the recorded Qiskit release.",
            qiskit_version,
            EXPECTED_QISKIT_VERSION,
        ),
        (
            "statevector_sampler_mode",
            config.mode == "qiskit-statevector-sampler",
            "The local comparison must use the finite-shot sampler mode.",
            config.mode,
            "qiskit-statevector-sampler",
        ),
        (
            "h2_system",
            config.system == "h2" and config.hamiltonian.num_qubits == 2,
            "The validation target is the representative two-qubit H2 system.",
            {"system": config.system, "qubits": config.hamiltonian.num_qubits},
            {"system": "h2", "qubits": 2},
        ),
        (
            "fixed_shots_per_term",
            config.shots_per_term == FIXED_SHOTS,
            "Every PUB must request exactly 1,024 physical shots.",
            config.shots_per_term,
            FIXED_SHOTS,
        ),
        (
            "fixed_term_order",
            tuple(term.pauli for term in config.hamiltonian.terms) == FIXED_PAULIS,
            "PUB positions are bound to YZ, ZI, ZZ, XX in that order.",
            [term.pauli for term in config.hamiltonian.terms],
            list(FIXED_PAULIS),
        ),
        (
            "fixed_evaluation_limit",
            config.max_iterations == FIXED_MAX_EVALUATIONS,
            "The monitored evaluation maximum is exactly 50.",
            config.max_iterations,
            FIXED_MAX_EVALUATIONS,
        ),
        (
            "fixed_physical_shot_budget",
            config.shot_budget == FIXED_SHOT_BUDGET,
            "The configured worst-case physical-shot budget is exact.",
            config.shot_budget,
            FIXED_SHOT_BUDGET,
        ),
        (
            "ask_tell_optimizer_policy",
            config.optimizer_protocol == "ask-tell" and config.optimizer is not None,
            "The comparable local experiment uses the explicit ask/tell policy.",
            config.optimizer_protocol,
            "ask-tell with explicit optimizer table",
        ),
        (
            "four_independent_pub_policy",
            config.sampler is not None
            and config.sampler.separate_pub_per_term
            and config.sampler.pubs_per_evaluation == FIXED_PUBS_PER_EVALUATION,
            "No term grouping or shared physical shots are permitted.",
            None if config.sampler is None else config.sampler.as_dict(),
            {"separate_pub_per_term": True, "pubs_per_evaluation": 4},
        ),
    ]
    for check_id, passed, detail, observed, expected in fixed_requirements:
        _add_check(
            checks,
            check_id,
            passed,
            detail,
            observed=observed,
            expected=expected,
        )
    if not all(item[1] for item in fixed_requirements):
        failed = sum(check["status"] == "FAIL" for check in checks)
        report["check_summary"] = {
            "passed": len(checks) - failed,
            "failed": failed,
            "total": len(checks),
        }
        report["failure"] = (
            "The supplied configuration or Qiskit environment is not the fixed "
            "comparison experiment; quantum execution was not attempted."
        )
        return report

    shots = config.shots_per_term
    report["environment"]["qiskit_module"] = str(Path(qiskit.__file__).resolve())
    report["environment"]["validated_api_calls"] = [
        "qiskit.primitives.StatevectorSampler(default_shots=1024, seed=7)",
        "StatevectorSampler.run(pubs, shots=1024)",
        "qiskit.primitives.StatevectorEstimator(default_precision=0.0, seed=7)",
        "StatevectorEstimator.run(pubs, precision=0.0)",
        "qiskit.circuit.library.efficient_su2(2, ['ry'], 'linear', reps=1)",
    ]

    # Required one-qubit count-total preflight.
    hadamard = QuantumCircuit(1)
    hadamard.h(0)
    hadamard_bits = ClassicalRegister(1, "meas")
    hadamard.add_register(hadamard_bits)
    hadamard.measure(0, hadamard_bits[0])
    hadamard_result = StatevectorSampler(default_shots=shots, seed=config.seed).run(
        [hadamard], shots=shots
    ).result()
    if len(hadamard_result) != 1:
        raise RuntimeError("Hadamard preflight did not return exactly one PUB")
    hadamard_record = evidence_from_pub_result(
        hadamard_result[0],
        term_id="hadamard_z",
        pauli="Z",
        requested_shots=shots,
    )
    hadamard_sum = sum(hadamard_record["counts"].values())
    hadamard_bound = simultaneous_hoeffding_bound(shots, 1)
    hadamard_pass = _add_check(
        checks,
        "hadamard_1024_shot_total",
        hadamard_record["observed_shots"] == shots
        and hadamard_sum == shots
        and set(hadamard_record["counts"]) <= {"0", "1"},
        "The complete one-qubit 0/1 count dictionary sums to exactly 1,024.",
        observed={
            "num_shots": hadamard_record["observed_shots"],
            "count_sum": hadamard_sum,
            "counts": hadamard_record["counts"],
        },
        expected={"num_shots": shots, "count_sum": shots},
    )
    hadamard_balance_pass = _add_check(
        checks,
        "hadamard_finite_shot_sanity",
        abs(float(hadamard_record["expectation"])) <= hadamard_bound,
        "The sampled Z expectation for |+> is inside its two-sided 99% Hoeffding bound.",
        observed=abs(float(hadamard_record["expectation"])),
        expected={"maximum_absolute_delta": hadamard_bound},
    )
    report["hadamard_preflight"] = {
        "status": "PASS" if hadamard_pass and hadamard_balance_pass else "FAIL",
        "requested_shots": shots,
        "observed_shots": hadamard_record["observed_shots"],
        "counts": hadamard_record["counts"],
        "count_sum": hadamard_sum,
        "negative_eigenvalue_count": hadamard_record[
            "negative_eigenvalue_count"
        ],
        "count_derived_z_expectation": hadamard_record["expectation"],
        "exact_z_expectation": 0.0,
        "absolute_delta": abs(float(hadamard_record["expectation"])),
        "statistical_bound": hadamard_bound,
        "raw_evidence_sha256": hadamard_record["raw_evidence_sha256"],
    }

    # Build the exact ansatz used by both the local and IBM Sampler experiments.
    ansatz = efficient_su2(
        config.hamiltonian.num_qubits,
        su2_gates=["ry"],
        entanglement="linear",
        reps=1,
    )
    _add_check(
        checks,
        "ansatz_parameter_count",
        ansatz.num_parameters == config.parameter_count,
        "The configured parameter dimension matches EfficientSU2 exactly.",
        observed=ansatz.num_parameters,
        expected=config.parameter_count,
    )
    initial_source = random.Random(config.seed)
    theta = tuple(
        initial_source.uniform(config.parameter_lower, config.parameter_upper)
        for _ in range(config.parameter_count)
    )
    measurement_circuits = tuple(
        build_measurement_circuit(ansatz, term.pauli)
        for term in config.hamiltonian.terms
    )
    independent_objects = len({id(circuit) for circuit in measurement_circuits}) == 4
    _add_check(
        checks,
        "four_independent_measurement_circuits",
        len(measurement_circuits) == 4 and independent_objects,
        "Four distinct circuit objects are submitted as four independent PUBs.",
        observed={
            "circuit_count": len(measurement_circuits),
            "distinct_object_count": len({id(circuit) for circuit in measurement_circuits}),
        },
        expected={"circuit_count": 4, "distinct_object_count": 4},
    )
    expected_basis_plans = {
        "YZ": [
            {"qubit": 0, "pauli": "Z", "gates": []},
            {"qubit": 1, "pauli": "Y", "gates": ["sdg", "h"]},
        ],
        "ZI": [{"qubit": 1, "pauli": "Z", "gates": []}],
        "ZZ": [
            {"qubit": 0, "pauli": "Z", "gates": []},
            {"qubit": 1, "pauli": "Z", "gates": []},
        ],
        "XX": [
            {"qubit": 0, "pauli": "X", "gates": ["h"]},
            {"qubit": 1, "pauli": "X", "gates": ["h"]},
        ],
    }
    actual_basis_plans = {pauli: _basis_plan_json(pauli) for pauli in FIXED_PAULIS}
    _add_check(
        checks,
        "measurement_basis_rotations",
        actual_basis_plans == expected_basis_plans,
        "X uses H, Y uses S-dagger then H, Z is direct, and I is excluded from parity.",
        observed=actual_basis_plans,
        expected=expected_basis_plans,
    )

    sampler = StatevectorSampler(default_shots=shots, seed=config.seed)
    sampler_pubs = [
        (circuit, list(theta)) for circuit in measurement_circuits
    ]
    sampled_result = sampler.run(sampler_pubs, shots=shots).result()
    _add_check(
        checks,
        "sampler_returned_four_pubs",
        len(sampled_result) == FIXED_PUBS_PER_EVALUATION,
        "One sampler job returned one result for each independently submitted term PUB.",
        observed=len(sampled_result),
        expected=FIXED_PUBS_PER_EVALUATION,
    )
    if len(sampled_result) != FIXED_PUBS_PER_EVALUATION:
        raise RuntimeError(
            f"StatevectorSampler returned {len(sampled_result)} PUBs; expected 4"
        )

    raw_records = tuple(
        evidence_from_pub_result(
            pub_result,
            term_id=term.term_id,
            pauli=term.pauli,
            requested_shots=shots,
        )
        for term, pub_result in zip(config.hamiltonian.terms, sampled_result)
    )
    validated_records = validate_h2_record_sequence(raw_records, config)
    _add_check(
        checks,
        "complete_h2_raw_evidence_sequence",
        len(validated_records) == FIXED_PUBS_PER_EVALUATION,
        "All four raw records validate in their fixed PUB positions.",
        observed=len(validated_records),
        expected=FIXED_PUBS_PER_EVALUATION,
    )

    estimator = StatevectorEstimator(default_precision=0.0, seed=config.seed)
    estimator_pubs = [
        (ansatz, SparsePauliOp(term.pauli), list(theta))
        for term in config.hamiltonian.terms
    ]
    exact_values = _exact_expectations(estimator, estimator_pubs)
    term_bound = simultaneous_hoeffding_bound(
        shots,
        len(config.hamiltonian.terms),
        family_alpha=FAMILY_ALPHA,
    )
    report["statistical_acceptance"] = {
        "method": "two-sided Hoeffding inequality with a union bound",
        "outcome_range": [-1, 1],
        "shots_per_term": shots,
        "simultaneous_comparisons": len(config.hamiltonian.terms),
        "family_alpha": FAMILY_ALPHA,
        "simultaneous_confidence_at_least": 1.0 - FAMILY_ALPHA,
        "tail_bound": "2*m*exp(-n*epsilon^2/2) <= family_alpha",
        "solved_bound": "epsilon = sqrt(2*ln(2*m/family_alpha)/n)",
        "absolute_expectation_bound": term_bound,
        "numeric_slack": config.expectation_abs_tolerance,
    }
    report["ansatz"] = {
        "constructor": "qiskit.circuit.library.efficient_su2",
        "display_name": "EfficientSU2",
        "num_qubits": ansatz.num_qubits,
        "su2_gates": ["ry"],
        "entanglement": "linear",
        "reps": 1,
        "num_parameters": ansatz.num_parameters,
        "parameter_order": [str(parameter) for parameter in ansatz.parameters],
        "initial_theta": list(theta),
        "initial_theta_sha256": vector_digest(theta),
        "parameterized_qpy_sha256": _qpy_sha256(ansatz),
    }
    report["measurement_design"] = {
        "register_name": "meas",
        "bit_order": "qiskit-msb-qn-1-to-q0",
        "term_order": list(FIXED_PAULIS),
        "basis_plans": actual_basis_plans,
        "pub_count": len(measurement_circuits),
        "shots_per_pub": shots,
        "physical_shots_for_validation_evaluation": len(measurement_circuits)
        * shots,
        "circuit_qpy_sha256": [
            _qpy_sha256(circuit) for circuit in measurement_circuits
        ],
        "circuit_operations": [
            dict(circuit.count_ops()) for circuit in measurement_circuits
        ],
    }

    h2_terms: list[dict[str, Any]] = []
    sampled_energy_parts: list[float] = []
    exact_energy_parts: list[float] = []
    for pub_index, (term, pub_result, record, exact) in enumerate(
        zip(
            config.hamiltonian.terms,
            sampled_result,
            validated_records,
            exact_values,
        )
    ):
        counts = record["counts"]
        count_sum = sum(counts.values())
        recomputed_negative = negative_eigenvalue_count(counts, term.pauli)
        reconstructed = expectation_from_negative_count(
            recomputed_negative, record["observed_shots"]
        )
        raw_match = math.isclose(
            reconstructed,
            float(record["expectation"]),
            rel_tol=0.0,
            abs_tol=config.expectation_abs_tolerance,
        )
        delta = abs(reconstructed - exact)
        within_bound = delta <= term_bound + config.expectation_abs_tolerance
        standard_error = math.sqrt(max(0.0, 1.0 - exact * exact) / shots)
        prefix = f"h2_{term.term_id}_{term.pauli.lower()}"
        _add_check(
            checks,
            f"{prefix}_shot_total",
            record["requested_shots"] == shots
            and record["observed_shots"] == shots
            and count_sum == shots,
            "Requested shots, BitArray.num_shots, and complete count sum all agree.",
            observed={
                "requested_shots": record["requested_shots"],
                "observed_shots": record["observed_shots"],
                "count_sum": count_sum,
            },
            expected=shots,
        )
        _add_check(
            checks,
            f"{prefix}_parity_reconstruction",
            recomputed_negative == record["negative_eigenvalue_count"] and raw_match,
            "Odd parity over non-identity positions reconstructs the archived expectation.",
            observed={
                "negative_eigenvalue_count": recomputed_negative,
                "reconstructed_expectation": reconstructed,
                "archived_expectation": record["expectation"],
            },
            expected={"absolute_tolerance": config.expectation_abs_tolerance},
        )
        _add_check(
            checks,
            f"{prefix}_finite_shot_exact_comparison",
            within_bound,
            "The count-derived expectation is within the simultaneous finite-shot bound.",
            observed={"absolute_delta": delta},
            expected={
                "maximum_delta": term_bound + config.expectation_abs_tolerance
            },
        )
        packed_data = b64decode(
            record["packed_bitarray"]["data"].encode("ascii"), validate=True
        )
        pub_metadata = _json_safe(getattr(pub_result, "metadata", None))
        h2_terms.append(
            {
                "pub_index": pub_index,
                "term_id": term.term_id,
                "pauli": term.pauli,
                "coefficient_integer": term.coeff_int,
                "coefficient_scale": config.hamiltonian.coeff_scale,
                "coefficient": term.coeff_int / config.hamiltonian.coeff_scale,
                "requested_shots": record["requested_shots"],
                "observed_bitarray_num_shots": record["observed_shots"],
                "complete_counts": counts,
                "count_sum": count_sum,
                "negative_eigenvalue_count": recomputed_negative,
                "reconstruction_formula": (
                    f"1 - 2*{recomputed_negative}/{record['observed_shots']}"
                ),
                "count_derived_expectation": reconstructed,
                "statevector_estimator_exact_expectation": exact,
                "absolute_delta": delta,
                "single_term_theoretical_standard_error": standard_error,
                "simultaneous_hoeffding_bound": term_bound,
                "within_statistical_bound": within_bound,
                "raw_evidence_sha256": record["raw_evidence_sha256"],
                "packed_bitarray": {
                    "encoding": record["packed_bitarray"]["encoding"],
                    "dtype": record["packed_bitarray"]["dtype"],
                    "shape": record["packed_bitarray"]["shape"],
                    "packed_bytes_sha256": hashlib.sha256(packed_data).hexdigest(),
                },
                "pub_metadata": pub_metadata,
            }
        )
        sampled_energy_parts.append(term.coeff_int * reconstructed)
        exact_energy_parts.append(term.coeff_int * exact)
    report["h2_terms"] = h2_terms

    sampled_energy = math.fsum(sampled_energy_parts) / config.hamiltonian.coeff_scale
    exact_energy = math.fsum(exact_energy_parts) / config.hamiltonian.coeff_scale
    energy_delta = abs(sampled_energy - exact_energy)
    conservative_energy_bound = config.hamiltonian.coefficient_bound * term_bound
    _add_check(
        checks,
        "h2_energy_finite_shot_comparison",
        energy_delta
        <= conservative_energy_bound + config.energy_abs_tolerance,
        "The reconstructed H2 energy lies inside the coefficient-weighted term bound.",
        observed={"absolute_delta": energy_delta},
        expected={
            "maximum_delta": conservative_energy_bound
            + config.energy_abs_tolerance
        },
    )
    report["h2_energy"] = {
        "count_derived_energy": sampled_energy,
        "statevector_estimator_exact_energy": exact_energy,
        "absolute_delta": energy_delta,
        "conservative_coefficient_weighted_bound": conservative_energy_bound,
        "within_bound": energy_delta
        <= conservative_energy_bound + config.energy_abs_tolerance,
    }

    # Deterministic eigenstates pin down the Qiskit label/bitstring convention.
    ordering_cases = [
        _ordering_case(
            name="leftmost_pauli_character_is_q1",
            prepared_x_qubit=1,
            pauli="ZI",
            cross_pauli="IZ",
            expected_bitstring="10",
            shots=shots,
            seed=config.seed,
            sampler_type=StatevectorSampler,
            estimator=estimator,
            sparse_pauli_op_type=SparsePauliOp,
            quantum_circuit_type=QuantumCircuit,
        ),
        _ordering_case(
            name="rightmost_pauli_character_is_q0",
            prepared_x_qubit=0,
            pauli="IZ",
            cross_pauli="ZI",
            expected_bitstring="01",
            shots=shots,
            seed=config.seed,
            sampler_type=StatevectorSampler,
            estimator=estimator,
            sparse_pauli_op_type=SparsePauliOp,
            quantum_circuit_type=QuantumCircuit,
        ),
    ]
    for case in ordering_cases:
        _add_check(
            checks,
            case["id"],
            case["status"] == "PASS",
            case["interpretation"],
            observed={
                "counts": case["counts"],
                "count_derived_expectation": case[
                    "count_derived_expectation"
                ],
                "exact_expectation": case["exact_expectation"],
                "cross_exact_expectation": case["cross_exact_expectation"],
            },
            expected={
                "counts": {case["expected_displayed_bitstring"]: shots},
                "measured_expectation": -1.0,
                "cross_expectation": 1.0,
            },
        )
    report["qiskit_ordering_verification"] = {
        "pauli_label_rule": "left-most character acts on q1; right-most acts on q0",
        "displayed_bitstring_rule": "two-qubit strings are displayed as q1q0",
        "cases": ordering_cases,
    }

    # Required negative cases.  All mutations are checked through the same
    # production evidence validators used during experiment execution/replay.
    negative_tests: list[dict[str, Any]] = []
    corrupted_counts = list(deepcopy(validated_records))
    corrupted_counts[0] = _mutate_one_count(corrupted_counts[0])
    negative_tests.append(
        _negative_test(
            checks,
            "reject_corrupted_counts",
            lambda: validate_h2_record_sequence(corrupted_counts, config),
        )
    )
    negative_tests.append(
        _negative_test(
            checks,
            "reject_missing_pub",
            lambda: validate_h2_record_sequence(validated_records[:-1], config),
        )
    )
    wrong_terms = list(deepcopy(validated_records))
    wrong_terms[0], wrong_terms[1] = wrong_terms[1], wrong_terms[0]
    negative_tests.append(
        _negative_test(
            checks,
            "reject_wrong_term_assignment",
            lambda: validate_h2_record_sequence(wrong_terms, config),
        )
    )
    wrong_shots = list(deepcopy(validated_records))
    wrong_shots[0]["requested_shots"] = shots - 1
    wrong_shots[0]["raw_evidence_sha256"] = raw_evidence_sha256(wrong_shots[0])
    negative_tests.append(
        _negative_test(
            checks,
            "reject_wrong_shot_total",
            lambda: validate_h2_record_sequence(wrong_shots, config),
        )
    )
    corrupted_packed = list(deepcopy(validated_records))
    packed_bytes = bytearray(
        b64decode(
            corrupted_packed[0]["packed_bitarray"]["data"].encode("ascii"),
            validate=True,
        )
    )
    packed_bytes[0] ^= 1
    corrupted_packed[0]["packed_bitarray"]["data"] = b64encode(
        bytes(packed_bytes)
    ).decode("ascii")
    corrupted_packed[0]["raw_evidence_sha256"] = raw_evidence_sha256(
        corrupted_packed[0]
    )
    negative_tests.append(
        _negative_test(
            checks,
            "reject_corrupted_packed_shots",
            lambda: validate_h2_record_sequence(corrupted_packed, config),
        )
    )
    report["negative_tests"] = negative_tests

    failed = sum(check["status"] == "FAIL" for check in checks)
    report["check_summary"] = {
        "passed": len(checks) - failed,
        "failed": failed,
        "total": len(checks),
    }
    report["overall_status"] = "PASS" if failed == 0 else "FAIL"
    return report


def _failure_report(config_path: str | Path, exc: BaseException) -> dict[str, Any]:
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_type": "h2-samplerv2-local-validation",
        "generated_at_utc": _utc_now(),
        "overall_status": "FAIL",
        "environment": {
            "python_executable": sys.executable,
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "qiskit": _distribution_version("qiskit"),
        },
        "inputs": {"config_path": str(Path(config_path).resolve())},
        "checks": [
            {
                "id": "validation_harness_completed",
                "status": "FAIL",
                "detail": "The validation harness raised an exception.",
                "observed": f"{type(exc).__name__}: {exc}",
                "expected": "complete execution",
            }
        ],
        "check_summary": {"passed": 0, "failed": 1, "total": 1},
        "exception": {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        },
    }


def _write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(
        report,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the fixed 1,024-shot, four-PUB H2 StatevectorSampler "
            "experiment before IBM hardware submission."
        )
    )
    parser.add_argument(
        "--config",
        default=str(WORKSPACE_ROOT / "configs" / "h2_statevector.toml"),
        help="Sampler experiment TOML configuration",
    )
    parser.add_argument(
        "--out",
        default=str(
            WORKSPACE_ROOT
            / "artifacts"
            / "validation"
            / "h2_sampler_local_validation.json"
        ),
        help="Destination JSON report",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Write the report without also printing it to stdout",
    )
    args = parser.parse_args(argv)
    try:
        report = run_validation(args.config)
    except Exception as exc:
        report = _failure_report(args.config, exc)
    output_path = Path(args.out).resolve()
    _write_report(output_path, report)
    if not args.quiet:
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
        print(f"report_path={output_path}")
    return 0 if report.get("overall_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
