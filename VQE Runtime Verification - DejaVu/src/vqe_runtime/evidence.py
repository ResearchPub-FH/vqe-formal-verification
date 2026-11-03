"""Durable, replayable JSONL journals for raw Sampler evidence.

The trace links to a PUB record only by ``raw_evidence_sha256``.  The sidecar
path is supplied independently by the verifier; this module deliberately does
not resolve or trust a path found in a trace event.

``EvidenceJournal.append_pub`` flushes (and, by default, ``fsync``s) a PUB
record before returning.  A caller can therefore append the PUB here and only
then emit the corresponding compact trace event.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import threading
from typing import Any

from .sampling import (
    SamplingEvidenceError,
    raw_evidence_sha256,
    validate_evidence_record,
)


EVIDENCE_JOURNAL_SCHEMA_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_WRAPPER_FIELDS = frozenset(
    {
        "journal_schema_version",
        "record_type",
        "record_index",
        "run_id",
        "config_hash",
    }
)
_MANIFEST_FIELDS = frozenset(
    {
        "journal_schema_version",
        "record_type",
        "run_id",
        "config_hash",
        "record_count",
        "total_observed_shots",
        "ordered_record_hashes",
        "record_hashes_sha256",
        "manifest_sha256",
    }
)
_MANIFEST_ONLY_FIELDS = _MANIFEST_FIELDS - _WRAPPER_FIELDS


class EvidenceJournalError(ValueError):
    """Raised when a sidecar record or journal operation is invalid."""


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise EvidenceJournalError(f"{name} must be a non-empty string")
    return value


def _require_sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise EvidenceJournalError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _require_nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EvidenceJournalError(f"{name} must be a nonnegative integer")
    return value


def _json_clone(value: Any, *, location: str = "value") -> Any:
    """Return detached JSON data while rejecting lossy/non-finite values."""

    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise EvidenceJournalError(f"{location} contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise EvidenceJournalError(f"{location} contains a non-string key")
            result[key] = _json_clone(item, location=f"{location}.{key}")
        return result
    if isinstance(value, (list, tuple)):
        return [
            _json_clone(item, location=f"{location}[{index}]")
            for index, item in enumerate(value)
        ]
    raise EvidenceJournalError(
        f"{location} contains a non-JSON value of type {type(value).__name__}"
    )


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise EvidenceJournalError("evidence journal data is not canonical JSON") from exc


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def record_hashes_sha256(record_hashes: Sequence[str]) -> str:
    """Digest an ordered record-hash list using canonical JSON framing."""

    if isinstance(record_hashes, (str, bytes)) or not isinstance(
        record_hashes, Sequence
    ):
        raise EvidenceJournalError("ordered record hashes must be a sequence")
    hashes = [
        _require_sha256(value, f"ordered_record_hashes[{index}]")
        for index, value in enumerate(record_hashes)
    ]
    return _canonical_sha256(hashes)


def manifest_sha256(record: Mapping[str, Any]) -> str:
    """Hash a canonical manifest while excluding its own digest field."""

    if not isinstance(record, Mapping):
        raise EvidenceJournalError("manifest must be an object")
    payload = _json_clone(record, location="manifest")
    payload.pop("manifest_sha256", None)
    return _canonical_sha256(payload)


def validate_pub_record(
    record: Mapping[str, Any],
    *,
    expected_run_id: str | None = None,
    expected_config_hash: str | None = None,
    expected_record_index: int | None = None,
) -> dict[str, Any]:
    """Validate both the journal wrapper and the complete raw-shot record."""

    if not isinstance(record, Mapping):
        raise EvidenceJournalError("PUB record must be an object")
    candidate = _json_clone(record, location="PUB record")
    missing = _WRAPPER_FIELDS - set(candidate)
    if missing:
        raise EvidenceJournalError(f"PUB record is missing {sorted(missing)}")
    forbidden = _MANIFEST_ONLY_FIELDS & set(candidate)
    if forbidden:
        raise EvidenceJournalError(
            f"PUB record contains manifest-only fields {sorted(forbidden)}"
        )
    if candidate["journal_schema_version"] != EVIDENCE_JOURNAL_SCHEMA_VERSION:
        raise EvidenceJournalError("unsupported evidence-journal schema version")
    if candidate["record_type"] != "pub":
        raise EvidenceJournalError("PUB record_type must be 'pub'")
    run_id = _require_text(candidate["run_id"], "run_id")
    config_hash = _require_sha256(candidate["config_hash"], "config_hash")
    record_index = _require_nonnegative_int(candidate["record_index"], "record_index")
    if expected_run_id is not None and run_id != _require_text(
        expected_run_id, "expected_run_id"
    ):
        raise EvidenceJournalError(
            f"PUB run_id {run_id!r} does not match expected run_id"
        )
    if expected_config_hash is not None and config_hash != _require_sha256(
        expected_config_hash, "expected_config_hash"
    ):
        raise EvidenceJournalError("PUB config_hash does not match expected config_hash")
    if expected_record_index is not None and record_index != _require_nonnegative_int(
        expected_record_index, "expected_record_index"
    ):
        raise EvidenceJournalError(
            f"PUB record_index {record_index} is out of sequence; "
            f"expected {expected_record_index}"
        )

    try:
        return validate_evidence_record(candidate)
    except SamplingEvidenceError as exc:
        raise EvidenceJournalError(str(exc)) from exc


def validate_manifest_record(
    manifest: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    *,
    expected_run_id: str | None = None,
    expected_config_hash: str | None = None,
) -> dict[str, Any]:
    """Validate a seal against the PUB records that precede it."""

    if not isinstance(manifest, Mapping):
        raise EvidenceJournalError("manifest must be an object")
    candidate = _json_clone(manifest, location="manifest")
    missing = _MANIFEST_FIELDS - set(candidate)
    unknown = set(candidate) - _MANIFEST_FIELDS
    if missing:
        raise EvidenceJournalError(f"manifest is missing {sorted(missing)}")
    if unknown:
        raise EvidenceJournalError(f"manifest has unknown fields {sorted(unknown)}")
    if candidate["journal_schema_version"] != EVIDENCE_JOURNAL_SCHEMA_VERSION:
        raise EvidenceJournalError("unsupported evidence-journal schema version")
    if candidate["record_type"] != "manifest":
        raise EvidenceJournalError("manifest record_type must be 'manifest'")

    run_id = _require_text(candidate["run_id"], "manifest run_id")
    config_hash = _require_sha256(candidate["config_hash"], "manifest config_hash")
    if expected_run_id is not None and run_id != _require_text(
        expected_run_id, "expected_run_id"
    ):
        raise EvidenceJournalError("manifest run_id does not match expected run_id")
    if expected_config_hash is not None and config_hash != _require_sha256(
        expected_config_hash, "expected_config_hash"
    ):
        raise EvidenceJournalError(
            "manifest config_hash does not match expected config_hash"
        )

    record_count = _require_nonnegative_int(candidate["record_count"], "record_count")
    total_shots = _require_nonnegative_int(
        candidate["total_observed_shots"], "total_observed_shots"
    )
    ordered = candidate["ordered_record_hashes"]
    if not isinstance(ordered, list):
        raise EvidenceJournalError("ordered_record_hashes must be an array")
    ordered_hashes = [
        _require_sha256(value, f"ordered_record_hashes[{index}]")
        for index, value in enumerate(ordered)
    ]
    if len(set(ordered_hashes)) != len(ordered_hashes):
        raise EvidenceJournalError("manifest contains duplicate record hashes")
    aggregate = _require_sha256(
        candidate["record_hashes_sha256"], "record_hashes_sha256"
    )
    declared_manifest_hash = _require_sha256(
        candidate["manifest_sha256"], "manifest_sha256"
    )
    if not hmac.compare_digest(aggregate, record_hashes_sha256(ordered_hashes)):
        raise EvidenceJournalError("manifest aggregate record-hash digest mismatch")
    if not hmac.compare_digest(declared_manifest_hash, manifest_sha256(candidate)):
        raise EvidenceJournalError("manifest SHA-256 mismatch")

    actual_records = [_json_clone(record, location="PUB record") for record in records]
    actual_hashes = [record["raw_evidence_sha256"] for record in actual_records]
    actual_total = sum(record["observed_shots"] for record in actual_records)
    if record_count != len(actual_records):
        raise EvidenceJournalError(
            f"manifest record_count is {record_count}; observed {len(actual_records)}"
        )
    if total_shots != actual_total:
        raise EvidenceJournalError(
            f"manifest total_observed_shots is {total_shots}; observed {actual_total}"
        )
    if ordered_hashes != actual_hashes:
        raise EvidenceJournalError(
            "manifest ordered record hashes do not match the PUB record order"
        )
    for index, record in enumerate(actual_records):
        if record.get("run_id") != run_id:
            raise EvidenceJournalError(f"PUB record {index} has an orphan run_id")
        if record.get("config_hash") != config_hash:
            raise EvidenceJournalError(f"PUB record {index} has an orphan config_hash")
    return candidate


@dataclass(slots=True)
class EvidenceLoadResult:
    """The validated view of one explicitly selected evidence sidecar."""

    records: tuple[dict[str, Any], ...]
    records_by_hash: dict[str, dict[str, Any]]
    manifest: dict[str, Any] | None
    errors: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


class EvidenceJournal:
    """Append-only, durably flushed PUB evidence followed by one manifest."""

    def __init__(
        self,
        path: str | Path,
        *,
        run_id: str,
        config_hash: str,
        durable: bool = True,
        overwrite: bool = False,
    ) -> None:
        self.path = Path(path)
        self.run_id = _require_text(run_id, "run_id")
        self.config_hash = _require_sha256(config_hash, "config_hash")
        if not isinstance(durable, bool):
            raise EvidenceJournalError("durable must be Boolean")
        if not isinstance(overwrite, bool):
            raise EvidenceJournalError("overwrite must be Boolean")
        self.durable = durable
        self._lock = threading.RLock()
        self._records: list[dict[str, Any]] = []
        self._manifest: dict[str, Any] | None = None
        self._closed = False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = self.path.open(
            "w" if overwrite else "x", encoding="utf-8", buffering=1, newline="\n"
        )

    @property
    def record_count(self) -> int:
        return len(self._records)

    @property
    def sealed(self) -> bool:
        return self._manifest is not None

    @property
    def records(self) -> tuple[dict[str, Any], ...]:
        return tuple(deepcopy(record) for record in self._records)

    @property
    def manifest(self) -> dict[str, Any] | None:
        return None if self._manifest is None else deepcopy(self._manifest)

    def _ensure_writable(self) -> None:
        if self._closed:
            raise EvidenceJournalError("evidence journal is closed")
        if self._manifest is not None:
            raise EvidenceJournalError("evidence journal is already sealed")

    def _persist(self, record: Mapping[str, Any]) -> None:
        self._stream.write(_canonical_json(record) + "\n")
        self._stream.flush()
        if self.durable:
            os.fsync(self._stream.fileno())

    def append_pub(
        self,
        raw_evidence: Mapping[str, Any],
        *,
        identity: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Durably append one PUB, returning only after it is trace-linkable.

        ``identity`` is flattened into the PUB record so every supplied field
        participates in ``raw_evidence_sha256``.  Identity fields may not
        replace raw-shot fields or journal-reserved fields.
        """

        with self._lock:
            self._ensure_writable()
            if not isinstance(raw_evidence, Mapping):
                raise EvidenceJournalError("raw_evidence must be an object")
            core = _json_clone(raw_evidence, location="raw_evidence")
            forbidden_core = (_WRAPPER_FIELDS | _MANIFEST_ONLY_FIELDS) & set(core)
            if forbidden_core:
                raise EvidenceJournalError(
                    "raw evidence already contains journal-reserved fields "
                    f"{sorted(forbidden_core)}"
                )
            try:
                validate_evidence_record(core)
            except SamplingEvidenceError as exc:
                raise EvidenceJournalError(str(exc)) from exc

            metadata = {} if identity is None else _json_clone(identity, location="identity")
            if not isinstance(metadata, dict):
                raise EvidenceJournalError("identity must be an object")
            invalid_keys = [key for key in metadata if not key]
            if invalid_keys:
                raise EvidenceJournalError("identity field names must be non-empty")
            collisions = set(metadata) & (set(core) | _WRAPPER_FIELDS | _MANIFEST_ONLY_FIELDS)
            if collisions:
                raise EvidenceJournalError(
                    f"identity fields collide with reserved fields {sorted(collisions)}"
                )

            record = core
            record.pop("raw_evidence_sha256", None)
            record.update(metadata)
            record.update(
                {
                    "journal_schema_version": EVIDENCE_JOURNAL_SCHEMA_VERSION,
                    "record_type": "pub",
                    "record_index": len(self._records),
                    "run_id": self.run_id,
                    "config_hash": self.config_hash,
                }
            )
            record["raw_evidence_sha256"] = raw_evidence_sha256(record)
            validated = validate_pub_record(
                record,
                expected_run_id=self.run_id,
                expected_config_hash=self.config_hash,
                expected_record_index=len(self._records),
            )
            self._persist(validated)
            stored = _json_clone(validated, location="PUB record")
            self._records.append(stored)
            return deepcopy(stored)

    def seal(self) -> dict[str, Any]:
        """Durably append the sole final manifest and prevent further PUBs."""

        with self._lock:
            self._ensure_writable()
            hashes = [record["raw_evidence_sha256"] for record in self._records]
            manifest: dict[str, Any] = {
                "journal_schema_version": EVIDENCE_JOURNAL_SCHEMA_VERSION,
                "record_type": "manifest",
                "run_id": self.run_id,
                "config_hash": self.config_hash,
                "record_count": len(self._records),
                "total_observed_shots": sum(
                    record["observed_shots"] for record in self._records
                ),
                "ordered_record_hashes": hashes,
                "record_hashes_sha256": record_hashes_sha256(hashes),
            }
            manifest["manifest_sha256"] = manifest_sha256(manifest)
            validated = validate_manifest_record(
                manifest,
                self._records,
                expected_run_id=self.run_id,
                expected_config_hash=self.config_hash,
            )
            self._persist(validated)
            self._manifest = _json_clone(validated, location="manifest")
            return deepcopy(self._manifest)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._stream.flush()
            if self.durable:
                os.fsync(self._stream.fileno())
            self._stream.close()
            self._closed = True

    def __enter__(self) -> "EvidenceJournal":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


