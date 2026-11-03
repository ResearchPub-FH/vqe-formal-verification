from __future__ import annotations

from contextlib import redirect_stdout
from importlib import metadata as importlib_metadata
import io
import json
import math
from pathlib import Path
import tempfile
import unittest

from tools.validate_sampler_experiment import (
    EXPECTED_QISKIT_VERSION,
    FAMILY_ALPHA,
    FIXED_PAULIS,
    FIXED_SHOTS,
    main,
    simultaneous_hoeffding_bound,
)


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = WORKSPACE_ROOT / "configs" / "h2_statevector.toml"


def _has_exact_qiskit() -> bool:
    try:
        return importlib_metadata.version("qiskit") == EXPECTED_QISKIT_VERSION
    except importlib_metadata.PackageNotFoundError:
        return False


class StatisticalBoundTests(unittest.TestCase):
    def test_simultaneous_bound_matches_documented_formula(self):
        observed = simultaneous_hoeffding_bound(
            FIXED_SHOTS, len(FIXED_PAULIS), family_alpha=FAMILY_ALPHA
        )
        expected = math.sqrt(
            2.0
            * math.log((2.0 * len(FIXED_PAULIS)) / FAMILY_ALPHA)
            / FIXED_SHOTS
        )
        self.assertAlmostEqual(observed, expected, places=15)
        self.assertGreater(observed, 0.0)
        self.assertLess(observed, 2.0)

    def test_bound_rejects_invalid_inputs(self):
        invalid = [
            (0, 4, FAMILY_ALPHA),
            (1024, 0, FAMILY_ALPHA),
            (1024, 4, 0.0),
            (1024, 4, 1.0),
        ]
        for shots, comparisons, alpha in invalid:
            with self.subTest(shots=shots, comparisons=comparisons, alpha=alpha):
                with self.assertRaises(ValueError):
                    simultaneous_hoeffding_bound(
                        shots, comparisons, family_alpha=alpha
                    )


@unittest.skipUnless(
    _has_exact_qiskit(),
    f"requires the pinned Qiskit {EXPECTED_QISKIT_VERSION} environment",
)
class ExecutableValidationTests(unittest.TestCase):
    def test_cli_writes_a_complete_all_pass_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "validation.json"
            with redirect_stdout(io.StringIO()):
                exit_code = main(
                    [
                        "--config",
                        str(CONFIG_PATH),
                        "--out",
                        str(output),
                        "--quiet",
                    ]
                )
            self.assertEqual(exit_code, 0)
            report = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(report["overall_status"], "PASS")
        self.assertEqual(report["environment"]["qiskit"], EXPECTED_QISKIT_VERSION)
        self.assertEqual(report["check_summary"]["failed"], 0)
        self.assertTrue(report["checks"])
        self.assertTrue(all(item["status"] == "PASS" for item in report["checks"]))

        self.assertEqual(report["hadamard_preflight"]["observed_shots"], 1024)
        self.assertEqual(report["hadamard_preflight"]["count_sum"], 1024)
        self.assertEqual(len(report["h2_terms"]), 4)
        self.assertEqual(
            [item["pauli"] for item in report["h2_terms"]], list(FIXED_PAULIS)
        )
        for term in report["h2_terms"]:
            self.assertEqual(term["requested_shots"], 1024)
            self.assertEqual(term["observed_bitarray_num_shots"], 1024)
            self.assertEqual(term["count_sum"], 1024)
            self.assertTrue(term["within_statistical_bound"])
            self.assertEqual(len(term["raw_evidence_sha256"]), 64)

        self.assertEqual(
            {item["id"] for item in report["negative_tests"]},
            {
                "reject_corrupted_counts",
                "reject_missing_pub",
                "reject_wrong_term_assignment",
                "reject_wrong_shot_total",
                "reject_corrupted_packed_shots",
            },
        )
        self.assertTrue(
            all(item["status"] == "PASS" for item in report["negative_tests"])
        )
        ordering = report["qiskit_ordering_verification"]["cases"]
        self.assertEqual([item["counts"] for item in ordering], [{"10": 1024}, {"01": 1024}])
        self.assertTrue(all(item["status"] == "PASS" for item in ordering))


if __name__ == "__main__":
    unittest.main()
