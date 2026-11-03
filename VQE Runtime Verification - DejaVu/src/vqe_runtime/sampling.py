"""Raw Sampler evidence and Pauli-basis measurement utilities.

The module deliberately has no import-time dependency on Qiskit or NumPy.
Qiskit is imported only by :func:`build_measurement_circuit`; evidence replay
operates solely on JSON-compatible values and Python's standard library.

Qiskit writes a classical register as ``c[n-1] ... c[0]``.  A Pauli label is
written in the matching order, so the right-most Pauli character acts on
qubit 0.  Consequently, a complete bitstring returned by ``BitArray`` can be
paired character-for-character with its Pauli label when computing parity.
"""

from __future__ import annotations

from base64 import b64decode, b64encode
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import hmac
import json
import math
from typing import Any


RAW_EVIDENCE_SCHEMA_VERSION = 1
RAW_EVIDENCE_FORMAT = "packed-bitarray-v1"
QISKIT_BIT_ORDER = "qiskit-msb-qn-1-to-q0"
_PAULI_SYMBOLS = frozenset("IXYZ")


class SamplingEvidenceError(ValueError):
    """Raised when sampled evidence is missing, ambiguous, or inconsistent."""


@dataclass(frozen=True, slots=True)
class BasisMeasurement:
    """The basis rotation needed before measuring one active qubit in Z."""

    qubit: int
    pauli: str
    gates: tuple[str, ...]


def _positive_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SamplingEvidenceError(f"{name} must be a positive integer")
    return value


def validate_pauli_label(pauli: Any, *, num_qubits: int | None = None) -> str:
    """Return a validated uppercase I/X/Y/Z Pauli label.

    Labels are intentionally not stripped or uppercased: canonical evidence
    must not admit two spellings of the same observable.
    """

    if not isinstance(pauli, str) or not pauli:
        raise SamplingEvidenceError("pauli must be a non-empty string")
    if any(symbol not in _PAULI_SYMBOLS for symbol in pauli):
        raise SamplingEvidenceError("pauli may contain only uppercase I, X, Y, and Z")
    if num_qubits is not None:
        _positive_integer(num_qubits, "num_qubits")
        if len(pauli) != num_qubits:
            raise SamplingEvidenceError(
                f"Pauli label has {len(pauli)} qubits; expected {num_qubits}"
            )
    return pauli


def measurement_basis_plan(pauli: str) -> tuple[BasisMeasurement, ...]:
    """Describe basis rotations in ascending Qiskit qubit order.

    ``X`` uses H, ``Y`` uses S-dagger followed by H, ``Z`` needs no rotation,
    and identity positions are excluded.  For example, ``ZI`` produces a
    single entry for qubit 1 because the right-most character addresses q0.
    """

    label = validate_pauli_label(pauli)
    gates = {"X": ("h",), "Y": ("sdg", "h"), "Z": ()}
    return tuple(
        BasisMeasurement(qubit, symbol, gates[symbol])
        for qubit, symbol in enumerate(reversed(label))
        if symbol != "I"
    )


def build_measurement_circuit(
    circuit: Any,
    pauli: str,
    *,
    register_name: str = "meas",
) -> Any:
    """Copy an unmeasured Qiskit circuit and append one Pauli measurement.

    Every logical qubit is measured into the same-index classical bit.  Bits
    corresponding to ``I`` are retained as raw evidence but excluded from the
    parity computation.  Requiring an initially classical-bit-free circuit
    prevents register concatenation from making the bitstring convention
    ambiguous.
    """

    try:
        from qiskit.circuit import ClassicalRegister
    except ImportError as exc:  # pragma: no cover - exercised without the extra
        raise RuntimeError("install the qiskit extra to build measurement circuits") from exc

    if not isinstance(register_name, str) or not register_name:
        raise SamplingEvidenceError("register_name must be a non-empty string")
    try:
        num_qubits = circuit.num_qubits
        num_clbits = circuit.num_clbits
    except AttributeError as exc:
        raise TypeError("circuit must be a Qiskit QuantumCircuit") from exc
    label = validate_pauli_label(pauli, num_qubits=num_qubits)
    if num_clbits != 0:
        raise SamplingEvidenceError(
            "measurement source circuit must not already contain classical bits"
        )

    measured = circuit.copy()
    classical = ClassicalRegister(num_qubits, register_name)
    measured.add_register(classical)
    for item in measurement_basis_plan(label):
        for gate in item.gates:
            getattr(measured, gate)(item.qubit)
    for qubit in range(num_qubits):
        measured.measure(qubit, classical[qubit])
    return measured


