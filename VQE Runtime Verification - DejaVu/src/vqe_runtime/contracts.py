from __future__ import annotations

from dataclasses import dataclass, field, replace
import math
import random
from typing import Any

from .config import (
    RuntimeConfig,
    canonical_digest,
    canonical_json,
    energy_digest,
    vector_digest,
)
from .events import RuntimeEvent
from .report import VerificationReport


EVENT_ARITIES: dict[str, int] = {
    "runStarted": 2,
    "activity": 3,
    "optimizerAskTellConfigured": 2,
    "optimizerOpaqueConfigured": 2,
    "firstIterationStarted": 5,
    "nextIterationStarted": 6,
    "parametersBound": 5,
    "termExpected": 6,
    "jobSubmitIntent": 6,
    "jobSubmitted": 7,
    "termObserved": 8,
    "measurementsSealed": 5,
    "numericValid": 6,
    "firstConvergenceChecked": 7,
    "nextConvergenceChecked": 9,
    "convergenceTrue": 5,
    "convergenceFalse": 5,
    "iterationPass": 5,
    "objectiveReleaseIntent": 5,
    "optimizerUpdateIntent": 5,
    "optimizerUpdated": 5,
    "opaqueOptimizerAdvanced": 5,
    "iterationLimitReached": 4,
    "iterationClosed": 8,
    "criticalFail": 5,
    "iterationAborted": 5,
    "runConverged": 5,
    "runMaxIterations": 5,
    "runOptimizerStopped": 5,
    "runAborted": 5,
    "runClosed": 2,
}

_ACTIVE_ITERATION_EVENTS = {
    "parametersBound",
    "termExpected",
    "jobSubmitIntent",
    "jobSubmitted",
    "termObserved",
    "measurementsSealed",
    "numericValid",
    "firstConvergenceChecked",
    "nextConvergenceChecked",
    "convergenceTrue",
    "convergenceFalse",
    "iterationPass",
    "objectiveReleaseIntent",
    "optimizerUpdateIntent",
    "optimizerUpdated",
    "iterationLimitReached",
    "iterationClosed",
    "iterationAborted",
}

_ACTIVITY_TARGET_EVENTS = _ACTIVE_ITERATION_EVENTS | {
    "optimizerAskTellConfigured",
    "optimizerOpaqueConfigured",
    "firstIterationStarted",
    "nextIterationStarted",
    "opaqueOptimizerAdvanced",
    "criticalFail",
}


@dataclass(frozen=True, slots=True)
class ObservedTerm:
    term_id: str
    expectation: float
    shots: int | None
    counts_ones: int | None
    pub_index: int | None = None
    raw_evidence_sha256: str | None = None
    executable_circuit_qpy_sha256: str | None = None


@dataclass(slots=True)
class ActiveIteration:
    iteration: int
    evaluation_id: str
    theta: tuple[float, ...]
    theta_hash: str
    previous_evaluation_id: str | None
    phase: str = "started"
    declared_submission_id: str | None = None
    declared_terms: set[str] = field(default_factory=set)
    declared_pub_indices: dict[str, int] = field(default_factory=dict)
    declared_circuit_hashes: dict[str, str] = field(default_factory=dict)
    submission_id: str | None = None
    external_job_id: str | None = None
    observed: dict[str, ObservedTerm] = field(default_factory=dict)
    energy: float | None = None
    energy_hash: str | None = None
    effective_term_samples: int = 0
    converged: bool | None = None
    convergence_certified: bool = False
    passed: bool = False
    released: bool = False
    update_intent_recorded: bool = False
    update_applied: bool = False
    stable_count: int = 0
    energy_delta: float = 0.0
    next_theta: tuple[float, ...] | None = None
    next_theta_hash: str | None = None
    limit_reached: bool = False


@dataclass(frozen=True, slots=True)
class Checkpoint:
    iteration: int
    evaluation_id: str
    theta_hash: str
    energy: float
    energy_hash: str
    converged: bool
    stable_count: int
    next_theta_hash: str | None
    effective_term_samples: int
    limit_reached: bool


