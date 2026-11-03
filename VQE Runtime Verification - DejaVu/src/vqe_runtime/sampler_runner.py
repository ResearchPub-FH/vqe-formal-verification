"""Comparable finite-shot VQE drivers for StatevectorSampler and IBM SamplerV2."""

from __future__ import annotations

from base64 import b64decode
from datetime import datetime, timezone
from io import BytesIO
import hashlib
import math
from pathlib import Path
import random
from typing import Any, Mapping, Sequence

from .config import RuntimeConfig, vector_digest
from .optimizer import AskTellPatternSearch
from .report import VerificationReport
from .sampling import (
    QISKIT_BIT_ORDER,
    RAW_EVIDENCE_FORMAT,
    build_measurement_circuit,
    evidence_from_pub_result,
    raw_evidence_sha256,
)
from .session import (
    RuntimeSession,
    TermObservation,
    TerminationReason,
    VerificationAbort,
)


SAMPLER_MODES = frozenset(
    {"qiskit-statevector-sampler", "qiskit-runtime-sampler"}
)
TRANSPILE_OPTIMIZATION_LEVEL = 3
STATEVECTOR_LAYOUT_STRATEGY = "logical-identity-untranspiled-v1"
HARDWARE_LAYOUT_STRATEGY = "seeded-ansatz-layout-fixed-across-pubs-v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _qpy_digest(circuit: Any) -> str:
    from qiskit import qpy

    stream = BytesIO()
    qpy.dump(circuit, stream)
    return hashlib.sha256(stream.getvalue()).hexdigest()


def _job_id(job: Any, fallback: str) -> str:
    value = getattr(job, "job_id", None)
    if callable(value):
        value = value()
    return fallback if value is None else str(value)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        if isinstance(value, float) and not math.isfinite(value):
            return repr(value)
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "tolist"):
        try:
            return _json_safe(value.tolist())
        except Exception:
            pass
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return repr(value)


def _call_metadata(job: Any) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for name in ("creation_date", "status", "tags", "usage_estimation"):
        attribute = getattr(job, name, None)
        if attribute is None:
            continue
        try:
            value = attribute() if callable(attribute) else attribute
        except Exception as exc:
            values[f"{name}_error"] = type(exc).__name__
        else:
            values[name] = _json_safe(value)
    metrics = getattr(job, "metrics", None)
    if callable(metrics):
        try:
            values["metrics"] = _json_safe(metrics())
        except Exception as exc:
            values["metrics_error"] = type(exc).__name__
    return values


def _layout_record(circuit: Any) -> dict[str, Any]:
    layout = getattr(circuit, "layout", None)
    if layout is None:
        return {
            "transpiled": False,
            "logical_to_physical": list(range(circuit.num_qubits)),
        }
    try:
        indices = [
            int(value)
            for value in layout.final_index_layout(filter_ancillas=True)
        ]
    except Exception:
        indices = []
    return {
        "transpiled": True,
        "logical_to_physical": indices,
        "output_qubits": int(circuit.num_qubits),
    }