def extract_bit_array(pub_result: Any, *, register_name: str = "meas") -> Any:
    """Extract one named BitArray-like object from a Sampler PUB result."""

    if not isinstance(register_name, str) or not register_name:
        raise SamplingEvidenceError("register_name must be a non-empty string")
    try:
        data = pub_result.data
    except AttributeError as exc:
        raise SamplingEvidenceError("Sampler PUB result has no data bin") from exc

    sentinel = object()
    bit_array = getattr(data, register_name, sentinel)
    if bit_array is sentinel:
        try:
            bit_array = data[register_name]
        except (KeyError, TypeError, AttributeError) as exc:
            raise SamplingEvidenceError(
                f"Sampler PUB result has no {register_name!r} BitArray"
            ) from exc

    required = ("array", "num_bits", "num_shots", "shape", "get_bitstrings", "get_counts")
    missing = [name for name in required if not hasattr(bit_array, name)]
    if missing:
        raise SamplingEvidenceError(
            f"Sampler field {register_name!r} is not a BitArray; missing {missing}"
        )
    return bit_array


def _normalise_bitstrings(values: Any, num_bits: int) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise SamplingEvidenceError("ordered bitstrings must be a sequence")
    try:
        bitstrings = tuple(values)
    except TypeError as exc:
        raise SamplingEvidenceError("ordered bitstrings must be iterable") from exc
    for value in bitstrings:
        if (
            not isinstance(value, str)
            or len(value) != num_bits
            or any(bit not in "01" for bit in value)
        ):
            raise SamplingEvidenceError(
                f"each bitstring must contain exactly {num_bits} binary digits"
            )
    return bitstrings


def _normalise_counts(values: Any, num_bits: int) -> dict[str, int]:
    if not isinstance(values, Mapping):
        raise SamplingEvidenceError("counts must be a mapping")
    counts: dict[str, int] = {}
    for bitstring, count in values.items():
        if (
            not isinstance(bitstring, str)
            or len(bitstring) != num_bits
            or any(bit not in "01" for bit in bitstring)
        ):
            raise SamplingEvidenceError(
                f"each count key must contain exactly {num_bits} binary digits"
            )
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise SamplingEvidenceError("count values must be positive integers")
        counts[bitstring] = count
    return dict(sorted(counts.items()))


def negative_eigenvalue_count(counts: Mapping[str, int], pauli: str) -> int:
    """Count shots with odd parity on the Pauli's non-identity positions.

    Both Pauli labels and Qiskit count keys are most-significant-bit first, so
    their characters align directly.  In particular, for ``ZI`` the key
    ``"10"`` is negative while ``"01"`` is positive.
    """

    label = validate_pauli_label(pauli)
    normalised = _normalise_counts(counts, len(label))
    active_positions = tuple(
        position for position, symbol in enumerate(label) if symbol != "I"
    )
    return sum(
        count
        for bitstring, count in normalised.items()
        if sum(bitstring[position] == "1" for position in active_positions) % 2
    )


def expectation_from_negative_count(negative_count: int, shots: int) -> float:
    """Reconstruct a Pauli expectation as ``1 - 2*N_negative/shots``."""

    total = _positive_integer(shots, "shots")
    if (
        isinstance(negative_count, bool)
        or not isinstance(negative_count, int)
        or not 0 <= negative_count <= total
    ):
        raise SamplingEvidenceError(
            "negative_eigenvalue_count must be an integer within [0, shots]"
        )
    return 1.0 - (2.0 * negative_count / total)


