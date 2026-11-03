from __future__ import annotations

from pathlib import Path

from .config import RuntimeConfig
from .contracts import ContractEngine
from .dejavu import DejaVuError, EventMonitor, SynchronousDejaVu
from .evidence_replay import verify_trace_evidence
from .events import load_events
from .report import VerificationReport


def check_trace(
    config: RuntimeConfig,
    trace_path: str | Path,
    *,
    report_path: str | Path | None = None,
    evidence_path: str | Path | None = None,
    monitor: EventMonitor | None = None,
) -> VerificationReport:
    events, errors = load_events(trace_path)
    run_id = events[0].args[0] if events and events[0].args else "unknown-run"
    report = VerificationReport(run_id, config.digest)
    for message in errors:
        report.add_failure("run_event_schema", message)
    engine = ContractEngine(config, report)
    owned_monitor = monitor is None
    try:
        active_monitor = monitor or SynchronousDejaVu(
            timeout_seconds=config.monitor_timeout_seconds,
            bits_per_variable=config.bits_per_variable,
        )
    except DejaVuError as exc:
        report.add_inconclusive(
            "run_monitor_available", f"cannot start DejaVu for replay: {exc}"
        )
        active_monitor = None

    monitor_to_close = active_monitor if owned_monitor else None
    if type(active_monitor) is SynchronousDejaVu:
        report.monitor_provenance = dict(active_monitor.provenance)
    elif active_monitor is not None:
        report.monitor_provenance = type(active_monitor).__name__
        report.add_inconclusive(
            "run_monitor_available",
            "a non-DejaVu shadow/test monitor cannot establish temporal assurance",
            source="monitor",
        )

    try:
        for event in events:
            engine.consume(event)
            if active_monitor is None:
                continue
            try:
                ack = active_monitor.submit(event)
            except Exception as exc:
                report.add_inconclusive(
                    "run_monitor_available",
                    f"DejaVu replay stopped at sequence {event.seq}: {exc}",
                    seq=event.seq,
                    source="dejavu",
                )
                active_monitor = None
                continue
            if ack.seq != event.seq:
                report.add_inconclusive(
                    "run_monitor_available",
                    f"monitor watermark mismatch at sequence {event.seq}",
                    seq=event.seq,
                    source="dejavu",
                )
            if not ack.passed:
                for property_id in ack.violations or ("run_monitor_rejected_event",):
                    report.add_failure(
                        property_id,
                        f"DejaVu rejected {event.name}",
                        seq=event.seq,
                        source="dejavu",
                    )
    finally:
        if monitor_to_close is not None:
            monitor_to_close.close()

    if not events:
        report.add_inconclusive("run_trace_complete", "trace contains no events")
    elif not engine.closed:
        report.add_inconclusive(
            "run_trace_complete",
            "finite trace has no valid runClosed event; run-level PASS is withheld",
        )
    if not engine.checkpoints and not any(
        finding.property_id == "intra_iteration_evidence"
        for finding in report.findings
    ):
        report.add_inconclusive(
            "intra_iteration_evidence",
            "trace contains no fully verified iteration",
        )
        report.add_inconclusive(
            "inter_iteration_evidence",
            "trace contains no verified checkpoint history",
        )
    elif len(engine.checkpoints) < 2 and not any(
        finding.property_id == "inter_iteration_evidence"
        for finding in report.findings
    ):
        report.add_inconclusive(
            "inter_iteration_evidence",
            "trace contains only one checkpoint and no adjacent transition",
        )
    report.complete = engine.closed and engine.terminal_reason is not None
    report.terminal_reason = engine.terminal_reason
    verify_trace_evidence(config, events, evidence_path, report, run_id)
    report.finish()
    if report_path is not None:
        report.write_json(report_path)
    return report
