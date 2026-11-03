from __future__ import annotations

from io import BytesIO
import hashlib
import math
from pathlib import Path
import random
from typing import Any, Sequence

from .config import RuntimeConfig, canonical_digest
from .report import VerificationReport
from .session import (
    RuntimeSession,
    TermObservation,
    TerminationReason,
    VerificationAbort,
)


class _VerifiedStop(Exception):
    pass


def _qpy_digest(circuit: Any) -> str:
    from qiskit import qpy

    stream = BytesIO()
    qpy.dump(circuit, stream)
    return hashlib.sha256(stream.getvalue()).hexdigest()


def _values(result: Any, expected: int) -> list[float]:
    try:
        raw = result[0].data.evs
        if hasattr(raw, "reshape"):
            values = raw.reshape(-1).tolist()
        elif hasattr(raw, "tolist"):
            converted = raw.tolist()
            values = converted if isinstance(converted, list) else [converted]
        else:
            values = list(raw)
    except Exception as exc:
        raise RuntimeError(f"cannot decode Estimator expectation vector: {exc}") from exc
    flattened = [float(value) for value in values]
    if len(flattened) != expected or not all(math.isfinite(v) for v in flattened):
        raise RuntimeError(
            f"Estimator returned {len(flattened)} finite values; expected {expected}"
        )
    return flattened


def _observed_shots(result: Any) -> int | None:
    """Return the executed PUB shot total when IBM reports it.

    EstimatorV2 places the observed total in the first PubResult metadata.  A
    configured request is never used as a fallback: missing metadata remains
    unknown, and malformed metadata stops the guarded integration.
    """
    try:
        metadata = result[0].metadata
    except (AttributeError, IndexError, KeyError, TypeError):
        return None
    if not isinstance(metadata, dict) or "shots" not in metadata:
        return None
    shots = metadata["shots"]
    if isinstance(shots, bool) or not isinstance(shots, int) or shots <= 0:
        raise RuntimeError("Estimator returned invalid observed-shot metadata")
    return shots


def _job_id(job: Any, fallback: str) -> str:
    value = getattr(job, "job_id", None)
    if callable(value):
        return str(value())
    if value is not None:
        return str(value)
    return fallback


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
        session.finish(TerminationReason.OPTIMIZER_STOPPED)