def _sampler_experiment_provenance(
    config: RuntimeConfig,
    *,
    ansatz: Any,
    circuits: Sequence[Any],
    circuit_hashes: Sequence[str],
    initial_theta: Sequence[float],
) -> dict[str, Any]:
    if config.sampler is None or config.optimizer is None:
        raise ValueError("SamplerV2 experiment policies are missing")
    if len(circuit_hashes) != len(circuits):
        raise ValueError("each Sampler circuit requires one captured QPY digest")
    try:
        import qiskit
    except ImportError:  # pragma: no cover - guarded by the public entry point
        qiskit = None
    qiskit_version = None if qiskit is None else getattr(qiskit, "__version__", None)
    runtime_version = None
    if config.mode == "qiskit-runtime-sampler":
        try:
            import qiskit_ibm_runtime

            runtime_version = getattr(qiskit_ibm_runtime, "__version__", None)
        except ImportError:
            runtime_version = None

    api_options: dict[str, Any]
    if config.mode == "qiskit-runtime-sampler":
        api_options = {
            "primitive": "qiskit_ibm_runtime.SamplerV2",
            "constructor": {
                "default_shots": config.shots_per_term,
                "dynamical_decoupling": {"enable": False},
                "execution": {"init_qubits": True, "meas_type": "classified"},
                "twirling": {"enable_gates": False, "enable_measure": False},
            },
            "run_shots": config.shots_per_term,
        }
    else:
        api_options = {
            "primitive": "qiskit.primitives.StatevectorSampler",
            "constructor": {
                "default_shots": config.shots_per_term,
                "seed": config.seed,
            },
            "run_shots": config.shots_per_term,
        }
    return {
        "qiskit_version": qiskit_version,
        "qiskit_ibm_runtime_version": runtime_version,
        "ansatz": {
            "class": "EfficientSU2",
            "num_qubits": config.hamiltonian.num_qubits,
            "su2_gates": ["ry"],
            "entanglement": "linear",
            "reps": 1,
            "parameter_count": ansatz.num_parameters,
            "qpy_sha256": _qpy_digest(ansatz),
        },
        "initial_theta": list(initial_theta),
        "initial_theta_hash": vector_digest(tuple(initial_theta)),
        "sampler_experiment": {
            "pubs_per_evaluation": len(circuits),
            "term_order": [term.term_id for term in config.hamiltonian.terms],
            "pauli_order": [term.pauli for term in config.hamiltonian.terms],
            "shots_per_pub": config.shots_per_term,
            "physical_shots_per_evaluation": (
                len(circuits) * config.shots_per_term
            ),
            "maximum_submitted_pubs": (
                config.max_iterations * len(circuits)
            ),
            "maximum_physical_shots": config.shot_budget,
            "bitstring_order": QISKIT_BIT_ORDER,
            "raw_evidence_format": RAW_EVIDENCE_FORMAT,
            "layout_strategy": (
                HARDWARE_LAYOUT_STRATEGY
                if config.mode == "qiskit-runtime-sampler"
                else STATEVECTOR_LAYOUT_STRATEGY
            ),
            "sampler_policy": config.sampler.as_dict(),
            "optimizer_policy": config.optimizer.as_dict(),
            "optimizer_gate_order": [
                "preview_update_no_mutation",
                "verifier_authorize_exact_theta",
                "commit_update",
                "verifier_record_commit",
            ],
            "api_options": api_options,
            "parameterized_circuit_qpy_sha256": [
                str(digest) for digest in circuit_hashes
            ],
            "physical_layouts": [_layout_record(circuit) for circuit in circuits],
            "transpiler_optimization_level": (
                TRANSPILE_OPTIMIZATION_LEVEL
                if config.mode == "qiskit-runtime-sampler"
                else None
            ),
            "seed_transpiler": (
                config.seed if config.mode == "qiskit-runtime-sampler" else None
            ),
        },
    }


def _make_circuits(
    config: RuntimeConfig,
    *,
    runtime_backend: Any | None = None,
) -> tuple[Any, tuple[Any, ...]]:
    try:
        from qiskit.circuit.library import efficient_su2
    except ImportError as exc:
        raise RuntimeError("install the qiskit extra to use SamplerV2 modes") from exc

    ansatz = efficient_su2(
        config.hamiltonian.num_qubits,
        su2_gates=["ry"],
        entanglement="linear",
        reps=1,
    )
    if ansatz.num_parameters != config.parameter_count:
        raise ValueError(
            f"configured parameter_count={config.parameter_count} but the ansatz "
            f"has {ansatz.num_parameters} parameters"
        )
    logical = tuple(
        build_measurement_circuit(ansatz, term.pauli)
        for term in config.hamiltonian.terms
    )
    if config.mode == "qiskit-statevector-sampler":
        return ansatz, logical

    try:
        from qiskit.transpiler.preset_passmanagers import (
            generate_preset_pass_manager,
        )
    except ImportError as exc:
        raise RuntimeError("qiskit-ibm-runtime is required for hardware mode") from exc
    if runtime_backend is None:
        raise ValueError("hardware circuit construction requires a resolved backend")
    selector = generate_preset_pass_manager(
        target=runtime_backend.target,
        optimization_level=TRANSPILE_OPTIMIZATION_LEVEL,
        seed_transpiler=config.seed,
    )
    selected = _layout_record(selector.run(ansatz))["logical_to_physical"]
    if (
        len(selected) != config.hamiltonian.num_qubits
        or len(set(selected)) != len(selected)
    ):
        raise RuntimeError("transpiler did not select a complete two-qubit layout")
    pass_manager = generate_preset_pass_manager(
        target=runtime_backend.target,
        initial_layout=selected,
        optimization_level=TRANSPILE_OPTIMIZATION_LEVEL,
        seed_transpiler=config.seed,
    )
    compiled = tuple(pass_manager.run(circuit) for circuit in logical)
    compiled_layouts = tuple(
        _layout_record(circuit)["logical_to_physical"] for circuit in compiled
    )
    if any(layout != selected for layout in compiled_layouts):
        raise RuntimeError(
            "transpiler did not preserve the fixed logical-to-physical layout "
            "across all measurement PUBs"
        )
    return ansatz, compiled


