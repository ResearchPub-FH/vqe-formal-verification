from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from vqe_runtime.config import load_config
from vqe_runtime.sampler_runner import (
    _sampler_experiment_provenance,
    run_sampled_vqe,
)


ROOT = Path(__file__).resolve().parents[1]


class SamplerRunnerSafetyTests(unittest.TestCase):
    def test_provenance_reuses_single_captured_qpy_digest_per_circuit(self):
        config = load_config(ROOT / "configs" / "h2_statevector.toml")

        class FakeCircuit:
            num_qubits = 2
            layout = None

        class FakeAnsatz(FakeCircuit):
            num_parameters = 4

        circuit_hashes = tuple(str(index) * 64 for index in range(1, 5))
        with patch(
            "vqe_runtime.sampler_runner._qpy_digest",
            return_value="a" * 64,
        ) as qpy_digest:
            provenance = _sampler_experiment_provenance(
                config,
                ansatz=FakeAnsatz(),
                circuits=tuple(FakeCircuit() for _ in range(4)),
                circuit_hashes=circuit_hashes,
                initial_theta=(0.1, 0.2, 0.3, 0.4),
            )

        self.assertEqual(qpy_digest.call_count, 1)
        self.assertEqual(
            provenance["sampler_experiment"][
                "parameterized_circuit_qpy_sha256"
            ],
            list(circuit_hashes),
        )

    def test_hardware_run_refuses_existing_artifact_before_backend_resolution(self):
        config = load_config(ROOT / "configs" / "h2_ibm_sampler_50.toml")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = root / "trace.jsonl"
            trace.write_text("already submitted\n", encoding="utf-8")
            evidence = root / "evidence.jsonl"
            report = root / "report.json"

            with self.assertRaisesRegex(ValueError, "duplicate jobs"):
                run_sampled_vqe(
                    config,
                    trace_path=trace,
                    report_path=report,
                    evidence_path=evidence,
                    run_id="must-not-resubmit",
                )

            self.assertEqual(trace.read_text(encoding="utf-8"), "already submitted\n")
            self.assertFalse(evidence.exists())
            self.assertFalse(report.exists())

    def test_output_artifact_paths_must_be_distinct(self):
        config = load_config(ROOT / "configs" / "h2_statevector.toml")
        with tempfile.TemporaryDirectory() as directory:
            shared = Path(directory) / "shared.jsonl"
            with self.assertRaisesRegex(ValueError, "must be distinct"):
                run_sampled_vqe(
                    config,
                    trace_path=shared,
                    report_path=shared,
                    evidence_path=Path(directory) / "evidence.jsonl",
                    run_id="distinct-paths",
                )


if __name__ == "__main__":
    unittest.main()
