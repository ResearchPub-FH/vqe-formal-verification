from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import json
from pathlib import Path
import time
from types import MappingProxyType
from typing import Any, Mapping
import warnings


class Level(str, Enum):
    INTRA_ITERATION = "intra_iteration"
    INTER_ITERATION = "inter_iteration"
    RUN_LEVEL = "run_level"


class Status(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"


class UnknownPropertyLevelWarning(UserWarning):
    """A property ID has no audited entry in the level registry."""


# Python's executable contracts use stable snake_case IDs. Keep this list
# explicit: report level is part of the verification result and must not be
# inferred from naming convention alone.
_PYTHON_INTRA_ITERATION_PROPERTIES = frozenset(
    {
        "intra_abort_after_failure",
        "intra_backend_provenance",
        "intra_binding_after_start",
        "intra_convergence_check_once",
        "intra_energy_bound",
        "intra_energy_computation",
        "intra_energy_freshness",
        "intra_event_context",
        "intra_expectation_domain",
        "intra_iteration_closure",
        "intra_iteration_evidence",
        "intra_iteration_pass_after_check",
        "intra_iteration_pass_once",
        "intra_objective_release_after_pass",
        "intra_objective_release_once",
        "intra_parameter_dimension",
        "intra_parameter_domain",
        "intra_parameter_freshness",
        "intra_parity_reconstruction",
        "intra_pub_assignment",
        "intra_raw_evidence_link",
        "intra_shot_consistency",
        "intra_term_after_binding",
        "intra_term_completeness",
        "intra_term_identity",
    }
)

_PYTHON_INTER_ITERATION_PROPERTIES = frozenset(
    {
        "inter_backend_job_unique",
        "inter_budget_continuity",
        "inter_checkpoint_continuity",
        "inter_config_immutable",
        "inter_convergence_consistency",
        "inter_evaluation_identity_unique",
        "inter_iteration_contiguous",
        "inter_iteration_evidence",
        "inter_no_overlapping_iterations",
        "inter_no_successor_after_convergence",
        "inter_no_successor_after_iteration_limit",
        "inter_no_update_at_iteration_limit",
        "inter_opaque_advance_once",
        "inter_optimizer_commit_enforcement",
        "inter_optimizer_protocol",
        "inter_parameter_dimension",
        "inter_previous_energy_continuity",
        "inter_raw_evidence_identity_unique",
        "inter_run_identity",
        "inter_submission_identity_unique",
        "inter_theta_continuity",
        "inter_update_after_objective_release",
        "inter_update_applied_once",
        "inter_update_commit_complete",
        "inter_update_intent_once",
        "inter_updated_after_intent",
        # The iteration-limit certificate relates adjacent optimization steps.
        # Its legacy ID predates the scoped Python naming convention.
        "run_iteration_limit_once",
    }
)

_PYTHON_RUN_LEVEL_PROPERTIES = frozenset(
    {
        "run_abort_has_cause",
        "run_activity_pairing",
        "run_all_iterations_closed",
        "run_event_schema",
        "run_event_sequence",
        "run_execution_options",
        "run_execution_provenance",
        "run_failure_context",
        "run_failure_forces_abort",
        "run_final_checkpoint_identity",
        "run_journal_available",
        "run_monitor_available",
        "run_monitor_rejected_event",
        "run_physical_shot_budget",
        "run_raw_evidence_complete",
        "run_resource_budget",
        "run_single_close",
        "run_single_start",
        "run_single_terminal",
        "run_start_precedes_activity",
        "run_terminal_absorbing",
        "run_trace_complete",
        "run_truthful_termination",
    }
)


# DejaVu returns the generated QTL property names verbatim. These names are
# camelCase after their first underscore and are registered by the section in
# specs/vqe_runtime.qtl, not by their textual prefix.
_DEJAVU_INTRA_ITERATION_PROPERTIES = frozenset(
    {
        "intra_abortAfterFailure",
        "intra_allDeclaredTermsObserved",
        "intra_bindingAfterStart",
        "intra_bindingOnce",
        "intra_closeAfterRelease",
        "intra_energyAfterSeal",
        "intra_energyOnce",
        "intra_firstCheckAfterEnergy",
        "intra_firstCheckOnce",
        "intra_nextCheckAfterEnergy",
        "intra_nextCheckOnce",
        "intra_oneSubmissionPerIteration",
        "intra_passAfterCheck",
        "intra_passOnce",
        "intra_releaseAfterPass",
        "intra_releaseOnce",
        "intra_sealAfterSubmission",
        "intra_sealOnce",
        "intra_submitAfterBinding",
        "intra_submittedAfterIntent",
        "intra_submittedOnce",
        "intra_termAfterSubmission",
        "intra_termDeclaredOnce",
        "intra_termExpectedAfterBinding",
        "intra_termObservedOnce",
        "intra_termWasDeclared",
    }
)

_DEJAVU_INTER_ITERATION_PROPERTIES = frozenset(
    {
        "inter_askTellIntentUsesConfiguredProtocol",
        "inter_askTellProtocolConfiguredOnce",
        "inter_askTellUpdateUsesConfiguredProtocol",
        "inter_backendJobIdentityUnique",
        "inter_closeAfterCommittedUpdate",
        "inter_firstEvaluationIdentityUnique",
        "inter_firstIterationAfterConfiguredProtocol",
        "inter_iterationClosedOnce",
        "inter_nextAfterOptimizerUpdate",
        "inter_nextAfterPreviousClose",
        "inter_nextEvaluationIdentityUnique",
        "inter_nextIterationAfterConfiguredProtocol",
        "inter_opaqueAdvanceAfterClose",
        "inter_opaqueAdvanceBeforeLimit",
        "inter_opaqueAdvanceOnce",
        "inter_opaqueAdvanceUsesConfiguredProtocol",
        "inter_opaqueProtocolConfiguredOnce",
        "inter_previousEnergyIsLastCheckpoint",
        "inter_submissionIdentityUnique",
        "inter_updateAppliedOnce",
        "inter_updateIntentAfterRelease",
        "inter_updateIntentOnce",
        "inter_updateOnlyWhenNotConverged",
        "inter_updatedAfterIntent",
        # Despite its historical run_ prefix, this property is declared in the
        # QTL inter-iteration section and is therefore classified here.
        "run_iterationLimitOnce",
    }
)

_DEJAVU_RUN_LEVEL_PROPERTIES = frozenset(
    {
        "run_abortAfterFailure",
        "run_abortIsFirstTerminal",
        "run_activityAfterMatchingStart",
        "run_closeAfterOptimizerProtocol",
        "run_closeAfterTerminal",
        "run_closeOnce",
        "run_convergedAfterTrueClose",
        "run_convergedIsFirstTerminal",
        "run_failureRequiresAbortAtClose",
        "run_maxAfterLimitAndFalseClose",
        "run_maxIsFirstTerminal",
        "run_noActivityAfterClose",
        "run_noActivityAfterTerminal",
        "run_normalTerminalWithoutFailure",
        "run_optimizerStopAfterFalseClose",
        "run_optimizerStopIsFirstTerminal",
        "run_startOnce",
    }
)


def _build_property_level_registry() -> Mapping[str, Level]:
    groups = (
        (Level.INTRA_ITERATION, _PYTHON_INTRA_ITERATION_PROPERTIES),
        (Level.INTER_ITERATION, _PYTHON_INTER_ITERATION_PROPERTIES),
        (Level.RUN_LEVEL, _PYTHON_RUN_LEVEL_PROPERTIES),
        (Level.INTRA_ITERATION, _DEJAVU_INTRA_ITERATION_PROPERTIES),
        (Level.INTER_ITERATION, _DEJAVU_INTER_ITERATION_PROPERTIES),
        (Level.RUN_LEVEL, _DEJAVU_RUN_LEVEL_PROPERTIES),
    )
    registry: dict[str, Level] = {}
    for level, property_ids in groups:
        for property_id in property_ids:
            previous = registry.setdefault(property_id, level)
            if previous is not level:
                raise RuntimeError(
                    f"property {property_id!r} is registered at multiple levels"
                )
    return MappingProxyType(registry)


PROPERTY_LEVEL_REGISTRY = _build_property_level_registry()


def level_for_property(property_id: str) -> Level:
    """Return an audited level, warning on unregistered external property IDs.

    Run level is the conservative compatibility fallback: it preserves the
    three-level report schema and ensures an unknown finding still affects the
    overall verdict without pretending that it belongs to a narrower scope.
    """

    level = PROPERTY_LEVEL_REGISTRY.get(property_id)
    if level is not None:
        return level
    warnings.warn(
        f"unregistered property ID {property_id!r}; conservatively assigning "
        f"{Level.RUN_LEVEL.value}",
        UnknownPropertyLevelWarning,
        stacklevel=2,
    )
    return Level.RUN_LEVEL


@dataclass(frozen=True, slots=True)
class Finding:
    property_id: str
    level: Level
    status: Status
    message: str
    seq: int | None = None
    source: str = "python"


@dataclass(slots=True)
class VerificationReport:
    run_id: str
    config_hash: str
    complete: bool = False
    terminal_reason: str | None = None
    started_ns: int = field(default_factory=time.monotonic_ns)
    finished_ns: int | None = None
    event_count: int = 0
    iterations: int = 0
    effective_term_samples: int = 0
    monitor_provenance: dict[str, Any] | str = "unknown"
    execution_provenance: dict[str, Any] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    checked_properties: set[str] = field(default_factory=set)

    def add_failure(
        self,
        property_id: str,
        message: str,
        *,
        seq: int | None = None,
        source: str = "python",
    ) -> None:
        self.checked_properties.add(property_id)
        self.findings.append(
            Finding(
                property_id,
                level_for_property(property_id),
                Status.FAIL,
                message,
                seq,
                source,
            )
        )

    def add_inconclusive(
        self,
        property_id: str,
        message: str,
        *,
        seq: int | None = None,
        source: str = "python",
    ) -> None:
        self.checked_properties.add(property_id)
        self.findings.append(
            Finding(
                property_id,
                level_for_property(property_id),
                Status.INCONCLUSIVE,
                message,
                seq,
                source,
            )
        )

    def mark_checked(self, *property_ids: str) -> None:
        self.checked_properties.update(property_ids)

    def status_for_level(self, level: Level) -> Status:
        scoped = [finding for finding in self.findings if finding.level == level]
        if any(item.status == Status.FAIL for item in scoped):
            return Status.FAIL
        if any(
            item.property_id == "run_monitor_available"
            and item.status == Status.INCONCLUSIVE
            for item in self.findings
        ):
            return Status.INCONCLUSIVE
        if any(item.status == Status.INCONCLUSIVE for item in scoped):
            return Status.INCONCLUSIVE
        if level == Level.RUN_LEVEL and not self.complete:
            return Status.INCONCLUSIVE
        return Status.PASS

    @property
    def status(self) -> Status:
        levels = [self.status_for_level(level) for level in Level]
        if Status.FAIL in levels:
            return Status.FAIL
        if Status.INCONCLUSIVE in levels:
            return Status.INCONCLUSIVE
        return Status.PASS

    def finish(self) -> None:
        if self.finished_ns is None:
            self.finished_ns = time.monotonic_ns()

    def as_dict(self) -> dict[str, Any]:
        self.finish()
        duration = (self.finished_ns - self.started_ns) / 1_000_000_000
        levels = {}
        for level in Level:
            findings = [asdict(item) for item in self.findings if item.level == level]
            for finding in findings:
                finding["level"] = finding["level"].value
                finding["status"] = finding["status"].value
            levels[level.value] = {
                "status": self.status_for_level(level).value,
                "findings": findings,
            }
        return {
            "schema_version": 1,
            "run_id": self.run_id,
            "config_hash": self.config_hash,
            "status": self.status.value,
            "complete": self.complete,
            "terminal_reason": self.terminal_reason,
            "monitor_provenance": self.monitor_provenance,
            "execution_provenance": self.execution_provenance,
            "levels": levels,
            "metrics": {
                "event_count": self.event_count,
                "iterations": self.iterations,
                "verified_effective_term_samples": self.effective_term_samples,
                "duration_seconds": duration,
                "recorded_contract_count": len(self.checked_properties),
            },
        }

    def write_json(self, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(self.as_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