# Both names are intentionally supported: "journal" emphasizes replay while
# "writer" is often clearer at the call site in a live runner.
EvidenceWriter = EvidenceJournal


class _DuplicateJSONKey(ValueError):
    pass


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJSONKey(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f"non-standard JSON constant {value}")


def _strict_json_loads(raw: str) -> Any:
    return json.loads(
        raw,
        object_pairs_hook=_object_without_duplicate_keys,
        parse_constant=_reject_json_constant,
    )


def load_evidence(
    path: str | Path,
    *,
    expected_run_id: str | None = None,
    expected_config_hash: str | None = None,
) -> EvidenceLoadResult:
    """Strictly load an explicitly chosen sidecar without consulting a trace.

    All errors are accumulated into the result.  Consumers must require
    ``result.ok`` before using ``records_by_hash`` for a verification verdict.
    """

    records: list[dict[str, Any]] = []
    records_by_hash: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    manifest: dict[str, Any] | None = None
    manifest_line: int | None = None
    seen_record_indexes: set[int] = set()
    seen_logical_identities: set[tuple[str, str, int]] = set()
    pub_ordinal = 0

    if expected_run_id is not None:
        try:
            _require_text(expected_run_id, "expected_run_id")
        except EvidenceJournalError as exc:
            errors.append(str(exc))
    if expected_config_hash is not None:
        try:
            _require_sha256(expected_config_hash, "expected_config_hash")
        except EvidenceJournalError as exc:
            errors.append(str(exc))

    try:
        with Path(path).open("r", encoding="utf-8", newline="") as stream:
            for line_number, raw in enumerate(stream, 1):
                if not raw.endswith("\n"):
                    errors.append(f"line {line_number}: unterminated JSONL record")
                if not raw.strip():
                    errors.append(f"line {line_number}: blank lines are not permitted")
                    continue
                try:
                    value = _strict_json_loads(raw)
                except (json.JSONDecodeError, ValueError) as exc:
                    errors.append(f"line {line_number}: {exc}")
                    continue
                if not isinstance(value, dict):
                    errors.append(f"line {line_number}: journal record must be an object")
                    continue
                if manifest_line is not None:
                    errors.append(
                        f"line {line_number}: record appears after manifest on line "
                        f"{manifest_line}"
                    )
                record_type = value.get("record_type")
                if record_type == "pub":
                    expected_index = pub_ordinal
                    pub_ordinal += 1
                    try:
                        record = validate_pub_record(value)
                    except EvidenceJournalError as exc:
                        errors.append(f"line {line_number}: invalid PUB record: {exc}")
                        continue
                    digest = record["raw_evidence_sha256"]
                    record_index = record["record_index"]
                    if expected_run_id is not None and record["run_id"] != expected_run_id:
                        errors.append(
                            f"line {line_number}: PUB run_id {record['run_id']!r} "
                            "does not match expected run_id"
                        )
                    if (
                        expected_config_hash is not None
                        and record["config_hash"] != expected_config_hash
                    ):
                        errors.append(
                            f"line {line_number}: PUB config_hash does not match "
                            "expected config_hash"
                        )
                    if record_index != expected_index:
                        errors.append(
                            f"line {line_number}: PUB record_index {record_index} is "
                            f"out of sequence; expected {expected_index}"
                        )
                    if digest in records_by_hash:
                        errors.append(
                            f"line {line_number}: duplicate raw evidence hash {digest}"
                        )
                    else:
                        records_by_hash[digest] = record
                    if record_index in seen_record_indexes:
                        errors.append(
                            f"line {line_number}: duplicate record_index {record_index}"
                        )
                    seen_record_indexes.add(record_index)

                    evaluation_id = record.get("evaluation_id")
                    pub_index = record.get("pub_index")
                    if evaluation_id is not None:
                        if not isinstance(evaluation_id, str) or not evaluation_id:
                            errors.append(
                                f"line {line_number}: evaluation_id must be a "
                                "non-empty string"
                            )
                        elif (
                            isinstance(pub_index, bool)
                            or not isinstance(pub_index, int)
                            or pub_index < 0
                        ):
                            errors.append(
                                f"line {line_number}: pub_index must be a nonnegative "
                                "integer when evaluation_id is supplied"
                            )
                        else:
                            logical_identity = (
                                record["run_id"],
                                evaluation_id,
                                pub_index,
                            )
                            if logical_identity in seen_logical_identities:
                                errors.append(
                                    f"line {line_number}: duplicate PUB identity "
                                    f"{logical_identity!r}"
                                )
                            seen_logical_identities.add(logical_identity)
                    elif pub_index is not None:
                        errors.append(
                            f"line {line_number}: pub_index is orphaned without "
                            "evaluation_id"
                        )
                    records.append(record)
                elif record_type == "manifest":
                    if manifest is not None:
                        errors.append(f"line {line_number}: duplicate manifest")
                    else:
                        manifest = value
                        manifest_line = line_number
                else:
                    errors.append(
                        f"line {line_number}: unknown record_type {record_type!r}"
                    )
    except (OSError, UnicodeError) as exc:
        errors.append(f"cannot read evidence sidecar: {exc}")
        return EvidenceLoadResult((), {}, None, tuple(errors))

    if manifest is None:
        if records:
            errors.append(
                f"missing manifest; {len(records)} PUB record(s) are orphaned"
            )
        else:
            errors.append("missing manifest")
    else:
        try:
            manifest = validate_manifest_record(
                manifest,
                records,
                expected_run_id=expected_run_id,
                expected_config_hash=expected_config_hash,
            )
        except EvidenceJournalError as exc:
            errors.append(f"invalid manifest: {exc}")

    return EvidenceLoadResult(
        tuple(records), records_by_hash, manifest, tuple(errors)
    )


__all__ = [
    "EVIDENCE_JOURNAL_SCHEMA_VERSION",
    "EvidenceJournal",
    "EvidenceJournalError",
    "EvidenceLoadResult",
    "EvidenceWriter",
    "load_evidence",
    "manifest_sha256",
    "record_hashes_sha256",
    "validate_manifest_record",
    "validate_pub_record",
]
