#!/usr/bin/env python3
"""Check concrete VQE JSONL traces against the Dafny proof assumptions."""

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from instrumented_vqe import SCHEMA_VERSION, hash_energy, hash_vector


PROPERTY_NAMES = (
    "schema",
    "term_completeness",
    "expectation_domain",
    "shot_consistency",
    "energy_computation",
    "parameter_bounds",
    "convergence_check",
    "layout_consistency",
    "optimizer_freshness",
    "trace_sequence",
)


@dataclass
class Violation:
    property: str
    line: int
    message: str


@dataclass
class TraceResult:
    path: str
    valid: bool
    records: int
    violations: List[Violation]

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["violations"] = [asdict(item) for item in self.violations]
        return data


REQUIRED_FIELDS = {
    "schema_version",
    "run_id",
    "system",
    "iter",
    "expected_term_count",
    "term_ids",
    "paulis",
    "coefficients",
    "expectations",
    "per_term_energies",
    "terms_done",
    "shots",
    "counts_ones",
    "counts_available",
    "total_shots_this_iter",
    "estimator_kind",
    "theta",
    "parameter_count",
    "parameter_lower",
    "parameter_upper",
    "theta_hash",
    "bound_theta_hash",
    "energy_theta_hash",
    "optimizer_input_theta_hash",
    "energy_hash",
    "energy_terms_hash",
    "optimizer_input_energy_hash",
    "ansatz_layout_hash",
    "hamiltonian_layout_hash",
    "reported_energy",
    "previous_energy",
    "previous_energy_available",
    "energy_delta",
    "convergence_tolerance",
    "delta_within_tolerance",
    "stable_delta_count",
    "min_iterations",
    "convergence_patience",
    "converged",
    "final_iteration",
    "max_iterations",
    "energy_ready",
    "params_ready",
    "shot_budget",
    "budget_used",
}

TERM_FIELDS = (
    "term_ids",
    "paulis",
    "coefficients",
    "expectations",
    "per_term_energies",
    "terms_done",
    "shots",
    "counts_ones",
    "counts_available",
)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _finite_number(value: Any) -> bool:
    return _is_number(value) and math.isfinite(float(value))


def _finite_vector(value: Any) -> bool:
    return isinstance(value, list) and all(_finite_number(item) for item in value)


def _close(left: float, right: float, tolerance: float) -> bool:
    scale = max(1.0, abs(left), abs(right))
    return abs(left - right) <= tolerance * scale


def _add(
    violations: List[Violation],
    property_name: str,
    line: int,
    condition: bool,
    message: str,
) -> None:
    if not condition:
        violations.append(Violation(property_name, line, message))


def load_trace(path: Path) -> Tuple[List[Dict[str, Any]], List[Violation]]:
    records: List[Dict[str, Any]] = []
    violations: List[Violation] = []
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line_number, raw_line in enumerate(stream, 1):
                if not raw_line.strip():
                    continue
                try:
                    value = json.loads(raw_line)
                except json.JSONDecodeError as exc:
                    violations.append(
                        Violation("schema", line_number, "invalid JSON: {}".format(exc))
                    )
                    continue
                if not isinstance(value, dict):
                    violations.append(
                        Violation("schema", line_number, "record must be a JSON object")
                    )
                    continue
                records.append(value)
    except OSError as exc:
        violations.append(Violation("schema", 0, "cannot read trace: {}".format(exc)))
    return records, violations


