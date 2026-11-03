from __future__ import annotations

from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from vqe_runtime.evidence import (
    EvidenceJournal,
    EvidenceJournalError,
    load_evidence,
    manifest_sha256,
    record_hashes_sha256,
)
from vqe_runtime.sampling import (
    QISKIT_BIT_ORDER,
    RAW_EVIDENCE_FORMAT,
    RAW_EVIDENCE_SCHEMA_VERSION,
    expectation_from_negative_count,
    negative_eigenvalue_count,
    raw_evidence_sha256,
    validate_evidence_record,
)


CONFIG_HASH = "a" * 64
SAMPLES = ("00", "01", "01", "10", "10", "10", "11", "11")


def _raw_record(*, term_id: str = "t0", pauli: str = "YZ") -> dict:
    raw = b"".join(int(sample, 2).to_bytes(1, "big") for sample in SAMPLES)
    counts = dict(sorted(Counter(SAMPLES).items()))
    negative = negative_eigenvalue_count(counts, pauli)
    record = {
        "schema_version": RAW_EVIDENCE_SCHEMA_VERSION,
        "raw_evidence_format": RAW_EVIDENCE_FORMAT,
        "term_id": term_id,
        "pauli": pauli,
        "requested_shots": len(SAMPLES),
        "observed_shots": len(SAMPLES),
        "num_bits": 2,
        "bit_order": QISKIT_BIT_ORDER,
        "ordered_bitstrings": list(SAMPLES),
        "counts": counts,
        "packed_bitarray": {
            "encoding": "base64",
            "dtype": "uint8",
            "shape": [len(SAMPLES), 1],
            "order": "C",
            "byte_order": "big",
            "data": __import__("base64").b64encode(raw).decode("ascii"),
        },
        "negative_eigenvalue_count": negative,
        "expectation": expectation_from_negative_count(negative, len(SAMPLES)),
    }
    record["raw_evidence_sha256"] = raw_evidence_sha256(record)
    return validate_evidence_record(record)


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


class EvidenceJournalRoundTripTests(unittest.TestCase):
    def test_append_is_durable_and_wrapper_metadata_is_hashed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.jsonl"
            core = _raw_record()
            original_packed = core["packed_bitarray"]["data"]
            with EvidenceJournal(
                path, run_id="sample-run", config_hash=CONFIG_HASH
            ) as journal:
                first = journal.append_pub(
                    core,
                    identity={
                        "evaluation_id": "eval0",
                        "external_job_id": "localJob0",
                        "pub_index": 0,
                        "backend": "statevector_sampler",
                        "parameter_vector": [0.1, -0.2],
                        "returned_metadata": {"shots": 8},
                    },
                )

                # append_pub returns only after the complete first line is visible,
                # which lets the runner safely emit its trace event afterwards.
                on_disk = path.read_text(encoding="utf-8").splitlines()
                self.assertEqual(len(on_disk), 1)
                self.assertEqual(json.loads(on_disk[0]), first)
                self.assertNotEqual(
                    first["raw_evidence_sha256"], core["raw_evidence_sha256"]
                )
                self.assertEqual(first["record_type"], "pub")
                self.assertEqual(first["record_index"], 0)
                self.assertEqual(first["evaluation_id"], "eval0")
                self.assertEqual(first["packed_bitarray"]["data"], original_packed)
                self.assertEqual(
                    first["raw_evidence_sha256"], raw_evidence_sha256(first)
                )
                validate_evidence_record(first)

                second = journal.append_pub(
                    _raw_record(term_id="t1", pauli="ZI"),
                    identity={
                        "evaluation_id": "eval0",
                        "external_job_id": "localJob0",
                        "pub_index": 1,
                    },
                )
                manifest = journal.seal()
                self.assertTrue(journal.sealed)

            loaded = load_evidence(
                path,
                expected_run_id="sample-run",
                expected_config_hash=CONFIG_HASH,
            )
            self.assertTrue(loaded.ok, loaded.errors)
            self.assertEqual(len(loaded.records), 2)
            self.assertEqual(
                set(loaded.records_by_hash),
                {first["raw_evidence_sha256"], second["raw_evidence_sha256"]},
            )
            self.assertEqual(manifest["record_count"], 2)
            self.assertEqual(manifest["total_observed_shots"], 16)
            self.assertEqual(
                manifest["ordered_record_hashes"],
                [first["raw_evidence_sha256"], second["raw_evidence_sha256"]],
            )
            self.assertEqual(
                manifest["record_hashes_sha256"],
                record_hashes_sha256(manifest["ordered_record_hashes"]),
            )
            self.assertEqual(manifest["manifest_sha256"], manifest_sha256(manifest))

    def test_records_and_return_values_do_not_alias_journal_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.jsonl"
            journal = EvidenceJournal(path, run_id="run", config_hash=CONFIG_HASH)
            returned = journal.append_pub(
                _raw_record(), identity={"evaluation_id": "eval0", "pub_index": 0}
            )
            returned["counts"]["00"] = 999
            snapshot = journal.records
            snapshot[0]["ordered_bitstrings"][0] = "11"
            manifest = journal.seal()
            journal.close()
            self.assertEqual(manifest["total_observed_shots"], 8)
            self.assertTrue(load_evidence(path).ok)

    def test_reserved_metadata_and_append_after_seal_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.jsonl"
            journal = EvidenceJournal(path, run_id="run", config_hash=CONFIG_HASH)
            with self.assertRaisesRegex(EvidenceJournalError, "collide"):
                journal.append_pub(_raw_record(), identity={"term_id": "replacement"})
            journal.append_pub(_raw_record(), identity={"note": "kept verbatim"})
            journal.seal()
            with self.assertRaisesRegex(EvidenceJournalError, "already sealed"):
                journal.append_pub(_raw_record())
            with self.assertRaisesRegex(EvidenceJournalError, "already sealed"):
                journal.seal()
            journal.close()


