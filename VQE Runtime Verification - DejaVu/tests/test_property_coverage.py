from __future__ import annotations

from collections import Counter
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("property_coverage", ROOT / "tools/property_coverage.py")
coverage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(coverage)

ASK_TELL = {"optimizer_protocol": "ask-tell", "allow_optimizer_stopped": False}
OPAQUE = {"optimizer_protocol": "opaque", "allow_optimizer_stopped": True}


class PropertyCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.properties = coverage.parse_spec()

    def test_every_property_has_a_trigger(self):
        self.assertEqual(len(self.properties), 68)
        self.assertTrue(all(p["triggers"] for p in self.properties.values()))
        self.assertEqual({n: p["nested"] for n, p in self.properties.items() if p["nested"]}, coverage.NESTED)

    def test_disjunctive_trigger_is_exercised_by_any_disjunct(self):
        name = "run_normalTerminalWithoutFailure"
        self.assertEqual(self.properties[name]["triggers"], ["runConverged", "runMaxIterations", "runOptimizerStopped"])
        row = coverage.classify(self.properties, Counter(runMaxIterations=1), ASK_TELL)[name]
        self.assertEqual(row["status"], "EXERCISED")
        self.assertEqual(row["inapplicable_triggers"], ["runOptimizerStopped"])
        self.assertEqual(row["unfired_triggers"], ["runConverged"])
        self.assertEqual(coverage.classify(self.properties, Counter(), ASK_TELL)[name]["status"], "NOT_EXERCISED")

    def test_each_class_is_assigned(self):
        rows = coverage.classify(self.properties, Counter(runClosed=1, runAborted=0), ASK_TELL)
        self.assertEqual(rows["inter_opaqueAdvanceOnce"]["status"], "NOT_APPLICABLE")
        self.assertEqual(rows["run_optimizerStopIsFirstTerminal"]["status"], "NOT_APPLICABLE")
        self.assertEqual(rows["run_abortAfterFailure"]["status"], "NOT_EXERCISED")
        self.assertEqual(rows["run_failureRequiresAbortAtClose"]["status"], "NESTED_NOT_EXERCISED")
        self.assertEqual(rows["run_closeOnce"]["status"], "EXERCISED")
        rows = coverage.classify(self.properties, Counter(runClosed=1, criticalFail=1), ASK_TELL)
        self.assertEqual(rows["run_failureRequiresAbortAtClose"]["status"], "EXERCISED")

    def test_applicability_follows_recorded_protocol(self):
        rows = coverage.classify(self.properties, Counter(), OPAQUE)
        self.assertEqual(rows["inter_opaqueAdvanceOnce"]["status"], "NOT_EXERCISED")
        self.assertEqual(rows["inter_updateIntentOnce"]["status"], "NOT_APPLICABLE")
        self.assertEqual(rows["run_optimizerStopIsFirstTerminal"]["status"], "NOT_EXERCISED")

    def test_trace_configuration_is_read_from_run_start(self):
        events = [{"event": "runStarted", "args": ["r", "c"], "payload": {"config": {"execution": ASK_TELL}}},
                  {"event": "runClosed", "args": ["r", "c"], "payload": {}}]
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "trace.jsonl"
            trace.write_text("".join(json.dumps(e) + "\n" for e in events))
            result = coverage.report(trace, self.properties)
        self.assertEqual(result["configuration"]["optimizer_protocol"], "ask-tell")
        self.assertEqual(result["rows"]["run_closeOnce"]["status"], "EXERCISED")
        self.assertEqual(sum(result["summary"].values()), 68)


if __name__ == "__main__":
    unittest.main()
