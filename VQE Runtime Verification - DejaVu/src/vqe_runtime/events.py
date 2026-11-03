from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import threading
import time
from typing import Any, Iterable, Mapping


TRACE_SCHEMA_VERSION = 1
_SAFE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")
_SAFE_ATOM = re.compile(r"^[A-Za-z0-9._:-]+$")


def safe_atom(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("monitor atoms must be strings")
    if not value or not _SAFE_ATOM.fullmatch(value):
        raise ValueError(f"unsafe monitor atom: {value!r}")
    return value


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    seq: int
    monotonic_ns: int
    name: str
    args: tuple[str, ...]
    payload: Mapping[str, Any] = field(default_factory=dict)
    schema_version: int = TRACE_SCHEMA_VERSION

    def bridge_line(self) -> str:
        return "\t".join(("RV1", str(self.seq), self.name, *self.args)) + "\n"

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "seq": self.seq,
            "monotonic_ns": self.monotonic_ns,
            "event": self.name,
            "args": list(self.args),
            "payload": dict(self.payload),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "RuntimeEvent":
        if not isinstance(value, dict):
            raise ValueError("event record must be a JSON object")
        required = {"schema_version", "seq", "monotonic_ns", "event", "args", "payload"}
        missing = required - set(value)
        if missing:
            raise ValueError(f"event record is missing {sorted(missing)}")
        unknown = set(value) - required
        if unknown:
            raise ValueError(f"event record has unknown fields {sorted(unknown)}")
        schema_version = value["schema_version"]
        if (
            isinstance(schema_version, bool)
            or not isinstance(schema_version, int)
            or schema_version != TRACE_SCHEMA_VERSION
        ):
            raise ValueError("unsupported trace schema version")
        seq = value["seq"]
        monotonic_ns = value["monotonic_ns"]
        if isinstance(seq, bool) or not isinstance(seq, int) or seq <= 0:
            raise ValueError("event seq must be a positive integer")
        if (
            isinstance(monotonic_ns, bool)
            or not isinstance(monotonic_ns, int)
            or monotonic_ns < 0
        ):
            raise ValueError("monotonic_ns must be a nonnegative integer")
        name = value["event"]
        if not isinstance(name, str) or not _SAFE_NAME.fullmatch(name):
            raise ValueError("invalid event name")
        raw_args = value["args"]
        if not isinstance(raw_args, list):
            raise ValueError("event args must be an array")
        args = tuple(safe_atom(item) for item in raw_args)
        payload = value["payload"]
        if not isinstance(payload, dict):
            raise ValueError("event payload must be an object")
        return cls(seq, monotonic_ns, name, args, payload)


class EventJournal:
    """Ordered JSONL journal whose sequence numbers are DejaVu watermarks."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        durable: bool = False,
        overwrite: bool = False,
    ) -> None:
        self.path = None if path is None else Path(path)
        self.durable = durable
        self._lock = threading.RLock()
        self._seq = 0
        self._stream = None
        self.events: list[RuntimeEvent] = []
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._stream = self.path.open(
                "w" if overwrite else "x", encoding="utf-8", buffering=1
            )

    def append(
        self,
        name: str,
        *args: Any,
        payload: Mapping[str, Any] | None = None,
    ) -> RuntimeEvent:
        if not _SAFE_NAME.fullmatch(name):
            raise ValueError(f"invalid event name: {name!r}")
        safe_args = tuple(safe_atom(arg) for arg in args)
        with self._lock:
            self._seq += 1
            event = RuntimeEvent(
                self._seq,
                time.monotonic_ns(),
                name,
                safe_args,
                dict(payload or {}),
            )
            self.events.append(event)
            if self._stream is not None:
                self._stream.write(json.dumps(event.as_dict(), sort_keys=True) + "\n")
                self._stream.flush()
                if self.durable:
                    os.fsync(self._stream.fileno())
            return event

    @property
    def last_sequence(self) -> int:
        return self._seq

    def close(self) -> None:
        with self._lock:
            if self._stream is not None:
                self._stream.close()
                self._stream = None

    def __enter__(self) -> "EventJournal":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def load_events(path: str | Path) -> tuple[list[RuntimeEvent], list[str]]:
    events: list[RuntimeEvent] = []
    errors: list[str] = []
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            for line_number, raw in enumerate(stream, 1):
                if not raw.strip():
                    continue
                try:
                    events.append(RuntimeEvent.from_dict(json.loads(raw)))
                except (json.JSONDecodeError, ValueError) as exc:
                    errors.append(f"line {line_number}: {exc}")
    except OSError as exc:
        errors.append(f"cannot read trace: {exc}")
    return events, errors


def write_events(path: str | Path, events: Iterable[RuntimeEvent]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as stream:
        for event in events:
            stream.write(json.dumps(event.as_dict(), sort_keys=True) + "\n")