def classical_distribution_fidelity(
    ideal_probabilities: Mapping[str, float],
    observed_counts: Mapping[str, int],
) -> float:
    """Return squared Bhattacharyya fidelity for ideal and sampled outcomes.

    The count dictionary is normalized internally.  This is a measurement-
    distribution fidelity, not a tomographic quantum-state fidelity.  It is
    appropriate for comparing one sampled measurement PUB with the ideal
    distribution of the same bound measurement circuit.
    """

    if not isinstance(ideal_probabilities, Mapping) or not ideal_probabilities:
        raise SamplingEvidenceError("ideal probabilities must be a non-empty mapping")
    if not isinstance(observed_counts, Mapping) or not observed_counts:
        raise SamplingEvidenceError("observed counts must be a non-empty mapping")

    ideal: dict[str, float] = {}
    ideal_total = 0.0
    for outcome, value in ideal_probabilities.items():
        if not isinstance(outcome, str) or not outcome:
            raise SamplingEvidenceError("ideal outcome labels must be non-empty strings")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SamplingEvidenceError("ideal probabilities must be numeric")
        probability = float(value)
        if not math.isfinite(probability) or probability < 0.0:
            raise SamplingEvidenceError(
                "ideal probabilities must be finite and nonnegative"
            )
        ideal[outcome] = probability
        ideal_total += probability
    if ideal_total <= 0.0:
        raise SamplingEvidenceError("ideal probabilities must have positive mass")

    observed: dict[str, int] = {}
    observed_total = 0
    for outcome, value in observed_counts.items():
        if not isinstance(outcome, str) or not outcome:
            raise SamplingEvidenceError(
                "observed outcome labels must be non-empty strings"
            )
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise SamplingEvidenceError(
                "observed counts must be nonnegative integers"
            )
        observed[outcome] = value
        observed_total += value
    if observed_total <= 0:
        raise SamplingEvidenceError("observed counts must have positive mass")

    coefficient = math.fsum(
        math.sqrt(
            ideal.get(outcome, 0.0)
            / ideal_total
            * observed.get(outcome, 0)
            / observed_total
        )
        for outcome in set(ideal) | set(observed)
    )
    # Floating-point normalization can place a unit result a few ulps outside
    # the closed interval.
    return min(1.0, max(0.0, coefficient * coefficient))


def expectation_from_counts(counts: Mapping[str, int], pauli: str) -> float:
    """Reconstruct a Pauli expectation from a complete counts dictionary."""

    label = validate_pauli_label(pauli)
    normalised = _normalise_counts(counts, len(label))
    shots = sum(normalised.values())
    return expectation_from_negative_count(
        negative_eigenvalue_count(normalised, label), shots
    )


def _packed_array_record(
    bit_array: Any,
    bitstrings: Sequence[str],
    *,
    num_bits: int,
    observed_shots: int,
) -> dict[str, Any]:
    """Capture the exact scalar Qiskit BitArray uint8 buffer."""

    try:
        pub_shape = tuple(int(value) for value in bit_array.shape)
    except (TypeError, ValueError) as exc:
        raise SamplingEvidenceError("BitArray shape is malformed") from exc
    if pub_shape:
        raise SamplingEvidenceError(
            "parameter-swept BitArrays are ambiguous; bind one parameter vector per PUB"
        )

    array = bit_array.array
    if str(getattr(array, "dtype", "")) != "uint8":
        raise SamplingEvidenceError("BitArray packed data must have dtype uint8")
    try:
        shape = tuple(int(value) for value in array.shape)
    except (AttributeError, TypeError, ValueError) as exc:
        raise SamplingEvidenceError("BitArray packed-array shape is malformed") from exc
    bytes_per_shot = (num_bits + 7) // 8
    expected_shape = (observed_shots, bytes_per_shot)
    if shape != expected_shape:
        raise SamplingEvidenceError(
            f"BitArray packed-array shape is {shape}; expected {expected_shape}"
        )
    try:
        raw = array.tobytes(order="C")
    except TypeError:
        raw = array.tobytes()
    except AttributeError as exc:
        raise SamplingEvidenceError("BitArray packed data cannot be serialized") from exc
    if not isinstance(raw, bytes) or len(raw) != observed_shots * bytes_per_shot:
        raise SamplingEvidenceError("BitArray packed byte length is inconsistent")

    mask = (1 << num_bits) - 1
    decoded: list[str] = []
    for offset in range(0, len(raw), bytes_per_shot):
        value = int.from_bytes(raw[offset : offset + bytes_per_shot], "big")
        if value & ~mask:
            raise SamplingEvidenceError("BitArray has nonzero unused high bits")
        decoded.append(format(value, f"0{num_bits}b"))
    if tuple(decoded) != tuple(bitstrings):
        raise SamplingEvidenceError(
            "BitArray packed bytes disagree with its ordered bitstrings"
        )

    return {
        "encoding": "base64",
        "dtype": "uint8",
        "shape": list(shape),
        "order": "C",
        "byte_order": "big",
        "data": b64encode(raw).decode("ascii"),
    }