class ContractEngine:
    """Executable data contracts shared by online instrumentation and replay.

    DejaVu remains the authority for temporal relations. This engine validates
    schema, arithmetic, identities, resource totals, and finite-trace closure.
    """

    def __init__(self, config: RuntimeConfig, report: VerificationReport) -> None:
        self.config = config
        self.report = report
        self.run_id = report.run_id
        self.expected_seq = 1
        self.started = False
        self.active: ActiveIteration | None = None
        self.checkpoints: list[Checkpoint] = []
        self.terminal_reason: str | None = None
        self.critical_failure = False
        self.failure_context: tuple[str, str, str] | None = None
        self.closed = False
        self.total_effective_term_samples = 0
        self._missing_counts_reported = False
        self._unverified_samples_reported = False
        self.optimizer_protocol_certificate: str | None = None
        self.seen_evaluation_ids: set[str] = set()
        self.seen_submission_ids: set[str] = set()
        self.seen_external_job_ids: set[str] = set()
        self.seen_raw_evidence_hashes: set[str] = set()
        self.pending_activity: str | None = None

    def _fail(self, property_id: str, message: str, event: RuntimeEvent) -> None:
        self.report.add_failure(property_id, message, seq=event.seq)

    @staticmethod
    def _number(value: Any) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        result = float(value)
        return result if math.isfinite(result) else None

    @staticmethod
    def _integer(value: Any) -> int | None:
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value

    @staticmethod
    def _canonical_equal(left: Any, right: Any) -> bool:
        try:
            return canonical_json(left) == canonical_json(right)
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _sha256(value: Any) -> str | None:
        if (
            isinstance(value, str)
            and len(value) == 64
            and all(character in "0123456789abcdef" for character in value)
        ):
            return value
        return None

    def consume(self, event: RuntimeEvent) -> bool:
        before = len(self.report.findings)
        if event.seq != self.expected_seq:
            self._fail(
                "run_event_sequence",
                f"expected event sequence {self.expected_seq}, got {event.seq}",
                event,
            )
            self.expected_seq = event.seq + 1
        else:
            self.expected_seq += 1
        expected_arity = EVENT_ARITIES.get(event.name)
        if expected_arity is None:
            self._fail("run_event_schema", f"unknown event {event.name!r}", event)
            return False
        if len(event.args) != expected_arity:
            self._fail(
                "run_event_schema",
                f"{event.name} has arity {len(event.args)}, expected {expected_arity}",
                event,
            )
            return False
        if event.name == "activity":
            activity_kind = event.args[2]
            if self.pending_activity is not None:
                self._fail(
                    "run_activity_pairing",
                    f"activity for {activity_kind!r} replaced pending "
                    f"{self.pending_activity!r}",
                    event,
                )
            if activity_kind not in _ACTIVITY_TARGET_EVENTS:
                self._fail(
                    "run_activity_pairing",
                    f"activity names unsupported domain event {activity_kind!r}",
                    event,
                )
            self.pending_activity = activity_kind
        else:
            if event.name in _ACTIVITY_TARGET_EVENTS:
                if self.pending_activity != event.name:
                    self._fail(
                        "run_activity_pairing",
                        f"{event.name} lacks an immediately preceding matching activity",
                        event,
                    )
            elif self.pending_activity is not None:
                self._fail(
                    "run_activity_pairing",
                    f"pending activity {self.pending_activity!r} was not completed",
                    event,
                )
            self.pending_activity = None
        if event.args[0] != self.run_id:
            self._fail("inter_run_identity", "run_id changed inside trace", event)
        if event.args[1] != self.config.digest:
            self._fail(
                "inter_config_immutable", "configuration hash changed inside trace", event
            )
        if not self.started and event.name != "runStarted":
            self._fail(
                "run_start_precedes_activity",
                f"{event.name} occurred before runStarted",
                event,
            )
        if self.closed and event.name != "runClosed":
            self._fail(
                "run_terminal_absorbing", "event occurred after runClosed", event
            )
        elif self.terminal_reason is not None and event.name != "runClosed":
            self._fail(
                "run_terminal_absorbing", "event occurred after terminal state", event
            )
        if self.critical_failure and event.name not in {
            "activity",
            "iterationAborted",
            "runAborted",
            "runClosed",
        }:
            self._fail(
                "run_failure_forces_abort",
                f"{event.name} occurred after criticalFail instead of the abort path",
                event,
            )
        if event.name in _ACTIVE_ITERATION_EVENTS:
            if self.active is None:
                self._fail(
                    "intra_event_context",
                    f"{event.name} occurred without an open iteration",
                    event,
                )
            elif (
                event.args[2] != str(self.active.iteration)
                or event.args[3] != self.active.evaluation_id
            ):
                self._fail(
                    "intra_event_context",
                    f"{event.name} refers to a different iteration/evaluation",
                    event,
                )
        handler = getattr(self, f"_on_{event.name}", None)
        if handler is not None:
            try:
                handler(event)
            except Exception as exc:
                self._fail(
                    "run_event_schema",
                    f"malformed {event.name} payload: {exc}",
                    event,
                )
        self.report.event_count = max(self.report.event_count, event.seq)
        return not any(
            finding.status.value == "fail"
            for finding in self.report.findings[before:]
        )

    def _on_runStarted(self, event: RuntimeEvent) -> None:
        if self.started:
            self._fail("run_single_start", "runStarted occurred more than once", event)
        if event.payload.get("config_hash") != self.config.digest:
            self._fail(
                "inter_config_immutable",
                "runStarted payload does not contain the resolved configuration hash",
                event,
            )
        snapshot = event.payload.get("config")
        if not self._canonical_equal(
            snapshot, self.config.as_dict(include_source=False)
        ):
            self._fail(
                "inter_config_immutable",
                "runStarted configuration snapshot differs from the checker configuration",
                event,
            )
        provenance = event.payload.get("execution_provenance")
        provenance_hash = event.payload.get("execution_provenance_hash")
        if not isinstance(provenance, dict) or not all(
            isinstance(key, str) for key in provenance
        ):
            self._fail(
                "run_execution_provenance",
                "runStarted must contain a JSON execution-provenance object",
                event,
            )
        else:
            expected_identity = {
                "mode": self.config.mode,
                "system": self.config.system,
                "backend": self.config.backend,
                "seed": self.config.seed,
            }
            if any(
                type(provenance.get(key)) is not type(value)
                or provenance.get(key) != value
                for key, value in expected_identity.items()
            ):
                self._fail(
                    "run_execution_provenance",
                    "execution provenance disagrees with the resolved configuration",
                    event,
                )
            try:
                calculated_provenance_hash = canonical_digest(provenance)
            except (TypeError, ValueError) as exc:
                self._fail(
                    "run_execution_provenance",
                    f"execution provenance is not canonical JSON: {exc}",
                    event,
                )
            else:
                if provenance_hash != calculated_provenance_hash:
                    self._fail(
                        "run_execution_provenance",
                        "execution provenance hash mismatch",
                        event,
                    )
                self.report.execution_provenance = dict(provenance)
            if self.config.is_sampler_mode:
                sampler_experiment = provenance.get("sampler_experiment")
                expected_order = [
                    term.term_id for term in self.config.hamiltonian.terms
                ]
                expected_paulis = [
                    term.pauli for term in self.config.hamiltonian.terms
                ]
                expected_api_primitive = (
                    "qiskit_ibm_runtime.SamplerV2"
                    if self.config.mode == "qiskit-runtime-sampler"
                    else "qiskit.primitives.StatevectorSampler"
                )
                valid_options = False
                if isinstance(sampler_experiment, dict):
                    api_options = sampler_experiment.get("api_options")
                    valid_options = bool(
                        isinstance(api_options, dict)
                        and api_options.get("primitive") == expected_api_primitive
                        and api_options.get("run_shots")
                        == self.config.shots_per_term
                    )
                    if self.config.mode == "qiskit-runtime-sampler":
                        valid_options = valid_options and api_options.get(
                            "constructor"
                        ) == {
                            "default_shots": self.config.shots_per_term,
                            "dynamical_decoupling": {"enable": False},
                            "execution": {
                                "init_qubits": True,
                                "meas_type": "classified",
                            },
                            "twirling": {
                                "enable_gates": False,
                                "enable_measure": False,
                            },
                        }
                    else:
                        valid_options = valid_options and api_options.get(
                            "constructor"
                        ) == {
                            "default_shots": self.config.shots_per_term,
                            "seed": self.config.seed,
                        }
                initial_source = random.Random(self.config.seed)
                expected_initial_theta = [
                    initial_source.uniform(
                        self.config.parameter_lower,
                        self.config.parameter_upper,
                    )
                    for _ in range(self.config.parameter_count)
                ]
                if (
                    not isinstance(sampler_experiment, dict)
                    or self.config.sampler is None
                    or self.config.optimizer is None
                    or sampler_experiment.get("pubs_per_evaluation")
                    != len(expected_order)
                    or sampler_experiment.get("term_order") != expected_order
                    or sampler_experiment.get("pauli_order") != expected_paulis
                    or sampler_experiment.get("shots_per_pub")
                    != self.config.shots_per_term
                    or sampler_experiment.get("physical_shots_per_evaluation")
                    != len(expected_order) * self.config.shots_per_term
                    or sampler_experiment.get("maximum_submitted_pubs")
                    != self.config.max_iterations * len(expected_order)
                    or sampler_experiment.get("maximum_physical_shots")
                    != self.config.shot_budget
                    or sampler_experiment.get("bitstring_order")
                    != self.config.sampler.bitstring_order
                    or sampler_experiment.get("raw_evidence_format")
                    != self.config.sampler.raw_evidence_format
                    or sampler_experiment.get("sampler_policy")
                    != self.config.sampler.as_dict()
                    or sampler_experiment.get("optimizer_policy")
                    != self.config.optimizer.as_dict()
                    or sampler_experiment.get("optimizer_gate_order")
                    != [
                        "preview_update_no_mutation",
                        "verifier_authorize_exact_theta",
                        "commit_update",
                        "verifier_record_commit",
                    ]
                    or provenance.get("initial_theta") != expected_initial_theta
                    or provenance.get("initial_theta_hash")
                    != vector_digest(expected_initial_theta)
                    or not valid_options
                ):
                    self._fail(
                        "run_execution_options",
                        "Sampler execution provenance disagrees with the fixed "
                        "four-PUB raw-count policy",
                        event,
                    )
                self.report.mark_checked("run_execution_options")
        self.started = True
        self.report.mark_checked(
            "run_single_start", "inter_config_immutable", "run_execution_provenance"
        )
        if self.config.optimizer_protocol == "opaque":
            self.report.add_inconclusive(
                "inter_optimizer_commit_enforcement",
                "opaque optimizers expose the next candidate only after their internal update; "
                "candidate-to-binding continuity is checked observationally",
                seq=event.seq,
            )

    def _optimizer_protocol_configured(
        self, event: RuntimeEvent, protocol: str
    ) -> None:
        if self.optimizer_protocol_certificate is not None:
            self._fail(
                "inter_optimizer_protocol",
                "optimizer protocol was certified more than once",
                event,
            )
        if self.active is not None or self.checkpoints or self.seen_evaluation_ids:
            self._fail(
                "inter_optimizer_protocol",
                "optimizer protocol must be certified during INIT before any iteration",
                event,
            )
        if self.config.optimizer_protocol != protocol:
            self._fail(
                "inter_optimizer_protocol",
                f"trace certifies {protocol!r}, configured protocol is "
                f"{self.config.optimizer_protocol!r}",
                event,
            )
        if event.payload.get("optimizer_protocol") != protocol:
            self._fail(
                "inter_optimizer_protocol",
                "optimizer protocol certificate payload disagrees with its event",
                event,
            )
        self.optimizer_protocol_certificate = protocol
        self.report.mark_checked("inter_optimizer_protocol")

    def _on_optimizerAskTellConfigured(self, event: RuntimeEvent) -> None:
        self._optimizer_protocol_configured(event, "ask-tell")

    def _on_optimizerOpaqueConfigured(self, event: RuntimeEvent) -> None:
        self._optimizer_protocol_configured(event, "opaque")

    def _iteration_payload(self, event: RuntimeEvent) -> tuple[int, str, tuple[float, ...], str]:
        iteration = self._integer(event.payload.get("iteration"))
        evaluation_id = event.payload.get("evaluation_id")
        raw_theta = event.payload.get("theta")
        theta_hash = event.payload.get("theta_hash")
        if iteration is None or iteration < 0:
            raise ValueError("iteration must be a nonnegative integer")
        if not isinstance(evaluation_id, str) or not evaluation_id:
            raise ValueError("evaluation_id must be a nonempty string")
        if not isinstance(raw_theta, list) or not raw_theta:
            raise ValueError("theta must be a nonempty array")
        theta_values: list[float] = []
        for value in raw_theta:
            parsed = self._number(value)
            if parsed is None:
                raise ValueError("theta contains a non-finite or nonnumeric value")
            theta_values.append(parsed)
        theta = tuple(theta_values)
        if len(theta) != self.config.parameter_count:
            self._fail(
                "intra_parameter_dimension",
                f"theta has length {len(theta)}, expected {self.config.parameter_count}",
                event,
            )
        calculated_hash = vector_digest(theta)
        if (
            event.args[2] != str(iteration)
            or event.args[3] != evaluation_id
            or theta_hash != calculated_hash
            or event.args[-1] != calculated_hash
        ):
            self._fail("intra_parameter_freshness", "theta hash mismatch", event)
        if not all(
            self.config.parameter_lower <= value <= self.config.parameter_upper
            for value in theta
        ):
            self._fail(
                "intra_parameter_domain",
                "one or more variational parameters are outside the configured domain",
                event,
            )
        return iteration, evaluation_id, theta, calculated_hash

    def _begin_iteration(self, event: RuntimeEvent, *, first: bool) -> None:
        if self.optimizer_protocol_certificate != self.config.optimizer_protocol:
            self._fail(
                "inter_optimizer_protocol",
                "iteration started before the configured optimizer protocol certificate",
                event,
            )
        if self.active is not None:
            self._fail(
                "inter_no_overlapping_iterations",
                "a new iteration started while another iteration remained open",
                event,
            )
        iteration, evaluation_id, theta, theta_hash = self._iteration_payload(event)
        expected = len(self.checkpoints)
        if iteration != expected:
            self._fail(
                "inter_iteration_contiguous",
                f"expected iteration {expected}, got {iteration}",
                event,
            )
        if iteration >= self.config.max_iterations:
            self._fail(
                "run_resource_budget",
                "an iteration started after the configured evaluation limit",
                event,
            )
        if first != (expected == 0):
            self._fail(
                "inter_iteration_contiguous",
                "first/next iteration event kind disagrees with trace position",
                event,
            )
        if evaluation_id in self.seen_evaluation_ids:
            self._fail(
                "inter_evaluation_identity_unique",
                f"evaluation ID {evaluation_id!r} was reused",
                event,
            )
        self.seen_evaluation_ids.add(evaluation_id)
        previous_evaluation_id = None
        if not first:
            previous_evaluation_id = event.payload.get("previous_evaluation_id")
            previous = self.checkpoints[-1]
            if previous_evaluation_id != previous.evaluation_id:
                self._fail(
                    "inter_checkpoint_continuity",
                    "next iteration does not name the last verified checkpoint",
                    event,
                )
            if event.args[4] != previous.evaluation_id:
                self._fail(
                    "inter_checkpoint_continuity",
                    "next-iteration monitor arguments name a stale checkpoint",
                    event,
                )
            if previous.converged:
                self._fail(
                    "inter_no_successor_after_convergence",
                    "a successor iteration started after convergence",
                    event,
                )
            if previous.next_theta_hash != theta_hash:
                self._fail(
                    "inter_theta_continuity",
                    "next bound theta does not equal the authorized optimizer output",
                    event,
                )
        self.active = ActiveIteration(
            iteration, evaluation_id, theta, theta_hash, previous_evaluation_id
        )
        self.report.mark_checked(
            "intra_parameter_domain",
            "intra_parameter_dimension",
            "intra_parameter_freshness",
            "inter_iteration_contiguous",
            "inter_checkpoint_continuity",
            "inter_theta_continuity",
        )

    def _on_firstIterationStarted(self, event: RuntimeEvent) -> None:
        self._begin_iteration(event, first=True)

    def _on_nextIterationStarted(self, event: RuntimeEvent) -> None:
        self._begin_iteration(event, first=False)

    def _on_parametersBound(self, event: RuntimeEvent) -> None:
        if self.active is None:
            self._fail("intra_binding_after_start", "parameters bound without iteration", event)
            return
        if event.args[4] != self.active.theta_hash:
            self._fail(
                "intra_parameter_freshness",
                "bound parameter hash differs from the iteration candidate",
                event,
            )
        raw_theta = event.payload.get("theta")
        if (
            event.payload.get("theta_hash") != self.active.theta_hash
            or not isinstance(raw_theta, list)
            or len(raw_theta) != len(self.active.theta)
            or any(
                self._number(value) is None
                or float(value) != expected
                for value, expected in zip(raw_theta, self.active.theta)
            )
        ):
            self._fail(
                "intra_parameter_freshness",
                "parameter-binding payload disagrees with the active candidate",
                event,
            )
        self.active.phase = "bound"

    def _on_termExpected(self, event: RuntimeEvent) -> None:
        active = self.active
        if active is None:
            return
        if active.phase != "bound":
            self._fail(
                "intra_term_after_binding",
                "term manifest must be declared after binding and before submission intent",
                event,
            )
        submission_id = event.args[4]
        term_id = event.args[5]
        expected = {term.term_id: term for term in self.config.hamiltonian.terms}
        if term_id not in expected:
            self._fail(
                "intra_term_identity", f"undeclared expected term {term_id!r}", event
            )
        elif (
            event.payload.get("term_id") != term_id
            or event.payload.get("pauli") != expected[term_id].pauli
        ):
            self._fail(
                "intra_term_identity",
                f"term manifest payload disagrees with {term_id!r}",
                event,
            )
        if term_id in active.declared_terms:
            self._fail(
                "intra_term_identity", f"term {term_id!r} was declared twice", event
            )
        if (
            active.declared_submission_id is not None
            and active.declared_submission_id != submission_id
        ):
            self._fail(
                "intra_backend_provenance",
                "expected terms were split across different submission IDs",
                event,
            )
        if self.config.is_sampler_mode and term_id in expected:
            expected_index = next(
                index
                for index, term in enumerate(self.config.hamiltonian.terms)
                if term.term_id == term_id
            )
            pub_index = self._integer(event.payload.get("pub_index"))
            requested_shots = self._integer(
                event.payload.get("requested_shots")
            )
            circuit_hash = self._sha256(
                event.payload.get("parameterized_circuit_qpy_sha256")
            )
            if (
                pub_index != expected_index
                or event.payload.get("expected_pub_index") != expected_index
                or requested_shots != self.config.shots_per_term
                or self.config.sampler is None
                or event.payload.get("measurement_strategy")
                != self.config.sampler.measurement_strategy
                or circuit_hash is None
            ):
                self._fail(
                    "intra_pub_assignment",
                    f"term {term_id!r} does not declare its fixed PUB/circuit policy",
                    event,
                )
            elif pub_index in active.declared_pub_indices.values():
                self._fail(
                    "intra_pub_assignment",
                    f"PUB index {pub_index} was assigned more than once",
                    event,
                )
            else:
                active.declared_pub_indices[term_id] = pub_index
                active.declared_circuit_hashes[term_id] = circuit_hash
            self.report.mark_checked("intra_pub_assignment")
        active.declared_submission_id = submission_id
        active.declared_terms.add(term_id)

    def _on_jobSubmitIntent(self, event: RuntimeEvent) -> None:
        if self.active is None:
            return
        if self.active.submission_id is not None:
            self._fail(
                "intra_backend_provenance",
                "more than one job submission intent occurred in an iteration",
                event,
            )
        if event.args[4] in self.seen_submission_ids:
            self._fail(
                "inter_submission_identity_unique",
                f"submission ID {event.args[4]!r} was reused",
                event,
            )
        self.seen_submission_ids.add(event.args[4])
        expected_terms = {term.term_id for term in self.config.hamiltonian.terms}
        if (
            self.active.declared_submission_id != event.args[4]
            or self.active.declared_terms != expected_terms
        ):
            self._fail(
                "intra_term_completeness",
                "submission intent does not match a complete declared term manifest",
                event,
            )
        if self.config.is_sampler_mode:
            expected_order = [
                term.term_id for term in self.config.hamiltonian.terms
            ]
            expected_pubs = len(expected_order)
            if (
                event.payload.get("pub_count") != expected_pubs
                or event.payload.get("term_order") != expected_order
                or event.payload.get("shots_per_pub")
                != self.config.shots_per_term
                or event.payload.get("requested_physical_shots")
                != expected_pubs * self.config.shots_per_term
                or set(self.active.declared_pub_indices)
                != set(expected_order)
                or sorted(self.active.declared_pub_indices.values())
                != list(range(expected_pubs))
            ):
                self._fail(
                    "intra_pub_assignment",
                    "submission intent does not describe four independent ordered PUBs",
                    event,
                )
        self.active.submission_id = event.args[4]
        if event.args[5] != self.active.theta_hash:
            self._fail(
                "intra_parameter_freshness", "submission uses stale parameters", event
            )
        if (
            event.payload.get("submission_id") != event.args[4]
            or event.payload.get("theta_hash") != event.args[5]
        ):
            self._fail(
                "intra_backend_provenance",
                "submission-intent payload disagrees with monitor-visible identities",
                event,
            )
        self.active.phase = "submit_intent"

    def _on_jobSubmitted(self, event: RuntimeEvent) -> None:
        if self.active is None:
            return
        if self.active.external_job_id is not None:
            self._fail(
                "intra_backend_provenance",
                "jobSubmitted occurred more than once for the iteration",
                event,
            )
        if event.args[5] in self.seen_external_job_ids:
            self._fail(
                "inter_backend_job_unique",
                f"backend job ID {event.args[5]!r} was reused",
                event,
            )
        self.seen_external_job_ids.add(event.args[5])
        if (
            event.args[4] != self.active.submission_id
            or event.args[6] != self.active.theta_hash
        ):
            self._fail(
                "intra_backend_provenance",
                "submitted job does not match the authorized submission/theta",
                event,
            )
        external = event.payload.get("external_job_id")
        if not isinstance(external, str) or not external:
            self._fail(
                "intra_backend_provenance", "backend job ID must be recorded", event
            )
        if isinstance(external, str) and event.args[5] != external:
            self._fail(
                "intra_backend_provenance",
                "monitor-visible backend job ID differs from the journal payload",
                event,
            )
        if (
            event.payload.get("submission_id") != event.args[4]
            or event.payload.get("theta_hash") != event.args[6]
        ):
            self._fail(
                "intra_backend_provenance",
                "job-submission payload disagrees with monitor-visible identities",
                event,
            )
        self.active.external_job_id = external if isinstance(external, str) else None
        self.active.phase = "submitted"

    def _on_termObserved(self, event: RuntimeEvent) -> None:
        active = self.active
        if active is None:
            self._fail("intra_term_identity", "term observed outside an iteration", event)
            return
        payload = event.payload
        term_id = payload.get("term_id")
        if not isinstance(term_id, str):
            self._fail("intra_term_identity", "term_id must be a string", event)
            return
        expected = {term.term_id: term for term in self.config.hamiltonian.terms}
        spec = expected.get(term_id)
        if spec is None:
            self._fail("intra_term_identity", f"undeclared term {term_id!r}", event)
            return
        if (
            event.args[4] != active.submission_id
            or event.args[5] != active.external_job_id
            or event.args[6] != term_id
            or event.args[7] != active.theta_hash
        ):
            self._fail(
                "intra_term_identity",
                "term monitor arguments disagree with submission, term, or theta payload",
                event,
            )
        if term_id in active.observed:
            self._fail("intra_term_identity", f"duplicate term {term_id!r}", event)
            return
        if payload.get("pauli") != spec.pauli:
            self._fail("intra_term_identity", f"Pauli mismatch for {term_id}", event)
        expectation = self._number(payload.get("expectation"))
        if expectation is None:
            self._fail(
                "intra_expectation_domain", f"non-finite expectation for {term_id}", event
            )
            return
        tolerance = self.config.expectation_abs_tolerance
        if not -1.0 - tolerance <= expectation <= 1.0 + tolerance:
            self._fail(
                "intra_expectation_domain",
                f"expectation for {term_id} is outside [-1, 1]",
                event,
            )
        shots_raw = payload.get("shots")
        shots = None if shots_raw is None else self._integer(shots_raw)
        if shots_raw is not None and (shots is None or shots < 0):
            self._fail(
                "intra_shot_consistency",
                "shots must be null (unverified) or a nonnegative integer",
                event,
            )
            return
        counts_raw = payload.get("counts_ones")
        counts_ones = None if counts_raw is None else self._integer(counts_raw)
        pub_index: int | None = None
        raw_evidence_hash: str | None = None
        executable_circuit_hash: str | None = None
        if counts_raw is not None and counts_ones is None:
            self._fail(
                "intra_shot_consistency",
                "counts_ones must be null or an integer",
                event,
            )
            return
        if self.config.shots_per_term == 0:
            if shots != 0 or counts_ones is not None:
                self._fail(
                    "intra_shot_consistency",
                    "exact statevector observations must not claim finite shots/counts",
                    event,
                )
        elif shots is None:
            if counts_ones is not None:
                self._fail(
                    "intra_shot_consistency",
                    "raw counts cannot be certified without an observed shot total",
                    event,
                )
            elif self.config.require_raw_counts:
                self._fail(
                    "intra_shot_consistency",
                    f"raw counts and observed shots are required for {term_id}",
                    event,
                )
            elif not self._unverified_samples_reported:
                self.report.add_inconclusive(
                    "intra_shot_consistency",
                    "the backend returned expectations without observed shot/count metadata",
                    seq=event.seq,
                )
                self.report.add_inconclusive(
                    "run_resource_budget",
                    "requested shots are configured, but executed sample totals were not observed",
                    seq=event.seq,
                )
                self.report.add_inconclusive(
                    "inter_budget_continuity",
                    "cross-iteration sample-budget continuity cannot be established without observed totals",
                    seq=event.seq,
                )
                self._unverified_samples_reported = True
        else:
            if shots <= 0:
                self._fail(
                    "intra_shot_consistency",
                    "shot-based observations must report a positive shot total",
                    event,
                )
            if shots != self.config.shots_per_term:
                self._fail(
                    "intra_shot_consistency",
                    f"term {term_id} used {shots} shots, expected {self.config.shots_per_term}",
                    event,
                )
            if counts_ones is None:
                if self.config.require_raw_counts:
                    self._fail(
                        "intra_shot_consistency",
                        f"raw counts are required for shot-based term {term_id}",
                        event,
                    )
                elif not self._missing_counts_reported:
                    self.report.add_inconclusive(
                        "intra_shot_consistency",
                        "shot totals were observed, but raw counts were unavailable",
                        seq=event.seq,
                    )
                    self._missing_counts_reported = True
            elif shots <= 0 or not 0 <= counts_ones <= shots:
                self._fail(
                    "intra_shot_consistency", "counts_ones must lie within shots", event
                )
            else:
                reconstructed = 1.0 - 2.0 * counts_ones / shots
                if abs(reconstructed - expectation) > tolerance:
                    self._fail(
                        "intra_shot_consistency",
                        f"term {term_id} expectation disagrees with raw counts",
                        event,
                    )
        if self.config.is_sampler_mode:
            negative_count = self._integer(
                payload.get("negative_eigenvalue_count")
            )
            pub_index = self._integer(payload.get("pub_index"))
            raw_evidence_hash = self._sha256(
                payload.get("raw_evidence_sha256")
            )
            executable_circuit_hash = self._sha256(
                payload.get("executable_circuit_qpy_sha256")
            )
            expected_pub_index = active.declared_pub_indices.get(term_id)
            already_observed_indices = {
                item.pub_index
                for item in active.observed.values()
                if item.pub_index is not None
            }
            if (
                payload.get("requested_shots") != self.config.shots_per_term
                or payload.get("observed_shots") != shots
                or pub_index != expected_pub_index
                or pub_index in already_observed_indices
            ):
                self._fail(
                    "intra_pub_assignment",
                    f"term {term_id} observation does not match its authorized PUB",
                    event,
                )
            if negative_count is None or negative_count != counts_ones:
                self._fail(
                    "intra_parity_reconstruction",
                    "negative_eigenvalue_count is missing or differs from the "
                    "legacy counts_ones alias",
                    event,
                )
            elif shots is not None and shots > 0:
                reconstructed = 1.0 - 2.0 * negative_count / shots
                if abs(reconstructed - expectation) > tolerance:
                    self._fail(
                        "intra_parity_reconstruction",
                        f"term {term_id} expectation disagrees with negative parity",
                        event,
                    )
            if raw_evidence_hash is None or executable_circuit_hash is None:
                self._fail(
                    "intra_raw_evidence_link",
                    f"term {term_id} lacks a valid evidence or executable-circuit hash",
                    event,
                )
            elif raw_evidence_hash in self.seen_raw_evidence_hashes:
                self._fail(
                    "inter_raw_evidence_identity_unique",
                    "raw evidence was reused across PUB observations",
                    event,
                )
            else:
                self.seen_raw_evidence_hashes.add(raw_evidence_hash)
            self.report.mark_checked(
                "intra_pub_assignment",
                "intra_parity_reconstruction",
                "intra_raw_evidence_link",
                "inter_raw_evidence_identity_unique",
            )
        active.observed[term_id] = ObservedTerm(
            term_id,
            expectation,
            shots,
            counts_ones,
            pub_index,
            raw_evidence_hash,
            executable_circuit_hash,
        )
        if shots is not None and shots > 0:
            active.effective_term_samples += shots
        self.report.mark_checked(
            "intra_term_identity",
            "intra_expectation_domain",
            "intra_shot_consistency",
        )

    def _on_measurementsSealed(self, event: RuntimeEvent) -> None:
        if self.active is None:
            return
        if event.args[4] != self.active.submission_id:
            self._fail(
                "intra_term_completeness",
                "measurement seal names a different submission",
                event,
            )
        expected = {term.term_id for term in self.config.hamiltonian.terms}
        actual = set(self.active.observed)
        if actual != expected:
            self._fail(
                "intra_term_completeness",
                f"measurement set mismatch: missing={sorted(expected-actual)}, "
                f"unexpected={sorted(actual-expected)}",
                event,
            )
        observed_ids = event.payload.get("observed_term_ids")
        if observed_ids != sorted(actual):
            self._fail(
                "intra_term_completeness",
                "measurement-seal payload disagrees with observed term identities",
                event,
            )
        if self.config.is_sampler_mode:
            expected_pub_indices = list(range(len(self.config.hamiltonian.terms)))
            observed_pub_indices = sorted(
                item.pub_index
                for item in self.active.observed.values()
                if item.pub_index is not None
            )
            evidence_hashes = sorted(
                item.raw_evidence_sha256
                for item in self.active.observed.values()
                if item.raw_evidence_sha256 is not None
            )
            if (
                observed_pub_indices != expected_pub_indices
                or event.payload.get("observed_pub_indices")
                != expected_pub_indices
                or event.payload.get("pub_count") != len(expected_pub_indices)
            ):
                self._fail(
                    "intra_pub_assignment",
                    "measurement seal does not contain exactly one PUB per term",
                    event,
                )
            if (
                event.payload.get("verified_physical_shots")
                != self.active.effective_term_samples
                or self.active.effective_term_samples
                != len(expected_pub_indices) * self.config.shots_per_term
            ):
                self._fail(
                    "run_physical_shot_budget",
                    "measurement seal physical-shot total is inconsistent",
                    event,
                )
            if (
                len(evidence_hashes) != len(expected_pub_indices)
                or event.payload.get("raw_evidence_sha256") != evidence_hashes
            ):
                self._fail(
                    "intra_raw_evidence_link",
                    "measurement seal does not bind every PUB evidence record",
                    event,
                )
            self.report.mark_checked(
                "intra_pub_assignment",
                "intra_raw_evidence_link",
                "run_physical_shot_budget",
            )
        self.active.phase = "sealed"
        self.report.mark_checked("intra_term_completeness")

    def _on_numericValid(self, event: RuntimeEvent) -> None:
        active = self.active
        if active is None:
            return
        reported = self._number(event.payload.get("reported_energy"))
        if reported is None:
            self._fail("intra_energy_computation", "reported energy is non-finite", event)
            return
        terms = {term.term_id: term for term in self.config.hamiltonian.terms}
        try:
            reconstructed = math.fsum(
                terms[term_id].coeff_int
                * observation.expectation
                / self.config.hamiltonian.coeff_scale
                for term_id, observation in active.observed.items()
            )
        except KeyError:
            reconstructed = math.nan
        if not math.isfinite(reconstructed) or abs(reported - reconstructed) > self.config.energy_abs_tolerance:
            self._fail(
                "intra_energy_computation",
                f"reported energy {reported!r} disagrees with reconstruction {reconstructed!r}",
                event,
            )
        if abs(reported) > (
            self.config.hamiltonian.coefficient_bound
            + self.config.energy_abs_tolerance
        ):
            self._fail(
                "intra_energy_bound",
                "energy exceeds the coefficient-induced Hamiltonian bound",
                event,
            )
        digest = energy_digest(reported)
        if event.args[4] != digest or event.args[5] != active.theta_hash:
            self._fail(
                "intra_energy_freshness",
                "energy identity or parameter provenance is stale",
                event,
            )
        active.energy = reported
        active.energy_hash = digest
        active.phase = "aggregated"
        self.report.mark_checked(
            "intra_energy_computation", "intra_energy_bound", "intra_energy_freshness"
        )

    def _check_convergence(self, event: RuntimeEvent, *, first: bool) -> None:
        active = self.active
        if active is None or active.energy is None:
            return
        if active.converged is not None:
            self._fail(
                "intra_convergence_check_once",
                "convergence was checked more than once in the iteration",
                event,
            )
        payload = event.payload
        declared = payload.get("converged")
        stable = self._integer(payload.get("stable_count"))
        delta = self._number(payload.get("energy_delta"))
        if not isinstance(declared, bool) or stable is None or stable < 0 or delta is None:
            self._fail(
                "inter_convergence_consistency",
                "convergence fields are missing or malformed",
                event,
            )
            return
        if first:
            expected_delta = 0.0
            expected_stable = 0
            expected_converged = False
            if self.checkpoints:
                self._fail(
                    "inter_previous_energy_continuity",
                    "first convergence event occurred after a checkpoint",
                    event,
                )
        else:
            if not self.checkpoints:
                self._fail(
                    "inter_previous_energy_continuity",
                    "next convergence event has no prior checkpoint",
                    event,
                )
                return
            previous = self.checkpoints[-1]
            expected_delta = abs(active.energy - previous.energy)
            within = expected_delta <= (
                self.config.convergence_tolerance + self.config.energy_abs_tolerance
            )
            expected_stable = previous.stable_count + 1 if within else 0
            expected_converged = (
                within
                and active.iteration + 1 >= self.config.min_iterations
                and expected_stable >= self.config.convergence_patience
            )
            if payload.get("previous_evaluation_id") != previous.evaluation_id:
                self._fail(
                    "inter_previous_energy_continuity",
                    "convergence check did not use the last verified evaluation",
                    event,
                )
            previous_energy = self._number(payload.get("previous_energy"))
            if previous_energy is None or abs(previous_energy - previous.energy) > self.config.energy_abs_tolerance:
                self._fail(
                    "inter_previous_energy_continuity",
                    "convergence check used a stale previous energy",
                    event,
                )
            if (
                event.args[6] != previous.evaluation_id
                or event.args[7] != previous.energy_hash
            ):
                self._fail(
                    "inter_previous_energy_continuity",
                    "monitor-visible previous checkpoint is stale",
                    event,
                )
        if event.args[4] != active.energy_hash or event.args[5] != active.theta_hash:
            self._fail(
                "intra_energy_freshness",
                "convergence check refers to stale energy or parameters",
                event,
            )
        if abs(delta - expected_delta) > self.config.energy_abs_tolerance:
            self._fail(
                "inter_convergence_consistency",
                f"energy delta {delta} does not equal {expected_delta}",
                event,
            )
        if stable != expected_stable or declared != expected_converged:
            self._fail(
                "inter_convergence_consistency",
                "convergence flag/patience counter disagrees with configured policy",
                event,
            )
        if event.args[-1] != ("T" if declared else "F"):
            self._fail(
                "inter_convergence_consistency",
                "monitor-visible convergence token disagrees with payload",
                event,
            )
        active.converged = declared
        active.stable_count = stable
        active.energy_delta = delta
        active.phase = "checked"
        self.report.mark_checked(
            "inter_previous_energy_continuity", "inter_convergence_consistency"
        )

    def _on_firstConvergenceChecked(self, event: RuntimeEvent) -> None:
        self._check_convergence(event, first=True)

    def _on_nextConvergenceChecked(self, event: RuntimeEvent) -> None:
        self._check_convergence(event, first=False)

    def _convergence_certificate(self, event: RuntimeEvent, expected: bool) -> None:
        active = self.active
        if active is None or active.energy_hash is None:
            self._fail(
                "inter_convergence_consistency",
                "convergence certificate occurred without valid active evidence",
                event,
            )
            return
        if active.converged is not expected or event.args[4] != active.energy_hash:
            self._fail(
                "inter_convergence_consistency",
                "convergence certificate disagrees with the executable check",
                event,
            )
        if (
            event.payload.get("converged") is not expected
            or event.payload.get("energy_hash") != active.energy_hash
        ):
            self._fail(
                "inter_convergence_consistency",
                "convergence certificate payload disagrees with active evidence",
                event,
            )
        if active.convergence_certified:
            self._fail(
                "intra_convergence_check_once",
                "convergence certificate occurred more than once",
                event,
            )
        active.convergence_certified = True

    def _on_convergenceTrue(self, event: RuntimeEvent) -> None:
        self._convergence_certificate(event, True)

    def _on_convergenceFalse(self, event: RuntimeEvent) -> None:
        self._convergence_certificate(event, False)

    def _on_iterationPass(self, event: RuntimeEvent) -> None:
        active = self.active
        if active is None:
            return
        if active.passed:
            self._fail(
                "intra_iteration_pass_once", "iterationPass occurred more than once", event
            )
        if active.converged is None or not active.convergence_certified:
            self._fail(
                "intra_iteration_pass_after_check",
                "iterationPass occurred before a complete convergence check",
                event,
            )
        if event.args[4] != active.energy_hash:
            self._fail(
                "intra_energy_freshness", "iterationPass references stale energy", event
            )
        active.passed = True

    def _on_objectiveReleaseIntent(self, event: RuntimeEvent) -> None:
        active = self.active
        if active is None:
            return
        if active.released:
            self._fail(
                "intra_objective_release_once",
                "objective release was authorized more than once",
                event,
            )
        if not active.passed or event.args[4] != active.energy_hash:
            self._fail(
                "intra_objective_release_after_pass",
                "objective release lacks a matching iteration pass",
                event,
            )
        active.released = True

    def _optimizer_theta(self, event: RuntimeEvent) -> None:
        if self.active is None:
            return
        raw = event.payload.get("next_theta")
        if not isinstance(raw, list) or not raw:
            self._fail("inter_theta_continuity", "next_theta must be recorded", event)
            return
        values: list[float] = []
        for value in raw:
            parsed = self._number(value)
            if parsed is None:
                self._fail(
                    "inter_theta_continuity", "next_theta contains non-finite data", event
                )
                return
            values.append(parsed)
        theta = tuple(values)
        if len(theta) != self.config.parameter_count:
            self._fail(
                "inter_parameter_dimension",
                f"optimizer output has length {len(theta)}, expected "
                f"{self.config.parameter_count}",
                event,
            )
        digest = vector_digest(theta)
        if digest != event.args[4] or event.payload.get("next_theta_hash") != digest:
            self._fail("inter_theta_continuity", "next theta hash mismatch", event)
        if not all(
            self.config.parameter_lower <= value <= self.config.parameter_upper
            for value in theta
        ):
            self._fail(
                "intra_parameter_domain", "optimizer proposed out-of-domain theta", event
            )
        if self.active.converged:
            self._fail(
                "inter_no_successor_after_convergence",
                "optimizer update occurred after convergence",
                event,
            )
        if self.active.next_theta_hash is not None and self.active.next_theta_hash != digest:
            self._fail(
                "inter_theta_continuity",
                "applied optimizer output differs from authorized output",
                event,
            )
        self.active.next_theta = theta
        self.active.next_theta_hash = digest
        self.report.mark_checked("inter_theta_continuity", "inter_parameter_dimension")

    def _on_optimizerUpdateIntent(self, event: RuntimeEvent) -> None:
        if self.config.optimizer_protocol != "ask-tell":
            self._fail(
                "inter_optimizer_protocol",
                "ask/tell update intent occurred under the opaque optimizer protocol",
                event,
            )
        if self.active is not None and not self.active.released:
            self._fail(
                "inter_update_after_objective_release",
                "optimizer update intent occurred before objective release",
                event,
            )
        if (
            self.active is not None
            and self.active.iteration + 1 >= self.config.max_iterations
        ):
            self._fail(
                "inter_no_update_at_iteration_limit",
                "optimizer update intent occurred after the last permitted evaluation",
                event,
            )
        if self.active is not None and self.active.update_intent_recorded:
            self._fail(
                "inter_update_intent_once",
                "optimizer update intent occurred more than once",
                event,
            )
        self._optimizer_theta(event)
        if self.active is not None:
            self.active.update_intent_recorded = True

    def _on_optimizerUpdated(self, event: RuntimeEvent) -> None:
        if self.config.optimizer_protocol != "ask-tell":
            self._fail(
                "inter_optimizer_protocol",
                "ask/tell update completion occurred under the opaque optimizer protocol",
                event,
            )
        if self.active is not None:
            if not self.active.update_intent_recorded:
                self._fail(
                    "inter_updated_after_intent",
                    "optimizer mutation occurred without update intent",
                    event,
                )
            if self.active.update_applied:
                self._fail(
                    "inter_update_applied_once",
                    "optimizer mutation was recorded more than once",
                    event,
                )
        self._optimizer_theta(event)
        if self.active is not None:
            self.active.update_applied = True
            if (
                self.active.update_intent_recorded
                and self.active.next_theta_hash == event.args[4]
            ):
                self.report.mark_checked("inter_optimizer_commit_enforcement")

    def _on_opaqueOptimizerAdvanced(self, event: RuntimeEvent) -> None:
        if self.config.optimizer_protocol != "opaque":
            self._fail(
                "inter_optimizer_protocol",
                "opaque optimizer advance occurred under the ask/tell protocol",
                event,
            )
        if self.active is not None or not self.checkpoints:
            self._fail(
                "inter_theta_continuity",
                "opaque optimizer advance requires one closed previous checkpoint",
                event,
            )
            return
        previous = self.checkpoints[-1]
        if previous.next_theta_hash is not None:
            self._fail(
                "inter_opaque_advance_once",
                "opaque optimizer exposed more than one candidate for a checkpoint",
                event,
            )
            return
        if (
            event.args[2] != str(previous.iteration)
            or event.args[3] != previous.evaluation_id
        ):
            self._fail(
                "inter_checkpoint_continuity",
                "opaque optimizer advance does not identify the last checkpoint",
                event,
            )
        if previous.converged:
            self._fail(
                "inter_no_successor_after_convergence",
                "opaque optimizer advanced after convergence",
                event,
            )
        if previous.limit_reached:
            self._fail(
                "inter_no_successor_after_iteration_limit",
                "opaque optimizer advanced after the configured iteration limit",
                event,
            )
        raw = event.payload.get("next_theta")
        if not isinstance(raw, list) or not raw:
            self._fail(
                "inter_theta_continuity", "opaque candidate theta is missing", event
            )
            return
        values: list[float] = []
        for value in raw:
            parsed = self._number(value)
            if parsed is None:
                self._fail(
                    "inter_theta_continuity",
                    "opaque candidate contains non-finite data",
                    event,
                )
                return
            values.append(parsed)
        if len(values) != self.config.parameter_count:
            self._fail(
                "inter_parameter_dimension",
                f"opaque candidate has length {len(values)}, expected "
                f"{self.config.parameter_count}",
                event,
            )
        if not all(
            self.config.parameter_lower <= value <= self.config.parameter_upper
            for value in values
        ):
            self._fail(
                "intra_parameter_domain",
                "opaque optimizer candidate is outside the parameter domain",
                event,
            )
        digest = vector_digest(values)
        if event.args[4] != digest or event.payload.get("next_theta_hash") != digest:
            self._fail(
                "inter_theta_continuity", "opaque candidate hash mismatch", event
            )
        self.checkpoints[-1] = replace(previous, next_theta_hash=digest)
        self.report.mark_checked("inter_theta_continuity", "inter_parameter_dimension")

    def _on_iterationLimitReached(self, event: RuntimeEvent) -> None:
        if self.active is None:
            return
        if self.active.limit_reached:
            self._fail(
                "run_iteration_limit_once",
                "iteration-limit certificate occurred more than once",
                event,
            )
        if self.active.iteration + 1 != self.config.max_iterations:
            self._fail(
                "run_truthful_termination",
                "iteration limit certificate was emitted before the configured limit",
                event,
            )
        if self.active.converged is not False:
            self._fail(
                "run_truthful_termination",
                "iteration-limit certificate requires a completed nonconvergence check",
                event,
            )
        self.active.limit_reached = True

    def _on_iterationClosed(self, event: RuntimeEvent) -> None:
        active = self.active
        if active is None or active.energy is None or active.energy_hash is None:
            self._fail("intra_iteration_closure", "iteration closed without valid energy", event)
            return
        if active.converged is None:
            self._fail(
                "intra_iteration_closure", "iteration closed before convergence check", event
            )
            return
        if not active.released:
            self._fail(
                "intra_iteration_closure",
                "iteration closed without an authorized objective release",
                event,
            )
        if active.update_intent_recorded and not active.update_applied:
            self._fail(
                "inter_update_commit_complete",
                "iteration closed after optimizer intent but before mutation completion",
                event,
            )
        if self.config.optimizer_protocol == "ask-tell":
            terminal_iteration = bool(
                active.converged
                or active.limit_reached
                or (
                    self.config.allow_optimizer_stopped
                    and not active.update_intent_recorded
                    and not active.update_applied
                    and active.next_theta_hash is None
                )
            )
            has_complete_update = bool(
                active.update_intent_recorded
                and active.update_applied
                and active.next_theta_hash is not None
            )
            if not terminal_iteration and not has_complete_update:
                self._fail(
                    "inter_optimizer_commit_enforcement",
                    "a nonterminal ask/tell iteration closed without one approved "
                    "and committed optimizer proposal",
                    event,
                )
            if terminal_iteration and (
                active.update_intent_recorded
                or active.update_applied
                or active.next_theta_hash is not None
            ):
                self._fail(
                    "inter_optimizer_commit_enforcement",
                    "a terminal iteration must not commit an orphan optimizer proposal",
                    event,
                )
        if event.args[4] != active.energy_hash or event.args[5] != active.theta_hash:
            self._fail(
                "intra_iteration_closure", "iteration close references stale evidence", event
            )
        expected_result = "T" if active.converged else "F"
        if event.args[6] != expected_result:
            self._fail(
                "intra_iteration_closure", "close convergence token mismatch", event
            )
        expected_next = active.next_theta_hash or "none"
        if event.args[7] != expected_next:
            self._fail(
                "inter_theta_continuity", "close next-theta token mismatch", event
            )
        expected_payload = {
            "iteration": active.iteration,
            "evaluation_id": active.evaluation_id,
            "energy": active.energy,
            "energy_hash": active.energy_hash,
            "theta_hash": active.theta_hash,
            "converged": active.converged,
            "next_theta_hash": active.next_theta_hash,
            "effective_term_samples": active.effective_term_samples,
        }
        if not self._canonical_equal(dict(event.payload), expected_payload):
            self._fail(
                "intra_iteration_closure",
                "iteration-close payload disagrees with verified active evidence",
                event,
            )
        checkpoint = Checkpoint(
            active.iteration,
            active.evaluation_id,
            active.theta_hash,
            active.energy,
            active.energy_hash,
            active.converged,
            active.stable_count,
            active.next_theta_hash,
            active.effective_term_samples,
            active.limit_reached,
        )
        self.checkpoints.append(checkpoint)
        self.total_effective_term_samples += active.effective_term_samples
        if self.total_effective_term_samples > self.config.shot_budget:
            self._fail(
                "run_resource_budget",
                "cumulative effective term samples "
                f"{self.total_effective_term_samples} exceed budget {self.config.shot_budget}",
                event,
            )
        if len(self.checkpoints) > self.config.max_iterations:
            self._fail(
                "run_resource_budget", "iteration count exceeds configured maximum", event
            )
        self.active = None
        self.report.iterations = len(self.checkpoints)
        self.report.effective_term_samples = self.total_effective_term_samples
        self.report.mark_checked(
            "intra_iteration_closure", "run_resource_budget", "inter_budget_continuity"
        )

    def _on_criticalFail(self, event: RuntimeEvent) -> None:
        context = (event.args[2], event.args[3], event.args[4])
        if self.failure_context is not None:
            self._fail(
                "run_failure_context",
                "critical failure cause was recorded more than once",
                event,
            )
        if self.active is None:
            if context[:2] != ("0", "none"):
                self._fail(
                    "run_failure_context",
                    "failure outside an iteration must use the canonical 0/none sentinel",
                    event,
                )
        elif context[:2] != (str(self.active.iteration), self.active.evaluation_id):
            self._fail(
                "run_failure_context",
                "critical failure does not identify the active iteration",
                event,
            )
        self.failure_context = context
        self.critical_failure = True

    def _on_iterationAborted(self, event: RuntimeEvent) -> None:
        if not self.critical_failure:
            self._fail(
                "intra_abort_after_failure",
                "iterationAborted occurred without a critical failure",
                event,
            )
        if self.active is None:
            self._fail(
                "intra_abort_after_failure",
                "iterationAborted occurred without an open iteration",
                event,
            )
        if self.failure_context != (event.args[2], event.args[3], event.args[4]):
            self._fail(
                "run_failure_context",
                "iteration abort does not match the recorded critical failure",
                event,
            )
        self.active = None

    def _set_terminal(self, reason: str, event: RuntimeEvent) -> None:
        if self.terminal_reason is not None:
            self._fail("run_single_terminal", "more than one terminal event occurred", event)
        self.terminal_reason = reason
        self.report.terminal_reason = reason

    def _last_checkpoint(self, event: RuntimeEvent) -> Checkpoint | None:
        if self.active is not None:
            self._fail("run_all_iterations_closed", "terminal event with open iteration", event)
        if not self.checkpoints:
            self._fail("run_truthful_termination", "terminal event has no checkpoint", event)
            return None
        checkpoint = self.checkpoints[-1]
        if (
            event.args[2] != str(checkpoint.iteration)
            or event.args[3] != checkpoint.evaluation_id
            or event.args[4] != checkpoint.energy_hash
        ):
            self._fail(
                "run_final_checkpoint_identity",
                "terminal event does not identify the last verified checkpoint",
                event,
            )
        return checkpoint

    def _on_runConverged(self, event: RuntimeEvent) -> None:
        last = self._last_checkpoint(event)
        if last is not None and not last.converged:
            self._fail(
                "run_truthful_termination", "CONVERGED without a converged checkpoint", event
            )
        if last is not None and last.next_theta_hash is not None:
            self._fail(
                "run_truthful_termination",
                "CONVERGED checkpoint contains an orphan optimizer output",
                event,
            )
        self._set_terminal("converged", event)

    def _on_runMaxIterations(self, event: RuntimeEvent) -> None:
        last = self._last_checkpoint(event)
        if last is not None and (
            last.converged
            or len(self.checkpoints) != self.config.max_iterations
            or not last.limit_reached
            or last.next_theta_hash is not None
        ):
            self._fail(
                "run_truthful_termination",
                "MAX_ITERATIONS does not match the verified iteration history",
                event,
            )
        self._set_terminal("max_iterations", event)

    def _on_runOptimizerStopped(self, event: RuntimeEvent) -> None:
        last = self._last_checkpoint(event)
        if not self.config.allow_optimizer_stopped:
            self._fail(
                "run_truthful_termination",
                "optimizer-stopped is not enabled by the resolved termination policy",
                event,
            )
        if last is not None and (
            last.converged
            or len(self.checkpoints) >= self.config.max_iterations
            or last.next_theta_hash is not None
        ):
            self._fail(
                "run_truthful_termination",
                "optimizer-stopped reason requires a nonconverged checkpoint before the limit",
                event,
            )
        self._set_terminal("optimizer_stopped", event)

    def _on_runAborted(self, event: RuntimeEvent) -> None:
        if not self.critical_failure:
            self._fail("run_abort_has_cause", "ABORTED has no recorded critical failure", event)
        if self.failure_context != (event.args[2], event.args[3], event.args[4]):
            self._fail(
                "run_failure_context",
                "run abort does not match the recorded critical failure context",
                event,
            )
        self._set_terminal("aborted", event)

    def _on_runClosed(self, event: RuntimeEvent) -> None:
        if self.terminal_reason is None:
            self._fail("run_trace_complete", "runClosed occurred before a terminal event", event)
        if self.active is not None:
            self._fail("run_all_iterations_closed", "runClosed with open iteration", event)
        if self.closed:
            self._fail("run_single_close", "runClosed occurred more than once", event)
        if self.optimizer_protocol_certificate != self.config.optimizer_protocol:
            self._fail(
                "inter_optimizer_protocol",
                "run closed without exactly one matching optimizer protocol certificate",
                event,
            )
        if not self.checkpoints:
            self.report.add_inconclusive(
                "intra_iteration_evidence",
                "the run closed without a verified iteration",
                seq=event.seq,
            )
            self.report.add_inconclusive(
                "inter_iteration_evidence",
                "the run contains no verified checkpoint history",
                seq=event.seq,
            )
        elif len(self.checkpoints) < 2:
            self.report.add_inconclusive(
                "inter_iteration_evidence",
                "one checkpoint contains no adjacent transition to verify",
                seq=event.seq,
            )
        self.closed = True
        self.report.complete = self.terminal_reason is not None and self.active is None
        self.report.mark_checked(
            "run_trace_complete",
            "run_single_terminal",
            "run_single_close",
            "run_all_iterations_closed",
            "run_truthful_termination",
            "run_abort_has_cause",
        )
