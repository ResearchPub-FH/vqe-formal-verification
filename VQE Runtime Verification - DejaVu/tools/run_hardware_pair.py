#!/usr/bin/env python3
"""Compare unverified and verified H-RZ-Y VQE runs on IBM hardware.

One pair is one ``unverified`` run and one ``verified`` run of the same workload:
the configured Hamiltonian, ask/tell optimizer, seed, shots, and stop rule, on the
same frozen compiled circuits. The ansatz is the manuscript's four-parameter
circuit, ``efficient_su2(2, su2_gates=["h", "rz", "y"], reps=1)``, instead of the
RY-only ansatz in ``vqe_runtime.sampler_runner``.

* ``unverified`` executes sampling, energy calculation, the numeric stop rule, and
  the optimizer without RuntimeSession or DejaVu. Its raw evidence is written after
  the timing boundary, as in ``benchmark_sampler_verification_scaling.py``.
* ``verified`` adds RuntimeSession, the synchronous DejaVu monitor, durable trace and
  evidence, and an offline replay. Every monitor acknowledgement is kept, so each
  property can be reported as obeyed or violated.

Added time compares client-side time only: time spent submitting to IBM, waiting for
a result, and fetching job metadata is timed separately and excluded, because queue
stalls are far larger than the verification cost. A run may stop early under the
stop rule; its cumulative values then hold at their last value for later bounds.

Subcommands ``check``, ``preflight``, and ``pair`` contact IBM. Only ``preflight`` and
``pair`` submit jobs, and both require ``--submit``. ``local-test`` and ``analyze`` are
offline.
"""

from __future__ import annotations

import argparse
from base64 import b64decode
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "tools"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from benchmark_sampler_verification_scaling import (  # noqa: E402
    _convergence,
    _ideal_probabilities,
    _initial_theta,
    _optimizer,
)
import property_coverage  # noqa: E402
from vqe_runtime.checker import check_trace  # noqa: E402
from vqe_runtime.config import RuntimeConfig, load_config, vector_digest  # noqa: E402
from vqe_runtime.dejavu import SynchronousDejaVu  # noqa: E402
from vqe_runtime.events import load_events  # noqa: E402
from vqe_runtime.evidence import EvidenceJournal  # noqa: E402
from vqe_runtime.sampler_runner import (  # noqa: E402
    TRANSPILE_OPTIMIZATION_LEVEL,
    _call_metadata,
    _job_id,
    _json_safe,
    _layout_record,
    _make_sampler,
    _qpy_digest,
    _resolve_runtime_backend,
    _sampler_experiment_provenance,
    _utc_now,
)
from vqe_runtime.sampling import (  # noqa: E402
    build_measurement_circuit,
    classical_distribution_fidelity,
    evidence_from_pub_result,
    expectation_from_negative_count,
    extract_bit_array,
    negative_eigenvalue_count,
)
from vqe_runtime.session import (  # noqa: E402
    RuntimeSession,
    TermObservation,
    TerminationReason,
    VerificationAbort,
)


SU2_GATES = ("h", "rz", "y")
PAIR_CONFIG = ROOT / "configs/h2_ibm_sampler_50.toml"
PREFLIGHT_CONFIG = ROOT / "configs/h2_ibm_sampler_preflight.toml"
CONDITIONS = ("unverified", "verified")
BOUNDS = (10, 20, 30, 40, 50)
EQUIVALENCE_THETAS = 8
EQUIVALENCE_TOLERANCE = 1e-9
ASSUMED_CHARGE_SECONDS = 3.0


class QpuCapReached(RuntimeError):
    """The next job could pass the declared charged-QPU cap."""


class RunFailed(RuntimeError):
    """A run stopped before its terminal state; nothing is rerun automatically."""


def build_ansatz(config: RuntimeConfig) -> tuple[Any, tuple[Any, ...]]:
    from qiskit.circuit.library import efficient_su2

    ansatz = efficient_su2(
        config.hamiltonian.num_qubits,
        su2_gates=list(SU2_GATES),
        entanglement="linear",
        reps=1,
    )
    if ansatz.num_parameters != config.parameter_count:
        raise ValueError(
            f"ansatz has {ansatz.num_parameters} parameters, "
            f"configured {config.parameter_count}"
        )
    return ansatz, tuple(
        build_measurement_circuit(ansatz, term.pauli)
        for term in config.hamiltonian.terms
    )


def compile_circuits(
    config: RuntimeConfig, ansatz: Any, logical: Sequence[Any], target: Any
) -> tuple[Any, ...]:
    from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager

    selector = generate_preset_pass_manager(
        target=target,
        optimization_level=TRANSPILE_OPTIMIZATION_LEVEL,
        seed_transpiler=config.seed,
    )
    selected = _layout_record(selector.run(ansatz))["logical_to_physical"]
    if len(selected) != config.hamiltonian.num_qubits or len(set(selected)) != len(selected):
        raise RuntimeError("transpiler did not select a complete layout")
    manager = generate_preset_pass_manager(
        target=target,
        initial_layout=selected,
        optimization_level=TRANSPILE_OPTIMIZATION_LEVEL,
        seed_transpiler=config.seed,
    )
    compiled = tuple(manager.run(circuit) for circuit in logical)
    if any(_layout_record(c)["logical_to_physical"] != selected for c in compiled):
        raise RuntimeError("compiled measurement circuits disagree on the layout")
    return compiled


def compiled_distribution(circuit: Any, theta: Sequence[float]) -> dict[str, float]:
    """Ideal outcome distribution of a compiled circuit, simulated on its active qubits."""

    from qiskit import QuantumCircuit
    from qiskit.quantum_info import Statevector

    bound = circuit.assign_parameters(list(theta), inplace=False)
    active = sorted(
        {
            bound.find_bit(qubit).index
            for item in bound.data
            if item.operation.name not in {"barrier", "delay"}
            for qubit in item.qubits
        }
    )
    position = {physical: index for index, physical in enumerate(active)}
    reduced = QuantumCircuit(len(active))
    reduced.global_phase = bound.global_phase
    measured: dict[int, int] = {}
    for item in bound.data:
        if item.operation.name in {"barrier", "delay"}:
            continue
        indices = [position[bound.find_bit(qubit).index] for qubit in item.qubits]
        if item.operation.name == "measure":
            measured[bound.find_bit(item.clbits[0]).index] = indices[0]
        else:
            reduced.append(item.operation, indices)
    distribution: dict[str, float] = {}
    for basis, probability in enumerate(Statevector.from_instruction(reduced).probabilities()):
        bits = "".join(
            str((basis >> measured[bit]) & 1) for bit in reversed(range(len(measured)))
        )
        distribution[bits] = distribution.get(bits, 0.0) + float(probability)
    return distribution