def run_qiskit(
    config: RuntimeConfig,
    *,
    trace_path: str | Path,
    report_path: str | Path,
    run_id: str,
) -> VerificationReport:
    """Execute the configured Qiskit profile behind RuntimeSession gates.

    SciPy is an opaque optimizer: candidate continuity is checked when the next
    objective callback arrives, but pre-mutation ask/tell enforcement is not
    claimed and is reported INCONCLUSIVE for that one inter-iteration property.
    """
    if config.mode not in {"qiskit-statevector", "qiskit-runtime"}:
        raise ValueError("run_qiskit requires a Qiskit execution mode")
    try:
        from scipy.optimize import minimize
        from qiskit.circuit.library import efficient_su2
        from qiskit.quantum_info import SparsePauliOp
    except ImportError as exc:
        raise RuntimeError("install the qiskit extra to use this execution mode") from exc

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
    ansatz_hash = _qpy_digest(ansatz)
    random_source = random.Random(config.seed)
    initial = [
        random_source.uniform(config.parameter_lower, config.parameter_upper)
        for _ in range(ansatz.num_parameters)
    ]
    bounds = [
        (config.parameter_lower, config.parameter_upper)
        for _ in range(ansatz.num_parameters)
    ]

    if config.mode == "qiskit-statevector":
        try:
            from qiskit.primitives import StatevectorEstimator
        except ImportError as exc:
            raise RuntimeError("StatevectorEstimator is unavailable") from exc
        estimator = StatevectorEstimator()
        circuit = ansatz
        observables = [
            SparsePauliOp.from_list([(term.pauli, 1.0)])
            for term in config.hamiltonian.terms
        ]
    else:
        try:
            from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
            from qiskit_ibm_runtime import EstimatorV2, QiskitRuntimeService
        except ImportError as exc:
            raise RuntimeError("qiskit-ibm-runtime is required for hardware mode") from exc
        service = QiskitRuntimeService()
        backend = service.backend(config.backend)
        pass_manager = generate_preset_pass_manager(
            target=backend.target,
            optimization_level=3,
            seed_transpiler=config.seed,
        )
        circuit = pass_manager.run(ansatz)
        observables = [
            SparsePauliOp.from_list([(term.pauli, 1.0)]).apply_layout(circuit.layout)
            for term in config.hamiltonian.terms
        ]
        estimator = EstimatorV2(mode=backend)
        estimator.options.default_shots = config.shots_per_term

    execution_provenance = {
        "ansatz_qpy_sha256": ansatz_hash,
        "executable_circuit_qpy_sha256": _qpy_digest(circuit),
        "layout_sha256": canonical_digest(repr(getattr(circuit, "layout", None))),
        "optimizer": "scipy.COBYLA",
        "requested_shots_per_term": config.shots_per_term,
        "transpiler_optimization_level": (
            3 if config.mode == "qiskit-runtime" else None
        ),
        "seed_transpiler": config.seed if config.mode == "qiskit-runtime" else None,
    }

    session = RuntimeSession(
        config,
        run_id=run_id,
        trace_path=trace_path,
        report_path=report_path,
        execution_provenance=execution_provenance,
        durable=config.mode == "qiskit-runtime",
        overwrite=True,
    )
    callback_count = 0

    def objective(params: Sequence[float]) -> float:
        nonlocal callback_count
        theta = tuple(float(value) for value in params)
        if session.contracts.checkpoints:
            session.observe_opaque_optimizer_candidate(theta)
        iteration = len(session.contracts.checkpoints)
        if iteration >= config.max_iterations:
            raise _VerifiedStop
        session.begin_iteration(theta, evaluation_id=f"eval{iteration}")
        session.bind_parameters()
        session.authorize_job(f"submission{iteration}")
        pub = (circuit, observables, [list(theta)])
        job = estimator.run([pub])
        session.mark_job_submitted(_job_id(job, f"localJob{iteration}"))
        result = job.result()
        expectations = _values(result, len(config.hamiltonian.terms))
        observed_shots = (
            0 if config.mode == "qiskit-statevector" else _observed_shots(result)
        )
        session.observe_terms(
            TermObservation(
                term.term_id,
                expectation,
                observed_shots,
                None,
            )
            for term, expectation in zip(config.hamiltonian.terms, expectations)
        )
        session.seal_measurements()
        energy = math.fsum(
            term.coeff_int * expectation / config.hamiltonian.coeff_scale
            for term, expectation in zip(config.hamiltonian.terms, expectations)
        )
        session.aggregate_energy(energy)
        converged = session.check_convergence()
        verified_energy = session.authorize_objective_release()
        session.close_iteration()
        callback_count += 1
        if converged:
            session.finish(TerminationReason.CONVERGED)
            raise _VerifiedStop
        if callback_count >= config.max_iterations:
            session.finish(TerminationReason.MAX_ITERATIONS)
            raise _VerifiedStop
        return verified_energy

    try:
        try:
            minimize(
                objective,
                initial,
                method="COBYLA",
                bounds=bounds,
                options={"maxiter": config.max_iterations},
            )
        except _VerifiedStop:
            pass
        _finalize_normal(session)
        return session.seal_run()
    except VerificationAbort:
        if session.report.terminal_reason is not None and not session.report.complete:
            session.seal_run()
        raise
    except Exception:
        session.abort("optimizerOrBackendFailure")
        if session.report.terminal_reason is not None:
            session.seal_run()
        raise
    finally:
        session.close()
