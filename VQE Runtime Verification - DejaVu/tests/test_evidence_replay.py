from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
from dataclasses import replace
from importlib import metadata as importlib_metadata
import io
import json
from pathlib import Path
import tempfile
import unittest

from vqe_runtime.checker import check_trace
from vqe_runtime.cli import main as cli_main
from vqe_runtime.config import load_config
from vqe_runtime.evidence import manifest_sha256, record_hashes_sha256
from vqe_runtime.report import Status
from vqe_runtime.sampler_runner import run_sampled_vqe
from vqe_runtime.sampling import raw_evidence_sha256


ROOT = Path(__file__).resolve().parents[1]
BASE_CONFIG_PATH = ROOT / "configs" / "h2_statevector.toml"
EXPECTED_QISKIT_VERSION = "2.5.2"


def _has_exact_qiskit() -> bool:
    try:
        return importlib_metadata.version("qiskit") == EXPECTED_QISKIT_VERSION
    except importlib_metadata.PackageNotFoundError:
        return False


@unittest.skipUnless(
    _has_exact_qiskit(),
    f"requires the pinned Qiskit {EXPECTED_QISKIT_VERSION} environment",
)
class EvidenceReplayIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        base = load_config(BASE_CONFIG_PATH)
        cls.config = replace(
            base,
            max_iterations=3,
            shot_budget=3 * len(base.hamiltonian.terms) * base.shots_per_term,
            min_iterations=3,
            convergence_patience=2,
        )
        cls.trace = cls.root / "trace.jsonl"
        cls.evidence = cls.root / "evidence.jsonl"
        cls.online_report = cls.root / "online.json"
        run_sampled_vqe(
            cls.config,
            trace_path=cls.trace,
            report_path=cls.online_report,
            evidence_path=cls.evidence,
            run_id="evidence-replay-integration",
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def test_valid_sidecar_passes_all_three_levels(self) -> None:
        report = check_trace(
            self.config,
            self.trace,
            evidence_path=self.evidence,
        )
        self.assertEqual(report.status, Status.PASS)
        self.assertFalse(report.findings)
        self.assertTrue(
            {
                "intra_raw_evidence_link",
                "intra_pub_assignment",
                "intra_parity_reconstruction",
                "inter_raw_evidence_identity_unique",
                "run_raw_evidence_complete",
                "run_physical_shot_budget",
                "run_execution_options",
            }
            <= report.checked_properties
        )

    def test_sampler_replay_without_explicit_sidecar_is_inconclusive(self) -> None:
        report = check_trace(self.config, self.trace)
        self.assertEqual(report.status, Status.INCONCLUSIVE)
        self.assertTrue(
            any(
                finding.property_id == "run_raw_evidence_complete"
                and finding.status == Status.INCONCLUSIVE
                for finding in report.findings
            )
        )

    def test_rehashed_count_corruption_is_rejected(self) -> None:
        records = [
            json.loads(line)
            for line in self.evidence.read_text(encoding="utf-8").splitlines()
        ]
        altered = deepcopy(records)
        altered[0]["counts"] = {"00": altered[0]["observed_shots"]}
        altered[0]["raw_evidence_sha256"] = raw_evidence_sha256(altered[0])
        altered[-1]["ordered_record_hashes"][0] = altered[0][
            "raw_evidence_sha256"
        ]
        altered[-1]["record_hashes_sha256"] = record_hashes_sha256(
            altered[-1]["ordered_record_hashes"]
        )
        altered[-1]["manifest_sha256"] = manifest_sha256(altered[-1])
        corrupted = self.root / "corrupted-counts.jsonl"
        corrupted.write_text(
            "".join(
                json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                for record in altered
            ),
            encoding="utf-8",
        )

        report = check_trace(
            self.config,
            self.trace,
            evidence_path=corrupted,
        )
        self.assertEqual(report.status, Status.FAIL)
        self.assertTrue(
            any(
                finding.property_id == "run_raw_evidence_complete"
                and finding.status == Status.FAIL
                for finding in report.findings
            )
        )

    def test_cli_check_accepts_the_explicit_evidence_path(self) -> None:
        config_text = BASE_CONFIG_PATH.read_text(encoding="utf-8")
        config_text = config_text.replace(
            'hamiltonian = "../data/h2_hamiltonian.json"',
            f'hamiltonian = "{(ROOT / "data" / "h2_hamiltonian.json").as_posix()}"',
        )
        config_text = config_text.replace("max_iterations = 50", "max_iterations = 3")
        config_text = config_text.replace("shot_budget = 204800", "shot_budget = 12288")
        config_text = config_text.replace("min_iterations = 10", "min_iterations = 3")
        config_text = config_text.replace("patience = 3", "patience = 2")
        config_path = self.root / "replay-config.toml"
        config_path.write_text(config_text, encoding="utf-8")
        replay_report = self.root / "cli-replay.json"

        with redirect_stdout(io.StringIO()):
            exit_code = cli_main(
                [
                    "check",
                    str(self.trace),
                    "--config",
                    str(config_path),
                    "--evidence",
                    str(self.evidence),
                    "--report",
                    str(replay_report),
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            json.loads(replay_report.read_text(encoding="utf-8"))["status"],
            "pass",
        )


if __name__ == "__main__":
    unittest.main()
