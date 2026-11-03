from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from vqe_runtime.checker import check_trace
from vqe_runtime.config import load_config
from vqe_runtime.dejavu import AlwaysPassMonitor
from vqe_runtime.demo import run_demo
from vqe_runtime.events import RuntimeEvent, load_events, write_events
from vqe_runtime.report import Level, Status


ROOT = Path(__file__).resolve().parents[1]


def resequence(events: list[RuntimeEvent]) -> list[RuntimeEvent]:
    return [replace(event, seq=index) for index, event in enumerate(events, 1)]


class ReplayLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config(ROOT / "configs/h2_demo.toml")
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        cls.valid_trace = root / "valid.jsonl"
        cls.valid_report = root / "valid.json"
        run_demo(
            cls.config,
            trace_path=cls.valid_trace,
            report_path=cls.valid_report,
            run_id="replay-run",
        )
        cls.events, errors = load_events(cls.valid_trace)
        if errors:
            raise AssertionError(errors)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def _write(self, name: str, events: list[RuntimeEvent]) -> Path:
        path = Path(self.temp.name) / name
        write_events(path, events)
        return path

    def test_valid_trace_passes_all_three_levels(self):
        report = check_trace(self.config, self.valid_trace)
        self.assertEqual(report.status, Status.PASS)
        self.assertTrue(report.complete)
        self.assertTrue(
            all(report.status_for_level(level) == Status.PASS for level in Level)
        )

    def test_truncated_trace_is_inconclusive_not_pass(self):
        trace = self._write("truncated.jsonl", self.events[:-1])
        report = check_trace(self.config, trace)
        self.assertEqual(report.status, Status.INCONCLUSIVE)
        self.assertEqual(report.status_for_level(Level.RUN_LEVEL), Status.INCONCLUSIVE)
        self.assertFalse(report.complete)

    def test_activity_after_terminal_fails_absorbing_state(self):
        terminal_index = next(
            index for index, event in enumerate(self.events) if event.name == "runConverged"
        )
        injected = RuntimeEvent(
            1,
            self.events[terminal_index].monotonic_ns + 1,
            "activity",
            ("replay-run", self.config.digest, "parametersBound"),
            {},
        )
        mutated = self.events[: terminal_index + 1] + [injected] + self.events[terminal_index + 1 :]
        trace = self._write("post-terminal.jsonl", resequence(mutated))
        report = check_trace(self.config, trace)
        self.assertEqual(report.status, Status.FAIL)
        self.assertTrue(
            any(
                item.property_id in {"run_terminal_absorbing", "run_noActivityAfterTerminal"}
                for item in report.findings
            )
        )

    def test_config_drift_is_detected(self):
        mutated = list(self.events)
        target = next(i for i, event in enumerate(mutated) if event.name == "activity")
        event = mutated[target]
        mutated[target] = replace(
            event, args=(event.args[0], "different-config", event.args[2])
        )
        trace = self._write("config-drift.jsonl", mutated)
        report = check_trace(self.config, trace)
        self.assertEqual(report.status, Status.FAIL)
        self.assertTrue(
            any(item.property_id == "inter_config_immutable" for item in report.findings)
        )

    def test_skipped_iteration_is_detected_by_python_certificate_checker(self):
        mutated = list(self.events)
        target = next(
            i for i, event in enumerate(mutated) if event.name == "nextIterationStarted"
        )
        event = mutated[target]
        payload = dict(event.payload)
        payload["iteration"] = 2
        args = list(event.args)
        args[2] = "2"
        mutated[target] = replace(event, args=tuple(args), payload=payload)
        trace = self._write("skipped-iteration.jsonl", mutated)
        report = check_trace(self.config, trace)
        self.assertEqual(report.status, Status.FAIL)
        self.assertTrue(
            any(item.property_id == "inter_iteration_contiguous" for item in report.findings)
        )

    def test_critical_failure_cannot_continue_to_normal_completion(self):
        started = self.events[0]
        injected = [
            RuntimeEvent(
                1,
                started.monotonic_ns + 1,
                "activity",
                ("replay-run", self.config.digest, "criticalFail"),
                {},
            ),
            RuntimeEvent(
                1,
                started.monotonic_ns + 2,
                "criticalFail",
                ("replay-run", self.config.digest, "0", "none", "seededFault"),
                {},
            ),
        ]
        trace = self._write(
            "failure-continued.jsonl",
            resequence([started, *injected, *self.events[1:]]),
        )
        report = check_trace(self.config, trace)
        self.assertEqual(report.status, Status.FAIL)
        self.assertTrue(
            any(
                item.property_id
                in {"run_failure_forces_abort", "run_normalTerminalWithoutFailure"}
                for item in report.findings
            )
        )

    def test_duplicate_backend_submission_with_new_job_id_is_detected(self):
        target = next(
            i for i, event in enumerate(self.events) if event.name == "jobSubmitted"
        )
        original = self.events[target]
        activity = RuntimeEvent(
            1,
            original.monotonic_ns + 1,
            "activity",
            ("replay-run", self.config.digest, "jobSubmitted"),
            {},
        )
        args = list(original.args)
        args[5] = "differentJob"
        payload = dict(original.payload)
        payload["external_job_id"] = "differentJob"
        duplicate = replace(
            original,
            seq=1,
            monotonic_ns=original.monotonic_ns + 2,
            args=tuple(args),
            payload=payload,
        )
        mutated = self.events[: target + 1] + [activity, duplicate] + self.events[target + 1 :]
        trace = self._write("duplicate-job.jsonl", resequence(mutated))
        report = check_trace(self.config, trace)
        self.assertEqual(report.status, Status.FAIL)
        self.assertTrue(
            any(
                item.property_id
                in {"intra_backend_provenance", "intra_submittedOnce"}
                for item in report.findings
            )
        )

    def test_exactly_once_enforcement_gates_reject_duplicates(self):
        for event_name in (
            "firstConvergenceChecked",
            "iterationPass",
            "objectiveReleaseIntent",
            "optimizerUpdateIntent",
        ):
            with self.subTest(event=event_name):
                target = next(
                    i for i, event in enumerate(self.events) if event.name == event_name
                )
                original = self.events[target]
                activity = RuntimeEvent(
                    1,
                    original.monotonic_ns + 1,
                    "activity",
                    ("replay-run", self.config.digest, event_name),
                    {},
                )
                duplicate = replace(
                    original, seq=1, monotonic_ns=original.monotonic_ns + 2
                )
                mutated = (
                    self.events[: target + 1]
                    + [activity, duplicate]
                    + self.events[target + 1 :]
                )
                trace = self._write(
                    f"duplicate-{event_name}.jsonl", resequence(mutated)
                )
                report = check_trace(self.config, trace)
                self.assertEqual(report.status, Status.FAIL)

    def test_shadow_monitor_cannot_mint_a_pass(self):
        report = check_trace(
            self.config, self.valid_trace, monitor=AlwaysPassMonitor()
        )
        self.assertEqual(report.status, Status.INCONCLUSIVE)
        self.assertTrue(
            all(
                report.status_for_level(level) == Status.INCONCLUSIVE
                for level in Level
            )
        )

    def test_monitor_outage_withholds_pass_at_every_level(self):
        class BrokenMonitor:
            def submit(self, event):
                raise RuntimeError("seeded monitor outage")

            def close(self):
                return None

        report = check_trace(self.config, self.valid_trace, monitor=BrokenMonitor())
        self.assertEqual(report.status, Status.INCONCLUSIVE)
        self.assertTrue(
            all(
                report.status_for_level(level) == Status.INCONCLUSIVE
                for level in Level
            )
        )

    def test_empty_trace_withholds_pass_at_every_level(self):
        trace = self._write("empty.jsonl", [])
        report = check_trace(self.config, trace)
        self.assertTrue(
            all(
                report.status_for_level(level) == Status.INCONCLUSIVE
                for level in Level
            )
        )

    def test_single_checkpoint_has_no_inter_iteration_evidence(self):
        config = replace(
            self.config,
            max_iterations=1,
            min_iterations=1,
            shot_budget=4000,
        )
        trace = Path(self.temp.name) / "single.jsonl"
        report_path = Path(self.temp.name) / "single.json"
        online = run_demo(
            config,
            trace_path=trace,
            report_path=report_path,
            run_id="single-run",
        )
        self.assertEqual(online.status_for_level(Level.INTRA_ITERATION), Status.PASS)
        self.assertEqual(online.status_for_level(Level.INTER_ITERATION), Status.INCONCLUSIVE)
        self.assertEqual(online.status_for_level(Level.RUN_LEVEL), Status.PASS)
        replay = check_trace(config, trace)
        self.assertEqual(replay.status_for_level(Level.INTRA_ITERATION), Status.PASS)
        self.assertEqual(replay.status_for_level(Level.INTER_ITERATION), Status.INCONCLUSIVE)
        self.assertEqual(replay.status_for_level(Level.RUN_LEVEL), Status.PASS)

    def test_reused_backend_job_identity_is_rejected_run_wide(self):
        targets = [
            index
            for index, event in enumerate(self.events)
            if event.name == "jobSubmitted"
        ]
        first = self.events[targets[0]]
        second = self.events[targets[1]]
        args = list(second.args)
        args[5] = first.args[5]
        payload = dict(second.payload)
        payload["external_job_id"] = first.args[5]
        mutated = list(self.events)
        mutated[targets[1]] = replace(second, args=tuple(args), payload=payload)
        trace = self._write("reused-job-id.jsonl", mutated)
        report = check_trace(self.config, trace)
        self.assertEqual(report.status, Status.FAIL)
        self.assertTrue(
            any(
                item.property_id == "inter_backend_job_unique"
                for item in report.findings
            )
        )

    def test_optimizer_protocol_certificate_cannot_be_swapped(self):
        target = next(
            index
            for index, event in enumerate(self.events)
            if event.name == "optimizerAskTellConfigured"
        )
        original = self.events[target]
        mutated = list(self.events)
        mutated[target] = replace(
            original,
            name="optimizerOpaqueConfigured",
            payload={"optimizer_protocol": "opaque"},
        )
        trace = self._write("wrong-protocol.jsonl", mutated)
        report = check_trace(self.config, trace)
        self.assertEqual(report.status, Status.FAIL)
        self.assertTrue(
            any(
                item.property_id == "inter_optimizer_protocol"
                for item in report.findings
            )
        )

    def test_redundant_payload_cannot_contradict_monitor_identity(self):
        target = next(
            index
            for index, event in enumerate(self.events)
            if event.name == "parametersBound"
        )
        original = self.events[target]
        payload = dict(original.payload)
        payload["theta_hash"] = "contradictory"
        mutated = list(self.events)
        mutated[target] = replace(original, payload=payload)
        trace = self._write("contradictory-payload.jsonl", mutated)
        report = check_trace(self.config, trace)
        self.assertEqual(report.status, Status.FAIL)
        self.assertTrue(
            any(
                item.property_id == "intra_parameter_freshness"
                for item in report.findings
            )
        )

    def test_optimizer_mutation_cannot_precede_objective_release(self):
        intent = next(
            index
            for index, event in enumerate(self.events)
            if event.name == "optimizerUpdateIntent"
        )
        updated = next(
            index
            for index, event in enumerate(self.events)
            if event.name == "optimizerUpdated"
        )
        moved_indices = {intent - 1, intent, updated - 1, updated}
        moved = [self.events[index] for index in sorted(moved_indices)]
        remaining = [
            event
            for index, event in enumerate(self.events)
            if index not in moved_indices
        ]
        release = next(
            index
            for index, event in enumerate(remaining)
            if event.name == "objectiveReleaseIntent"
        )
        mutated = remaining[: release - 1] + moved + remaining[release - 1 :]
        trace = self._write("early-optimizer-mutation.jsonl", resequence(mutated))
        report = check_trace(self.config, trace)
        self.assertEqual(report.status, Status.FAIL)
        self.assertTrue(
            any(
                item.property_id
                in {
                    "inter_update_after_objective_release",
                    "inter_updateIntentAfterRelease",
                }
                for item in report.findings
            )
        )

    def test_iteration_limit_certificate_is_exactly_once(self):
        config = replace(self.config, convergence_patience=4)
        trace = Path(self.temp.name) / "max-valid.jsonl"
        report_path = Path(self.temp.name) / "max-valid.json"
        run_demo(
            config,
            trace_path=trace,
            report_path=report_path,
            run_id="max-run",
        )
        events, errors = load_events(trace)
        self.assertFalse(errors)
        target = next(
            index
            for index, event in enumerate(events)
            if event.name == "iterationLimitReached"
        )
        duplicate = [events[target - 1], events[target]]
        mutated = events[: target + 1] + duplicate + events[target + 1 :]
        mutated_trace = self._write("duplicate-limit.jsonl", resequence(mutated))
        report = check_trace(config, mutated_trace)
        self.assertEqual(report.status, Status.FAIL)
        self.assertTrue(
            any(
                item.property_id
                in {"run_iteration_limit_once", "run_iterationLimitOnce"}
                for item in report.findings
            )
        )

    def test_activity_witnesses_are_closed_world_and_paired(self):
        without_activity = [
            event for event in self.events if event.name != "activity"
        ]
        trace = self._write(
            "missing-activity.jsonl", resequence(without_activity)
        )
        report = check_trace(self.config, trace)
        self.assertEqual(report.status, Status.FAIL)
        self.assertTrue(
            any(item.property_id == "run_activity_pairing" for item in report.findings)
        )

        started = self.events[0]
        phantom = RuntimeEvent(
            1,
            started.monotonic_ns + 1,
            "activity",
            ("replay-run", self.config.digest, "phantomBackendWrite"),
            {},
        )
        trace = self._write(
            "phantom-activity.jsonl",
            resequence([started, phantom, *self.events[1:]]),
        )
        report = check_trace(self.config, trace)
        self.assertEqual(report.status, Status.FAIL)
        self.assertTrue(
            any(item.property_id == "run_activity_pairing" for item in report.findings)
        )

    def test_term_manifest_cannot_precede_parameter_binding(self):
        term_indices = [
            index
            for index, event in enumerate(self.events)
            if event.name == "termExpected" and event.args[2] == "0"
        ]
        moved_indices = {
            index for term_index in term_indices for index in (term_index - 1, term_index)
        }
        moved = [self.events[index] for index in sorted(moved_indices)]
        remaining = [
            event
            for index, event in enumerate(self.events)
            if index not in moved_indices
        ]
        binding = next(
            index
            for index, event in enumerate(remaining)
            if event.name == "parametersBound"
        )
        mutated = remaining[: binding - 1] + moved + remaining[binding - 1 :]
        trace = self._write("terms-before-bind.jsonl", resequence(mutated))
        report = check_trace(self.config, trace)
        self.assertEqual(report.status, Status.FAIL)
        self.assertTrue(
            any(
                item.property_id
                in {"intra_term_after_binding", "intra_termExpectedAfterBinding"}
                for item in report.findings
            )
        )

    def test_optimizer_protocol_must_be_certified_during_init(self):
        certificate = next(
            index
            for index, event in enumerate(self.events)
            if event.name == "optimizerAskTellConfigured"
        )
        moved_indices = {certificate - 1, certificate}
        moved = [self.events[index] for index in sorted(moved_indices)]
        remaining = [
            event
            for index, event in enumerate(self.events)
            if index not in moved_indices
        ]
        update = next(
            index
            for index, event in enumerate(remaining)
            if event.name == "optimizerUpdateIntent"
        )
        mutated = remaining[: update - 1] + moved + remaining[update - 1 :]
        trace = self._write("late-protocol.jsonl", resequence(mutated))
        report = check_trace(self.config, trace)
        self.assertEqual(report.status, Status.FAIL)
        self.assertTrue(
            any(
                item.property_id == "inter_optimizer_protocol"
                or item.property_id == "inter_firstIterationAfterConfiguredProtocol"
                for item in report.findings
            )
        )

    def test_trace_arguments_are_not_type_coerced(self):
        records = [json.loads(event_path) for event_path in self.valid_trace.read_text(
            encoding="utf-8"
        ).splitlines()]
        target = next(
            index
            for index, record in enumerate(records)
            if record["event"] == "firstIterationStarted"
        )
        for replacement in (0, False, None):
            with self.subTest(replacement=replacement):
                mutated = json.loads(json.dumps(records))
                mutated[target]["args"][2] = replacement
                trace = Path(self.temp.name) / f"typed-arg-{replacement!r}.jsonl"
                trace.write_text(
                    "\n".join(json.dumps(record) for record in mutated) + "\n",
                    encoding="utf-8",
                )
                report = check_trace(self.config, trace)
                self.assertEqual(report.status, Status.FAIL)
                self.assertTrue(
                    any(
                        item.property_id == "run_event_schema"
                        for item in report.findings
                    )
                )

    def test_certificate_payload_types_are_exact(self):
        records = [
            json.loads(line)
            for line in self.valid_trace.read_text(encoding="utf-8").splitlines()
        ]
        started = next(
            index
            for index, record in enumerate(records)
            if record["event"] == "runStarted"
        )
        closed = next(
            index
            for index, record in enumerate(records)
            if record["event"] == "iterationClosed"
        )

        def mutate_converged(value):
            value[closed]["payload"]["converged"] = 0

        def mutate_samples(value):
            samples = value[closed]["payload"]["effective_term_samples"]
            value[closed]["payload"]["effective_term_samples"] = float(samples)

        def mutate_shots(value):
            shots = value[started]["payload"]["config"]["execution"]["shots_per_term"]
            value[started]["payload"]["config"]["execution"]["shots_per_term"] = float(shots)

        def mutate_schema(value):
            value[started]["payload"]["config"]["schema_version"] = True

        for name, mutation in (
            ("converged", mutate_converged),
            ("samples", mutate_samples),
            ("shots", mutate_shots),
            ("schema", mutate_schema),
        ):
            with self.subTest(field=name):
                mutated = json.loads(json.dumps(records))
                mutation(mutated)
                trace = Path(self.temp.name) / f"typed-payload-{name}.jsonl"
                trace.write_text(
                    "\n".join(json.dumps(record) for record in mutated) + "\n",
                    encoding="utf-8",
                )
                report = check_trace(self.config, trace)
                self.assertEqual(report.status, Status.FAIL)

    def test_trace_record_schema_is_type_exact_and_closed(self):
        records = [
            json.loads(line)
            for line in self.valid_trace.read_text(encoding="utf-8").splitlines()
        ]
        for name, mutation in (
            ("boolean-version", lambda value: value[0].__setitem__("schema_version", True)),
            ("float-version", lambda value: value[0].__setitem__("schema_version", 1.0)),
            ("unknown-field", lambda value: value[0].__setitem__("extra", "field")),
        ):
            with self.subTest(mutation=name):
                mutated = json.loads(json.dumps(records))
                mutation(mutated)
                trace = Path(self.temp.name) / f"record-schema-{name}.jsonl"
                trace.write_text(
                    "\n".join(json.dumps(record) for record in mutated) + "\n",
                    encoding="utf-8",
                )
                report = check_trace(self.config, trace)
                self.assertEqual(report.status, Status.FAIL)
                self.assertTrue(
                    any(
                        item.property_id == "run_event_schema"
                        for item in report.findings
                    )
                )

    def test_abort_cause_cannot_name_a_nonexistent_iteration(self):
        closes = [
            index
            for index, event in enumerate(self.events)
            if event.name == "iterationClosed"
        ]
        prefix = self.events[: closes[1] + 1]
        timestamp = prefix[-1].monotonic_ns
        suffix = [
            RuntimeEvent(
                1,
                timestamp + 1,
                "activity",
                ("replay-run", self.config.digest, "criticalFail"),
                {},
            ),
            RuntimeEvent(
                1,
                timestamp + 2,
                "criticalFail",
                (
                    "replay-run",
                    self.config.digest,
                    "999",
                    "ghostEval",
                    "impossibleContext",
                ),
                {},
            ),
            RuntimeEvent(
                1,
                timestamp + 3,
                "runAborted",
                (
                    "replay-run",
                    self.config.digest,
                    "999",
                    "ghostEval",
                    "impossibleContext",
                ),
                {},
            ),
            RuntimeEvent(
                1,
                timestamp + 4,
                "runClosed",
                ("replay-run", self.config.digest),
                {},
            ),
        ]
        trace = self._write(
            "ghost-abort-context.jsonl", resequence([*prefix, *suffix])
        )
        report = check_trace(self.config, trace)
        self.assertEqual(report.status, Status.FAIL)
        self.assertTrue(
            any(
                item.property_id == "run_failure_context"
                for item in report.findings
            )
        )


if __name__ == "__main__":
    unittest.main()