def compiled_equivalence_error(
    compiled: Sequence[Any], logical: Sequence[Any], *, seed: int = 20261105
) -> float:
    """Largest total-variation distance between compiled and logical outcomes."""

    import numpy as np

    rng = np.random.default_rng(seed)
    worst = 0.0
    for _ in range(EQUIVALENCE_THETAS):
        theta = rng.uniform(-math.pi, math.pi, logical[0].num_parameters).tolist()
        for circuit, reference in zip(compiled, logical):
            ideal = _ideal_probabilities(reference, theta)
            actual = compiled_distribution(circuit, theta)
            outcomes = set(ideal) | set(actual)
            worst = max(
                worst,
                0.5 * sum(abs(ideal.get(o, 0.0) - actual.get(o, 0.0)) for o in outcomes),
            )
    return worst


def freeze_circuits(out_dir: Path, compiled: Sequence[Any], metadata: Mapping[str, Any]) -> Path:
    from qiskit import qpy

    frozen = out_dir / "frozen"
    frozen.mkdir(parents=True, exist_ok=False)
    path = frozen / "circuits.qpy"
    with path.open("wb") as stream:
        qpy.dump(list(compiled), stream)
    manifest = {
        **metadata,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "su2_gates": list(SU2_GATES),
        "transpiler_seed": metadata.get("transpiler_seed"),
        "transpiler_optimization_level": TRANSPILE_OPTIMIZATION_LEVEL,
        "logical_to_physical": _layout_record(compiled[0])["logical_to_physical"],
        "circuits": [
            {
                "depth": circuit.depth(),
                "gates": {k: int(v) for k, v in circuit.count_ops().items()},
                "parameters": circuit.num_parameters,
            }
            for circuit in compiled
        ],
    }
    (frozen / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return path


def load_frozen(out_dir: Path) -> tuple[tuple[Any, ...], dict[str, Any]]:
    from qiskit import qpy

    path = out_dir / "frozen/circuits.qpy"
    manifest = json.loads((out_dir / "frozen/manifest.json").read_text())
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["sha256"]:
        raise RuntimeError("frozen circuits differ from their manifest")
    with path.open("rb") as stream:
        circuits = tuple(qpy.load(stream))
    for circuit in circuits:
        if _layout_record(circuit)["logical_to_physical"] != manifest["logical_to_physical"]:
            raise RuntimeError("frozen circuit lost its recorded layout")
    return circuits, manifest


class QpuLedger:
    """Charged QPU seconds across every job of this experiment directory."""

    def __init__(self, path: Path, cap_seconds: float) -> None:
        self.path = path
        self.cap_seconds = cap_seconds
        self.jobs: list[dict[str, Any]] = (
            json.loads(path.read_text()) if path.exists() else []
        )

    @property
    def charged_seconds(self) -> float:
        return math.fsum(job["charged_seconds"] for job in self.jobs)

    def require_room(self) -> None:
        if self.charged_seconds + ASSUMED_CHARGE_SECONDS > self.cap_seconds:
            raise QpuCapReached(
                f"{self.charged_seconds:.0f} s charged; cap is {self.cap_seconds:.0f} s"
            )

    def record(self, run_id: str, job_id: str, metadata: Mapping[str, Any]) -> None:
        metrics = metadata.get("metrics") or {}
        usage = metrics.get("usage") or {}
        seconds = usage.get("qpu_charge_time_seconds", usage.get("seconds"))
        self.jobs.append(
            {
                "run_id": run_id,
                "job_id": job_id,
                "charged_seconds": float(ASSUMED_CHARGE_SECONDS if seconds is None else seconds),
                "circuits_execution_time_ns": metrics.get("circuits_execution_time_ns"),
                "reported": seconds is not None,
            }
        )
        self.path.write_text(json.dumps(self.jobs, indent=1) + "\n")


class _RecordingMonitor:
    """Keep every acknowledgement of one SynchronousDejaVu instance."""

    def __init__(self, config: RuntimeConfig) -> None:
        self.monitor = SynchronousDejaVu(
            timeout_seconds=config.monitor_timeout_seconds,
            bits_per_variable=config.bits_per_variable,
        )
        self.rows: list[dict[str, Any]] = []
        submit = self.monitor.submit

        def recorded(event: Any) -> Any:
            started = time.perf_counter()
            ack = submit(event)
            self.rows.append(
                {
                    "seq": event.seq,
                    "event": event.name,
                    "passed": ack.passed,
                    "violations": list(ack.violations),
                    "latency_seconds": time.perf_counter() - started,
                }
            )
            return ack

        # Assign on the instance: the session requires this exact monitor type.
        self.monitor.submit = recorded  # type: ignore[method-assign]


def _identity(
    *,
    config: RuntimeConfig,
    provenance: Mapping[str, Any],
    circuit: Any,
    circuit_hash: str,
    theta: Sequence[float],
    evaluation: int,
    pub_index: int,
    external_job_id: str,
    submitted_at: str,
    retrieved_at: str,
    job_metadata: Mapping[str, Any],
    primitive_metadata: Any,
    pub_metadata: Any,
    raw_record: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "execution_mode": config.mode,
        "backend": config.backend,
        "iteration": evaluation,
        "evaluation_id": f"eval{evaluation}",
        "submission_id": f"submission{evaluation}",
        "external_job_id": external_job_id,
        "pub_index": pub_index,
        "theta": list(theta),
        "theta_hash": vector_digest(theta),
        "parameterized_circuit_qpy_sha256": circuit_hash,
        "executable_circuit_qpy_sha256": _qpy_digest(
            circuit.assign_parameters(list(theta), inplace=False)
        ),
        "raw_shot_data_sha256": hashlib.sha256(
            b64decode(raw_record["packed_bitarray"]["data"].encode("ascii"), validate=True)
        ).hexdigest(),
        "physical_layout": _layout_record(circuit),
        "transpiler_seed": config.seed,
        "transpiler_optimization_level": TRANSPILE_OPTIMIZATION_LEVEL,
        "submitted_at_utc": submitted_at,
        "retrieved_at_utc": retrieved_at,
        "sampler_options": provenance["sampler_experiment"]["api_options"],
        "job_metadata": dict(job_metadata),
        "primitive_result_metadata": _json_safe(primitive_metadata),
        "pub_metadata": _json_safe(pub_metadata),
    }


def _provenance(
    config: RuntimeConfig,
    ansatz: Any,
    circuits: Sequence[Any],
    circuit_hashes: Sequence[str],
    theta: Sequence[float],
    frozen_sha256: str,
) -> dict[str, Any]:
    provenance = _sampler_experiment_provenance(
        config,
        ansatz=ansatz,
        circuits=circuits,
        circuit_hashes=circuit_hashes,
        initial_theta=theta,
    )
    # The shared helper names the RY ansatz it was written for.
    provenance["ansatz"]["su2_gates"] = list(SU2_GATES)
    provenance["frozen_circuits_sha256"] = frozen_sha256
    return provenance


def run_condition(
    *,
    config: RuntimeConfig,
    condition: str,
    run_id: str,
    run_dir: Path,
    ansatz: Any,
    circuits: Sequence[Any],
    frozen_sha256: str,
    make_sampler: Callable[[], Any],
    ledger: QpuLedger,
    calibration: Callable[[], Any],
) -> dict[str, Any]:
    if condition not in CONDITIONS:
        raise ValueError(f"unknown condition {condition!r}")
    verified = condition == "verified"
    run_dir.mkdir(parents=True, exist_ok=False)
    trace_path = run_dir / "trace.jsonl"
    evidence_path = run_dir / "evidence.jsonl"
    online_path = run_dir / "online_report.json"
    replay_path = run_dir / "replay_report.json"
    jobs_log = (run_dir / "jobs.log").open("a", encoding="utf-8")
    calibration_before = calibration()

    evaluations: list[dict[str, Any]] = []
    recording: _RecordingMonitor | None = None
    session: RuntimeSession | None = None
    evidence: EvidenceJournal | None = None
    provenance: dict[str, Any] = {}
    circuit_hashes: tuple[str, ...] = ()
    report = None
    terminal_reason = "error"
    status = "error"
    failure: str | None = None

    total_started = time.perf_counter()
    started_utc = _utc_now()
    sampler = make_sampler()
    optimizer = _optimizer(config)
    theta = _initial_theta(config)
    if verified:
        circuit_hashes = tuple(_qpy_digest(circuit) for circuit in circuits)
        provenance = _provenance(config, ansatz, circuits, circuit_hashes, theta, frozen_sha256)
        recording = _RecordingMonitor(config)
        evidence = EvidenceJournal(
            evidence_path, run_id=run_id, config_hash=config.digest, durable=True, overwrite=False
        )
        session = RuntimeSession(
            config,
            run_id=run_id,
            trace_path=trace_path,
            report_path=online_path,
            monitor=recording.monitor,
            execution_provenance=provenance,
            durable=True,
            overwrite=False,
        )
    setup_seconds = time.perf_counter() - total_started

    previous_energy: float | None = None
    stable_count = 0
    finalize_seconds = 0.0
    try:
        for evaluation in range(config.max_iterations):
            evaluation_started = time.perf_counter()
            ledger.require_room()
            if session is not None:
                session.begin_iteration(theta, evaluation_id=f"eval{evaluation}")
                session.bind_parameters()
                session.authorize_job(
                    f"submission{evaluation}",
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
            started = time.perf_counter()
            job = sampler.run(pubs, shots=config.shots_per_term)
            submit_seconds = time.perf_counter() - started
            external_job_id = _job_id(job, f"localSamplerJob{evaluation}")
            jobs_log.write(external_job_id + "\n")
            jobs_log.flush()
            if session is not None:
                session.mark_job_submitted(external_job_id)
            started = time.perf_counter()
            result = job.result()
            result_wait_seconds = time.perf_counter() - started
            retrieved_at = _utc_now()
            if len(result) != len(config.hamiltonian.terms):
                raise RuntimeError(f"Sampler returned {len(result)} PUB results")
            started = time.perf_counter()
            job_metadata = _call_metadata(job)
            metadata_seconds = time.perf_counter() - started
            ledger.record(run_id, external_job_id, job_metadata)
            primitive_metadata = _json_safe(getattr(result, "metadata", None))

            expectations: list[float] = []
            term_records: list[dict[str, Any]] = []
            retained: list[Any] = []
            for pub_index, (term, circuit, pub_result) in enumerate(
                zip(config.hamiltonian.terms, circuits, result)
            ):
                if session is not None and evidence is not None:
                    raw_record = evidence_from_pub_result(
                        pub_result,
                        term_id=term.term_id,
                        pauli=term.pauli,
                        requested_shots=config.shots_per_term,
                    )
                    identity = _identity(
                        config=config,
                        provenance=provenance,
                        circuit=circuit,
                        circuit_hash=circuit_hashes[pub_index],
                        theta=theta,
                        evaluation=evaluation,
                        pub_index=pub_index,
                        external_job_id=external_job_id,
                        submitted_at=submitted_at,
                        retrieved_at=retrieved_at,
                        job_metadata=job_metadata,
                        primitive_metadata=primitive_metadata,
                        pub_metadata=getattr(pub_result, "metadata", None),
                        raw_record=raw_record,
                    )
                    archived = evidence.append_pub(raw_record, identity=identity)
                    expectation = float(archived["expectation"])
                    negative = int(archived["negative_eigenvalue_count"])
                    counts = {str(k): int(v) for k, v in archived["counts"].items()}
                    session.observe_term(
                        TermObservation(
                            term.term_id,
                            expectation,
                            int(archived["observed_shots"]),
                            negative,
                            negative_eigenvalue_count=negative,
                            pub_index=pub_index,
                            raw_evidence_sha256=archived["raw_evidence_sha256"],
                            executable_circuit_qpy_sha256=identity[
                                "executable_circuit_qpy_sha256"
                            ],
                        )
                    )
                else:
                    bit_array = extract_bit_array(pub_result)
                    counts = {str(k): int(v) for k, v in bit_array.get_counts().items()}
                    negative = negative_eigenvalue_count(counts, term.pauli)
                    expectation = expectation_from_negative_count(
                        negative, int(bit_array.num_shots)
                    )
                    # Full raw evidence is built after the timing boundary.
                    retained.append(pub_result)
                expectations.append(expectation)
                term_records.append(
                    {"pauli": term.pauli, "counts": counts, "expectation": expectation}
                )

            if session is not None:
                session.seal_measurements()
            energy = math.fsum(
                term.coeff_int * expectation / config.hamiltonian.coeff_scale
                for term, expectation in zip(config.hamiltonian.terms, expectations)
            )
            if session is not None:
                session.aggregate_energy(energy)
                converged = session.check_convergence()
                active = session.contracts.active
                if active is None:
                    raise RuntimeError("verified convergence check lost the evaluation")
                delta = float(active.energy_delta or 0.0)
                stable_count = active.stable_count
                released = session.authorize_objective_release()
            else:
                converged, delta, stable_count = _convergence(
                    config,
                    evaluation=evaluation,
                    energy=energy,
                    previous_energy=previous_energy,
                    previous_stable_count=stable_count,
                )
                released = energy

            if not converged and evaluation + 1 < config.max_iterations:
                next_theta, token = optimizer.preview_update(theta, released)
                if session is not None:
                    session.authorize_and_commit_optimizer_update(optimizer, token, next_theta)
                else:
                    optimizer.commit_update(token, authorized_theta=next_theta)
            else:
                next_theta = theta
            if session is not None:
                session.close_iteration()

            evaluation_seconds = time.perf_counter() - evaluation_started
            evaluations.append(
                {
                    "evaluation": evaluation,
                    "external_job_id": external_job_id,
                    "theta": list(theta),
                    "energy": energy,
                    "energy_delta": delta,
                    "stable_count": stable_count,
                    "converged": converged,
                    "terms": term_records,
                    "evaluation_seconds": evaluation_seconds,
                    "submit_seconds": submit_seconds,
                    "result_wait_seconds": result_wait_seconds,
                    "metadata_seconds": metadata_seconds,
                    "client_seconds": evaluation_seconds
                    - submit_seconds
                    - result_wait_seconds
                    - metadata_seconds,
                    "submitted_at_utc": submitted_at,
                    "retrieved_at_utc": retrieved_at,
                    "job_metadata": job_metadata,
                    "_retained": retained,
                    "_primitive_metadata": primitive_metadata,
                }
            )
            previous_energy = energy
            theta = tuple(next_theta)
            if converged:
                terminal_reason = "converged"
                break
        else:
            terminal_reason = "max_iterations"

        started = time.perf_counter()
        if session is not None and evidence is not None:
            session.finish(
                TerminationReason.CONVERGED
                if terminal_reason == "converged"
                else TerminationReason.MAX_ITERATIONS
            )
            evidence.seal()
            session.report.mark_checked(
                "run_raw_evidence_complete",
                "run_physical_shot_budget",
                "run_execution_options",
            )
            report = session.seal_run()
            status = report.status.value
        else:
            status = "completed"
        finalize_seconds = time.perf_counter() - started
    except Exception as exc:  # Keep whatever was paid for; the caller stops the campaign.
        failure = f"{type(exc).__name__}: {exc}"
        terminal_reason = "aborted"
        if session is not None:
            session.abort(
                "verificationAbort"
                if isinstance(exc, VerificationAbort)
                else "optimizerOrBackendFailure"
            )
            if session.report.terminal_reason is not None and not session.report.complete:
                try:
                    if evidence is not None and not evidence.sealed:
                        evidence.seal()
                finally:
                    report = session.seal_run()
                    status = report.status.value
    finally:
        if evidence is not None:
            evidence.close()
        if session is not None:
            session.close()
        jobs_log.close()
    total_seconds = time.perf_counter() - total_started

    # Everything below is outside the timing boundary.
    if not verified and evaluations:
        hashes = tuple(_qpy_digest(circuit) for circuit in circuits)
        provenance = _provenance(config, ansatz, circuits, hashes, _initial_theta(config), frozen_sha256)
        with EvidenceJournal(
            evidence_path, run_id=run_id, config_hash=config.digest, durable=True, overwrite=False
        ) as journal:
            for row in evaluations:
                for pub_index, (term, circuit, pub_result) in enumerate(
                    zip(config.hamiltonian.terms, circuits, row["_retained"])
                ):
                    raw_record = evidence_from_pub_result(
                        pub_result,
                        term_id=term.term_id,
                        pauli=term.pauli,
                        requested_shots=config.shots_per_term,
                    )
                    journal.append_pub(
                        raw_record,
                        identity=_identity(
                            config=config,
                            provenance=provenance,
                            circuit=circuit,
                            circuit_hash=hashes[pub_index],
                            theta=row["theta"],
                            evaluation=row["evaluation"],
                            pub_index=pub_index,
                            external_job_id=row["external_job_id"],
                            submitted_at=row["submitted_at_utc"],
                            retrieved_at=row["retrieved_at_utc"],
                            job_metadata=row["job_metadata"],
                            primitive_metadata=row["_primitive_metadata"],
                            pub_metadata=getattr(pub_result, "metadata", None),
                            raw_record=raw_record,
                        ),
                    )
            journal.seal()

    replay_status = None
    if recording is not None:
        _write_jsonl(run_dir / "monitor_acks_online.jsonl", recording.rows)
        recording.monitor.close()
        replaying = _RecordingMonitor(config)
        try:
            replay = check_trace(
                config,
                trace_path,
                evidence_path=evidence_path,
                report_path=replay_path,
                monitor=replaying.monitor,
            )
            replay_status = replay.status.value
        finally:
            replaying.monitor.close()
        _write_jsonl(run_dir / "monitor_acks_replay.jsonl", replaying.rows)

    _write_jsonl(
        run_dir / "evaluations.jsonl",
        [{k: v for k, v in row.items() if not k.startswith("_")} for row in evaluations],
    )
    summary = {
        "run_id": run_id,
        "condition": condition,
        "backend": config.backend,
        "su2_gates": list(SU2_GATES),
        "frozen_circuits_sha256": frozen_sha256,
        "config_hash": config.digest,
        "started_utc": started_utc,
        "finished_utc": _utc_now(),
        "calibration_before": calibration_before,
        "calibration_after": calibration(),
        "status": status,
        "failure": failure,
        "replay_status": replay_status,
        "terminal_reason": terminal_reason,
        "completed_evaluations": len(evaluations),
        "setup_seconds": setup_seconds,
        "finalize_seconds": finalize_seconds,
        "total_seconds": total_seconds,
        "ibm_seconds": math.fsum(
            row["submit_seconds"] + row["result_wait_seconds"] + row["metadata_seconds"]
            for row in evaluations
        ),
    }
    (run_dir / "run.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    if failure is not None:
        raise RunFailed(f"{run_id}: {failure}")
    return summary


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def load_run(run_dir: Path) -> dict[str, Any]:
    return {
        **json.loads((run_dir / "run.json").read_text()),
        "evaluations": _read_jsonl(run_dir / "evaluations.jsonl"),
    }


def add_fidelities(run: dict[str, Any], logical: Sequence[Any]) -> None:
    for row in run["evaluations"]:
        row["fidelity"] = statistics.fmean(
            classical_distribution_fidelity(
                _ideal_probabilities(circuit, row["theta"]), term["counts"]
            )
            for circuit, term in zip(logical, row["terms"])
        )


def cumulative_at(run: Mapping[str, Any], bound: int) -> dict[str, Any]:
    """Cumulative values through ``bound``, held at the last value after an early stop."""

    rows = run["evaluations"][:bound]
    if not rows:
        raise ValueError(f"{run['run_id']} has no evaluations")
    edge = run["setup_seconds"] + run["finalize_seconds"]
    return {
        "evaluations_used": len(rows),
        "held": len(rows) < bound,
        "mean_fidelity": statistics.fmean(row["fidelity"] for row in rows),
        "cumulative_infidelity": math.fsum(1.0 - row["fidelity"] for row in rows),
        "client_seconds": edge + math.fsum(row["client_seconds"] for row in rows),
        "elapsed_seconds": edge + math.fsum(row["evaluation_seconds"] for row in rows),
        "ibm_seconds": math.fsum(
            row["submit_seconds"] + row["result_wait_seconds"] + row["metadata_seconds"]
            for row in rows
        ),
    }


def pair_rows(
    unverified: Mapping[str, Any], verified: Mapping[str, Any], bounds: Sequence[int] = BOUNDS
) -> list[dict[str, Any]]:
    rows = []
    for bound in bounds:
        u = cumulative_at(unverified, bound)
        v = cumulative_at(verified, bound)
        rows.append(
            {
                "bound": bound,
                "unverified": u,
                "verified": v,
                "fidelity_change": v["mean_fidelity"] - u["mean_fidelity"],
                "added_seconds": v["client_seconds"] - u["client_seconds"],
                "elapsed_difference_seconds": v["elapsed_seconds"] - u["elapsed_seconds"],
            }
        )
    return rows


def energy_summary(run: Mapping[str, Any], config: RuntimeConfig, ansatz: Any) -> dict[str, Any]:
    import numpy as np
    from qiskit.quantum_info import SparsePauliOp, Statevector

    hamiltonian = SparsePauliOp.from_list(
        [
            (term.pauli, term.coeff_int / config.hamiltonian.coeff_scale)
            for term in config.hamiltonian.terms
        ]
    )
    reference = float(np.linalg.eigvalsh(hamiltonian.to_matrix())[0])

    def exact(theta: Sequence[float]) -> float:
        state = Statevector.from_instruction(ansatz.assign_parameters(list(theta)))
        return float(np.real(state.expectation_value(hamiltonian)))

    rows = run["evaluations"]
    best = min(rows, key=lambda row: row["energy"])
    final = exact(rows[-1]["theta"])
    return {
        "reference_energy": reference,
        "first_measured": rows[0]["energy"],
        "best_measured": best["energy"],
        "best_measured_evaluation": best["evaluation"] + 1,
        "exact_at_best_measured": exact(best["theta"]),
        "final_measured": rows[-1]["energy"],
        "exact_at_final": final,
        "final_gap": final - reference,
        "measured_trajectory": [row["energy"] for row in rows],
    }


def property_report(run_dir: Path) -> dict[str, Any]:
    """Each DejaVu property's verdict on every event, with what actually triggered it."""

    properties = property_coverage.parse_spec()
    counts, execution = property_coverage.load_trace(run_dir / "trace.jsonl")
    coverage = property_coverage.classify(properties, counts, execution)
    online = _read_jsonl(run_dir / "monitor_acks_online.jsonl")
    replay = _read_jsonl(run_dir / "monitor_acks_replay.jsonl")

    def violations(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        found: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            for name in row["violations"]:
                found.setdefault(name, []).append({"seq": row["seq"], "event": row["event"]})
        return found

    online_found = violations(online)
    replay_found = violations(replay)
    rows = []
    for name, item in coverage.items():
        rows.append(
            {
                "property": name,
                "level": name.split("_", 1)[0],
                "online": "VIOLATED" if name in online_found else "OBEYED",
                "replay": "VIOLATED" if name in replay_found else "OBEYED",
                "violated_at_online": online_found.get(name, []),
                "violated_at_replay": replay_found.get(name, []),
                "coverage": item["status"],
                "trigger_events": sum(item["trigger_counts"].values()),
                "unfired_triggers": item["unfired_triggers"],
            }
        )
    unknown = (set(online_found) | set(replay_found)) - set(coverage)
    report = {
        "properties": len(rows),
        "events_online": len(online),
        "events_replay": len(replay),
        "events_rejected_online": sum(not row["passed"] for row in online),
        "events_rejected_replay": sum(not row["passed"] for row in replay),
        "obeyed_online": sum(row["online"] == "OBEYED" for row in rows),
        "violated_online": sum(row["online"] == "VIOLATED" for row in rows),
        "obeyed_replay": sum(row["replay"] == "OBEYED" for row in rows),
        "violated_replay": sum(row["replay"] == "VIOLATED" for row in rows),
        "violations_outside_spec": sorted(unknown),
        "coverage": {
            status: sum(row["coverage"] == status for row in rows)
            for status in (
                "EXERCISED",
                "NOT_APPLICABLE",
                "NOT_EXERCISED",
                "NESTED_NOT_EXERCISED",
            )
        },
        "monitor_latency_median_seconds": statistics.median(
            row["latency_seconds"] for row in online
        )
        if online
        else None,
        "rows": rows,
    }
    for name, path in (("online", "online_report.json"), ("replay", "replay_report.json")):
        document = json.loads((run_dir / path).read_text())
        report[f"{name}_status"] = document["status"]
        report[f"{name}_levels"] = document["levels"]
        report[f"{name}_contract_count"] = document["metrics"]["recorded_contract_count"]
    return report


def property_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# DejaVu property verdicts for the verified run",
        "",
        f"- Events checked: {report['events_online']} online, {report['events_replay']} in replay.",
        f"- Events rejected: {report['events_rejected_online']} online, "
        f"{report['events_rejected_replay']} in replay.",
        f"- Properties obeyed: {report['obeyed_online']}/{report['properties']} online, "
        f"{report['obeyed_replay']}/{report['properties']} in replay.",
        f"- Properties violated: {report['violated_online']} online, "
        f"{report['violated_replay']} in replay.",
        f"- Overall status: {report['online_status']} online, {report['replay_status']} in replay.",
        "- Coverage: "
        + ", ".join(f"{count} {status}" for status, count in report["coverage"].items())
        + ".",
        "",
        "`OBEYED` on a property that is not `EXERCISED` is vacuous: its trigger never occurred "
        "or cannot occur under this configuration.",
        "",
        "| Level | Status online | Status replay | Findings online | Findings replay |",
        "|---|---|---|---:|---:|",
    ]
    for level in ("intra_iteration", "inter_iteration", "run_level"):
        online = report["online_levels"][level]
        replay = report["replay_levels"][level]
        lines.append(
            f"| {level} | {online['status']} | {replay['status']} | "
            f"{len(online['findings'])} | {len(replay['findings'])} |"
        )
    lines += [
        "",
        "| Property | Online | Replay | Coverage | Trigger events | Violated at (online) |",
        "|---|---|---|---|---:|---|",
    ]
    order = {"VIOLATED": 0, "OBEYED": 1}
    for row in sorted(
        report["rows"], key=lambda r: (order[r["online"]], r["level"], r["property"])
    ):
        where = ", ".join(f"seq {v['seq']} {v['event']}" for v in row["violated_at_online"])
        lines.append(
            f"| `{row['property']}` | {row['online']} | {row['replay']} | {row['coverage']} | "
            f"{row['trigger_events']} | {where} |"
        )
    return "\n".join(lines) + "\n"


def pair_markdown(result: Mapping[str, Any]) -> str:
    u, v = result["unverified"], result["verified"]
    lines = [
        f"# Hardware pair `{result['pair_id']}`: unverified vs verified",
        "",
        f"- Backend `{result['backend']}`, qubits {result['logical_to_physical']}, "
        f"frozen circuits `{result['frozen_sha256'][:16]}`.",
        f"- Order: {' then '.join(result['order'])}.",
        f"- Unverified: {u['completed_evaluations']} evaluations, stop `{u['terminal_reason']}`, "
        f"status `{u['status']}`.",
        f"- Verified: {v['completed_evaluations']} evaluations, stop `{v['terminal_reason']}`, "
        f"online `{v['status']}`, replay `{v['replay_status']}`.",
        f"- Charged QPU: {result['charged_seconds']['unverified']:.0f} s + "
        f"{result['charged_seconds']['verified']:.0f} s.",
        "",
        "| N | Fidelity U | Fidelity V | Change (V-U) | Added client time (s) | Elapsed diff (s) | Held |",
        "|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in result["rows"]:
        held = "/".join(
            name
            for name, side in (("U", row["unverified"]), ("V", row["verified"]))
            if side["held"]
        )
        lines.append(
            f"| {row['bound']} | {row['unverified']['mean_fidelity']:.6f} | "
            f"{row['verified']['mean_fidelity']:.6f} | {row['fidelity_change']:+.6f} | "
            f"{row['added_seconds']:.3f} | {row['elapsed_difference_seconds']:+.1f} | {held} |"
        )
    lines += [
        "",
        "| Run | Client (s) | IBM wait (s) | Total (s) | Best measured | Exact at final | Gap to E_ref |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, run, energy in (
        ("Unverified", u, result["energy"]["unverified"]),
        ("Verified", v, result["energy"]["verified"]),
    ):
        lines.append(
            f"| {name} | {run['total_seconds'] - run['ibm_seconds']:.3f} | {run['ibm_seconds']:.1f} | "
            f"{run['total_seconds']:.1f} | {energy['best_measured']:.4f} | "
            f"{energy['exact_at_final']:.4f} | {energy['final_gap']:.4f} |"
        )
    return "\n".join(lines) + "\n"


def analyze_pair(
    *,
    config: RuntimeConfig,
    ansatz: Any,
    logical: Sequence[Any],
    pair_dir: Path,
    frozen_manifest: Mapping[str, Any],
    order: Sequence[str],
) -> dict[str, Any]:
    runs = {name: load_run(pair_dir / name) for name in CONDITIONS}
    for run in runs.values():
        add_fidelities(run, logical)
    ledger_path = pair_dir.parent / "qpu_ledger.json"
    jobs = json.loads(ledger_path.read_text()) if ledger_path.exists() else []
    result = {
        "pair_id": pair_dir.name,
        "backend": config.backend,
        "su2_gates": list(SU2_GATES),
        "logical_to_physical": frozen_manifest["logical_to_physical"],
        "frozen_sha256": frozen_manifest["sha256"],
        "order": list(order),
        "unverified": {k: w for k, w in runs["unverified"].items() if k != "evaluations"},
        "verified": {k: w for k, w in runs["verified"].items() if k != "evaluations"},
        "rows": pair_rows(runs["unverified"], runs["verified"]),
        "fidelity_by_evaluation": {
            name: [row["fidelity"] for row in run["evaluations"]] for name, run in runs.items()
        },
        "energy": {name: energy_summary(run, config, ansatz) for name, run in runs.items()},
        "charged_seconds": {
            name: math.fsum(
                job["charged_seconds"] for job in jobs if job["run_id"] == runs[name]["run_id"]
            )
            for name in CONDITIONS
        },
    }
    (pair_dir / "pair_report.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    (pair_dir / "pair_report.md").write_text(pair_markdown(result))
    properties = property_report(pair_dir / "verified")
    (pair_dir / "property_report.json").write_text(
        json.dumps(properties, indent=2, sort_keys=True) + "\n"
    )
    (pair_dir / "property_report.md").write_text(property_markdown(properties))
    return result


def monitor_rejections(events: Sequence[Any], config: RuntimeConfig) -> list[dict[str, Any]]:
    """Submit events to a fresh monitor and return every rejection."""

    recording = _RecordingMonitor(config)
    try:
        for event in events:
            recording.monitor.submit(event)
    finally:
        recording.monitor.close()
    return [row for row in recording.rows if not row["passed"]]


class _LocalJob:
    def __init__(self, result: Any, job_id: str) -> None:
        self._result = result
        self._job_id = job_id

    def job_id(self) -> str:
        return self._job_id

    def result(self) -> Any:
        return self._result

    def metrics(self) -> dict[str, Any]:
        return {"usage": {"seconds": 0, "quantum_seconds": 0.0}}


class LocalHardwareStandIn:
    """Answer compiled PUBs from their logical circuits; never contacts IBM."""

    def __init__(self, compiled: Sequence[Any], logical: Sequence[Any], seed: int) -> None:
        import numpy as np
        from qiskit.primitives import StatevectorSampler

        self._logical = {id(c): l for c, l in zip(compiled, logical)}
        self._sampler = StatevectorSampler(seed=np.random.default_rng(seed))
        self._jobs = 0

    def run(self, pubs: Sequence[Any], shots: int) -> _LocalJob:
        mapped = [(self._logical[id(circuit)], theta) for circuit, theta in pubs]
        self._jobs += 1
        return _LocalJob(self._sampler.run(mapped, shots=shots).result(), f"local{self._jobs}")


class _FailingStandIn(LocalHardwareStandIn):
    def __init__(self, compiled: Sequence[Any], logical: Sequence[Any], seed: int, *, fail_at_job: int) -> None:
        super().__init__(compiled, logical, seed)
        self._fail_at_job = fail_at_job

    def run(self, pubs: Sequence[Any], shots: int) -> _LocalJob:
        if self._jobs + 1 == self._fail_at_job:
            raise RuntimeError("injected job failure")
        return super().run(pubs, shots)


def command_local_test(args: argparse.Namespace) -> int:
    from qiskit_ibm_runtime.fake_provider import FakeMarrakesh

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=False)
    config = load_config(PAIR_CONFIG)
    ansatz, logical = build_ansatz(config)
    compiled = compile_circuits(config, ansatz, logical, FakeMarrakesh().target)
    error = compiled_equivalence_error(compiled, logical)
    if error > EQUIVALENCE_TOLERANCE:
        raise RuntimeError(f"compiled circuits differ from the ansatz: {error}")
    print(f"compiled equivalence error {error:.2e}", flush=True)
    freeze_circuits(
        out_dir,
        compiled,
        {"backend": "fake_marrakesh (local test)", "transpiler_seed": config.seed,
         "equivalence_error": error},
    )
    circuits, manifest = load_frozen(out_dir)
    print(f"frozen layout {manifest['logical_to_physical']}", flush=True)
    ledger = QpuLedger(out_dir / "qpu_ledger.json", cap_seconds=10.0)
    pair_dir = out_dir / "pair00"
    for index, condition in enumerate(CONDITIONS):
        summary = run_condition(
            config=config,
            condition=condition,
            run_id=f"hrzy-local-pair00-{condition}",
            run_dir=pair_dir / condition,
            ansatz=ansatz,
            circuits=circuits,
            frozen_sha256=manifest["sha256"],
            make_sampler=lambda: LocalHardwareStandIn(circuits, logical, 100 + index),
            ledger=ledger,
            calibration=lambda: None,
        )
        print(
            f"{condition}: {summary['completed_evaluations']} evaluations, "
            f"{summary['terminal_reason']}, status {summary['status']}, "
            f"replay {summary['replay_status']}",
            flush=True,
        )
    analyze_pair(
        config=config,
        ansatz=ansatz,
        logical=logical,
        pair_dir=pair_dir,
        frozen_manifest=manifest,
        order=CONDITIONS,
    )
    events, errors = load_events(pair_dir / "verified/trace.jsonl")
    if errors:
        raise RuntimeError(f"trace errors: {errors}")
    kept = [event for event in events if event.name != "parametersBound"]
    tampered = [replace(event, seq=events[0].seq + i) for i, event in enumerate(kept)]
    rejected = monitor_rejections(tampered, config)
    names = sorted({name for row in rejected for name in row["violations"]})
    print(f"negative control: {len(rejected)} events rejected; properties {names}", flush=True)
    if not rejected:
        raise RuntimeError("negative control: the monitor accepted a trace with no bindings")
    (out_dir / "negative_control.json").write_text(
        json.dumps({"removed_event": "parametersBound", "rejected_events": len(rejected),
                    "properties": names}, indent=2) + "\n"
    )

    # The early-stop path: a wide tolerance makes both runs stop at min_iterations.
    early_config = replace(config, convergence_tolerance=1.0)
    early_dir = out_dir / "pair_early_stop"
    for index, condition in enumerate(CONDITIONS):
        run_condition(
            config=early_config,
            condition=condition,
            run_id=f"hrzy-local-early-{condition}",
            run_dir=early_dir / condition,
            ansatz=ansatz,
            circuits=circuits,
            frozen_sha256=manifest["sha256"],
            make_sampler=lambda: LocalHardwareStandIn(circuits, logical, 200 + index),
            ledger=ledger,
            calibration=lambda: None,
        )
    early = analyze_pair(
        config=early_config,
        ansatz=ansatz,
        logical=logical,
        pair_dir=early_dir,
        frozen_manifest=manifest,
        order=CONDITIONS,
    )
    stopped = {name: early[name]["completed_evaluations"] for name in CONDITIONS}
    reasons = {name: early[name]["terminal_reason"] for name in CONDITIONS}
    last = early["rows"][-1]
    if set(reasons.values()) != {"converged"} or not (
        last["unverified"]["held"] and last["verified"]["held"]
    ):
        raise RuntimeError(f"early-stop path did not hold values: {reasons}, {stopped}")
    print(
        f"early stop: {stopped}; verified online {early['verified']['status']}, "
        f"replay {early['verified']['replay_status']}; values held at N=50",
        flush=True,
    )

    # The failure path: a job failure keeps paid results and stops the campaign.
    failed_dir = out_dir / "pair_job_failure"
    for condition in CONDITIONS:
        try:
            run_condition(
                config=config,
                condition=condition,
                run_id=f"hrzy-local-failure-{condition}",
                run_dir=failed_dir / condition,
                ansatz=ansatz,
                circuits=circuits,
                frozen_sha256=manifest["sha256"],
                make_sampler=lambda: _FailingStandIn(circuits, logical, 300, fail_at_job=4),
                ledger=ledger,
                calibration=lambda: None,
            )
        except RunFailed as exc:
            kept = json.loads((failed_dir / condition / "run.json").read_text())
            records = len(_read_jsonl(failed_dir / condition / "evidence.jsonl"))
            print(
                f"job failure, {condition}: {exc}; kept {kept['completed_evaluations']} "
                f"evaluations and {records} evidence records; status {kept['status']}",
                flush=True,
            )
        else:
            raise RuntimeError("failure path: a failed job did not stop the run")
    print((pair_dir / "pair_report.md").read_text(), flush=True)
    return 0


def _calibration_stamp(backend: Any) -> Callable[[], Any]:
    def stamp() -> Any:
        try:
            return str(backend.properties(refresh=True).last_update_date)
        except Exception as exc:
            return f"unavailable: {type(exc).__name__}"

    return stamp


def command_check(args: argparse.Namespace) -> int:
    """Read-only IBM check: no job is submitted here."""

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    config = load_config(PAIR_CONFIG)
    service, backend = _resolve_runtime_backend(config)
    status = backend.status()
    try:
        usage = _json_safe(service.usage())
    except Exception as exc:
        usage = {"unavailable": f"{type(exc).__name__}: {exc}"}
    ansatz, logical = build_ansatz(config)
    compiled = compile_circuits(config, ansatz, logical, backend.target)
    error = compiled_equivalence_error(compiled, logical)
    if error > EQUIVALENCE_TOLERANCE:
        raise RuntimeError(f"compiled circuits differ from the ansatz: {error}")
    freeze_circuits(
        out_dir,
        compiled,
        {
            "backend": backend.name,
            "transpiler_seed": config.seed,
            "equivalence_error": error,
            "calibration": _calibration_stamp(backend)(),
            "frozen_utc": _utc_now(),
        },
    )
    _, manifest = load_frozen(out_dir)
    check = {
        "backend": backend.name,
        "operational": bool(status.operational),
        "pending_jobs": int(status.pending_jobs),
        "status_message": str(status.status_msg),
        "usage": usage,
        "manifest": manifest,
    }
    (out_dir / "ibm_check.json").write_text(json.dumps(check, indent=2, sort_keys=True) + "\n")
    print(json.dumps(check, indent=2, sort_keys=True), flush=True)
    return 0


def _require_submit(args: argparse.Namespace) -> None:
    if not args.submit:
        raise SystemExit("refusing to submit IBM jobs without --submit")


def command_preflight(args: argparse.Namespace) -> int:
    _require_submit(args)
    out_dir: Path = args.out_dir
    config = load_config(PREFLIGHT_CONFIG)
    service, backend = _resolve_runtime_backend(config)
    ansatz, logical = build_ansatz(config)
    circuits, manifest = load_frozen(out_dir)
    ledger = QpuLedger(out_dir / "qpu_ledger.json", cap_seconds=args.qpu_cap)
    for condition in CONDITIONS:
        summary = run_condition(
            config=config,
            condition=condition,
            run_id=f"hrzy-preflight-{condition}",
            run_dir=out_dir / "preflight" / condition,
            ansatz=ansatz,
            circuits=circuits,
            frozen_sha256=manifest["sha256"],
            make_sampler=lambda: _make_sampler(config, runtime_backend=backend),
            ledger=ledger,
            calibration=_calibration_stamp(backend),
        )
        print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    print(f"charged so far: {ledger.charged_seconds:.0f} s", flush=True)
    return 0


def command_pair(args: argparse.Namespace) -> int:
    _require_submit(args)
    out_dir: Path = args.out_dir
    config = load_config(PAIR_CONFIG)
    service, backend = _resolve_runtime_backend(config)
    ansatz, logical = build_ansatz(config)
    circuits, manifest = load_frozen(out_dir)
    ledger = QpuLedger(out_dir / "qpu_ledger.json", cap_seconds=args.qpu_cap)
    pair_dir = out_dir / args.pair_id
    order = tuple(args.order.split(","))
    if sorted(order) != sorted(CONDITIONS):
        raise SystemExit(f"--order must name each of {CONDITIONS}")
    for condition in order:
        summary = run_condition(
            config=config,
            condition=condition,
            run_id=f"hrzy-{args.pair_id}-{condition}",
            run_dir=pair_dir / condition,
            ansatz=ansatz,
            circuits=circuits,
            frozen_sha256=manifest["sha256"],
            make_sampler=lambda: _make_sampler(config, runtime_backend=backend),
            ledger=ledger,
            calibration=_calibration_stamp(backend),
        )
        print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    analyze_pair(
        config=config,
        ansatz=ansatz,
        logical=logical,
        pair_dir=pair_dir,
        frozen_manifest=manifest,
        order=order,
    )
    print((pair_dir / "pair_report.md").read_text(), flush=True)
    print(f"charged so far: {ledger.charged_seconds:.0f} s", flush=True)
    return 0


def command_analyze(args: argparse.Namespace) -> int:
    out_dir: Path = args.out_dir
    config = load_config(PAIR_CONFIG)
    ansatz, logical = build_ansatz(config)
    _, manifest = load_frozen(out_dir)
    analyze_pair(
        config=config,
        ansatz=ansatz,
        logical=logical,
        pair_dir=out_dir / args.pair_id,
        frozen_manifest=manifest,
        order=tuple(args.order.split(",")),
    )
    print((out_dir / args.pair_id / "pair_report.md").read_text(), flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    for name, handler in (
        ("local-test", command_local_test),
        ("check", command_check),
        ("preflight", command_preflight),
        ("pair", command_pair),
        ("analyze", command_analyze),
    ):
        command = commands.add_parser(name)
        command.add_argument("--out-dir", type=Path, required=True)
        command.set_defaults(handler=handler)
        if name in {"preflight", "pair"}:
            command.add_argument("--submit", action="store_true")
            command.add_argument("--qpu-cap", type=float, required=True)
        if name in {"pair", "analyze"}:
            command.add_argument("--pair-id", required=True)
            command.add_argument("--order", default="unverified,verified")
    args = parser.parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
