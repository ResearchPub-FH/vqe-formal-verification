#!/usr/bin/env python3
"""Compare sampled H2 VQE execution with and without runtime verification.

The experiment is simulator-only.  It runs the same four-PUB H2 workload at
10, 20, 30, 40, and 50 evaluations in two conditions:

* ``baseline`` executes the sampler, energy calculation, convergence policy,
  and ask/tell optimizer without RuntimeSession or DejaVu;
* ``verified`` adds the complete RuntimeSession, synchronous DejaVu monitor,
  online contract checks, event trace, and linked evidence archive.

Every run is retained.  Baseline evidence and fidelity analysis are written
after the timing boundary so the baseline measures the VQE workload itself.
Verified trace/evidence persistence is inside the timing boundary because it is
part of the verification layer being evaluated.  Offline replay and fidelity
analysis are outside both timing boundaries.

The fidelity reported here is classical measurement-distribution fidelity:
for each PUB, its sampled bitstring distribution is compared with the exact
statevector distribution of the same bound measurement circuit.  It is not a
tomographic quantum-state fidelity.
"""

from __future__ import annotations

import argparse
from base64 import b64decode
import csv
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import random
import resource
import statistics
import subprocess
import sys
import time
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from vqe_runtime.checker import check_trace  # noqa: E402
from vqe_runtime.config import RuntimeConfig, load_config, vector_digest  # noqa: E402
from vqe_runtime.dejavu import MonitorAck, SynchronousDejaVu  # noqa: E402
from vqe_runtime.evidence import EvidenceJournal  # noqa: E402
from vqe_runtime.events import RuntimeEvent  # noqa: E402
from vqe_runtime.optimizer import AskTellPatternSearch  # noqa: E402
from vqe_runtime.sampler_runner import (  # noqa: E402
    _call_metadata,
    _job_id,
    _json_safe,
    _layout_record,
    _make_circuits,
    _make_sampler,
    _qpy_digest,
    _sampler_experiment_provenance,
    _utc_now,
)
from vqe_runtime.sampling import (  # noqa: E402
    classical_distribution_fidelity,
    evidence_from_pub_result,
    expectation_from_negative_count,
    extract_bit_array,
    negative_eigenvalue_count,
)
from vqe_runtime.session import RuntimeSession, TermObservation, TerminationReason  # noqa: E402


CONDITIONS = ("baseline", "verified")
DEFAULT_SCALES = (10, 20, 30, 40, 50)
RUN_FIELDS = (
    "phase",
    "condition",
    "evaluations",
    "repetition",
    "run_id",
    "seed",
    "status",
    "terminal_reason",
    "completed_evaluations",
    "first_convergence_candidate_evaluation",
    "time_to_first_convergence_candidate_seconds",
    "final_energy",
    "total_seconds",
    "python_cpu_seconds",
    "setup_seconds",
    "loop_seconds",
    "finalize_seconds",
    "artifact_write_seconds",
    "replay_seconds",
    "mean_measurement_fidelity",
    "mean_measurement_infidelity",
    "cumulative_measurement_infidelity",
    "max_measurement_infidelity",
    "peak_python_rss_bytes",
    "peak_jvm_rss_bytes",
    "trace_bytes",
    "evidence_bytes",
    "process_bytes",
)
EVALUATION_FIELDS = (
    "phase",
    "condition",
    "evaluations",
    "repetition",
    "run_id",
    "evaluation",
    "evaluation_id",
    "theta_json",
    "theta_hash",
    "energy",
    "energy_delta",
    "stable_count",
    "converged",
    "convergence_candidate",
    "sampling_seconds",
    "result_processing_seconds",
    "convergence_check_seconds",
    "optimizer_seconds",
    "evaluation_seconds",
    "measurement_fidelity",
    "measurement_infidelity",
    "cumulative_measurement_infidelity",
)
PUB_FIELDS = (
    "phase",
    "condition",
    "evaluations",
    "repetition",
    "run_id",
    "evaluation",
    "term_id",
    "pauli",
    "pub_index",
    "shots",
    "fidelity",
    "infidelity",
    "ideal_probabilities_json",
    "observed_counts_json",
    "raw_evidence_sha256",
)
GATE_FIELDS = (
    "phase",
    "condition",
    "evaluations",
    "repetition",
    "run_id",
    "seq",
    "event",
    "latency_seconds",
)
MEMORY_FIELDS = (
    "phase",
    "condition",
    "evaluations",
    "repetition",
    "run_id",
    "elapsed_seconds",
    "role",
    "pid",
    "rss_bytes",
    "source",
)


def _parse_scales(raw: str) -> tuple[int, ...]:
    values: list[int] = []
    for item in raw.split(","):
        value = int(item.strip())
        if value <= 1:
            raise argparse.ArgumentTypeError("evaluation counts must be greater than one")
        if value not in values:
            values.append(value)
    if not values:
        raise argparse.ArgumentTypeError("at least one evaluation count is required")
    return tuple(sorted(values))


def _percentile(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(item) for item in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _distribution(values: Iterable[float]) -> dict[str, float | int | None]:
    samples = [float(item) for item in values]
    return {
        "count": len(samples),
        "min": min(samples) if samples else None,
        "p50": _percentile(samples, 0.50),
        "p95": _percentile(samples, 0.95),
        "max": max(samples) if samples else None,
        "mean": statistics.fmean(samples) if samples else None,
    }


def _write_csv(path: Path, fields: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fields))
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(
                json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False)
                + "\n"
            )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _command_output(command: Sequence[str]) -> str:
    try:
        completed = subprocess.run(
            list(command), check=False, capture_output=True, text=True
        )
    except OSError as exc:
        return f"unavailable: {exc}"
    return (completed.stdout + completed.stderr).strip()


