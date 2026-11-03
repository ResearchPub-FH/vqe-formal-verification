from __future__ import annotations

import unittest

from vqe_runtime.qiskit_runner import _observed_shots


class _PubResult:
    def __init__(self, metadata):
        self.metadata = metadata


class QiskitResultMetadataTests(unittest.TestCase):
    def test_observed_shots_are_read_from_pub_metadata(self):
        result = [_PubResult({"shots": 4096, "num_randomizations": 32})]
        self.assertEqual(_observed_shots(result), 4096)

    def test_missing_shot_metadata_remains_unknown(self):
        self.assertIsNone(_observed_shots([_PubResult({})]))

    def test_missing_pub_metadata_remains_unknown(self):
        self.assertIsNone(_observed_shots([]))

    def test_malformed_shot_metadata_is_rejected(self):
        for value in (True, 0, -1, 4096.0, "4096"):
            with self.subTest(value=value):
                with self.assertRaises(RuntimeError):
                    _observed_shots([_PubResult({"shots": value})])


if __name__ == "__main__":
    unittest.main()
