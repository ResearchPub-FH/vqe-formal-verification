from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from pathlib import Path
import uuid
from typing import Any, Iterable, Mapping, Sequence

from .config import RuntimeConfig, canonical_digest, energy_digest, vector_digest
from .contracts import ActiveIteration, ContractEngine
from .dejavu import DejaVuError, EventMonitor, SynchronousDejaVu
from .events import EventJournal, RuntimeEvent, safe_atom
from .report import Status, VerificationReport


class VerificationAbort(RuntimeError):
    def __init__(self, code: str, message: str, *, status: Status = Status.FAIL):
        super().__init__(message)
        self.code = code
        self.status = status


class TerminationReason(str, Enum):
    CONVERGED = "converged"
    MAX_ITERATIONS = "max_iterations"
    OPTIMIZER_STOPPED = "optimizer_stopped"
    ABORTED = "aborted"


@dataclass(frozen=True, slots=True)
class TermObservation:
    term_id: str
    expectation: float
    shots: int | None
    counts_ones: int | None = None
    negative_eigenvalue_count: int | None = None
    pub_index: int | None = None
    raw_evidence_sha256: str | None = None
    executable_circuit_qpy_sha256: str | None = None


class RuntimeSession:
    """Fail-closed online gate for one sequential VQE run.

    The public methods are placed at the actual side-effect boundaries: submit
    intent precedes a backend job, objective release follows all iteration
    checks, and optimizer intent precedes an ask/tell mutation.
    """

    def __init__(
        self,
        config: RuntimeConfig,
        *,
        run_id: str | None = None,
        trace_path: str | Path | None = None,
        report_path: str | Path | None = None,
        monitor: EventMonitor | None = None,
        execution_provenance: Mapping[str, Any] | None = None,
        durable: bool = False,
        overwrite: bool = False,
    ) -> None:
        self.config = config
        self.run_id = safe_atom(run_id or f"vqe-{uuid.uuid4().hex}")
        provenance: dict[str, Any] = {
            "mode": config.mode,
            "system": config.system,
            "backend": config.backend,
            "seed": config.seed,
        }
        if execution_provenance is not None:
            if not isinstance(execution_provenance, Mapping) or not all(
                isinstance(key, str) for key in execution_provenance
            ):
                raise ValueError("execution_provenance must have string keys")
            for key, expected in provenance.items():
                if key in execution_provenance and execution_provenance[key] != expected:
                    raise ValueError(
                        f"execution_provenance cannot override configured {key}"
                    )
            provenance.update(execution_provenance)
        provenance_hash = canonical_digest(provenance)
        self.report_path = None if report_path is None else Path(report_path)
        self.journal = EventJournal(
            trace_path, durable=durable, overwrite=overwrite
        )
        try:
            self.monitor = monitor or SynchronousDejaVu(
                timeout_seconds=config.monitor_timeout_seconds,
                bits_per_variable=config.bits_per_variable,
            )
        except DejaVuError as exc:
            self.journal.close()
            raise VerificationAbort(
                "monitorUnavailable",
                f"DejaVu could not start: {exc}",
                status=Status.INCONCLUSIVE,
            ) from exc
        self.report = VerificationReport(self.run_id, config.digest)
        self.report.execution_provenance = provenance
        if type(self.monitor) is SynchronousDejaVu:
            self.report.monitor_provenance = dict(self.monitor.provenance)
        else:
            self.report.monitor_provenance = type(self.monitor).__name__
            self.report.add_inconclusive(
                "run_monitor_available",
                "a non-DejaVu shadow/test monitor cannot establish temporal assurance",
                source="monitor",
            )
        self.contracts = ContractEngine(config, self.report)
        self._terminated = False
        self._sealed = False
        self._closed = False
        self._aborting = False
        try:
            self._emit_raw(
                "runStarted",
                self.run_id,
                self.config.digest,
                payload={
                    "config_hash": self.config.digest,
                    "config": self.config.as_dict(include_source=False),
                    "execution_provenance": provenance,
                    "execution_provenance_hash": provenance_hash,
                },
            )
            protocol_event = (
                "optimizerAskTellConfigured"
                if self.config.optimizer_protocol == "ask-tell"
                else "optimizerOpaqueConfigured"
            )
            self._emit_domain(
                protocol_event,
                self.run_id,
                self.config.digest,
                payload={"optimizer_protocol": self.config.optimizer_protocol},
            )
        except BaseException:
            try:
                try:
                    self.monitor.close()
                except Exception:
                    pass
            finally:
                self.journal.close()
                self._closed = True
            raise

    def _emit_raw(
        self,
        name: str,
        *args: Any,
        payload: dict[str, Any] | None = None,
        fatal: bool = True,
    ) -> RuntimeEvent:
        if self._closed:
            raise VerificationAbort("sessionClosed", "runtime session is already closed")
        try:
            event = self.journal.append(name, *args, payload=payload)
        except Exception as exc:
            self.report.add_inconclusive(
                "run_journal_available", f"cannot persist enforcement event: {exc}"
            )
            raise VerificationAbort(
                "journalFailure",
                "the runtime journal failed closed",
                status=Status.INCONCLUSIVE,
            ) from exc

        python_ok = self.contracts.consume(event)
        try:
            ack = self.monitor.submit(event)
        except Exception as exc:
            self.report.add_inconclusive(
                "run_monitor_available",
                f"DejaVu did not acknowledge sequence {event.seq}: {exc}",
                seq=event.seq,
                source="dejavu",
            )
            if fatal and not self._aborting:
                self._best_effort_abort("monitorInconclusive")
            raise VerificationAbort(
                "monitorInconclusive",
                "DejaVu failed to acknowledge the enforcement watermark",
                status=Status.INCONCLUSIVE,
            ) from exc
        monitor_ok = ack.seq == event.seq and ack.passed
        if ack.seq != event.seq:
            self.report.add_inconclusive(
                "run_monitor_available",
                f"monitor watermark mismatch: expected {event.seq}, got {ack.seq}",
                seq=event.seq,
                source="dejavu",
            )
        if not ack.passed:
            properties = ack.violations or ("run_monitor_rejected_event",)
            for property_id in properties:
                self.report.add_failure(
                    property_id,
                    f"DejaVu rejected event {name}",
                    seq=event.seq,
                    source="dejavu",
                )
        if fatal and (not python_ok or not monitor_ok):
            if not self._aborting:
                self._best_effort_abort("verificationViolation")
            raise VerificationAbort(
                "verificationViolation", f"runtime verification rejected event {name}"
            )
        return event

    def _emit_domain(
        self, name: str, *args: Any, payload: dict[str, Any] | None = None
    ) -> RuntimeEvent:
        self._emit_raw(
            "activity", self.run_id, self.config.digest, name, fatal=True
        )
        return self._emit_raw(name, *args, payload=payload, fatal=True)

    def _best_effort_abort(self, code: str) -> None:
        if self._terminated or self._aborting:
            return
        self._aborting = True
        active = self.contracts.active
        iteration = "0" if active is None else str(active.iteration)
        evaluation_id = "none" if active is None else active.evaluation_id
        try:
            self._emit_raw(
                "activity",
                self.run_id,
                self.config.digest,
                "criticalFail",
                fatal=False,
            )
            self._emit_raw(
                "criticalFail",
                self.run_id,
                self.config.digest,
                iteration,
                evaluation_id,
                safe_atom(code),
                fatal=False,
            )
            if self.contracts.active is not None:
                self._emit_raw(
                    "activity",
                    self.run_id,
                    self.config.digest,
                    "iterationAborted",
                    fatal=False,
                )
                self._emit_raw(
                    "iterationAborted",
                    self.run_id,
                    self.config.digest,
                    iteration,
                    evaluation_id,
                    safe_atom(code),
                    fatal=False,
                )
            self._emit_raw(
                "runAborted",
                self.run_id,
                self.config.digest,
                iteration,
                evaluation_id,
                safe_atom(code),
                fatal=False,
            )
            self._terminated = True
            self.report.terminal_reason = TerminationReason.ABORTED.value
        except Exception:
            self._terminated = True
        finally:
            self._aborting = False

    def _active(self) -> ActiveIteration:
        active = self.contracts.active
        if active is None:
            raise VerificationAbort("noActiveIteration", "there is no open iteration")
        return active

    def begin_iteration(
        self, theta: Sequence[float], *, evaluation_id: str | None = None
    ) -> str:
        if self._terminated:
            raise VerificationAbort("terminalRun", "cannot start after run termination")
        values = tuple(float(value) for value in theta)
        theta_hash = vector_digest(values)
        iteration = len(self.contracts.checkpoints)
        evaluation = safe_atom(evaluation_id or f"eval{iteration}")
        payload = {
            "iteration": iteration,
            "evaluation_id": evaluation,
            "theta": list(values),
            "theta_hash": theta_hash,
        }
        if iteration == 0:
            self._emit_domain(
                "firstIterationStarted",
                self.run_id,
                self.config.digest,
                str(iteration),
                evaluation,
                theta_hash,
                payload=payload,
            )
        else:
            previous = self.contracts.checkpoints[-1]
            payload["previous_evaluation_id"] = previous.evaluation_id
            self._emit_domain(
                "nextIterationStarted",
                self.run_id,
                self.config.digest,
                str(iteration),
                evaluation,
                previous.evaluation_id,
                theta_hash,
                payload=payload,
            )
        return evaluation

    def bind_parameters(self) -> None:
        active = self._active()
        self._emit_domain(
            "parametersBound",
            self.run_id,
            self.config.digest,
            str(active.iteration),
            active.evaluation_id,
            active.theta_hash,
            payload={"theta": list(active.theta), "theta_hash": active.theta_hash},
        )

    def authorize_job(
        self,
        submission_id: str,
        *,
        pub_indices: Mapping[str, int] | None = None,
        circuit_hashes: Mapping[str, str] | None = None,
    ) -> None:
        active = self._active()
        submission = safe_atom(submission_id)
        for expected_index, term in enumerate(self.config.hamiltonian.terms):
            payload: dict[str, Any] = {
                "term_id": term.term_id,
                "pauli": term.pauli,
            }
            if self.config.is_sampler_mode:
                pub_index = (
                    None if pub_indices is None else pub_indices.get(term.term_id)
                )
                circuit_hash = (
                    None if circuit_hashes is None else circuit_hashes.get(term.term_id)
                )
                payload.update(
                    {
                        "pub_index": pub_index,
                        "expected_pub_index": expected_index,
                        "requested_shots": self.config.shots_per_term,
                        "measurement_strategy": (
                            None
                            if self.config.sampler is None
                            else self.config.sampler.measurement_strategy
                        ),
                        "parameterized_circuit_qpy_sha256": circuit_hash,
                    }
                )
            self._emit_domain(
                "termExpected",
                self.run_id,
                self.config.digest,
                str(active.iteration),
                active.evaluation_id,
                submission,
                term.term_id,
                payload=payload,
            )
        intent_payload: dict[str, Any] = {
            "submission_id": submission,
            "theta_hash": active.theta_hash,
        }
        if self.config.is_sampler_mode:
            intent_payload.update(
                {
                    "pub_count": len(self.config.hamiltonian.terms),
                    "term_order": [
                        term.term_id for term in self.config.hamiltonian.terms
                    ],
                    "shots_per_pub": self.config.shots_per_term,
                    "requested_physical_shots": (
                        len(self.config.hamiltonian.terms)
                        * self.config.shots_per_term
                    ),
                }
            )
        self._emit_domain(
            "jobSubmitIntent",
            self.run_id,
            self.config.digest,
            str(active.iteration),
            active.evaluation_id,
            submission,
            active.theta_hash,
            payload=intent_payload,
        )

    def mark_job_submitted(self, external_job_id: str) -> None:
        active = self._active()
        if active.submission_id is None:
            raise VerificationAbort("noSubmissionIntent", "job was not authorized")
        external = safe_atom(external_job_id)
        self._emit_domain(
            "jobSubmitted",
            self.run_id,
            self.config.digest,
            str(active.iteration),
            active.evaluation_id,
            active.submission_id,
            external,
            active.theta_hash,
            payload={
                "submission_id": active.submission_id,
                "external_job_id": external,
                "theta_hash": active.theta_hash,
            },
        )

    def observe_term(self, observation: TermObservation) -> None:
        active = self._active()
        if active.submission_id is None:
            raise VerificationAbort("noSubmittedJob", "term arrived before job intent")
        if active.external_job_id is None:
            raise VerificationAbort("noSubmittedJob", "term arrived before job submission")
        term_id = safe_atom(observation.term_id)
        payload: dict[str, Any] = {
            "term_id": term_id,
            "pauli": next(
                (
                    term.pauli
                    for term in self.config.hamiltonian.terms
                    if term.term_id == term_id
                ),
                "unknown",
            ),
            "expectation": observation.expectation,
            "shots": observation.shots,
            "counts_ones": observation.counts_ones,
        }
        if self.config.is_sampler_mode:
            negative_count = observation.negative_eigenvalue_count
            payload.update(
                {
                    "requested_shots": self.config.shots_per_term,
                    "observed_shots": observation.shots,
                    "negative_eigenvalue_count": negative_count,
                    "pub_index": observation.pub_index,
                    "raw_evidence_sha256": observation.raw_evidence_sha256,
                    "executable_circuit_qpy_sha256": (
                        observation.executable_circuit_qpy_sha256
                    ),
                }
            )
        self._emit_domain(
            "termObserved",
            self.run_id,
            self.config.digest,
            str(active.iteration),
            active.evaluation_id,
            active.submission_id,
            active.external_job_id,
            term_id,
            active.theta_hash,
            payload=payload,
        )

    def observe_terms(self, observations: Iterable[TermObservation]) -> None:
        for observation in observations:
            self.observe_term(observation)

    def seal_measurements(self) -> None:
        active = self._active()
        if active.submission_id is None:
            raise VerificationAbort("noSubmittedJob", "cannot seal without submission")
        payload: dict[str, Any] = {
            "observed_term_ids": sorted(active.observed),
        }
        if self.config.is_sampler_mode:
            payload.update(
                {
                    "observed_pub_indices": sorted(
                        item.pub_index
                        for item in active.observed.values()
                        if item.pub_index is not None
                    ),
                    "pub_count": len(active.observed),
                    "verified_physical_shots": sum(
                        item.shots or 0 for item in active.observed.values()
                    ),
                    "raw_evidence_sha256": sorted(
                        item.raw_evidence_sha256
                        for item in active.observed.values()
                        if item.raw_evidence_sha256 is not None
                    ),
                }
            )
        self._emit_domain(
            "measurementsSealed",
            self.run_id,
            self.config.digest,
            str(active.iteration),
            active.evaluation_id,
            active.submission_id,
            payload=payload,
        )

    def aggregate_energy(self, reported_energy: float) -> float:
        active = self._active()
        energy = float(reported_energy)
        digest = energy_digest(energy)
        self._emit_domain(
            "numericValid",
            self.run_id,
            self.config.digest,
            str(active.iteration),
            active.evaluation_id,
            digest,
            active.theta_hash,
            payload={"reported_energy": energy},
        )
        return energy

    def check_convergence(self, declared: bool | None = None) -> bool:
        active = self._active()
        if active.energy is None or active.energy_hash is None:
            raise VerificationAbort("noValidEnergy", "energy has not been verified")
        previous = (
            None if not self.contracts.checkpoints else self.contracts.checkpoints[-1]
        )
        if previous is None:
            delta = 0.0
            stable_count = 0
            expected = False
        else:
            delta = abs(active.energy - previous.energy)
            within = delta <= (
                self.config.convergence_tolerance
                + self.config.energy_abs_tolerance
            )
            stable_count = previous.stable_count + 1 if within else 0
            expected = (
                within
                and active.iteration + 1 >= self.config.min_iterations
                and stable_count >= self.config.convergence_patience
            )
        value = expected if declared is None else bool(declared)
        token = "T" if value else "F"
        payload: dict[str, Any] = {
            "converged": value,
            "energy_delta": delta,
            "stable_count": stable_count,
        }
        if previous is None:
            self._emit_domain(
                "firstConvergenceChecked",
                self.run_id,
                self.config.digest,
                str(active.iteration),
                active.evaluation_id,
                active.energy_hash,
                active.theta_hash,
                token,
                payload=payload,
            )
        else:
            payload.update(
                {
                    "previous_evaluation_id": previous.evaluation_id,
                    "previous_energy": previous.energy,
                }
            )
            self._emit_domain(
                "nextConvergenceChecked",
                self.run_id,
                self.config.digest,
                str(active.iteration),
                active.evaluation_id,
                active.energy_hash,
                active.theta_hash,
                previous.evaluation_id,
                previous.energy_hash,
                token,
                payload=payload,
            )
        self._emit_domain(
            "convergenceTrue" if value else "convergenceFalse",
            self.run_id,
            self.config.digest,
            str(active.iteration),
            active.evaluation_id,
            active.energy_hash,
            payload={"converged": value, "energy_hash": active.energy_hash},
        )
        return value

    def authorize_objective_release(self) -> float:
        active = self._active()
        if active.energy is None or active.energy_hash is None:
            raise VerificationAbort("noValidEnergy", "energy has not been verified")
        self._emit_domain(
            "iterationPass",
            self.run_id,
            self.config.digest,
            str(active.iteration),
            active.evaluation_id,
            active.energy_hash,
        )
        self._emit_domain(
            "objectiveReleaseIntent",
            self.run_id,
            self.config.digest,
            str(active.iteration),
            active.evaluation_id,
            active.energy_hash,
        )
        return active.energy

    def authorize_optimizer_update(self, next_theta: Sequence[float]) -> str:
        if self.config.optimizer_protocol != "ask-tell":
            raise VerificationAbort(
                "wrongOptimizerProtocol",
                "authorize_optimizer_update requires optimizer_protocol='ask-tell'",
            )
        active = self._active()
        values = tuple(float(value) for value in next_theta)
        digest = vector_digest(values)
        self._emit_domain(
            "optimizerUpdateIntent",
            self.run_id,
            self.config.digest,
            str(active.iteration),
            active.evaluation_id,
            digest,
            payload={"next_theta": list(values), "next_theta_hash": digest},
        )
        return digest

    def mark_optimizer_updated(self, next_theta: Sequence[float]) -> None:
        if self.config.optimizer_protocol != "ask-tell":
            raise VerificationAbort(
                "wrongOptimizerProtocol",
                "mark_optimizer_updated requires optimizer_protocol='ask-tell'",
            )
        active = self._active()
        values = tuple(float(value) for value in next_theta)
        digest = vector_digest(values)
        self._emit_domain(
            "optimizerUpdated",
            self.run_id,
            self.config.digest,
            str(active.iteration),
            active.evaluation_id,
            digest,
            payload={"next_theta": list(values), "next_theta_hash": digest},
        )

    def authorize_and_commit_optimizer_update(
        self,
        optimizer: Any,
        update_token: object,
        next_theta: Sequence[float],
    ) -> str:
        """Approve an exact proposal, then cross the optimizer mutation boundary.

        The synchronous authorization event is fully acknowledged by both
        checkers before ``commit_update`` can be invoked.  A commit exception
        leaves the trace with an unmatched intent and therefore cannot produce
        a passing iteration.
        """

        values = tuple(float(value) for value in next_theta)
        digest = self.authorize_optimizer_update(values)
        commit = getattr(optimizer, "commit_update", None)
        if not callable(commit):
            raise VerificationAbort(
                "invalidAskTellOptimizer",
                "optimizer does not expose the required commit_update method",
            )
        commit(update_token, authorized_theta=values)
        self.mark_optimizer_updated(values)
        return digest

    def observe_opaque_optimizer_candidate(self, next_theta: Sequence[float]) -> None:
        """Link a SciPy-style objective callback to the prior checkpoint.

        This is observational: the optimizer has already chosen the candidate.
        The report therefore keeps inter_optimizer_commit_enforcement
        INCONCLUSIVE while still checking exact candidate-to-binding continuity.
        """
        if self.config.optimizer_protocol != "opaque":
            raise VerificationAbort(
                "wrongOptimizerProtocol",
                "observe_opaque_optimizer_candidate requires optimizer_protocol='opaque'",
            )
        if self.contracts.active is not None or not self.contracts.checkpoints:
            raise VerificationAbort(
                "noClosedCheckpoint", "opaque advance requires a closed checkpoint"
            )
        previous = self.contracts.checkpoints[-1]
        values = tuple(float(value) for value in next_theta)
        digest = vector_digest(values)
        self._emit_domain(
            "opaqueOptimizerAdvanced",
            self.run_id,
            self.config.digest,
            str(previous.iteration),
            previous.evaluation_id,
            digest,
            payload={"next_theta": list(values), "next_theta_hash": digest},
        )

    def close_iteration(self) -> None:
        active = self._active()
        if active.energy_hash is None or active.converged is None:
            raise VerificationAbort(
                "incompleteIteration", "cannot close before energy and convergence checks"
            )
        if active.iteration + 1 == self.config.max_iterations and not active.converged:
            self._emit_domain(
                "iterationLimitReached",
                self.run_id,
                self.config.digest,
                str(active.iteration),
                active.evaluation_id,
            )
        self._emit_domain(
            "iterationClosed",
            self.run_id,
            self.config.digest,
            str(active.iteration),
            active.evaluation_id,
            active.energy_hash,
            active.theta_hash,
            "T" if active.converged else "F",
            active.next_theta_hash or "none",
            payload={
                "iteration": active.iteration,
                "evaluation_id": active.evaluation_id,
                "energy": active.energy,
                "energy_hash": active.energy_hash,
                "theta_hash": active.theta_hash,
                "converged": active.converged,
                "next_theta_hash": active.next_theta_hash,
                "effective_term_samples": active.effective_term_samples,
            },
        )

    def finish(self, reason: TerminationReason) -> None:
        if reason == TerminationReason.ABORTED:
            self.abort("explicitAbort")
            return
        if self.contracts.active is not None:
            raise VerificationAbort("openIteration", "close the iteration before finish")
        if not self.contracts.checkpoints:
            raise VerificationAbort("noCheckpoint", "cannot finish without an iteration")
        last = self.contracts.checkpoints[-1]
        common = (
            self.run_id,
            self.config.digest,
            str(last.iteration),
            last.evaluation_id,
            last.energy_hash,
        )
        name = {
            TerminationReason.CONVERGED: "runConverged",
            TerminationReason.MAX_ITERATIONS: "runMaxIterations",
            TerminationReason.OPTIMIZER_STOPPED: "runOptimizerStopped",
        }[reason]
        self._emit_raw(name, *common)
        self._terminated = True
        self.report.terminal_reason = reason.value

    def abort(self, code: str) -> None:
        if self._terminated:
            return
        self._best_effort_abort(safe_atom(code))

    def seal_run(self) -> VerificationReport:
        if not self._terminated:
            raise VerificationAbort(
                "missingTerminal", "run must reach DONE or ABORT before runClosed"
            )
        if self._sealed:
            raise VerificationAbort("duplicateClose", "run is already sealed")
        self._emit_raw("runClosed", self.run_id, self.config.digest)
        self._sealed = True
        self.report.complete = True
        self.report.finish()
        if self.report_path is not None:
            self.report.write_json(self.report_path)
        return self.report

    def close(self) -> None:
        if self._closed:
            return
        if not self._sealed:
            self.report.add_inconclusive(
                "run_trace_complete",
                "session closed without an acknowledged runClosed event",
                source="python",
            )
        self.report.finish()
        if self.report_path is not None:
            self.report.write_json(self.report_path)
        try:
            self.monitor.close()
        finally:
            self.journal.close()
            self._closed = True

    def __enter__(self) -> "RuntimeSession":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc is not None and not self._terminated:
            self._best_effort_abort("driverException")
        self.close()