def check_record(
    record: Dict[str, Any], line: int, tolerance: float
) -> List[Violation]:
    violations: List[Violation] = []
    missing = sorted(REQUIRED_FIELDS - set(record))
    _add(
        violations,
        "schema",
        line,
        not missing,
        "missing required fields: {}".format(", ".join(missing)),
    )
    if missing:
        return violations

    _add(
        violations,
        "schema",
        line,
        record["schema_version"] == SCHEMA_VERSION,
        "unsupported schema_version {!r}".format(record["schema_version"]),
    )
    _add(
        violations,
        "schema",
        line,
        isinstance(record["run_id"], str) and bool(record["run_id"]),
        "run_id must be a non-empty string",
    )
    _add(
        violations,
        "schema",
        line,
        isinstance(record["system"], str) and bool(record["system"]),
        "system must be a non-empty string",
    )
    _add(
        violations,
        "schema",
        line,
        type(record["iter"]) is int and record["iter"] >= 0,
        "iter must be a non-negative integer",
    )
    expected_count = record["expected_term_count"]
    expected_count_valid = type(expected_count) is int and expected_count > 0
    _add(
        violations,
        "schema",
        line,
        expected_count_valid,
        "expected_term_count must be a positive integer",
    )

    term_vectors_valid = all(isinstance(record[field], list) for field in TERM_FIELDS)
    _add(
        violations,
        "schema",
        line,
        term_vectors_valid,
        "all term fields must be arrays",
    )
    if term_vectors_valid and expected_count_valid:
        for field in TERM_FIELDS:
            _add(
                violations,
                "term_completeness",
                line,
                len(record[field]) == expected_count,
                "{} has length {}, expected {}".format(
                    field, len(record[field]), expected_count
                ),
            )

        term_ids = record["term_ids"]
        valid_ids = all(type(value) is int and value >= 0 for value in term_ids)
        _add(
            violations,
            "term_completeness",
            line,
            valid_ids,
            "term_ids must contain non-negative integers",
        )
        _add(
            violations,
            "term_completeness",
            line,
            valid_ids
            and len(term_ids) == expected_count
            and sorted(term_ids) == list(range(expected_count)),
            "term_ids must contain each identifier 0..N-1 exactly once",
        )
        _add(
            violations,
            "term_completeness",
            line,
            all(type(value) is bool and value for value in record["terms_done"]),
            "every Hamiltonian term must be marked complete",
        )
        _add(
            violations,
            "schema",
            line,
            all(isinstance(value, str) and value for value in record["paulis"]),
            "paulis must contain non-empty strings",
        )

    coefficients_valid = _finite_vector(record["coefficients"])
    expectations_valid = _finite_vector(record["expectations"])
    per_term_energies_valid = _finite_vector(record["per_term_energies"])
    _add(
        violations,
        "schema",
        line,
        coefficients_valid,
        "coefficients must be finite numbers",
    )
    _add(
        violations,
        "schema",
        line,
        expectations_valid,
        "expectations must be finite numbers",
    )
    _add(
        violations,
        "schema",
        line,
        per_term_energies_valid,
        "per_term_energies must be finite numbers",
    )
    if expectations_valid:
        _add(
            violations,
                "expectation_domain",
                line,
            all(
                -1.0 - tolerance <= value <= 1.0 + tolerance
                for value in record["expectations"]
            ),
            "each Pauli expectation must lie in [-1, 1]",
        )

    estimator_kind = record["estimator_kind"]
    _add(
        violations,
        "schema",
        line,
        estimator_kind in ("shot", "exact"),
        "estimator_kind must be 'shot' or 'exact'",
    )
    shots = record["shots"]
    counts = record["counts_ones"]
    available = record["counts_available"]
    shot_values_valid = isinstance(shots, list) and all(
        type(value) is int and value >= 0 for value in shots
    )
    count_values_valid = isinstance(counts, list) and all(
        type(value) is int and value >= 0 for value in counts
    )
    flags_valid = isinstance(available, list) and all(
        type(value) is bool for value in available
    )
    _add(
        violations,
        "schema",
        line,
        shot_values_valid,
        "shots must contain non-negative integers",
    )
    _add(
        violations,
        "schema",
        line,
        count_values_valid,
        "counts_ones must contain non-negative integers",
    )
    _add(
        violations,
        "schema",
        line,
        flags_valid,
        "counts_available must contain booleans",
    )
    if shot_values_valid and estimator_kind in ("shot", "exact"):
        if estimator_kind == "shot":
            _add(
                violations,
                "shot_consistency",
                line,
                all(value > 0 for value in shots),
                "shot-based terms must use positive shot counts",
            )
        else:
            _add(
                violations,
                "shot_consistency",
                line,
                all(value == 0 for value in shots),
                "exact estimator records must use zero shots",
            )

    if (
        shot_values_valid
        and count_values_valid
        and flags_valid
        and expectations_valid
        and len(shots) == len(counts) == len(available) == len(record["expectations"])
    ):
        for index, (shot_count, count, has_counts, expectation) in enumerate(
            zip(shots, counts, available, record["expectations"])
        ):
            if has_counts:
                valid_count = shot_count > 0 and count <= shot_count
                _add(
                    violations,
                    "shot_consistency",
                    line,
                    valid_count,
                    "term {} has invalid count data".format(index),
                )
                if valid_count:
                    normalized = 1.0 - 2.0 * count / shot_count
                    _add(
                        violations,
                        "shot_consistency",
                        line,
                        _close(normalized, expectation, tolerance),
                        "term {} expectation {} does not match count normalization {}".format(
                            index, expectation, normalized
                        ),
                    )
            else:
                _add(
                    violations,
                    "shot_consistency",
                    line,
                    count == 0,
                    "term {} must store zero when counts are unavailable".format(index),
                )

    total_shots = record["total_shots_this_iter"]
    total_shots_valid = type(total_shots) is int and total_shots >= 0
    _add(
        violations,
        "schema",
        line,
        total_shots_valid,
        "total_shots_this_iter must be a non-negative integer",
    )
    if total_shots_valid and shot_values_valid:
        _add(
            violations,
            "shot_consistency",
            line,
            total_shots == sum(shots),
            "total_shots_this_iter {} does not equal sum(shots) {}".format(
                total_shots, sum(shots)
            ),
        )

    energy_valid = _finite_number(record["reported_energy"])
    _add(
        violations,
        "schema",
        line,
        energy_valid,
        "reported_energy must be finite",
    )
    if (
        coefficients_valid
        and expectations_valid
        and per_term_energies_valid
        and energy_valid
        and len(record["coefficients"])
        == len(record["expectations"])
        == len(record["per_term_energies"])
    ):
        expected_terms = [
            coefficient * expectation
            for coefficient, expectation in zip(
                record["coefficients"], record["expectations"]
            )
        ]
        for index, (expected, observed) in enumerate(
            zip(expected_terms, record["per_term_energies"])
        ):
            _add(
                violations,
                "energy_computation",
                line,
                _close(expected, observed, tolerance),
                "term {} energy contribution {} differs from coefficient*expectation {}".format(
                    index, observed, expected
                ),
            )
        recomputed = math.fsum(expected_terms)
        recomputed_from_terms = math.fsum(record["per_term_energies"])
        _add(
            violations,
            "energy_computation",
            line,
            _close(recomputed, float(record["reported_energy"]), tolerance),
            "reported energy {} differs from full weighted sum {}".format(
                record["reported_energy"], recomputed
            ),
        )
        _add(
            violations,
            "energy_computation",
            line,
            _close(recomputed_from_terms, float(record["reported_energy"]), tolerance),
            "reported energy {} differs from sum(per_term_energies) {}".format(
                record["reported_energy"], recomputed_from_terms
            ),
        )
        expected_terms_hash = hash_vector(record["per_term_energies"])
        _add(
            violations,
            "energy_computation",
            line,
            record["energy_terms_hash"] == expected_terms_hash,
            "energy_terms_hash does not identify per_term_energies",
        )
        bound = math.fsum(abs(value) for value in record["coefficients"])
        _add(
            violations,
            "energy_computation",
            line,
            -bound - tolerance <= float(record["reported_energy"]) <= bound + tolerance,
            "reported energy lies outside the Hamiltonian L1 bound +/-{}".format(
                bound
            ),
        )
        if (
            estimator_kind == "exact"
            and "reference_ground_energy" in record
            and _finite_number(record["reference_ground_energy"])
        ):
            _add(
                violations,
                "energy_computation",
                line,
                float(record["reported_energy"]) + tolerance
                >= float(record["reference_ground_energy"]),
                "exact variational energy is below the reference ground energy",
            )

    theta_valid = _finite_vector(record["theta"])
    parameter_count = record["parameter_count"]
    parameter_count_valid = type(parameter_count) is int and parameter_count >= 0
    lower_valid = _finite_number(record["parameter_lower"])
    upper_valid = _finite_number(record["parameter_upper"])
    _add(
        violations,
        "schema",
        line,
        theta_valid and lower_valid and upper_valid,
        "theta and its bounds must be finite",
    )
    _add(
        violations,
        "schema",
        line,
        parameter_count_valid,
        "parameter_count must be a non-negative integer",
    )
    if theta_valid and lower_valid and upper_valid:
        lower = float(record["parameter_lower"])
        upper = float(record["parameter_upper"])
        _add(
            violations,
            "parameter_bounds",
            line,
            parameter_count_valid and parameter_count == len(record["theta"]),
            "parameter_count {} does not equal len(theta) {}".format(
                parameter_count, len(record["theta"])
            ),
        )
        _add(
            violations,
            "parameter_bounds",
            line,
            lower <= upper
            and all(lower - tolerance <= value <= upper + tolerance for value in record["theta"]),
            "theta must lie inside the declared parameter domain",
        )
        expected_theta_hash = hash_vector(record["theta"])
        _add(
            violations,
            "optimizer_freshness",
            line,
            record["theta_hash"] == expected_theta_hash,
            "theta_hash does not identify the recorded theta vector",
        )
        _add(
            violations,
            "optimizer_freshness",
            line,
            record["bound_theta_hash"] == record["theta_hash"]
            and record["energy_theta_hash"] == record["theta_hash"]
            and record["optimizer_input_theta_hash"] == record["theta_hash"],
            "binding, energy, and optimizer must use the current theta",
        )

    if energy_valid:
        expected_energy_hash = hash_energy(float(record["reported_energy"]))
        _add(
            violations,
            "optimizer_freshness",
            line,
            record["energy_hash"] == expected_energy_hash,
            "energy_hash does not identify reported_energy",
        )
        _add(
            violations,
            "optimizer_freshness",
            line,
            record["optimizer_input_energy_hash"] == record["energy_hash"],
            "optimizer consumed an energy other than the current record's energy",
        )

    previous_energy_valid = _finite_number(record["previous_energy"])
    previous_available_valid = type(record["previous_energy_available"]) is bool
    energy_delta_valid = _finite_number(record["energy_delta"])
    tolerance_valid = _finite_number(record["convergence_tolerance"])
    delta_within_valid = type(record["delta_within_tolerance"]) is bool
    stable_count_valid = (
        type(record["stable_delta_count"]) is int
        and record["stable_delta_count"] >= 0
    )
    min_iterations_valid = (
        type(record["min_iterations"]) is int and record["min_iterations"] > 0
    )
    patience_valid = (
        type(record["convergence_patience"]) is int
        and record["convergence_patience"] > 0
    )
    converged_valid = type(record["converged"]) is bool
    final_iteration_valid = type(record["final_iteration"]) is bool
    max_iterations_valid = type(record["max_iterations"]) is int and record["max_iterations"] > 0
    _add(
        violations,
        "schema",
        line,
        previous_energy_valid
        and previous_available_valid
        and energy_delta_valid
        and tolerance_valid
        and delta_within_valid
        and stable_count_valid
        and min_iterations_valid
        and patience_valid
        and converged_valid
        and final_iteration_valid
        and max_iterations_valid,
        "convergence fields must be finite and well typed",
    )
    if (
        energy_valid
        and previous_energy_valid
        and previous_available_valid
        and energy_delta_valid
        and tolerance_valid
        and delta_within_valid
        and stable_count_valid
        and min_iterations_valid
        and patience_valid
        and converged_valid
        and final_iteration_valid
        and max_iterations_valid
    ):
        convergence_tolerance = float(record["convergence_tolerance"])
        energy_delta = float(record["energy_delta"])
        _add(
            violations,
            "convergence_check",
            line,
            convergence_tolerance >= 0.0,
            "convergence_tolerance must be non-negative",
        )
        _add(
            violations,
            "convergence_check",
            line,
            energy_delta >= 0.0,
            "energy_delta must be non-negative",
        )
        if record["iter"] == 0:
            _add(
                violations,
                "convergence_check",
                line,
                record["previous_energy_available"] is False
                and _close(float(record["energy_delta"]), 0.0, tolerance),
                "first record must not claim previous energy and must use zero energy_delta",
            )
        else:
            expected_delta = abs(
                float(record["reported_energy"]) - float(record["previous_energy"])
            )
            _add(
                violations,
                "convergence_check",
                line,
                record["previous_energy_available"] is True,
                "non-initial record must carry previous energy",
            )
            _add(
                violations,
                "convergence_check",
                line,
                _close(expected_delta, energy_delta, tolerance),
                "energy_delta {} does not equal |current-previous| {}".format(
                    energy_delta, expected_delta
                ),
            )
        expected_converged = (
            record["delta_within_tolerance"] is True
            and record["iter"] + 1 >= record["min_iterations"]
            and record["stable_delta_count"] >= record["convergence_patience"]
        )
        expected_delta_within = (
            record["previous_energy_available"] is True
            and energy_delta <= convergence_tolerance + tolerance
        )
        _add(
            violations,
            "convergence_check",
            line,
            record["delta_within_tolerance"] == expected_delta_within,
            "delta_within_tolerance {} does not match energy_delta <= tolerance ({})".format(
                record["delta_within_tolerance"], expected_delta_within
            ),
        )
        _add(
            violations,
            "convergence_check",
            line,
            record["converged"] == expected_converged,
            "converged flag {} does not match energy_delta <= tolerance ({})".format(
                record["converged"], expected_converged
            ),
        )
        _add(
            violations,
            "convergence_check",
            line,
            record["iter"] < record["max_iterations"],
            "iter must be smaller than max_iterations",
        )
        if record["final_iteration"]:
            _add(
                violations,
                "convergence_check",
                line,
                record["converged"]
                or record["iter"] + 1 == record["max_iterations"],
                "final_iteration requires convergence or max-iteration exhaustion",
            )

    _add(
        violations,
        "optimizer_freshness",
        line,
        record["energy_ready"] is True and record["params_ready"] is True,
        "optimizer inputs must be marked energy_ready and params_ready",
    )
    _add(
        violations,
        "layout_consistency",
        line,
        isinstance(record["ansatz_layout_hash"], str)
        and bool(record["ansatz_layout_hash"])
        and record["ansatz_layout_hash"] == record["hamiltonian_layout_hash"],
        "ansatz and Hamiltonian layout hashes must match",
    )

    shot_budget = record["shot_budget"]
    budget_used = record["budget_used"]
    budget_fields_valid = (
        type(shot_budget) is int
        and type(budget_used) is int
        and shot_budget >= 0
        and budget_used >= 0
    )
    _add(
        violations,
        "schema",
        line,
        budget_fields_valid,
        "shot_budget and budget_used must be non-negative integers",
    )
    if budget_fields_valid:
        _add(
            violations,
            "shot_consistency",
            line,
            budget_used <= shot_budget,
            "cumulative shot usage {} exceeds budget {}".format(
                budget_used, shot_budget
            ),
        )
    return violations