class _MemorySampler:
    """Record low-interference process peak-memory snapshots.

    ``ru_maxrss`` is used instead of polling ``ps`` so the observer does not
    launch subprocesses throughout the timed execution.  On macOS the value is
    already bytes; other supported Unix platforms report KiB.
    """

    def __init__(self) -> None:
        self.origin = time.perf_counter()
        self.rows: list[dict[str, Any]] = []
        self._jvm_pid: int | None = None

    @staticmethod
    def _rss_bytes(usage: Any) -> int:
        value = int(usage.ru_maxrss)
        return value if platform.system() == "Darwin" else value * 1024

    def _record(self, *, role: str, pid: int, usage: Any, source: str) -> None:
        self.rows.append(
            {
                "elapsed_seconds": time.perf_counter() - self.origin,
                "role": role,
                "pid": pid,
                "rss_bytes": self._rss_bytes(usage),
                "source": source,
            }
        )

    def add_process(self, pid: int, role: str) -> None:
        if role == "dejavu_jvm":
            self._jvm_pid = pid

    def start(self) -> None:
        self._record(
            role="python",
            pid=os.getpid(),
            usage=resource.getrusage(resource.RUSAGE_SELF),
            source="getrusage-self-peak",
        )

    def stop(self) -> list[dict[str, Any]]:
        self._record(
            role="python",
            pid=os.getpid(),
            usage=resource.getrusage(resource.RUSAGE_SELF),
            source="getrusage-self-peak",
        )
        if self._jvm_pid is not None:
            self._record(
                role="dejavu_jvm",
                pid=self._jvm_pid,
                usage=resource.getrusage(resource.RUSAGE_CHILDREN),
                source="getrusage-children-peak-after-jvm-exit",
            )
        return list(self.rows)


def _peak_memory(rows: Sequence[Mapping[str, Any]], role: str) -> int:
    return max(
        (int(row["rss_bytes"]) for row in rows if row["role"] == role),
        default=0,
    )


def _scaled_config(base: RuntimeConfig, evaluations: int) -> RuntimeConfig:
    return replace(
        base,
        max_iterations=evaluations,
        min_iterations=evaluations,
        shot_budget=evaluations
        * len(base.hamiltonian.terms)
        * base.shots_per_term,
    )


def _optimizer(config: RuntimeConfig) -> AskTellPatternSearch:
    if config.optimizer is None:
        raise ValueError("the benchmark requires an explicit optimizer policy")
    return AskTellPatternSearch(
        config.parameter_count,
        config.parameter_lower,
        config.parameter_upper,
        initial_step=config.optimizer.initial_step,
        step_shrink=config.optimizer.step_shrink,
        improvement_tolerance=config.optimizer.improvement_tolerance,
    )


def _initial_theta(config: RuntimeConfig) -> tuple[float, ...]:
    source = random.Random(config.seed)
    return tuple(
        source.uniform(config.parameter_lower, config.parameter_upper)
        for _ in range(config.parameter_count)
    )


def _convergence(
    config: RuntimeConfig,
    *,
    evaluation: int,
    energy: float,
    previous_energy: float | None,
    previous_stable_count: int,
) -> tuple[bool, float, int]:
    if previous_energy is None:
        return False, 0.0, 0
    delta = abs(energy - previous_energy)
    within = delta <= config.convergence_tolerance + config.energy_abs_tolerance
    stable = previous_stable_count + 1 if within else 0
    converged = (
        within
        and evaluation + 1 >= config.min_iterations
        and stable >= config.convergence_patience
    )
    return converged, delta, stable


def _ideal_probabilities(circuit: Any, theta: Sequence[float]) -> dict[str, float]:
    from qiskit.quantum_info import Statevector

    bound = circuit.assign_parameters(list(theta), inplace=False)
    unmeasured = bound.remove_final_measurements(inplace=False)
    probabilities = Statevector.from_instruction(unmeasured).probabilities_dict()
    return {
        str(outcome).replace(" ", ""): float(probability)
        for outcome, probability in probabilities.items()
    }