class StrictLoaderTests(unittest.TestCase):
    def _sealed_records(self, path: Path) -> list[dict]:
        with EvidenceJournal(
            path, run_id="strict-run", config_hash=CONFIG_HASH
        ) as journal:
            journal.append_pub(
                _raw_record(), identity={"evaluation_id": "eval0", "pub_index": 0}
            )
            journal.append_pub(
                _raw_record(term_id="t1", pauli="ZI"),
                identity={"evaluation_id": "eval0", "pub_index": 1},
            )
            journal.seal()
        return [json.loads(line) for line in path.read_text().splitlines()]

    def test_missing_manifest_and_pub_after_manifest_are_orphans(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.jsonl"
            records = self._sealed_records(path)
            _write_jsonl(path, records[:-1])
            missing = load_evidence(path)
            self.assertFalse(missing.ok)
            self.assertTrue(any("orphaned" in error for error in missing.errors))

            _write_jsonl(path, [records[0], records[-1], records[1]])
            after = load_evidence(path)
            self.assertFalse(after.ok)
            self.assertTrue(any("after manifest" in error for error in after.errors))

    def test_duplicate_hash_index_and_logical_identity_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.jsonl"
            records = self._sealed_records(path)
            duplicate = deepcopy(records[0])
            _write_jsonl(path, [records[0], duplicate, records[-1]])
            loaded = load_evidence(path)
            self.assertFalse(loaded.ok)
            self.assertTrue(any("duplicate raw evidence hash" in e for e in loaded.errors))
            self.assertTrue(any("duplicate record_index" in e for e in loaded.errors))
            self.assertTrue(any("duplicate PUB identity" in e for e in loaded.errors))

    def test_manifest_totals_hash_list_and_aggregate_are_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.jsonl"
            records = self._sealed_records(path)

            for field, replacement, expected in (
                ("record_count", 7, "record_count"),
                ("total_observed_shots", 7, "total_observed_shots"),
                ("ordered_record_hashes", list(reversed(records[-1]["ordered_record_hashes"])), "ordered record hashes"),
            ):
                with self.subTest(field=field):
                    altered = deepcopy(records)
                    altered[-1][field] = replacement
                    altered[-1]["record_hashes_sha256"] = record_hashes_sha256(
                        altered[-1]["ordered_record_hashes"]
                    )
                    altered[-1]["manifest_sha256"] = manifest_sha256(altered[-1])
                    _write_jsonl(path, altered)
                    loaded = load_evidence(path)
                    self.assertFalse(loaded.ok)
                    self.assertTrue(
                        any(expected in error for error in loaded.errors), loaded.errors
                    )

            altered = deepcopy(records)
            altered[-1]["record_hashes_sha256"] = "0" * 64
            altered[-1]["manifest_sha256"] = manifest_sha256(altered[-1])
            _write_jsonl(path, altered)
            loaded = load_evidence(path)
            self.assertTrue(any("aggregate" in error for error in loaded.errors))

    def test_raw_shots_are_replayed_even_if_attacker_rehashes_every_wrapper(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.jsonl"
            records = self._sealed_records(path)
            records[0]["counts"] = {"00": 8}
            records[0]["raw_evidence_sha256"] = raw_evidence_sha256(records[0])
            records[-1]["ordered_record_hashes"][0] = records[0]["raw_evidence_sha256"]
            records[-1]["record_hashes_sha256"] = record_hashes_sha256(
                records[-1]["ordered_record_hashes"]
            )
            records[-1]["manifest_sha256"] = manifest_sha256(records[-1])
            _write_jsonl(path, records)
            loaded = load_evidence(path)
            self.assertFalse(loaded.ok)
            self.assertTrue(
                any("count dictionary disagrees" in error for error in loaded.errors),
                loaded.errors,
            )

    def test_duplicate_json_keys_blank_lines_and_unterminated_records_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.jsonl"
            path.write_text(
                '{"record_type":"manifest","record_type":"manifest"}\n\n{}',
                encoding="utf-8",
            )
            loaded = load_evidence(path)
            self.assertFalse(loaded.ok)
            self.assertTrue(any("duplicate JSON object key" in e for e in loaded.errors))
            self.assertTrue(any("blank lines" in e for e in loaded.errors))
            self.assertTrue(any("unterminated" in e for e in loaded.errors))

    def test_expected_run_and_config_are_bound_without_using_trace_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.jsonl"
            self._sealed_records(path)
            loaded = load_evidence(
                path,
                expected_run_id="another-run",
                expected_config_hash="b" * 64,
            )
            self.assertFalse(loaded.ok)
            self.assertTrue(any("expected run_id" in e for e in loaded.errors))
            self.assertTrue(any("expected config_hash" in e for e in loaded.errors))


if __name__ == "__main__":
    unittest.main()