def _make_sampler(config: RuntimeConfig, *, runtime_backend: Any | None = None) -> Any:
    if config.mode == "qiskit-statevector-sampler":
        try:
            from qiskit.primitives import StatevectorSampler
        except ImportError as exc:
            raise RuntimeError("StatevectorSampler is unavailable") from exc
        return StatevectorSampler(
            default_shots=config.shots_per_term,
            seed=config.seed,
        )

    try:
        from qiskit_ibm_runtime import SamplerV2
        from qiskit_ibm_runtime.options import SamplerOptions
    except ImportError as exc:
        raise RuntimeError("qiskit-ibm-runtime is required for hardware mode") from exc
    if runtime_backend is None:
        raise ValueError("hardware SamplerV2 construction requires a resolved backend")
    options = SamplerOptions(
        default_shots=config.shots_per_term,
        dynamical_decoupling={"enable": False},
        execution={"init_qubits": True, "meas_type": "classified"},
        twirling={"enable_gates": False, "enable_measure": False},
    )
    return SamplerV2(mode=runtime_backend, options=options)


def _resolve_runtime_backend(config: RuntimeConfig) -> tuple[Any, Any]:
    try:
        from qiskit_ibm_runtime import QiskitRuntimeService
    except ImportError as exc:
        raise RuntimeError("qiskit-ibm-runtime is required for hardware mode") from exc
    service = QiskitRuntimeService()
    return service, service.backend(config.backend)


def _validate_output_paths(
    config: RuntimeConfig,
    *,
    trace_path: str | Path,
    report_path: str | Path,
    evidence_path: str | Path,
) -> bool:
    """Return whether writers may overwrite, guarding hardware resubmissions."""

    destinations = tuple(
        Path(path).expanduser().resolve()
        for path in (trace_path, report_path, evidence_path)
    )
    if len(set(destinations)) != len(destinations):
        raise ValueError("trace, report, and raw-evidence paths must be distinct")
    hardware = config.mode == "qiskit-runtime-sampler"
    if hardware:
        existing = [str(path) for path in destinations if path.exists()]
        if existing:
            raise ValueError(
                "refusing to start an IBM hardware run because durable output "
                f"already exists: {existing}; inspect/recover that run instead of "
                "submitting duplicate jobs"
            )
    return not hardware


def _finalize_normal(session: RuntimeSession) -> None:
    if session.report.terminal_reason is not None:
        return
    if not session.contracts.checkpoints:
        session.abort("optimizerReturnedNoEvaluation")
        return
    last = session.contracts.checkpoints[-1]
    if last.converged:
        session.finish(TerminationReason.CONVERGED)
    elif len(session.contracts.checkpoints) == session.config.max_iterations:
        session.finish(TerminationReason.MAX_ITERATIONS)
    else:
        session.abort("unexpectedOptimizerStop")


