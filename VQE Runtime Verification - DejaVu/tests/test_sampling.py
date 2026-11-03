from __future__ import annotations

from base64 import b64decode, b64encode
from collections import Counter
from copy import deepcopy
import importlib.util
import json
import math
import unittest

from vqe_runtime.sampling import (
    QISKIT_BIT_ORDER,
    RAW_EVIDENCE_FORMAT,
    SamplingEvidenceError,
    build_measurement_circuit,
    classical_distribution_fidelity,
    decode_packed_bitarray,
    evidence_from_bit_array,
    evidence_from_pub_result,
    expectation_from_counts,
    expectation_from_negative_count,
    extract_bit_array,
    measurement_basis_plan,
    negative_eigenvalue_count,
    raw_evidence_sha256,
    validate_evidence_record,
    validate_pauli_label,
)


class _PackedArray:
    dtype = "uint8"

    def __init__(self, samples: list[str]):
        num_bits = len(samples[0])
        self._data = b"".join(
            int(sample, 2).to_bytes((num_bits + 7) // 8, "big")
            for sample in samples
        )
        self.shape = (len(samples), (num_bits + 7) // 8)

    def tobytes(self, order="C"):
        if order != "C":
            raise AssertionError("tests expect C order")
        return self._data


class _BitArray:
    shape = ()

    def __init__(self, samples: list[str], *, reported_counts=None):
        self._samples = list(samples)
        self.num_bits = len(samples[0])
        self.num_shots = len(samples)
        self.array = _PackedArray(samples)
        self._reported_counts = reported_counts

    def get_bitstrings(self):
        return list(self._samples)

    def get_counts(self):
        if self._reported_counts is not None:
            return dict(self._reported_counts)
        return dict(Counter(self._samples))


class _DataBin:
    def __init__(self, **fields):
        self._fields = fields
        for name, value in fields.items():
            setattr(self, name, value)

    def __getitem__(self, name):
        return self._fields[name]


class _PubResult:
    def __init__(self, **fields):
        self.data = _DataBin(**fields)


SAMPLES = ["00", "01", "01", "10", "10", "10", "11", "11"]


class PauliConventionTests(unittest.TestCase):
    def test_labels_are_strict_and_canonical(self):
        self.assertEqual(validate_pauli_label("YZ", num_qubits=2), "YZ")
        for invalid in ("", "yz", "ZA", " Z"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(SamplingEvidenceError):
                    validate_pauli_label(invalid)
        with self.assertRaises(SamplingEvidenceError):
            validate_pauli_label("YZ", num_qubits=3)

    def test_measurement_plan_uses_qiskit_rightmost_qubit_zero_convention(self):
        plan = measurement_basis_plan("YIZ")
        self.assertEqual(
            [(item.qubit, item.pauli, item.gates) for item in plan],
            [(0, "Z", ()), (2, "Y", ("sdg", "h"))],
        )
        self.assertEqual(measurement_basis_plan("II"), ())

    def test_parity_for_h2_terms(self):
        counts = {"00": 1, "01": 2, "10": 3, "11": 4}
        self.assertEqual(negative_eigenvalue_count(counts, "YZ"), 5)
        self.assertEqual(negative_eigenvalue_count(counts, "ZI"), 7)
        self.assertEqual(negative_eigenvalue_count(counts, "ZZ"), 5)
        self.assertEqual(negative_eigenvalue_count(counts, "XX"), 5)

    def test_zi_uses_left_bit_q1_and_iz_uses_right_bit_q0(self):
        counts = {"01": 1, "10": 3}
        self.assertEqual(negative_eigenvalue_count(counts, "ZI"), 3)
        self.assertEqual(negative_eigenvalue_count(counts, "IZ"), 1)

    def test_expectation_is_reconstructed_from_negative_parity(self):
        counts = {"00": 1, "01": 2, "10": 3, "11": 2}
        self.assertEqual(expectation_from_negative_count(5, 8), -0.25)
        self.assertEqual(expectation_from_counts(counts, "YZ"), -0.25)


class DistributionFidelityTests(unittest.TestCase):
    def test_identical_and_disjoint_distributions(self):
        self.assertEqual(
            classical_distribution_fidelity({"0": 0.25, "1": 0.75}, {"0": 1, "1": 3}),
            1.0,
        )
        self.assertEqual(
            classical_distribution_fidelity({"0": 1.0}, {"1": 128}),
            0.0,
        )

    def test_inputs_are_normalized_before_comparison(self):
        fidelity = classical_distribution_fidelity(
            {"00": 2.0, "11": 2.0}, {"00": 3, "11": 1}
        )
        expected = (math.sqrt(0.5 * 0.75) + math.sqrt(0.5 * 0.25)) ** 2
        self.assertAlmostEqual(fidelity, expected)

    def test_invalid_probability_and_count_mass_are_rejected(self):
        with self.assertRaisesRegex(SamplingEvidenceError, "positive mass"):
            classical_distribution_fidelity({"0": 0.0}, {"0": 1})
        with self.assertRaisesRegex(SamplingEvidenceError, "positive mass"):
            classical_distribution_fidelity({"0": 1.0}, {"0": 0})
        with self.assertRaisesRegex(SamplingEvidenceError, "nonnegative"):
            classical_distribution_fidelity({"0": -0.1}, {"0": 1})


class RawEvidenceTests(unittest.TestCase):
    def record(self):
        return evidence_from_bit_array(
            _BitArray(SAMPLES),
            term_id="t0",
            pauli="YZ",
            requested_shots=8,
        )

    def test_record_is_complete_canonical_and_lossless(self):
        record = self.record()
        self.assertEqual(record["bit_order"], QISKIT_BIT_ORDER)
        self.assertEqual(record["raw_evidence_format"], RAW_EVIDENCE_FORMAT)
        self.assertEqual(record["observed_shots"], 8)
        self.assertEqual(record["counts"], dict(sorted(Counter(SAMPLES).items())))
        self.assertEqual(record["negative_eigenvalue_count"], 5)
        self.assertEqual(record["expectation"], -0.25)
        self.assertEqual(record["raw_evidence_sha256"], raw_evidence_sha256(record))
        self.assertEqual(
            decode_packed_bitarray(
                record["packed_bitarray"], num_bits=2, observed_shots=8
            ),
            tuple(SAMPLES),
        )

        round_trip = json.loads(json.dumps(record, sort_keys=True))
        self.assertEqual(validate_evidence_record(round_trip), round_trip)
        self.assertEqual(raw_evidence_sha256(round_trip), raw_evidence_sha256(record))

    def test_pub_result_extraction_uses_named_register(self):
        bits = _BitArray(SAMPLES)
        pub = _PubResult(meas=bits)
        self.assertIs(extract_bit_array(pub), bits)
        record = evidence_from_pub_result(
            pub, term_id="t0", pauli="YZ", requested_shots=8
        )
        self.assertEqual(record["counts"]["10"], 3)
        with self.assertRaises(SamplingEvidenceError):
            extract_bit_array(pub, register_name="other")

    def test_bitarray_counts_must_match_ordered_shots(self):
        bits = _BitArray(SAMPLES, reported_counts={"00": 8})
        with self.assertRaisesRegex(SamplingEvidenceError, "counts disagree"):
            evidence_from_bit_array(
                bits, term_id="t0", pauli="YZ", requested_shots=8
            )

    def test_wrong_shot_total_is_rejected(self):
        with self.assertRaisesRegex(SamplingEvidenceError, "exactly 1024"):
            evidence_from_bit_array(
                _BitArray(SAMPLES),
                term_id="t0",
                pauli="YZ",
                requested_shots=1024,
            )

        record = self.record()
        record["requested_shots"] = 7
        record["raw_evidence_sha256"] = raw_evidence_sha256(record)
        with self.assertRaisesRegex(SamplingEvidenceError, "do not equal"):
            validate_evidence_record(record)

    def test_wrong_term_assignment_is_rejected_even_for_valid_evidence(self):
        record = self.record()
        with self.assertRaisesRegex(SamplingEvidenceError, "not 't1'"):
            validate_evidence_record(
                record,
                expected_term_id="t1",
                expected_pauli="ZI",
                expected_shots=8,
            )

    def test_corrupted_counts_are_rejected_after_attacker_rehashes(self):
        record = self.record()
        record["counts"] = {"00": 2, "01": 1, "10": 3, "11": 2}
        record["raw_evidence_sha256"] = raw_evidence_sha256(record)
        with self.assertRaisesRegex(SamplingEvidenceError, "disagrees"):
            validate_evidence_record(record)

    def test_corrupted_ordered_shot_is_rejected_after_attacker_rehashes(self):
        record = self.record()
        record["ordered_bitstrings"][0] = "11"
        record["raw_evidence_sha256"] = raw_evidence_sha256(record)
        with self.assertRaisesRegex(SamplingEvidenceError, "packed BitArray"):
            validate_evidence_record(record)

    def test_corrupted_packed_data_is_rejected(self):
        record = self.record()
        packed = record["packed_bitarray"]
        raw = bytearray(b64decode(packed["data"]))
        raw[0] ^= 1
        packed["data"] = b64encode(raw).decode("ascii")
        with self.assertRaisesRegex(SamplingEvidenceError, "disagrees|SHA-256"):
            validate_evidence_record(record)

    def test_wrong_pauli_with_recomputed_digest_changes_parity_and_is_rejected(self):
        record = self.record()
        record["pauli"] = "IZ"
        record["raw_evidence_sha256"] = raw_evidence_sha256(record)
        with self.assertRaisesRegex(SamplingEvidenceError, "count is inconsistent"):
            validate_evidence_record(record)

    def test_declared_expectation_and_digest_corruption_are_rejected(self):
        record = self.record()
        bad_expectation = deepcopy(record)
        bad_expectation["expectation"] = 0.5
        bad_expectation["raw_evidence_sha256"] = raw_evidence_sha256(bad_expectation)
        with self.assertRaisesRegex(SamplingEvidenceError, "not reconstructed"):
            validate_evidence_record(bad_expectation)

        bad_digest = deepcopy(record)
        bad_digest["raw_evidence_sha256"] = "0" * 64
        with self.assertRaisesRegex(SamplingEvidenceError, "SHA-256 mismatch"):
            validate_evidence_record(bad_digest)

    def test_schema_numbers_are_not_type_coerced(self):
        record = self.record()
        record["schema_version"] = 1.0
        record["raw_evidence_sha256"] = raw_evidence_sha256(record)
        with self.assertRaisesRegex(SamplingEvidenceError, "schema version"):
            validate_evidence_record(record)


@unittest.skipUnless(importlib.util.find_spec("qiskit"), "qiskit extra not installed")
class QiskitIntegrationTests(unittest.TestCase):
    def test_measurement_circuit_and_sampler_confirm_label_order(self):
        from qiskit import QuantumCircuit
        from qiskit.primitives import StatevectorSampler

        source = QuantumCircuit(2)
        source.x(1)
        measured = build_measurement_circuit(source, "ZI")

        names = [instruction.operation.name for instruction in measured.data]
        self.assertEqual(names, ["x", "measure", "measure"])
        measurements = [
            instruction for instruction in measured.data if instruction.operation.name == "measure"
        ]
        self.assertEqual(
            [measured.find_bit(item.qubits[0]).index for item in measurements], [0, 1]
        )
        self.assertEqual(
            [measured.find_bit(item.clbits[0]).index for item in measurements], [0, 1]
        )

        result = StatevectorSampler(default_shots=8, seed=17).run([measured]).result()
        record = evidence_from_pub_result(
            result[0], term_id="t1", pauli="ZI", requested_shots=8
        )
        self.assertEqual(record["counts"], {"10": 8})
        self.assertEqual(record["negative_eigenvalue_count"], 8)
        self.assertEqual(record["expectation"], -1.0)

    def test_y_basis_is_sdg_then_h_on_the_labelled_qubit(self):
        from qiskit import QuantumCircuit

        measured = build_measurement_circuit(QuantumCircuit(2), "YZ")
        rotations = [
            (
                instruction.operation.name,
                measured.find_bit(instruction.qubits[0]).index,
            )
            for instruction in measured.data
            if instruction.operation.name != "measure"
        ]
        self.assertEqual(rotations, [("sdg", 1), ("h", 1)])


if __name__ == "__main__":
    unittest.main()