def decode_packed_bitarray(
    packed: Mapping[str, Any],
    *,
    num_bits: int,
    observed_shots: int,
) -> tuple[str, ...]:
    """Losslessly decode the packed representation without importing NumPy."""

    _positive_integer(num_bits, "num_bits")
    _positive_integer(observed_shots, "observed_shots")
    if not isinstance(packed, Mapping):
        raise SamplingEvidenceError("packed_bitarray must be an object")
    required = {"encoding", "dtype", "shape", "order", "byte_order", "data"}
    missing = required - set(packed)
    if missing:
        raise SamplingEvidenceError(f"packed_bitarray is missing {sorted(missing)}")
    if packed["encoding"] != "base64" or packed["dtype"] != "uint8":
        raise SamplingEvidenceError("unsupported packed BitArray encoding or dtype")
    if packed["order"] != "C" or packed["byte_order"] != "big":
        raise SamplingEvidenceError("unsupported packed BitArray ordering")
    bytes_per_shot = (num_bits + 7) // 8
    if packed["shape"] != [observed_shots, bytes_per_shot]:
        raise SamplingEvidenceError("packed BitArray shape is inconsistent")
    data = packed["data"]
    if not isinstance(data, str):
        raise SamplingEvidenceError("packed BitArray data must be base64 text")
    try:
        raw = b64decode(data.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError) as exc:
        raise SamplingEvidenceError("packed BitArray data is not valid base64") from exc
    if len(raw) != observed_shots * bytes_per_shot:
        raise SamplingEvidenceError("packed BitArray byte length is inconsistent")

    mask = (1 << num_bits) - 1
    decoded: list[str] = []
    for offset in range(0, len(raw), bytes_per_shot):
        value = int.from_bytes(raw[offset : offset + bytes_per_shot], "big")
        if value & ~mask:
            raise SamplingEvidenceError("packed BitArray has nonzero unused high bits")
        decoded.append(format(value, f"0{num_bits}b"))
    return tuple(decoded)


def raw_evidence_sha256(record: Mapping[str, Any]) -> str:
    """Hash a canonical JSON record, excluding its own digest field."""

    if not isinstance(record, Mapping):
        raise SamplingEvidenceError("raw evidence record must be an object")
    payload = dict(record)
    payload.pop("raw_evidence_sha256", None)
    try:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SamplingEvidenceError("raw evidence is not canonical JSON data") from exc
    return hashlib.sha256(encoded).hexdigest()