def run_sampled_vqe(
    config: RuntimeConfig,
    *,
    trace_path: str | Path,
    report_path: str | Path,
    evidence_path: str | Path,
    run_id: str,
) -> VerificationReport:
    """Run the fixed four-PUB H2 experiment through the online verifier."""

    if config.mode not in SAMPLER_MODES:
        raise ValueError("run_sampled_vqe requires a SamplerV2 execution mode")
    if config.sampler is None or config.optimizer is None:
        raise ValueError("SamplerV2 experiment requires explicit schema-2 policies")
    if tuple(term.pauli for term in config.hamiltonian.terms) != (
        "YZ",
        "ZI",
        "ZZ",
        "XX",
    ):
        raise ValueError("the fixed H2 experiment requires YZ, ZI, ZZ, XX order")

    overwrite = _validate_output_paths(
        config,
        trace_path=trace_path,
        report_path=report_path,
        evidence_path=evidence_path,
    )

    try:
        from .evidence import EvidenceJournal
    except ImportError as exc:  # pragma: no cover - repository integrity failure
        raise RuntimeError("raw-evidence journal is unavailable") from exc

    runtime_backend = None
    # Keep the service alive and use the exact same backend snapshot for both
    # transpilation and Sampler construction.
    _runtime_service = None
    if config.mode == "qiskit-runtime-sampler":
        _runtime_service, runtime_backend = _resolve_runtime_backend(config)
    ansatz, circuits = _make_circuits(
        config,
        runtime_backend=runtime_backend,
    )
    sampler = _make_sampler(config, runtime_backend=runtime_backend)
    circuit_hashes = tuple(_qpy_digest(circuit) for circuit in circuits)
    initial_source = random.Random(config.seed)
    initial_theta = tuple(
        initial_source.uniform(config.parameter_lower, config.parameter_upper)
        for _ in range(config.parameter_count)
    )
    provenance = _sampler_experiment_provenance(
        config,
        ansatz=ansatz,
        circuits=circuits,
        circuit_hashes=circuit_hashes,
        initial_theta=initial_theta,
    )
    optimizer = AskTellPatternSearch(
        config.parameter_count,
        config.parameter_lower,
        config.parameter_upper,
        initial_step=config.optimizer.initial_step,
        step_shrink=config.optimizer.step_shrink,
        improvement_tolerance=config.optimizer.improvement_tolerance,
    )
    evidence = EvidenceJournal(
        evidence_path,
        run_id=run_id,
        config_hash=config.digest,
        durable=config.mode == "qiskit-runtime-sampler",
        overwrite=overwrite,
    )
    session = RuntimeSession(
        config,
        run_id=run_id,
        trace_path=trace_path,
        report_path=report_path,
        execution_provenance=provenance,
        durable=config.mode == "qiskit-runtime-sampler",
        overwrite=overwrite,
    )
    theta = initial_theta
    try:
        for iteration in range(config.max_iterations):
            evaluation_id = f"eval{iteration}"
            submission_id = f"submission{iteration}"
            session.begin_iteration(theta, evaluation_id=evaluation_id)
            session.bind_parameters()
            session.authorize_job(
                submission_id,
                pub_indices={
                    term.term_id: index
                    for index, term in enumerate(config.hamiltonian.terms)
                },
                circuit_hashes={
                    term.term_id: circuit_hashes[index]
                    for index, term in enumerate(config.hamiltonian.terms)
                },
            )
            pubs = [(circuit, list(theta)) for circuit in circuits]
            submitted_at = _utc_now()
            job = sampler.run(pubs, shots=config.shots_per_term)
            external_job_id = _job_id(job, f"localSamplerJob{iteration}")
            session.mark_job_submitted(external_job_id)
            result = job.result()
            retrieved_at = _utc_now()
            if len(result) != len(config.hamiltonian.terms):
                raise RuntimeError(
                    f"Sampler returned {len(result)} PUB results; expected "
                    f"{len(config.hamiltonian.terms)}"
                )
            job_metadata = _call_metadata(job)
            primitive_metadata = _json_safe(getattr(result, "metadata", None))
            expectations: list[float] = []
            for pub_index, (term, circuit, circuit_hash, pub_result) in enumerate(
                zip(config.hamiltonian.terms, circuits, circuit_hashes, result)
            ):
                raw_record = evidence_from_pub_result(
                    pub_result,
                    term_id=term.term_id,
                    pauli=term.pauli,
                    requested_shots=config.shots_per_term,
                )
                bound_circuit_hash = _qpy_digest(
                    circuit.assign_parameters(list(theta), inplace=False)
                )
                packed = raw_record["packed_bitarray"]
                raw_bytes_sha256 = hashlib.sha256(
                    b64decode(packed["data"].encode("ascii"), validate=True)
                ).hexdigest()
                identity = {
                    "execution_mode": config.mode,
                    "backend": config.backend,
                    "iteration": iteration,
                    "evaluation_id": evaluation_id,
                    "submission_id": submission_id,
                    "external_job_id": external_job_id,
                    "pub_index": pub_index,
                    "theta": list(theta),
                    "theta_hash": vector_digest(theta),
                    "parameterized_circuit_qpy_sha256": circuit_hash,
                    "executable_circuit_qpy_sha256": bound_circuit_hash,
                    "raw_shot_data_sha256": raw_bytes_sha256,
                    "physical_layout": _layout_record(circuit),
                    "transpiler_seed": (
                        config.seed
                        if config.mode == "qiskit-runtime-sampler"
                        else None
                    ),
                    "transpiler_optimization_level": (
                        TRANSPILE_OPTIMIZATION_LEVEL
                        if config.mode == "qiskit-runtime-sampler"
                        else None
                    ),
                    "submitted_at_utc": submitted_at,
                    "retrieved_at_utc": retrieved_at,
                    "sampler_options": provenance["sampler_experiment"][
                        "api_options"
                    ],
                    "job_metadata": job_metadata,
                    "primitive_result_metadata": primitive_metadata,
                    "pub_metadata": _json_safe(getattr(pub_result, "metadata", None)),
                }
                archived = evidence.append_pub(raw_record, identity=identity)
                expectation = float(archived["expectation"])
                negative = int(archived["negative_eigenvalue_count"])
                expectations.append(expectation)
                session.observe_term(
                    TermObservation(
                        term.term_id,
                        expectation,
                        int(archived["observed_shots"]),
                        negative,
                        negative_eigenvalue_count=negative,
                        pub_index=pub_index,
                        raw_evidence_sha256=archived["raw_evidence_sha256"],
                        executable_circuit_qpy_sha256=bound_circuit_hash,
                    )
                )
            session.seal_measurements()
            energy = math.fsum(
                term.coeff_int * expectation / config.hamiltonian.coeff_scale
                for term, expectation in zip(config.hamiltonian.terms, expectations)
            )
            session.aggregate_energy(energy)
            converged = session.check_convergence()
            verified_energy = session.authorize_objective_release()
            if not converged and iteration + 1 < config.max_iterations:
                next_theta, update_token = optimizer.preview_update(
                    theta, verified_energy
                )
                before_generation = optimizer.generation
                session.authorize_and_commit_optimizer_update(
                    optimizer,
                    update_token,
                    next_theta,
                )
                if optimizer.generation != before_generation + 1:
                    raise RuntimeError("ask/tell optimizer did not commit exactly once")
            else:
                next_theta = theta
            session.close_iteration()
            if converged:
                session.finish(TerminationReason.CONVERGED)
                break
            theta = tuple(next_theta)
        else:
            session.finish(TerminationReason.MAX_ITERATIONS)

        manifest = evidence.seal()
        expected_records = (
            len(session.contracts.checkpoints) * len(config.hamiltonian.terms)
        )
        if (
            manifest.get("record_count") != expected_records
            or manifest.get("total_observed_shots")
            != session.report.effective_term_samples
        ):
            raise RuntimeError("sealed evidence manifest disagrees with verified trace")
        session.report.mark_checked(
            "run_raw_evidence_complete",
            "run_physical_shot_budget",
            "run_execution_options",
        )
        _finalize_normal(session)
        return session.seal_run()
    except VerificationAbort:
        session.abort("verificationAbort")
        if session.report.terminal_reason is not None and not session.report.complete:
            try:
                if not evidence.sealed:
                    evidence.seal()
            finally:
                session.seal_run()
        raise
    except Exception:
        session.abort("optimizerOrBackendFailure")
        if session.report.terminal_reason is not None and not session.report.complete:
            try:
                if not evidence.sealed:
                    evidence.seal()
            finally:
                session.seal_run()
        raise
    finally:
        evidence.close()
        session.close()


__all__ = [
    "HARDWARE_LAYOUT_STRATEGY",
    "SAMPLER_MODES",
    "STATEVECTOR_LAYOUT_STRATEGY",
    "run_sampled_vqe",
]
