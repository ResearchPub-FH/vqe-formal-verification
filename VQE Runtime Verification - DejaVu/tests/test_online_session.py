from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from vqe_runtime.config import load_config
from vqe_runtime.dejavu import AlwaysPassMonitor, MonitorAck
from vqe_runtime.report import Level, Status
from vqe_runtime.session import (
    RuntimeSession,
    TermObservation,
    TerminationReason,
    VerificationAbort,
)


ROOT = Path(__file__).resolve().parents[1]


def observations(shots: int = 1000) -> tuple[TermObservation, ...]:
    return (
        TermObservation("t0", -0.5, shots, 750),
        TermObservation("t1", 0.5, shots, 250),
        TermObservation("t2", 0.0, shots, 500),
        TermObservation("t3", -0.8, shots, 900),
    )


class OnlineSessionTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(ROOT / "configs/h2_demo.toml")
        self.temp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp.cleanup()

    def session(self) -> RuntimeSession:
        root = Path(self.temp.name)
        return RuntimeSession(
            self.config,
            run_id="test-run",
            trace_path=root / "trace.jsonl",
            report_path=root / "report.json",
            monitor=AlwaysPassMonitor(),
            overwrite=True,
        )

    @staticmethod
    def prepare(session: RuntimeSession, theta=(0.1, -0.2)) -> None:
        session.begin_iteration(theta)
        session.bind_parameters()
        session.authorize_job("submission")
        session.mark_job_submitted("job")

    def test_wrong_energy_aborts_before_release(self):
        session = self.session()
        try:
            self.prepare(session)
            session.observe_terms(observations())
            session.seal_measurements()
            with self.assertRaises(VerificationAbort):
                session.aggregate_energy(100.0)
            self.assertEqual(session.report.terminal_reason, "aborted")
            report = session.seal_run()
            self.assertEqual(report.status, Status.FAIL)
            self.assertEqual(
                report.status_for_level(Level.INTRA_ITERATION), Status.FAIL
            )
            self.assertFalse(
                any(event.name == "objectiveReleaseIntent" for event in session.journal.events)
            )
        finally:
            session.close()

    def test_missing_term_fails_at_measurement_seal(self):
        session = self.session()
        try:
            self.prepare(session)
            session.observe_terms(observations()[:-1])
            with self.assertRaises(VerificationAbort):
                session.seal_measurements()
            self.assertTrue(
                any(
                    item.property_id == "intra_term_completeness"
                    for item in session.report.findings
                )
            )
        finally:
            if session.report.terminal_reason:
                session.seal_run()
            session.close()

    def test_parameter_out_of_bounds_fails_before_backend_intent(self):
        session = self.session()
        try:
            with self.assertRaises(VerificationAbort):
                session.begin_iteration((10.0, 0.0))
            self.assertFalse(
                any(event.name == "jobSubmitIntent" for event in session.journal.events)
            )
        finally:
            if session.report.terminal_reason:
                session.seal_run()
            session.close()

    def test_false_convergence_is_rejected(self):
        session = self.session()
        try:
            self.prepare(session)
            session.observe_terms(observations())
            session.seal_measurements()
            session.aggregate_energy(-0.5428)
            with self.assertRaises(VerificationAbort):
                session.check_convergence(declared=True)
            self.assertTrue(
                any(
                    item.property_id == "inter_convergence_consistency"
                    for item in session.report.findings
                )
            )
        finally:
            if session.report.terminal_reason:
                session.seal_run()
            session.close()

    def test_next_theta_must_equal_authorized_optimizer_output(self):
        session = self.session()
        try:
            self.prepare(session)
            session.observe_terms(observations())
            session.seal_measurements()
            session.aggregate_energy(-0.5428)
            session.check_convergence()
            session.authorize_objective_release()
            session.authorize_optimizer_update((0.2, -0.3))
            session.mark_optimizer_updated((0.2, -0.3))
            session.close_iteration()
            with self.assertRaises(VerificationAbort):
                session.begin_iteration((0.2, -0.4))
            self.assertTrue(
                any(
                    item.property_id == "inter_theta_continuity"
                    for item in session.report.findings
                )
            )
        finally:
            if session.report.terminal_reason:
                session.seal_run()
            session.close()

    def test_unknown_backend_shots_are_not_counted_as_executed_samples(self):
        config = replace(
            self.config,
            require_raw_counts=False,
            allow_optimizer_stopped=True,
        )
        root = Path(self.temp.name)
        session = RuntimeSession(
            config,
            run_id="unknown-shots",
            trace_path=root / "unknown-shots.jsonl",
            overwrite=True,
        )
        try:
            self.prepare(session)
            session.observe_terms(
                TermObservation(item.term_id, item.expectation, None, None)
                for item in observations()
            )
            session.seal_measurements()
            session.aggregate_energy(-0.5428)
            session.check_convergence()
            session.authorize_objective_release()
            session.close_iteration()
            session.finish(TerminationReason.OPTIMIZER_STOPPED)
            report = session.seal_run()
            self.assertEqual(report.effective_term_samples, 0)
            self.assertTrue(
                all(
                    report.status_for_level(level) == Status.INCONCLUSIVE
                    for level in Level
                )
            )
            self.assertTrue(
                any(
                    item.property_id == "intra_shot_consistency"
                    and item.status == Status.INCONCLUSIVE
                    for item in report.findings
                )
            )
            self.assertTrue(
                any(
                    item.property_id == "run_resource_budget"
                    and item.status == Status.INCONCLUSIVE
                    for item in report.findings
                )
            )
            self.assertTrue(
                any(
                    item.property_id == "inter_budget_continuity"
                    and item.status == Status.INCONCLUSIVE
                    for item in report.findings
                )
            )
        finally:
            session.close()

    def test_optimizer_stopped_cannot_disguise_iteration_limit(self):
        config = replace(self.config, max_iterations=1, min_iterations=1)
        root = Path(self.temp.name)
        session = RuntimeSession(
            config,
            run_id="limit-reason",
            trace_path=root / "limit.jsonl",
            monitor=AlwaysPassMonitor(),
            overwrite=True,
        )
        try:
            self.prepare(session)
            session.observe_terms(observations())
            session.seal_measurements()
            session.aggregate_energy(-0.5428)
            session.check_convergence()
            session.authorize_objective_release()
            session.close_iteration()
            with self.assertRaises(VerificationAbort):
                session.finish(TerminationReason.OPTIMIZER_STOPPED)
            self.assertTrue(
                any(
                    item.property_id == "run_truthful_termination"
                    for item in session.report.findings
                )
            )
        finally:
            if session.report.terminal_reason and not session.report.complete:
                try:
                    session.seal_run()
                except VerificationAbort:
                    pass
            session.close()

    def test_startup_monitor_failure_closes_injected_monitor(self):
        class FailingStartupMonitor:
            def __init__(self):
                self.calls = 0
                self.closed = False

            def submit(self, event):
                self.calls += 1
                if self.calls == 1:
                    return MonitorAck(event.seq, True)
                raise RuntimeError("seeded startup outage")

            def close(self):
                self.closed = True

        monitor = FailingStartupMonitor()
        root = Path(self.temp.name)
        with self.assertRaises(VerificationAbort):
            RuntimeSession(
                self.config,
                run_id="startup-outage",
                trace_path=root / "startup.jsonl",
                monitor=monitor,
                overwrite=True,
            )
        self.assertTrue(monitor.closed)

    def test_opaque_optimizer_exposes_at_most_one_candidate_per_checkpoint(self):
        config = replace(self.config, optimizer_protocol="opaque")
        root = Path(self.temp.name)
        session = RuntimeSession(
            config,
            run_id="opaque-once",
            trace_path=root / "opaque-once.jsonl",
            monitor=AlwaysPassMonitor(),
            overwrite=True,
        )
        try:
            self.prepare(session)
            session.observe_terms(observations())
            session.seal_measurements()
            session.aggregate_energy(-0.5428)
            session.check_convergence()
            session.authorize_objective_release()
            session.close_iteration()
            session.observe_opaque_optimizer_candidate((0.2, -0.3))
            with self.assertRaises(VerificationAbort):
                session.observe_opaque_optimizer_candidate((0.25, -0.35))
            self.assertTrue(
                any(
                    item.property_id == "inter_opaque_advance_once"
                    for item in session.report.findings
                )
            )
        finally:
            if session.report.terminal_reason and not session.report.complete:
                try:
                    session.seal_run()
                except VerificationAbort:
                    pass
            session.close()

    def test_optimizer_cannot_change_parameter_dimension(self):
        session = self.session()
        try:
            self.prepare(session)
            session.observe_terms(observations())
            session.seal_measurements()
            session.aggregate_energy(-0.5428)
            session.check_convergence()
            session.authorize_objective_release()
            with self.assertRaises(VerificationAbort):
                session.authorize_optimizer_update((0.2, -0.3, 0.4))
            self.assertTrue(
                any(
                    item.property_id == "inter_parameter_dimension"
                    for item in session.report.findings
                )
            )
        finally:
            if session.report.terminal_reason and not session.report.complete:
                try:
                    session.seal_run()
                except VerificationAbort:
                    pass
            session.close()

    def test_iteration_cannot_close_with_uncommitted_optimizer_intent(self):
        session = self.session()
        try:
            self.prepare(session)
            session.observe_terms(observations())
            session.seal_measurements()
            session.aggregate_energy(-0.5428)
            session.check_convergence()
            session.authorize_objective_release()
            session.authorize_optimizer_update((0.2, -0.3))
            with self.assertRaises(VerificationAbort):
                session.close_iteration()
            self.assertTrue(
                any(
                    item.property_id == "inter_update_commit_complete"
                    for item in session.report.findings
                )
            )
        finally:
            if session.report.terminal_reason and not session.report.complete:
                try:
                    session.seal_run()
                except VerificationAbort:
                    pass
            session.close()

    def test_real_dejavu_rejection_aborts_the_online_session(self):
        root = Path(self.temp.name)
        session = RuntimeSession(
            self.config,
            run_id="real-dejavu-rejection",
            trace_path=root / "real-dejavu-rejection.jsonl",
            report_path=root / "real-dejavu-rejection-report.json",
            overwrite=True,
        )
        try:
            session.begin_iteration((0.1, -0.2))
            session.bind_parameters()
            # The Python engine deliberately permits this duplicate, while the
            # generated QTL monitor enforces intra_bindingOnce synchronously.
            with self.assertRaisesRegex(
                VerificationAbort, "rejected event parametersBound"
            ):
                session.bind_parameters()

            self.assertEqual(session.report.terminal_reason, "aborted")
            self.assertTrue(
                any(
                    finding.property_id == "intra_bindingOnce"
                    and finding.source == "dejavu"
                    and finding.status == Status.FAIL
                    for finding in session.report.findings
                )
            )
            self.assertEqual(session.journal.events[-1].name, "runAborted")
            report = session.seal_run()
            self.assertEqual(report.status, Status.FAIL)
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