def evidence_from_bit_array(
    bit_array: Any,
    *,
    term_id: str,
    pauli: str,
    requested_shots: int,
) -> dict[str, Any]:
    """Create a self-checking JSON-compatible record from one scalar BitArray."""

    if not isinstance(term_id, str) or not term_id:
        raise SamplingEvidenceError("term_id must be a non-empty string")
    requested = _positive_integer(requested_shots, "requested_shots")
    try:
        num_bits = _positive_integer(bit_array.num_bits, "BitArray.num_bits")
        observed = _positive_integer(bit_array.num_shots, "BitArray.num_shots")
    except AttributeError as exc:
        raise SamplingEvidenceError("sampled data is not a BitArray") from exc
    label = validate_pauli_label(pauli, num_qubits=num_bits)
    if observed != requested:
        raise SamplingEvidenceError(
            f"BitArray contains {observed} shots; exactly {requested} were requested"
        )
    try:
        bitstrings = _normalise_bitstrings(bit_array.get_bitstrings(), num_bits)
        counts = _normalise_counts(bit_array.get_counts(), num_bits)
    except AttributeError as exc:
        raise SamplingEvidenceError("sampled data is not a BitArray") from exc
    if len(bitstrings) != observed:
        raise SamplingEvidenceError(
            f"BitArray returned {len(bitstrings)} ordered shots; expected {observed}"
        )
    derived_counts = dict(sorted(Counter(bitstrings).items()))
    if counts != derived_counts:
        raise SamplingEvidenceError(
            "BitArray counts disagree with its ordered bitstrings"
        )
    if sum(counts.values()) != observed:
        raise SamplingEvidenceError("BitArray counts do not sum to observed shots")

    negative = negative_eigenvalue_count(counts, label)
    record: dict[str, Any] = {
        "schema_version": RAW_EVIDENCE_SCHEMA_VERSION,
        "raw_evidence_format": RAW_EVIDENCE_FORMAT,
        "term_id": term_id,
        "pauli": label,
        "requested_shots": requested,
        "observed_shots": observed,
        "num_bits": num_bits,
        "bit_order": QISKIT_BIT_ORDER,
        "ordered_bitstrings": list(bitstrings),
        "counts": counts,
        "packed_bitarray": _packed_array_record(
            bit_array,
            bitstrings,
            num_bits=num_bits,
            observed_shots=observed,
        ),
        "negative_eigenvalue_count": negative,
        "expectation": expectation_from_negative_count(negative, observed),
    }
    record["raw_evidence_sha256"] = raw_evidence_sha256(record)
    validate_evidence_record(
        record,
        expected_term_id=term_id,
        expected_pauli=label,
        expected_shots=requested,
    )
    return record


def evidence_from_pub_result(
    pub_result: Any,
    *,
    term_id: str,
    pauli: str,
    requested_shots: int,
    register_name: str = "meas",
) -> dict[str, Any]:
    """Extract and validate one PUB's named BitArray as raw evidence."""

    return evidence_from_bit_array(
        extract_bit_array(pub_result, register_name=register_name),
        term_id=term_id,
        pauli=pauli,
        requested_shots=requested_shots,
    )