def check_trace(path: Path, tolerance: float = 1e-9) -> TraceResult:
    records, violations = load_trace(path)
    if not records and not violations:
        violations.append(Violation("schema", 0, "trace contains no records"))

    for line, record in enumerate(records, 1):
        violations.extend(check_record(record, line, tolerance))

    if records:
        baseline = records[0]
        previous_budget = 0
        for index, record in enumerate(records):
            line = index + 1
            if REQUIRED_FIELDS - set(record):
                continue
            _add(
                violations,
                "trace_sequence",
                line,
                record["iter"] == index,
                "iter must be contiguous and equal {}, found {!r}".format(
                    index, record["iter"]
                ),
            )
            _add(
                violations,
                "trace_sequence",
                line,
                record["run_id"] == baseline["run_id"]
                and record["system"] == baseline["system"],
                "run_id and system must remain constant across a trace",
            )
            _add(
                violations,
                "trace_sequence",
                line,
                record["schema_version"] == baseline["schema_version"]
                and record["expected_term_count"] == baseline["expected_term_count"]
                and record["shot_budget"] == baseline["shot_budget"],
                "schema, Hamiltonian term count, and shot budget must remain constant",
            )
            _add(
                violations,
                "trace_sequence",
                line,
                record["parameter_count"] == baseline["parameter_count"]
                and record["max_iterations"] == baseline["max_iterations"]
                and record["min_iterations"] == baseline["min_iterations"]
                and record["convergence_patience"]
                == baseline["convergence_patience"]
                and _close(
                    float(record["convergence_tolerance"]),
                    float(baseline["convergence_tolerance"]),
                    tolerance,
                ),
                "parameter count, max_iterations, convergence tolerance, and convergence policy must remain constant",
            )
            shots = record["shots"]
            if isinstance(shots, list) and all(
                type(value) is int and value >= 0 for value in shots
            ):
                expected_budget = previous_budget + sum(shots)
                _add(
                    violations,
                    "shot_consistency",
                    line,
                    record["budget_used"] == expected_budget,
                    "budget_used must equal cumulative shots {}, found {!r}".format(
                        expected_budget, record["budget_used"]
                    ),
                )
                previous_budget = expected_budget
            if index == 0:
                _add(
                    violations,
                    "convergence_check",
                    line,
                    record["stable_delta_count"] == 0,
                    "first record must use stable_delta_count 0",
                )
                continue
            previous = records[index - 1]
            if not (REQUIRED_FIELDS - set(previous)):
                _add(
                    violations,
                    "convergence_check",
                    line,
                    record["previous_energy_available"] is True
                    and _finite_number(previous.get("reported_energy"))
                    and _close(
                        float(record["previous_energy"]),
                        float(previous["reported_energy"]),
                        tolerance,
                    ),
                    "previous_energy must equal the prior record's reported_energy",
                )
                expected_stable_count = (
                    int(previous["stable_delta_count"]) + 1
                    if record["delta_within_tolerance"]
                    else 0
                )
                _add(
                    violations,
                    "convergence_check",
                    line,
                    record["stable_delta_count"] == expected_stable_count,
                    "stable_delta_count must equal {}, found {!r}".format(
                        expected_stable_count, record["stable_delta_count"]
                    ),
                )

    return TraceResult(str(path), not violations, len(records), violations)


def check_paths(paths: Iterable[Path], tolerance: float = 1e-9) -> List[TraceResult]:
    return [check_trace(path, tolerance) for path in paths]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--tolerance", type=float, default=1e-9)
    parser.add_argument(
        "--json", action="store_true", help="emit a machine-readable report"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results = check_paths(args.paths, args.tolerance)
    if args.json:
        print(
            json.dumps(
                {"valid": all(result.valid for result in results),
                 "results": [result.to_dict() for result in results]},
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for result in results:
            status = "PASS" if result.valid else "FAIL"
            print("{} {} ({} records)".format(status, result.path, result.records))
            for violation in result.violations:
                print(
                    "  line {} [{}] {}".format(
                        violation.line, violation.property, violation.message
                    )
                )
    return 0 if all(result.valid for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