def _fidelity_rows(
    *,
    circuits: Sequence[Any],
    evaluations: Sequence[dict[str, Any]],
    meta: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    pub_rows: list[dict[str, Any]] = []
    cumulative = 0.0
    for evaluation in evaluations:
        fidelities: list[float] = []
        theta = tuple(float(value) for value in evaluation["theta"])
        for pub_index, (circuit, record) in enumerate(
            zip(circuits, evaluation["raw_records"])
        ):
            ideal = _ideal_probabilities(circuit, theta)
            counts = {str(key): int(value) for key, value in record["counts"].items()}
            fidelity = classical_distribution_fidelity(ideal, counts)
            fidelities.append(fidelity)
            pub_rows.append(
                {
                    **meta,
                    "evaluation": evaluation["evaluation"],
                    "term_id": record["term_id"],
                    "pauli": record["pauli"],
                    "pub_index": pub_index,
                    "shots": record["observed_shots"],
                    "fidelity": fidelity,
                    "infidelity": 1.0 - fidelity,
                    "ideal_probabilities_json": json.dumps(ideal, sort_keys=True),
                    "observed_counts_json": json.dumps(counts, sort_keys=True),
                    "raw_evidence_sha256": record["raw_evidence_sha256"],
                }
            )
        measurement_fidelity = statistics.fmean(fidelities)
        infidelity = 1.0 - measurement_fidelity
        cumulative += infidelity
        evaluation["measurement_fidelity"] = measurement_fidelity
        evaluation["measurement_infidelity"] = infidelity
        evaluation["cumulative_measurement_infidelity"] = cumulative

    infidelities = [float(row["measurement_infidelity"]) for row in evaluations]
    return pub_rows, {
        "mean_measurement_fidelity": statistics.fmean(
            float(row["measurement_fidelity"]) for row in evaluations
        ),
        "mean_measurement_infidelity": statistics.fmean(infidelities),
        "cumulative_measurement_infidelity": math.fsum(infidelities),
        "max_measurement_infidelity": max(infidelities),
    }


def _evidence_identity(
    *,
    config: RuntimeConfig,
    provenance: Mapping[str, Any],
    circuit: Any,
    circuit_hash: str,
    theta: Sequence[float],
    evaluation: int,
    pub_index: int,
    evaluation_id: str,
    submission_id: str,
    external_job_id: str,
    submitted_at: str,
    retrieved_at: str,
    job_metadata: Mapping[str, Any],
    primitive_metadata: Any,
    pub_metadata: Any,
    raw_shot_data_sha256: str,
) -> dict[str, Any]:
    bound_hash = _qpy_digest(circuit.assign_parameters(list(theta), inplace=False))
    return {
        "execution_mode": config.mode,
        "backend": config.backend,
        "iteration": evaluation,
        "evaluation_id": evaluation_id,
        "submission_id": submission_id,
        "external_job_id": external_job_id,
        "pub_index": pub_index,
        "theta": list(theta),
        "theta_hash": vector_digest(theta),
        "parameterized_circuit_qpy_sha256": circuit_hash,
        "executable_circuit_qpy_sha256": bound_hash,
        "raw_shot_data_sha256": raw_shot_data_sha256,
        "physical_layout": _layout_record(circuit),
        "transpiler_seed": None,
        "transpiler_optimization_level": None,
        "submitted_at_utc": submitted_at,
        "retrieved_at_utc": retrieved_at,
        "sampler_options": provenance["sampler_experiment"]["api_options"],
        "job_metadata": dict(job_metadata),
        "primitive_result_metadata": _json_safe(primitive_metadata),
        "pub_metadata": _json_safe(pub_metadata),
    }


def _persist_baseline_evidence(
    *,
    config: RuntimeConfig,
    run_id: str,
    path: Path,
    provenance: Mapping[str, Any],
    circuits: Sequence[Any],
    circuit_hashes: Sequence[str],
    evaluations: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    with EvidenceJournal(
        path,
        run_id=run_id,
        config_hash=config.digest,
        durable=False,
        overwrite=False,
    ) as evidence:
        for evaluation in evaluations:
            for pub_index, (circuit, circuit_hash, raw_record, pub_metadata) in enumerate(
                zip(
                    circuits,
                    circuit_hashes,
                    evaluation["raw_records"],
                    evaluation["pub_metadata"],
                )
            ):
                identity = _evidence_identity(
                    config=config,
                    provenance=provenance,
                    circuit=circuit,
                    circuit_hash=circuit_hash,
                    theta=evaluation["theta"],
                    evaluation=evaluation["evaluation"],
                    pub_index=pub_index,
                    evaluation_id=evaluation["evaluation_id"],
                    submission_id=evaluation["submission_id"],
                    external_job_id=evaluation["external_job_id"],
                    submitted_at=evaluation["submitted_at_utc"],
                    retrieved_at=evaluation["retrieved_at_utc"],
                    job_metadata=evaluation["job_metadata"],
                    primitive_metadata=evaluation["primitive_metadata"],
                    pub_metadata=pub_metadata,
                    raw_shot_data_sha256=hashlib.sha256(
                        b64decode(
                            raw_record["packed_bitarray"]["data"].encode("ascii"),
                            validate=True,
                        )
                    ).hexdigest(),
                )
                evidence.append_pub(raw_record, identity=identity)
        return evidence.seal()


def _baseline_process_rows(
    *,
    config: RuntimeConfig,
    run_id: str,
    evaluations: Sequence[dict[str, Any]],
    terminal_reason: str,
    fidelity: Mapping[str, float],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [
        {
            "record_type": "run_start",
            "run_id": run_id,
            "config_hash": config.digest,
            "config": config.as_dict(include_source=False),
        }
    ]
    for evaluation in evaluations:
        rows.append(
            {
                "record_type": "evaluation",
                "run_id": run_id,
                "evaluation": evaluation["evaluation"],
                "evaluation_id": evaluation["evaluation_id"],
                "submission_id": evaluation["submission_id"],
                "external_job_id": evaluation["external_job_id"],
                "theta": evaluation["theta"],
                "theta_hash": evaluation["theta_hash"],
                "energy": evaluation["energy"],
                "energy_delta": evaluation["energy_delta"],
                "stable_count": evaluation["stable_count"],
                "converged": evaluation["converged"],
                "convergence_candidate": evaluation["convergence_candidate"],
                "next_theta": evaluation["next_theta"],
                "next_theta_hash": evaluation["next_theta_hash"],
                "measurement_fidelity": evaluation["measurement_fidelity"],
                "measurement_infidelity": evaluation["measurement_infidelity"],
                "cumulative_measurement_infidelity": evaluation[
                    "cumulative_measurement_infidelity"
                ],
                "timing": {
                    key: evaluation[key]
                    for key in (
                        "sampling_seconds",
                        "result_processing_seconds",
                        "convergence_check_seconds",
                        "optimizer_seconds",
                        "evaluation_seconds",
                    )
                },
            }
        )
    rows.append(
        {
            "record_type": "run_end",
            "run_id": run_id,
            "terminal_reason": terminal_reason,
            "completed_evaluations": len(evaluations),
            "fidelity_summary": dict(fidelity),
        }
    )
    return rows


def _run_once(
    *,
    config: RuntimeConfig,
    condition: str,
    phase: str,
    repetition: int,
    artifact_dir: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if condition not in CONDITIONS:
        raise ValueError(f"unknown condition {condition!r}")
    verified = condition == "verified"
    run_id = f"sampler-scale-{condition}-n{config.max_iterations}-r{repetition}-{phase}"
    meta = {
        "phase": phase,
        "condition": condition,
        "evaluations": config.max_iterations,
        "repetition": repetition,
        "run_id": run_id,
    }
    artifact_dir.mkdir(parents=True, exist_ok=False)
    trace_path = artifact_dir / "trace.jsonl"
    evidence_path = artifact_dir / "evidence.jsonl"
    process_path = artifact_dir / "process.jsonl"
    online_path = artifact_dir / "online_report.json"
    replay_path = artifact_dir / "replay_report.json"
    resolved_config_path = artifact_dir / "resolved_config.json"
    evaluation_path = artifact_dir / "evaluations.jsonl"
    pub_fidelity_path = artifact_dir / "pub_fidelity.jsonl"
    gate_path = artifact_dir / "gate_latencies.jsonl"
    memory_path = artifact_dir / "memory_samples.jsonl"

    memory_sampler = _MemorySampler()
    memory_sampler.start()
    gate_rows: list[dict[str, Any]] = []
    evaluations: list[dict[str, Any]] = []
    session: RuntimeSession | None = None
    evidence: EvidenceJournal | None = None
    monitor: SynchronousDejaVu | None = None
    report = None
    circuit_hashes: tuple[str, ...] = ()
    provenance: dict[str, Any] = {}
    terminal_reason = "error"
    status = "error"

    total_started = time.perf_counter()
    cpu_started = time.process_time()
    setup_started = total_started
    ansatz, circuits = _make_circuits(config)
    sampler = _make_sampler(config)
    optimizer = _optimizer(config)
    theta = _initial_theta(config)
    if verified:
        circuit_hashes = tuple(_qpy_digest(circuit) for circuit in circuits)
        provenance = _sampler_experiment_provenance(
            config,
            ansatz=ansatz,
            circuits=circuits,
            circuit_hashes=circuit_hashes,
            initial_theta=theta,
        )
        monitor = SynchronousDejaVu(
            timeout_seconds=config.monitor_timeout_seconds,
            bits_per_variable=config.bits_per_variable,
        )
        memory_sampler.add_process(monitor._process.pid, "dejavu_jvm")
        original_submit = monitor.submit

        def timed_submit(event: RuntimeEvent) -> MonitorAck:
            started = time.perf_counter()
            acknowledgement = original_submit(event)
            gate_rows.append(
                {
                    **meta,
                    "seq": event.seq,
                    "event": event.name,
                    "latency_seconds": time.perf_counter() - started,
                }
            )
            return acknowledgement

        monitor.submit = timed_submit  # type: ignore[method-assign]
        evidence = EvidenceJournal(
            evidence_path,
            run_id=run_id,
            config_hash=config.digest,
            durable=False,
            overwrite=False,
        )
        session = RuntimeSession(
            config,
            run_id=run_id,
            trace_path=trace_path,
            report_path=online_path,
            monitor=monitor,
            execution_provenance=provenance,
            durable=False,
            overwrite=False,
        )
    setup_seconds = time.perf_counter() - setup_started

    previous_energy: float | None = None
    stable_count = 0
    loop_started = time.perf_counter()
    try:
        for evaluation in range(config.max_iterations):
            evaluation_started = time.perf_counter()
            evaluation_id = f"eval{evaluation}"
            submission_id = f"submission{evaluation}"
            if session is not None:
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
            sampling_started = time.perf_counter()
            submitted_at = _utc_now()
            job = sampler.run(pubs, shots=config.shots_per_term)
            external_job_id = _job_id(job, f"localSamplerJob{evaluation}")
            if session is not None:
                session.mark_job_submitted(external_job_id)
            result = job.result()
            retrieved_at = _utc_now()
            sampling_seconds = time.perf_counter() - sampling_started
            if len(result) != len(config.hamiltonian.terms):
                raise RuntimeError(
                    f"Sampler returned {len(result)} PUB results; expected "
                    f"{len(config.hamiltonian.terms)}"
                )

            processing_started = time.perf_counter()
            job_metadata = _call_metadata(job)
            primitive_metadata = _json_safe(getattr(result, "metadata", None))
            expectations: list[float] = []
            raw_records: list[dict[str, Any]] = []
            pub_metadata: list[Any] = []
            for pub_index, (term, circuit, pub_result) in enumerate(
                zip(config.hamiltonian.terms, circuits, result)
            ):
                if verified:
                    raw_record = evidence_from_pub_result(
                        pub_result,
                        term_id=term.term_id,
                        pauli=term.pauli,
                        requested_shots=config.shots_per_term,
                    )
                    assert evidence is not None
                    identity = _evidence_identity(
                        config=config,
                        provenance=provenance,
                        circuit=circuit,
                        circuit_hash=circuit_hashes[pub_index],
                        theta=theta,
                        evaluation=evaluation,
                        pub_index=pub_index,
                        evaluation_id=evaluation_id,
                        submission_id=submission_id,
                        external_job_id=external_job_id,
                        submitted_at=submitted_at,
                        retrieved_at=retrieved_at,
                        job_metadata=job_metadata,
                        primitive_metadata=primitive_metadata,
                        pub_metadata=getattr(pub_result, "metadata", None),
                        raw_shot_data_sha256=hashlib.sha256(
                            b64decode(
                                raw_record["packed_bitarray"]["data"].encode(
                                    "ascii"
                                ),
                                validate=True,
                            )
                        ).hexdigest(),
                    )
                    archived = evidence.append_pub(raw_record, identity=identity)
                    raw_records.append(archived)
                    expectation = float(archived["expectation"])
                    negative = int(archived["negative_eigenvalue_count"])
                    assert session is not None
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
                    counts = {
                        str(key): int(value)
                        for key, value in bit_array.get_counts().items()
                    }
                    negative = negative_eigenvalue_count(counts, term.pauli)
                    expectation = expectation_from_negative_count(
                        negative, int(bit_array.num_shots)
                    )
                    # Retain the result object for full raw-evidence extraction
                    # after the baseline timing boundary.
                    raw_records.append({"_pub_result": pub_result})
                expectations.append(expectation)
                pub_metadata.append(_json_safe(getattr(pub_result, "metadata", None)))

            if session is not None:
                session.seal_measurements()
            energy = math.fsum(
                term.coeff_int * expectation / config.hamiltonian.coeff_scale
                for term, expectation in zip(config.hamiltonian.terms, expectations)
            )
            if session is not None:
                session.aggregate_energy(energy)
            result_processing_seconds = time.perf_counter() - processing_started

            convergence_started = time.perf_counter()
            if session is not None:
                converged = session.check_convergence()
                checkpoint = session.contracts.active
                if checkpoint is None:
                    raise RuntimeError("verified convergence check lost active evaluation")
                delta = float(checkpoint.energy_delta or 0.0)
                stable_count = checkpoint.stable_count
                verified_energy = session.authorize_objective_release()
            else:
                converged, delta, stable_count = _convergence(
                    config,
                    evaluation=evaluation,
                    energy=energy,
                    previous_energy=previous_energy,
                    previous_stable_count=stable_count,
                )
                verified_energy = energy
            convergence_check_seconds = time.perf_counter() - convergence_started

            optimizer_started = time.perf_counter()
            if not converged and evaluation + 1 < config.max_iterations:
                next_theta, update_token = optimizer.preview_update(theta, verified_energy)
                if session is not None:
                    session.authorize_and_commit_optimizer_update(
                        optimizer, update_token, next_theta
                    )
                else:
                    optimizer.commit_update(update_token, authorized_theta=next_theta)
            else:
                next_theta = theta
            optimizer_seconds = time.perf_counter() - optimizer_started
            if session is not None:
                session.close_iteration()

            evaluations.append(
                {
                    "evaluation": evaluation,
                    "evaluation_id": evaluation_id,
                    "submission_id": submission_id,
                    "external_job_id": external_job_id,
                    "theta": list(theta),
                    "theta_hash": vector_digest(theta),
                    "energy": energy,
                    "energy_delta": delta,
                    "stable_count": stable_count,
                    "converged": converged,
                    "convergence_candidate": stable_count
                    >= config.convergence_patience,
                    "next_theta": list(next_theta),
                    "next_theta_hash": vector_digest(next_theta),
                    "sampling_seconds": sampling_seconds,
                    "result_processing_seconds": result_processing_seconds,
                    "convergence_check_seconds": convergence_check_seconds,
                    "optimizer_seconds": optimizer_seconds,
                    "evaluation_seconds": time.perf_counter() - evaluation_started,
                    "raw_records": raw_records,
                    "pub_metadata": pub_metadata,
                    "job_metadata": job_metadata,
                    "primitive_metadata": primitive_metadata,
                    "submitted_at_utc": submitted_at,
                    "retrieved_at_utc": retrieved_at,
                }
            )
            previous_energy = energy
            theta = tuple(next_theta)
            if converged:
                terminal_reason = "converged"
                break
        else:
            terminal_reason = "max_iterations"
        loop_seconds = time.perf_counter() - loop_started

        finalize_started = time.perf_counter()
        if session is not None:
            if terminal_reason == "converged":
                session.finish(TerminationReason.CONVERGED)
            else:
                session.finish(TerminationReason.MAX_ITERATIONS)
            assert evidence is not None
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
        finalize_seconds = time.perf_counter() - finalize_started
    finally:
        if evidence is not None:
            evidence.close()
        if session is not None:
            session.close()

    total_seconds = time.perf_counter() - total_started
    python_cpu_seconds = time.process_time() - cpu_started
    memory_rows = memory_sampler.stop()

    # Full baseline raw evidence is deliberately materialized after its timing
    # boundary.  Fidelity and verified replay are also post-run analyses.
    artifact_started = time.perf_counter()
    if not verified:
        circuit_hashes = tuple(_qpy_digest(circuit) for circuit in circuits)
        provenance = _sampler_experiment_provenance(
            config,
            ansatz=ansatz,
            circuits=circuits,
            circuit_hashes=circuit_hashes,
            initial_theta=_initial_theta(config),
        )
        for evaluation, stored in enumerate(evaluations):
            complete_records: list[dict[str, Any]] = []
            for term, placeholder in zip(config.hamiltonian.terms, stored["raw_records"]):
                complete_records.append(
                    evidence_from_pub_result(
                        placeholder["_pub_result"],
                        term_id=term.term_id,
                        pauli=term.pauli,
                        requested_shots=config.shots_per_term,
                    )
                )
            stored["raw_records"] = complete_records
        _persist_baseline_evidence(
            config=config,
            run_id=run_id,
            path=evidence_path,
            provenance=provenance,
            circuits=circuits,
            circuit_hashes=circuit_hashes,
            evaluations=evaluations,
        )

    pub_rows, fidelity = _fidelity_rows(
        circuits=circuits,
        evaluations=evaluations,
        meta=meta,
    )
    if not verified:
        _write_jsonl(
            process_path,
            _baseline_process_rows(
                config=config,
                run_id=run_id,
                evaluations=evaluations,
                terminal_reason=terminal_reason,
                fidelity=fidelity,
            ),
        )
    _write_json(resolved_config_path, config.as_dict())
    _write_jsonl(pub_fidelity_path, pub_rows)
    evaluation_rows = [
        {
            **meta,
            "evaluation": row["evaluation"],
            "evaluation_id": row["evaluation_id"],
            "theta_json": json.dumps(row["theta"]),
            "theta_hash": row["theta_hash"],
            "energy": row["energy"],
            "energy_delta": row["energy_delta"],
            "stable_count": row["stable_count"],
            "converged": row["converged"],
            "convergence_candidate": row["convergence_candidate"],
            "sampling_seconds": row["sampling_seconds"],
            "result_processing_seconds": row["result_processing_seconds"],
            "convergence_check_seconds": row["convergence_check_seconds"],
            "optimizer_seconds": row["optimizer_seconds"],
            "evaluation_seconds": row["evaluation_seconds"],
            "measurement_fidelity": row["measurement_fidelity"],
            "measurement_infidelity": row["measurement_infidelity"],
            "cumulative_measurement_infidelity": row[
                "cumulative_measurement_infidelity"
            ],
        }
        for row in evaluations
    ]
    _write_jsonl(evaluation_path, evaluation_rows)
    _write_jsonl(gate_path, gate_rows)
    decorated_memory = [{**meta, **row} for row in memory_rows]
    _write_jsonl(memory_path, decorated_memory)
    artifact_write_seconds = time.perf_counter() - artifact_started

    replay_seconds = 0.0
    if verified:
        replay_started = time.perf_counter()
        replay = check_trace(
            config,
            trace_path,
            evidence_path=evidence_path,
            report_path=replay_path,
        )
        replay_seconds = time.perf_counter() - replay_started
        if status != "pass" or replay.status.value != "pass":
            raise RuntimeError(
                f"verified run {run_id} did not pass online and replay: "
                f"online={status}, replay={replay.status.value}"
            )

    run_row = {
        **meta,
        "seed": config.seed,
        "status": status,
        "terminal_reason": terminal_reason,
        "completed_evaluations": len(evaluations),
        "first_convergence_candidate_evaluation": next(
            (
                int(row["evaluation"]) + 1
                for row in evaluations
                if row["convergence_candidate"]
            ),
            None,
        ),
        "time_to_first_convergence_candidate_seconds": next(
            (
                math.fsum(
                    float(prior["evaluation_seconds"])
                    for prior in evaluations[: index + 1]
                )
                for index, row in enumerate(evaluations)
                if row["convergence_candidate"]
            ),
            None,
        ),
        "final_energy": evaluations[-1]["energy"],
        "total_seconds": total_seconds,
        "python_cpu_seconds": python_cpu_seconds,
        "setup_seconds": setup_seconds,
        "loop_seconds": loop_seconds,
        "finalize_seconds": finalize_seconds,
        "artifact_write_seconds": artifact_write_seconds,
        "replay_seconds": replay_seconds,
        **fidelity,
        "peak_python_rss_bytes": _peak_memory(memory_rows, "python"),
        "peak_jvm_rss_bytes": _peak_memory(memory_rows, "dejavu_jvm"),
        "trace_bytes": trace_path.stat().st_size if trace_path.exists() else 0,
        "evidence_bytes": evidence_path.stat().st_size,
        "process_bytes": process_path.stat().st_size if process_path.exists() else 0,
    }
    _write_json(artifact_dir / "run_summary.json", run_row)
    return run_row, evaluation_rows, pub_rows, gate_rows, decorated_memory


def _summarize(run_rows: Sequence[Mapping[str, Any]], scales: Sequence[int]) -> dict[str, Any]:
    measured = [row for row in run_rows if row["phase"] == "measured"]
    scale_rows: list[dict[str, Any]] = []
    for evaluations in scales:
        by_condition: dict[str, Any] = {}
        for condition in CONDITIONS:
            selected = [
                row
                for row in measured
                if row["condition"] == condition
                and int(row["evaluations"]) == evaluations
            ]
            by_condition[condition] = {
                "execution_seconds": _distribution(
                    float(row["total_seconds"]) for row in selected
                ),
                "mean_measurement_infidelity": _distribution(
                    float(row["mean_measurement_infidelity"]) for row in selected
                ),
                "cumulative_measurement_infidelity": _distribution(
                    float(row["cumulative_measurement_infidelity"])
                    for row in selected
                ),
                "peak_python_rss_bytes": _distribution(
                    float(row["peak_python_rss_bytes"]) for row in selected
                ),
                "peak_jvm_rss_bytes": _distribution(
                    float(row["peak_jvm_rss_bytes"]) for row in selected
                ),
                "first_convergence_candidate_evaluation": _distribution(
                    float(row["first_convergence_candidate_evaluation"])
                    for row in selected
                    if row["first_convergence_candidate_evaluation"] is not None
                ),
                "time_to_first_convergence_candidate_seconds": _distribution(
                    float(row["time_to_first_convergence_candidate_seconds"])
                    for row in selected
                    if row["time_to_first_convergence_candidate_seconds"] is not None
                ),
                "final_energy": _distribution(
                    float(row["final_energy"]) for row in selected
                ),
            }
        baseline = by_condition["baseline"]["execution_seconds"]["p50"]
        verified = by_condition["verified"]["execution_seconds"]["p50"]
        difference = None if baseline is None or verified is None else verified - baseline
        percent = (
            None
            if difference is None or baseline == 0
            else 100.0 * difference / baseline
        )
        baseline_infidelity = by_condition["baseline"][
            "mean_measurement_infidelity"
        ]["p50"]
        verified_infidelity = by_condition["verified"][
            "mean_measurement_infidelity"
        ]["p50"]
        fidelity_impact = (
            None
            if baseline_infidelity is None or verified_infidelity is None
            else verified_infidelity - baseline_infidelity
        )
        baseline_final_energy = by_condition["baseline"]["final_energy"]["p50"]
        verified_final_energy = by_condition["verified"]["final_energy"]["p50"]
        final_energy_difference = (
            None
            if baseline_final_energy is None or verified_final_energy is None
            else verified_final_energy - baseline_final_energy
        )
        scale_rows.append(
            {
                "evaluations": evaluations,
                "conditions": by_condition,
                "direct_p50_difference_seconds": difference,
                "direct_p50_overhead_percent": percent,
                "direct_p50_mean_infidelity_difference": fidelity_impact,
                "direct_p50_final_energy_difference": final_energy_difference,
            }
        )
    return {
        "comparison": "independent condition summaries; no paired estimator",
        "scales": scale_rows,
    }


def _attach_evaluation_summary(
    summary: dict[str, Any], evaluation_rows: Sequence[Mapping[str, Any]]
) -> None:
    measured = [row for row in evaluation_rows if row["phase"] == "measured"]
    for scale in summary["scales"]:
        evaluations = int(scale["evaluations"])
        for condition in CONDITIONS:
            selected = [
                row
                for row in measured
                if row["condition"] == condition
                and int(row["evaluations"]) == evaluations
            ]
            scale["conditions"][condition]["convergence_check_seconds"] = _distribution(
                float(row["convergence_check_seconds"]) for row in selected
            )
            scale["conditions"][condition]["evaluation_seconds"] = _distribution(
                float(row["evaluation_seconds"]) for row in selected
            )


def _svg_figure(summary: Mapping[str, Any], path: Path) -> None:
    rows = list(summary["scales"])
    width, height = 900, 560
    left, right, top, bottom = 100, 40, 55, 90
    plot_width = width - left - right
    plot_height = height - top - bottom
    values = [
        float(row["conditions"][condition]["execution_seconds"]["p50"])
        for row in rows
        for condition in CONDITIONS
    ]
    maximum = max(values) if values else 1.0
    y_max = maximum * 1.12 if maximum > 0 else 1.0
    x_values = [int(row["evaluations"]) for row in rows]
    x_min, x_max = min(x_values), max(x_values)

    def x(value: int) -> float:
        return left + (value - x_min) / max(1, x_max - x_min) * plot_width

    def y(value: float) -> float:
        return top + plot_height - value / y_max * plot_height

    colors = {"baseline": "#2463a9", "verified": "#c64a32"}
    labels = {"baseline": "Baseline VQE", "verified": "VQE + runtime verification"}
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#20242a}.axis{stroke:#343a40;stroke-width:1.5}.grid{stroke:#d8dde3;stroke-width:1}.series{fill:none;stroke-width:3}.point{stroke:white;stroke-width:1.5}</style>',
        '<text x="450" y="28" text-anchor="middle" font-size="20" font-weight="600">Simulator execution time by evaluation count</text>',
    ]
    for tick in range(6):
        value = y_max * tick / 5
        py = y(value)
        elements.append(
            f'<line class="grid" x1="{left}" y1="{py:.2f}" x2="{left + plot_width}" y2="{py:.2f}"/>'
        )
        elements.append(
            f'<text x="{left - 12}" y="{py + 5:.2f}" text-anchor="end" font-size="13">{value:.2f}</text>'
        )
    elements.extend(
        [
            f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}"/>',
            f'<line class="axis" x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top + plot_height}"/>',
        ]
    )
    for value in x_values:
        px = x(value)
        elements.append(
            f'<text x="{px:.2f}" y="{top + plot_height + 27}" text-anchor="middle" font-size="13">{value}</text>'
        )
    for condition in CONDITIONS:
        points = [
            (
                x(int(row["evaluations"])),
                y(float(row["conditions"][condition]["execution_seconds"]["p50"])),
            )
            for row in rows
        ]
        point_text = " ".join(f"{px:.2f},{py:.2f}" for px, py in points)
        elements.append(
            f'<polyline class="series" stroke="{colors[condition]}" points="{point_text}"/>'
        )
        for px, py in points:
            elements.append(
                f'<circle class="point" cx="{px:.2f}" cy="{py:.2f}" r="5" fill="{colors[condition]}"/>'
            )
    elements.extend(
        [
            f'<text x="{left + plot_width / 2:.2f}" y="{height - 28}" text-anchor="middle" font-size="15">Completed objective evaluations</text>',
            f'<text x="24" y="{top + plot_height / 2:.2f}" text-anchor="middle" font-size="15" transform="rotate(-90 24 {top + plot_height / 2:.2f})">Median execution time (s)</text>',
        ]
    )
    legend_x, legend_y = left + 22, top + 18
    for index, condition in enumerate(CONDITIONS):
        ly = legend_y + index * 25
        elements.append(
            f'<line x1="{legend_x}" y1="{ly}" x2="{legend_x + 34}" y2="{ly}" stroke="{colors[condition]}" stroke-width="3"/>'
        )
        elements.append(
            f'<circle cx="{legend_x + 17}" cy="{ly}" r="4" fill="{colors[condition]}"/>'
        )
        elements.append(
            f'<text x="{legend_x + 44}" y="{ly + 5}" font-size="13">{labels[condition]}</text>'
        )
    elements.append('</svg>')
    path.write_text("\n".join(elements) + "\n", encoding="utf-8")


def _report_markdown(
    *,
    summary: Mapping[str, Any],
    config: RuntimeConfig,
    warmups: int,
    repetitions: int,
) -> str:
    lines = [
        "# Simulator VQE runtime-verification scaling experiment",
        "",
        "The timing comparison reports independent condition summaries; it does not use a paired estimator. Fidelity analysis and verified replay were performed after the execution-time boundary.",
        "",
        "## Configuration",
        "",
        f"- Backend: `{config.backend}` (`{config.mode}`)",
        f"- Warm-ups per condition/count: {warmups}",
        f"- Measured repetitions per condition/count: {repetitions}",
        f"- Shots per PUB: {config.shots_per_term}",
        f"- PUBs per evaluation: {len(config.hamiltonian.terms)}",
        f"- Seed: {config.seed}",
        f"- Convergence tolerance/patience: {config.convergence_tolerance} / {config.convergence_patience}",
        "- Timing-run minimum evaluations: equal to each configured evaluation count",
        "- Measurement fidelity: squared Bhattacharyya fidelity between exact and sampled PUB outcome distributions",
        "",
        "## Timing results",
        "",
        "| Evaluations | Baseline p50 (s) | Verified p50 (s) | Verified p95 (s) | Direct p50 difference (s) | Direct overhead (%) |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary["scales"]:
        baseline = row["conditions"]["baseline"]["execution_seconds"]
        verified = row["conditions"]["verified"]["execution_seconds"]
        lines.append(
            "| {n} | {bp:.6f} | {vp:.6f} | {v95:.6f} | {d:.6f} | {o:.2f} |".format(
                n=row["evaluations"],
                bp=baseline["p50"],
                vp=verified["p50"],
                v95=verified["p95"],
                d=row["direct_p50_difference_seconds"],
                o=row["direct_p50_overhead_percent"],
            )
        )
    lines.extend(
        [
            "",
            "## Convergence and fidelity diagnostics",
            "",
            "| Evaluations | Baseline check p50 (ms) | Verified check p50 (ms) | Baseline mean infidelity | Verified mean infidelity | Infidelity impact | Verified cumulative infidelity p50 | First stable evaluation (B/V) |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in summary["scales"]:
        baseline = row["conditions"]["baseline"]
        verified = row["conditions"]["verified"]
        lines.append(
            "| {n} | {bc:.6f} | {vc:.6f} | {bi:.8g} | {vi:.8g} | {fi:.8g} | {ci:.8g} | {be}/{ve} |".format(
                n=row["evaluations"],
                bc=1000.0 * baseline["convergence_check_seconds"]["p50"],
                vc=1000.0 * verified["convergence_check_seconds"]["p50"],
                bi=baseline["mean_measurement_infidelity"]["mean"],
                vi=verified["mean_measurement_infidelity"]["mean"],
                fi=row["direct_p50_mean_infidelity_difference"],
                ci=verified["cumulative_measurement_infidelity"]["p50"],
                be=baseline["first_convergence_candidate_evaluation"]["p50"],
                ve=verified["first_convergence_candidate_evaluation"]["p50"],
            )
        )
    lines.extend(
        [
            "",
            "The fidelity quantity measures agreement of sampled and exact measurement distributions for the four executed PUBs. It does not reconstruct a density matrix and should not be described as full quantum-state fidelity. The infidelity-impact column is the verified median minus the baseline median at the same evaluation count.",
            "",
            "The first stable evaluation is the first one-based evaluation whose tolerance condition has held for the configured patience, evaluated independently of the forced scaling bound. This diagnoses an evaluation-count convergence change while the timing figure reports wall-clock delay.",
            "",
            "All per-run traces, raw evidence, timings, distributions, monitor acknowledgements, memory samples, online reports, and replay reports are retained under `runs/`.",
            "",
        ]
    )
    return "\n".join(lines)


def _environment(config_path: Path, command: Sequence[str]) -> dict[str, Any]:
    packages = {}
    for package in ("qiskit", "qiskit-ibm-runtime", "numpy", "scipy"):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = None
    hash_paths = [
        config_path,
        ROOT / "data/h2_hamiltonian.json",
        ROOT / "specs/vqe_runtime.qtl",
        ROOT / "src/vqe_runtime/vendor/dejavu/vqe-three-level-monitor.jar",
        ROOT / "src/vqe_runtime/vendor/dejavu/dejavu.jar",
        Path(__file__).resolve(),
    ]
    return {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "command": list(command),
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "java": _command_output(["java", "-version"]),
        "packages": packages,
        "sha256": {
            str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path): _sha256(path)
            for path in hash_paths
            if path.is_file()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare StatevectorSampler VQE with and without runtime verification"
    )
    parser.add_argument(
        "--config", type=Path, default=ROOT / "configs/h2_statevector.toml"
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--scales", type=_parse_scales, default=DEFAULT_SCALES)
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--repetitions", type=int, default=30)
    parser.add_argument("--schedule-seed", type=int, default=20260930)
    args = parser.parse_args()
    if args.warmups < 0 or args.repetitions < 1:
        parser.error("warmups must be nonnegative and repetitions must be positive")
    out_dir = args.out_dir.resolve()
    if out_dir.exists() and any(out_dir.iterdir()):
        parser.error(f"output directory is not empty: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    config_path = args.config.resolve()
    base = load_config(config_path)
    if base.mode != "qiskit-statevector-sampler":
        parser.error("this benchmark is restricted to qiskit-statevector-sampler")
    if tuple(args.scales) != DEFAULT_SCALES:
        print(f"NOTE: running non-default evaluation counts {args.scales}", file=sys.stderr)

    _write_json(out_dir / "environment.json", _environment(config_path, sys.argv))
    run_rows: list[dict[str, Any]] = []
    evaluation_rows: list[dict[str, Any]] = []
    pub_rows: list[dict[str, Any]] = []
    gate_rows: list[dict[str, Any]] = []
    memory_rows: list[dict[str, Any]] = []

    schedule: list[tuple[str, str, int, int]] = []
    schedule_source = random.Random(args.schedule_seed)
    for phase, count in (("warmup", args.warmups), ("measured", args.repetitions)):
        phase_schedule: list[tuple[str, str, int, int]] = []
        for condition in CONDITIONS:
            for evaluations in args.scales:
                for repetition in range(1, count + 1):
                    phase_schedule.append((phase, condition, evaluations, repetition))
        schedule_source.shuffle(phase_schedule)
        schedule.extend(phase_schedule)
    _write_json(
        out_dir / "schedule.json",
        [
            {
                "phase": phase,
                "condition": condition,
                "evaluations": evaluations,
                "repetition": repetition,
            }
            for phase, condition, evaluations, repetition in schedule
        ],
    )

    total = len(schedule)
    for index, (phase, condition, evaluations, repetition) in enumerate(schedule, 1):
        config = _scaled_config(base, evaluations)
        artifact_dir = (
            out_dir
            / "runs"
            / phase
            / condition
            / f"n{evaluations:03d}"
            / f"r{repetition:03d}"
        )
        print(
            f"[{index}/{total}] {phase} {condition} n={evaluations} r={repetition}",
            flush=True,
        )
        run, evaluations_out, pubs_out, gates_out, memory_out = _run_once(
            config=config,
            condition=condition,
            phase=phase,
            repetition=repetition,
            artifact_dir=artifact_dir,
        )
        run_rows.append(run)
        evaluation_rows.extend(evaluations_out)
        pub_rows.extend(pubs_out)
        gate_rows.extend(gates_out)
        memory_rows.extend(memory_out)
        _write_csv(out_dir / "runs.csv", RUN_FIELDS, run_rows)
        _write_csv(out_dir / "evaluations.csv", EVALUATION_FIELDS, evaluation_rows)
        _write_csv(out_dir / "pub_fidelity.csv", PUB_FIELDS, pub_rows)
        _write_csv(out_dir / "gate_latencies.csv", GATE_FIELDS, gate_rows)
        _write_csv(out_dir / "memory_samples.csv", MEMORY_FIELDS, memory_rows)

    summary = _summarize(run_rows, args.scales)
    _attach_evaluation_summary(summary, evaluation_rows)
    summary.update(
        {
            "schema_version": 1,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "configuration": base.as_dict(),
            "timing_boundary": {
                "baseline": "VQE setup, sampling, numeric convergence, and optimizer only",
                "verified": "baseline work plus synchronous RuntimeSession, DejaVu, trace, and evidence persistence",
                "excluded_from_both": [
                    "measurement-distribution fidelity analysis",
                    "verified offline replay",
                    "baseline post-run artifact serialization",
                    "summary and figure generation",
                ],
            },
            "fidelity_definition": {
                "name": "measurement-distribution fidelity",
                "formula": "(sum_x sqrt(p_ideal(x) * p_sampled(x)))^2",
                "evaluation_aggregation": "arithmetic mean across four PUBs",
                "run_error_aggregations": [
                    "mean of per-evaluation (1-F)",
                    "sum of per-evaluation (1-F)",
                ],
                "qualification": "not a tomographic quantum-state fidelity",
            },
            "warmups": args.warmups,
            "measured_repetitions": args.repetitions,
            "schedule_seed": args.schedule_seed,
            "raw_files": [
                "runs.csv",
                "evaluations.csv",
                "pub_fidelity.csv",
                "gate_latencies.csv",
                "memory_samples.csv",
                "schedule.json",
                "environment.json",
            ],
        }
    )
    _write_json(out_dir / "summary.json", summary)
    _svg_figure(summary, out_dir / "timing_comparison.svg")
    (out_dir / "REPORT.md").write_text(
        _report_markdown(
            summary=summary,
            config=base,
            warmups=args.warmups,
            repetitions=args.repetitions,
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