def validate_evidence_record(
    record: Mapping[str, Any],
    *,
    expected_term_id: str | None = None,
    expected_pauli: str | None = None,
    expected_shots: int | None = None,
) -> dict[str, Any]:
    """Fully replay a raw evidence record and return a plain dictionary.

    Validation recomputes the digest, decodes the packed shots, rebuilds the
    complete count dictionary, re-counts negative parity, and reconstructs the
    expectation.  Optional expected values bind a PUB position to its declared
    Hamiltonian term and shot policy.
    """

    if not isinstance(record, Mapping):
        raise SamplingEvidenceError("raw evidence record must be an object")
    required = {
        "schema_version",
        "raw_evidence_format",
        "term_id",
        "pauli",
        "requested_shots",
        "observed_shots",
        "num_bits",
        "bit_order",
        "ordered_bitstrings",
        "counts",
        "packed_bitarray",
        "negative_eigenvalue_count",
        "expectation",
        "raw_evidence_sha256",
    }
    missing = required - set(record)
    if missing:
        raise SamplingEvidenceError(f"raw evidence is missing {sorted(missing)}")
    schema_version = record["schema_version"]
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != RAW_EVIDENCE_SCHEMA_VERSION
    ):
        raise SamplingEvidenceError("unsupported raw-evidence schema version")
    if record["raw_evidence_format"] != RAW_EVIDENCE_FORMAT:
        raise SamplingEvidenceError("unsupported raw-evidence format")

    term_id = record["term_id"]
    if not isinstance(term_id, str) or not term_id:
        raise SamplingEvidenceError("term_id must be a non-empty string")
    if expected_term_id is not None and term_id != expected_term_id:
        raise SamplingEvidenceError(
            f"raw evidence belongs to term {term_id!r}, not {expected_term_id!r}"
        )

    requested = _positive_integer(record["requested_shots"], "requested_shots")
    observed = _positive_integer(record["observed_shots"], "observed_shots")
    if requested != observed:
        raise SamplingEvidenceError(
            f"observed shots {observed} do not equal requested shots {requested}"
        )
    if expected_shots is not None:
        expected = _positive_integer(expected_shots, "expected_shots")
        if requested != expected:
            raise SamplingEvidenceError(
                f"raw evidence declares {requested} shots; expected {expected}"
            )

    num_bits = _positive_integer(record["num_bits"], "num_bits")
    label = validate_pauli_label(record["pauli"], num_qubits=num_bits)
    if expected_pauli is not None:
        expected_label = validate_pauli_label(expected_pauli, num_qubits=num_bits)
        if label != expected_label:
            raise SamplingEvidenceError(
                f"raw evidence measures {label!r}, not {expected_label!r}"
            )
    if record["bit_order"] != QISKIT_BIT_ORDER:
        raise SamplingEvidenceError("raw evidence has an unsupported bit order")

    bitstrings = _normalise_bitstrings(record["ordered_bitstrings"], num_bits)
    if len(bitstrings) != observed:
        raise SamplingEvidenceError("ordered bitstrings do not match observed shots")
    packed_bitstrings = decode_packed_bitarray(
        record["packed_bitarray"],
        num_bits=num_bits,
        observed_shots=observed,
    )
    if packed_bitstrings != bitstrings:
        raise SamplingEvidenceError(
            "packed BitArray data disagrees with ordered bitstrings"
        )

    counts = _normalise_counts(record["counts"], num_bits)
    if sum(counts.values()) != observed:
        raise SamplingEvidenceError("count dictionary does not sum to observed shots")
    if counts != dict(sorted(Counter(bitstrings).items())):
        raise SamplingEvidenceError("count dictionary disagrees with ordered shots")

    negative = negative_eigenvalue_count(counts, label)
    declared_negative = record["negative_eigenvalue_count"]
    if (
        isinstance(declared_negative, bool)
        or not isinstance(declared_negative, int)
        or declared_negative != negative
    ):
        raise SamplingEvidenceError("negative-eigenvalue count is inconsistent")
    reconstructed = expectation_from_negative_count(negative, observed)
    declared_expectation = record["expectation"]
    if (
        isinstance(declared_expectation, bool)
        or not isinstance(declared_expectation, (int, float))
        or not math.isfinite(float(declared_expectation))
        or not math.isclose(
            float(declared_expectation), reconstructed, rel_tol=0.0, abs_tol=1e-15
        )
    ):
        raise SamplingEvidenceError("expectation is not reconstructed from parity")

    declared_digest = record["raw_evidence_sha256"]
    if (
        not isinstance(declared_digest, str)
        or len(declared_digest) != 64
        or any(character not in "0123456789abcdef" for character in declared_digest)
        or not hmac.compare_digest(declared_digest, raw_evidence_sha256(record))
    ):
        raise SamplingEvidenceError("raw-evidence SHA-256 mismatch")
    return dict(record)


__all__ = [
    "BasisMeasurement",
    "QISKIT_BIT_ORDER",
    "RAW_EVIDENCE_FORMAT",
    "RAW_EVIDENCE_SCHEMA_VERSION",
    "SamplingEvidenceError",
    "build_measurement_circuit",
    "classical_distribution_fidelity",
    "decode_packed_bitarray",
    "evidence_from_bit_array",
    "evidence_from_pub_result",
    "expectation_from_counts",
    "expectation_from_negative_count",
    "extract_bit_array",
    "measurement_basis_plan",
    "negative_eigenvalue_count",
    "raw_evidence_sha256",
    "validate_evidence_record",
    "validate_pauli_label",
]
