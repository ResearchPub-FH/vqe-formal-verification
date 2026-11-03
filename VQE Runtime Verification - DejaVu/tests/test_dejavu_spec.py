from __future__ import annotations

import time
from pathlib import Path
import tempfile
import unittest

from vqe_runtime.dejavu import DejaVuUnavailable, SynchronousDejaVu
from vqe_runtime.events import RuntimeEvent


def event(seq: int, name: str, *args: str) -> RuntimeEvent:
    return RuntimeEvent(seq, time.monotonic_ns(), name, tuple(args), {})


class DejaVuSpecificationTests(unittest.TestCase):
    def test_runtime_rejects_monitor_without_pinned_build_hash(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "src/vqe_runtime/vendor/dejavu/vqe-three-level-monitor.jar"
        )
        with tempfile.TemporaryDirectory() as directory:
            altered = Path(directory) / "monitor.jar"
            altered.write_bytes(source.read_bytes() + b"altered")
            with self.assertRaises(DejaVuUnavailable):
                SynchronousDejaVu(monitor_jar=altered)

    def test_bridge_rejects_unknown_event(self):
        with SynchronousDejaVu() as monitor:
            ack = monitor.submit(event(1, "unknownEvent", "r", "c"))
        self.assertFalse(ack.passed)
        self.assertIn("run_event_schema", ack.violations)

    def test_bridge_rejects_wrong_arity(self):
        with SynchronousDejaVu() as monitor:
            ack = monitor.submit(event(1, "runStarted", "r"))
        self.assertFalse(ack.passed)
        self.assertIn("run_event_schema", ack.violations)

    def test_duplicate_run_start_is_rejected(self):
        with SynchronousDejaVu() as monitor:
            first = monitor.submit(event(1, "runStarted", "r", "c"))
            second = monitor.submit(event(2, "runStarted", "r", "c"))
        self.assertTrue(first.passed)
        self.assertFalse(second.passed)
        self.assertIn("run_startOnce", second.violations)

    def test_terminal_event_without_verified_checkpoint_is_rejected(self):
        with SynchronousDejaVu() as monitor:
            monitor.submit(event(1, "runStarted", "r", "c"))
            ack = monitor.submit(
                event(2, "runConverged", "r", "c", "0", "e", "energy")
            )
        self.assertFalse(ack.passed)
        self.assertIn("run_convergedAfterTrueClose", ack.violations)

    def test_close_without_terminal_is_rejected(self):
        with SynchronousDejaVu() as monitor:
            monitor.submit(event(1, "runStarted", "r", "c"))
            ack = monitor.submit(event(2, "runClosed", "r", "c"))
        self.assertFalse(ack.passed)
        self.assertIn("run_closeAfterTerminal", ack.violations)


if __name__ == "__main__":
    unittest.main()
