"""Strict correlation of compact Sampler traces with raw-shot sidecars.

The evidence path is an explicit verifier input.  Trace contents are never
used to discover a sidecar, which prevents an untrusted trace from selecting
the evidence against which it is checked.
"""

from __future__ import annotations

from base64 import b64decode
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime
import hashlib
import math
from pathlib import Path
import re
from typing import Any

from .config import RuntimeConfig, vector_digest
from .evidence import load_evidence
from .events import RuntimeEvent
from .report import VerificationReport
from .sampling import expectation_from_negative_count
from .sampler_runner import HARDWARE_LAYOUT_STRATEGY, STATEVECTOR_LAYOUT_STRATEGY


EVIDENCE_REPLAY_PROPERTIES = (
    "intra_raw_evidence_link",
    "intra_pub_assignment",
    "intra_parity_reconstruction",
    "inter_raw_evidence_identity_unique",
    "run_raw_evidence_complete",
    "run_physical_shot_budget",
    "run_execution_options",
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ITERATION_STARTS = frozenset({"firstIterationStarted", "nextIterationStarted"})


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _event_arg(event: RuntimeEvent, index: int) -> str | None:
    return event.args[index] if len(event.args) > index else None


def _parse_iteration(value: Any) -> int | None:
    if _is_integer(value) and value >= 0:
        return value
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        parsed = int(value)
        if str(parsed) == value:
            return parsed
    return None


def _parse_aware_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _expected_sampler_options(config: RuntimeConfig) -> dict[str, Any]:
    if config.mode == "qiskit-runtime-sampler":
        return {
            "primitive": "qiskit_ibm_runtime.SamplerV2",
            "constructor": {
                "default_shots": config.shots_per_term,
                "dynamical_decoupling": {"enable": False},
                "execution": {"init_qubits": True, "meas_type": "classified"},
                "twirling": {"enable_gates": False, "enable_measure": False},
            },
            "run_shots": config.shots_per_term,
        }
    return {
        "primitive": "qiskit.primitives.StatevectorSampler",
        "constructor": {
            "default_shots": config.shots_per_term,
            "seed": config.seed,
        },
        "run_shots": config.shots_per_term,
    }


def _valid_layout(config: RuntimeConfig, value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    physical = value.get("logical_to_physical")
    if (
        not isinstance(physical, list)
        or len(physical) != config.hamiltonian.num_qubits
        or any(not _is_integer(item) or item < 0 for item in physical)
        or len(set(physical)) != len(physical)
    ):
        return False
    if config.mode == "qiskit-statevector-sampler":
        return value == {
            "transpiled": False,
            "logical_to_physical": list(range(config.hamiltonian.num_qubits)),
        }
    output_qubits = value.get("output_qubits")
    return bool(
        value.get("transpiled") is True
        and _is_integer(output_qubits)
        and output_qubits >= config.hamiltonian.num_qubits
        and all(item < output_qubits for item in physical)
    )


def _start_identity(event: RuntimeEvent) -> tuple[int, str] | None:
    iteration = _parse_iteration(_event_arg(event, 2))
    evaluation_id = _event_arg(event, 3)
    if iteration is None or evaluation_id is None:
        return None
    return iteration, evaluation_id


def _term_expected_identity(
    event: RuntimeEvent,
) -> tuple[int, str, str, str] | None:
    iteration = _parse_iteration(_event_arg(event, 2))
    evaluation_id = _event_arg(event, 3)
    submission_id = _event_arg(event, 4)
    term_id = _event_arg(event, 5)
    if (
        iteration is None
        or evaluation_id is None
        or submission_id is None
        or term_id is None
    ):
        return None
    return iteration, evaluation_id, submission_id, term_id


def _job_identity(event: RuntimeEvent) -> tuple[int, str, str] | None:
    iteration = _parse_iteration(_event_arg(event, 2))
    evaluation_id = _event_arg(event, 3)
    submission_id = _event_arg(event, 4)
    if iteration is None or evaluation_id is None or submission_id is None:
        return None
    return iteration, evaluation_id, submission_id


def _observation_identity(
    event: RuntimeEvent,
) -> tuple[int, str, str, str, str] | None:
    iteration = _parse_iteration(_event_arg(event, 2))
    evaluation_id = _event_arg(event, 3)
    submission_id = _event_arg(event, 4)
    external_job_id = _event_arg(event, 5)
    term_id = _event_arg(event, 6)
    if (
        iteration is None
        or evaluation_id is None
        or submission_id is None
        or external_job_id is None
        or term_id is None
    ):
        return None
    return iteration, evaluation_id, submission_id, external_job_id, term_id


def verify_trace_evidence(
    config: RuntimeConfig,
    events: Sequence[RuntimeEvent],
    evidence_path: str | Path | None,
    report: VerificationReport,
    run_id: str,
) -> None:
    """Replay and correlate one explicitly supplied raw-evidence sidecar.

    This function is deliberately additive: it records findings on the report
    supplied by the caller and returns ``None``.  It does nothing for legacy
    estimator and demo modes.
    """

    if not config.is_sampler_mode:
        return

    if evidence_path is None:
        report.add_inconclusive(
            "run_raw_evidence_complete",
            "Sampler replay requires an explicitly supplied raw-evidence sidecar",
        )
        return

    try:
        path = Path(evidence_path)
        is_file = path.is_file()
    except (OSError, TypeError, ValueError) as exc:
        report.add_inconclusive(
            "run_raw_evidence_complete",
            f"raw-evidence sidecar cannot be resolved: {exc}",
        )
        return
    if not is_file:
        report.add_inconclusive(
            "run_raw_evidence_complete",
            f"raw-evidence sidecar is missing or unreadable: {path}",
        )
        return

    loaded = load_evidence(
        path,
        expected_run_id=run_id,
        expected_config_hash=config.digest,
    )
    if not loaded.ok:
        message = "; ".join(loaded.errors)
        if any(error.startswith("cannot read evidence sidecar") for error in loaded.errors):
            report.add_inconclusive(
                "run_raw_evidence_complete",
                f"raw-evidence sidecar is unreadable: {message}",
            )
        else:
            report.add_failure(
                "run_raw_evidence_complete",
                f"raw-evidence sidecar is malformed: {message}",
            )
        return

    event_list = tuple(events)
    run_started = [event for event in event_list if event.name == "runStarted"]
    starts: dict[tuple[int, str], list[RuntimeEvent]] = defaultdict(list)
    expected_terms: dict[tuple[int, str, str, str], list[RuntimeEvent]] = defaultdict(list)
    submitted_jobs: dict[tuple[int, str, str], list[RuntimeEvent]] = defaultdict(list)
    observations = [event for event in event_list if event.name == "termObserved"]

    for event in event_list:
        if event.name in _ITERATION_STARTS:
            identity = _start_identity(event)
            if identity is not None:
                starts[identity].append(event)
        elif event.name == "termExpected":
            identity = _term_expected_identity(event)
            if identity is not None:
                expected_terms[identity].append(event)
        elif event.name == "jobSubmitted":
            identity = _job_identity(event)
            if identity is not None:
                submitted_jobs[identity].append(event)

    provenance: Mapping[str, Any] | None = None
    sampler_provenance: Mapping[str, Any] | None = None
    if len(run_started) == 1:
        candidate = run_started[0].payload.get("execution_provenance")
        if isinstance(candidate, Mapping):
            provenance = candidate
            candidate_sampler = candidate.get("sampler_experiment")
            if isinstance(candidate_sampler, Mapping):
                sampler_provenance = candidate_sampler
    if provenance is None or sampler_provenance is None:
        report.add_failure(
            "run_execution_options",
            "trace does not contain exactly one usable Sampler execution-provenance record",
            seq=run_started[0].seq if run_started else None,
        )

    expected_options = _expected_sampler_options(config)
    provenance_circuit_hashes = (
        None
        if sampler_provenance is None
        else sampler_provenance.get("parameterized_circuit_qpy_sha256")
    )
    provenance_layouts = (
        None if sampler_provenance is None else sampler_provenance.get("physical_layouts")
    )
    provenance_options = (
        None if sampler_provenance is None else sampler_provenance.get("api_options")
    )
    expected_layout_strategy = (
        HARDWARE_LAYOUT_STRATEGY
        if config.mode == "qiskit-runtime-sampler"
        else STATEVECTOR_LAYOUT_STRATEGY
    )
    if sampler_provenance is not None and (
        provenance_options != expected_options
        or sampler_provenance.get("layout_strategy") != expected_layout_strategy
        or not isinstance(provenance_circuit_hashes, list)
        or len(provenance_circuit_hashes) != len(config.hamiltonian.terms)
        or not all(_is_sha256(item) for item in provenance_circuit_hashes)
        or not isinstance(provenance_layouts, list)
        or len(provenance_layouts) != len(config.hamiltonian.terms)
        or not all(_valid_layout(config, item) for item in provenance_layouts)
        or (
            config.mode == "qiskit-runtime-sampler"
            and len(
                {
                    tuple(item["logical_to_physical"])
                    for item in provenance_layouts
                }
            )
            != 1
        )
    ):
        report.add_failure(
            "run_execution_options",
            "trace Sampler provenance lacks the configured options, circuit hashes, or layouts",
            seq=run_started[0].seq if run_started else None,
        )

    term_specs = tuple(config.hamiltonian.terms)
    expected_term_ids = tuple(term.term_id for term in term_specs)
    expected_term_by_id = {term.term_id: term for term in term_specs}
    expected_pub_by_term = {
        term.term_id: index for index, term in enumerate(term_specs)
    }
    linked_hashes: list[str] = []
    correlated: list[tuple[RuntimeEvent, Mapping[str, Any]]] = []

    for event in observations:
        identity = _observation_identity(event)
        raw_hash = event.payload.get("raw_evidence_sha256")
        if identity is None or not _is_sha256(raw_hash):
            report.add_failure(
                "intra_raw_evidence_link",
                "termObserved lacks a complete identity or lowercase raw-evidence SHA-256",
                seq=event.seq,
            )
            continue
        if _event_arg(event, 0) != run_id or _event_arg(event, 1) != config.digest:
            report.add_failure(
                "intra_raw_evidence_link",
                "termObserved run/config identity does not match this replay",
                seq=event.seq,
            )
        linked_hashes.append(raw_hash)
        record = loaded.records_by_hash.get(raw_hash)
        if record is None:
            report.add_failure(
                "intra_raw_evidence_link",
                f"termObserved references absent evidence {raw_hash}",
                seq=event.seq,
            )
            continue
        correlated.append((event, record))

        iteration, evaluation_id, submission_id, external_job_id, term_id = identity
        record_identity = (
            record.get("iteration"),
            record.get("evaluation_id"),
            record.get("submission_id"),
            record.get("external_job_id"),
            record.get("term_id"),
        )
        if record_identity != identity:
            report.add_failure(
                "intra_raw_evidence_link",
                "sidecar iteration/evaluation/submission/job/term identity differs from termObserved",
                seq=event.seq,
            )
        if record.get("run_id") != run_id or record.get("config_hash") != config.digest:
            report.add_failure(
                "intra_raw_evidence_link",
                "sidecar run/config identity differs from the verified trace",
                seq=event.seq,
            )

        spec = expected_term_by_id.get(term_id)
        expected_pub = expected_pub_by_term.get(term_id)
        trace_pub = event.payload.get("pub_index")
        if (
            spec is None
            or event.payload.get("term_id") != term_id
            or event.payload.get("pauli") != (None if spec is None else spec.pauli)
            or record.get("pauli") != (None if spec is None else spec.pauli)
            or not _is_integer(trace_pub)
            or trace_pub != expected_pub
            or record.get("pub_index") != expected_pub
        ):
            report.add_failure(
                "intra_pub_assignment",
                "term/Pauli/PUB assignment differs across configuration, trace, and sidecar",
                seq=event.seq,
            )

        expected_key = (iteration, evaluation_id, submission_id, term_id)
        declarations = expected_terms.get(expected_key, [])
        if len(declarations) != 1:
            report.add_failure(
                "intra_pub_assignment",
                "termObserved does not have exactly one matching termExpected declaration",
                seq=event.seq,
            )
            declaration = None
        else:
            declaration = declarations[0]
        parameterized_hash = record.get("parameterized_circuit_qpy_sha256")
        if (
            declaration is None
            or not _is_sha256(parameterized_hash)
            or declaration.payload.get("parameterized_circuit_qpy_sha256")
            != parameterized_hash
            or declaration.payload.get("pub_index") != expected_pub
            or declaration.payload.get("requested_shots") != config.shots_per_term
            or declaration.payload.get("term_id") != term_id
            or declaration.payload.get("pauli") != (None if spec is None else spec.pauli)
        ):
            report.add_failure(
                "intra_pub_assignment",
                "sidecar circuit/PUB identity differs from its termExpected declaration",
                seq=event.seq,
            )
        if (
            expected_pub is not None
            and isinstance(provenance_circuit_hashes, list)
            and len(provenance_circuit_hashes) > expected_pub
            and provenance_circuit_hashes[expected_pub] != parameterized_hash
        ):
            report.add_failure(
                "run_execution_options",
                "sidecar parameterized-circuit hash differs from run provenance",
                seq=event.seq,
            )

        job_events = submitted_jobs.get((iteration, evaluation_id, submission_id), [])
        if (
            len(job_events) != 1
            or _event_arg(job_events[0], 5) != external_job_id
            or job_events[0].payload.get("external_job_id") != external_job_id
        ):
            report.add_failure(
                "intra_raw_evidence_link",
                "sidecar job identity lacks exactly one matching jobSubmitted event",
                seq=event.seq,
            )

        start_events = starts.get((iteration, evaluation_id), [])
        theta = record.get("theta")
        theta_hash = record.get("theta_hash")
        valid_theta = isinstance(theta, list) and len(theta) == config.parameter_count
        theta_values: tuple[float, ...] | None = None
        if valid_theta:
            try:
                theta_values = tuple(float(item) for item in theta)
            except (TypeError, ValueError):
                theta_values = None
            if theta_values is not None and not all(math.isfinite(item) for item in theta_values):
                theta_values = None
        calculated_theta_hash = (
            None if theta_values is None else vector_digest(theta_values)
        )
        start = start_events[0] if len(start_events) == 1 else None
        if (
            start is None
            or not _is_sha256(theta_hash)
            or calculated_theta_hash != theta_hash
            or _event_arg(event, 7) != theta_hash
            or _event_arg(start, 4 if start.name == "firstIterationStarted" else 5)
            != theta_hash
            or start.payload.get("theta_hash") != theta_hash
            or start.payload.get("theta") != theta
        ):
            report.add_failure(
                "intra_raw_evidence_link",
                "sidecar parameter vector/digest differs from the iteration and observation",
                seq=event.seq,
            )

        requested = record.get("requested_shots")
        observed = record.get("observed_shots")
        negative = record.get("negative_eigenvalue_count")
        trace_expectation = event.payload.get("expectation")
        record_expectation = record.get("expectation")
        numeric_expectation = (
            float(trace_expectation)
            if isinstance(trace_expectation, (int, float))
            and not isinstance(trace_expectation, bool)
            and math.isfinite(float(trace_expectation))
            else None
        )
        reconstructed = (
            expectation_from_negative_count(negative, observed)
            if _is_integer(negative)
            and _is_integer(observed)
            and observed > 0
            and 0 <= negative <= observed
            else None
        )
        if (
            requested != config.shots_per_term
            or observed != config.shots_per_term
            or event.payload.get("requested_shots") != requested
            or event.payload.get("observed_shots") != observed
            or event.payload.get("shots") != observed
            or event.payload.get("negative_eigenvalue_count") != negative
            or event.payload.get("counts_ones") != negative
            or numeric_expectation is None
            or not isinstance(record_expectation, (int, float))
            or isinstance(record_expectation, bool)
            or reconstructed is None
            or not math.isclose(
                numeric_expectation,
                float(record_expectation),
                rel_tol=0.0,
                abs_tol=config.expectation_abs_tolerance,
            )
            or not math.isclose(
                numeric_expectation,
                reconstructed,
                rel_tol=0.0,
                abs_tol=config.expectation_abs_tolerance,
            )
        ):
            report.add_failure(
                "intra_parity_reconstruction",
                "shots, negative parity, or expectation differ across raw data and trace",
                seq=event.seq,
            )

        executable_hash = record.get("executable_circuit_qpy_sha256")
        if (
            not _is_sha256(executable_hash)
            or event.payload.get("executable_circuit_qpy_sha256") != executable_hash
        ):
            report.add_failure(
                "intra_raw_evidence_link",
                "executable-circuit hash is absent or differs from termObserved",
                seq=event.seq,
            )

        packed = record.get("packed_bitarray")
        packed_data = packed.get("data") if isinstance(packed, Mapping) else None
        try:
            raw_bytes = b64decode(packed_data.encode("ascii"), validate=True)
        except (AttributeError, UnicodeEncodeError, ValueError):
            raw_bytes = None
        declared_raw_bytes_hash = record.get("raw_shot_data_sha256")
        if (
            raw_bytes is None
            or not _is_sha256(declared_raw_bytes_hash)
            or hashlib.sha256(raw_bytes).hexdigest() != declared_raw_bytes_hash
        ):
            report.add_failure(
                "intra_parity_reconstruction",
                "packed raw-shot byte SHA-256 is absent or inconsistent",
                seq=event.seq,
            )

        submitted_at = _parse_aware_timestamp(record.get("submitted_at_utc"))
        retrieved_at = _parse_aware_timestamp(record.get("retrieved_at_utc"))
        layout = record.get("physical_layout")
        required_metadata = {
            "job_metadata",
            "primitive_result_metadata",
            "pub_metadata",
        }
        expected_transpiler_seed = (
            config.seed if config.mode == "qiskit-runtime-sampler" else None
        )
        expected_optimization_level = (
            3 if config.mode == "qiskit-runtime-sampler" else None
        )
        options_valid = bool(
            record.get("execution_mode") == config.mode
            and record.get("backend") == config.backend
            and record.get("sampler_options") == expected_options
            and _valid_layout(config, layout)
            and record.get("transpiler_seed") == expected_transpiler_seed
            and record.get("transpiler_optimization_level")
            == expected_optimization_level
            and submitted_at is not None
            and retrieved_at is not None
            and retrieved_at >= submitted_at
            and required_metadata <= set(record)
            and isinstance(record.get("job_metadata"), Mapping)
            and isinstance(record.get("pub_metadata"), Mapping)
        )
        if (
            expected_pub is not None
            and isinstance(provenance_layouts, list)
            and len(provenance_layouts) > expected_pub
        ):
            options_valid = options_valid and layout == provenance_layouts[expected_pub]
        if sampler_provenance is not None:
            options_valid = bool(
                options_valid
                and sampler_provenance.get("transpiler_optimization_level")
                == expected_optimization_level
                and sampler_provenance.get("seed_transpiler")
                == expected_transpiler_seed
            )
        if not options_valid:
            report.add_failure(
                "run_execution_options",
                "sidecar mode/backend/layout/options/timestamps/metadata are incomplete or inconsistent",
                seq=event.seq,
            )

    duplicate_trace_hashes = sorted(
        digest for digest, count in Counter(linked_hashes).items() if count != 1
    )
    if duplicate_trace_hashes:
        report.add_failure(
            "inter_raw_evidence_identity_unique",
            f"trace reuses raw-evidence hashes: {duplicate_trace_hashes}",
        )

    linked_set = set(linked_hashes)
    record_set = set(loaded.records_by_hash)
    missing_records = linked_set - record_set
    orphan_records = record_set - linked_set
    if missing_records or orphan_records or len(observations) != len(loaded.records):
        report.add_failure(
            "run_raw_evidence_complete",
            "trace/sidecar PUB coverage differs "
            f"(observations={len(observations)}, records={len(loaded.records)}, "
            f"missing={len(missing_records)}, orphan={len(orphan_records)})",
        )

    groups: dict[tuple[int, str], list[tuple[RuntimeEvent, Mapping[str, Any]]]] = defaultdict(list)
    for event, record in correlated:
        identity = _observation_identity(event)
        if identity is not None:
            groups[(identity[0], identity[1])].append((event, record))
    for (iteration, evaluation_id), group in groups.items():
        ordered = sorted(group, key=lambda item: item[0].seq)
        pub_indices = [record.get("pub_index") for _, record in ordered]
        terms_in_event_order = [record.get("term_id") for _, record in ordered]
        terms_by_pub = {
            record.get("pub_index"): record.get("term_id") for _, record in group
        }
        submissions = {record.get("submission_id") for _, record in group}
        jobs = {record.get("external_job_id") for _, record in group}
        if (
            len(group) != len(term_specs)
            or set(pub_indices) != set(range(len(term_specs)))
            or len(pub_indices) != len(set(pub_indices))
            or tuple(terms_in_event_order) != expected_term_ids
            or tuple(terms_by_pub.get(index) for index in range(len(term_specs)))
            != expected_term_ids
            or len(submissions) != 1
            or len(jobs) != 1
            or iteration >= config.max_iterations
        ):
            report.add_failure(
                "intra_pub_assignment",
                f"evaluation {evaluation_id!r} does not contain one ordered, four-PUB, one-job term set",
                seq=ordered[0][0].seq if ordered else None,
            )

    manifest = loaded.manifest
    record_count = len(loaded.records)
    total_shots = sum(record["observed_shots"] for record in loaded.records)
    maximum_records = config.max_iterations * len(term_specs)
    if (
        manifest is None
        or manifest.get("record_count") != record_count
        or manifest.get("total_observed_shots") != total_shots
        or record_count != len(observations)
        or record_count > maximum_records
        or (record_count and record_count % len(term_specs) != 0)
    ):
        report.add_failure(
            "run_raw_evidence_complete",
            "manifest/count totals do not describe a complete bounded set of evaluations",
        )
    if total_shots > config.shot_budget:
        report.add_failure(
            "run_physical_shot_budget",
            f"observed {total_shots} physical shots, exceeding budget {config.shot_budget}",
        )

    report.mark_checked(*EVIDENCE_REPLAY_PROPERTIES)


# A descriptive alias keeps the call site readable when this is composed with
# the main trace checker.
verify_evidence_replay = verify_trace_evidence


__all__ = [
    "EVIDENCE_REPLAY_PROPERTIES",
    "verify_evidence_replay",
    "verify_trace_evidence",
]
