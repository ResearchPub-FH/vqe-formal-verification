from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import queue
import subprocess
import threading
import time
from typing import Any, Protocol
import zipfile

from .events import RuntimeEvent


class DejaVuError(RuntimeError):
    pass


class DejaVuUnavailable(DejaVuError):
    pass


class DejaVuProtocolError(DejaVuError):
    pass


@dataclass(frozen=True, slots=True)
class MonitorAck:
    seq: int
    passed: bool
    violations: tuple[str, ...] = ()


class EventMonitor(Protocol):
    def submit(self, event: RuntimeEvent) -> MonitorAck: ...

    def close(self) -> None: ...


class AlwaysPassMonitor:
    """Python-test/shadow monitor. It is not an assurance boundary."""

    def submit(self, event: RuntimeEvent) -> MonitorAck:
        return MonitorAck(event.seq, True)

    def close(self) -> None:
        return None


class SynchronousDejaVu:
    """Acknowledged, fail-closed bridge to the generated DejaVu monitor."""

    def __init__(
        self,
        *,
        dejavu_jar: str | Path | None = None,
        monitor_jar: str | Path | None = None,
        java: str = "java",
        bits_per_variable: int = 24,
        timeout_seconds: float = 10.0,
    ) -> None:
        package_root = Path(__file__).resolve().parent
        vendor_root = package_root / "vendor/dejavu"
        self.dejavu_jar = Path(dejavu_jar or vendor_root / "dejavu.jar")
        self.monitor_jar = Path(
            monitor_jar or vendor_root / "vqe-three-level-monitor.jar"
        )
        if not self.dejavu_jar.is_file():
            raise DejaVuUnavailable(f"DejaVu JAR not found: {self.dejavu_jar}")
        if not self.monitor_jar.is_file():
            raise DejaVuUnavailable(f"generated monitor JAR not found: {self.monitor_jar}")
        self.provenance = self._validate_build(
            vendor_root / "monitor-manifest.json", package_root
        )
        if (
            isinstance(bits_per_variable, bool)
            or not isinstance(bits_per_variable, int)
            or bits_per_variable <= 0
        ):
            raise ValueError("bits_per_variable must be a positive integer")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be positive")

        classpath = f"{self.monitor_jar}:{self.dejavu_jar}"
        try:
            self._process = subprocess.Popen(
                [java, "-cp", classpath, "SynchronousBridge", str(bits_per_variable)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            raise DejaVuUnavailable(f"cannot start DejaVu JVM: {exc}") from exc
        if self._process.stdin is None or self._process.stdout is None:
            raise DejaVuUnavailable("DejaVu subprocess pipes were not created")

        self.timeout_seconds = float(timeout_seconds)
        self._stdout: queue.Queue[str] = queue.Queue(maxsize=64)
        self._stdout_tail: deque[str] = deque(maxlen=20)
        self._stderr_tail: deque[str] = deque(maxlen=40)
        self._lock = threading.RLock()
        self._closed = False
        self._stdout_thread = threading.Thread(
            target=self._read_stdout, name="dejavu-stdout", daemon=True
        )
        self._stderr_thread = threading.Thread(
            target=self._read_stderr, name="dejavu-stderr", daemon=True
        )
        self._stdout_thread.start()
        self._stderr_thread.start()
        try:
            ready = self._next_protocol_line()
        except BaseException:
            self.close()
            raise
        if ready != ["RV1", "READY"]:
            self.close()
            raise DejaVuProtocolError(f"unexpected DejaVu startup reply: {ready}")

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _validate_build(
        self, manifest_path: Path, package_root: Path
    ) -> dict[str, Any]:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(manifest, dict):
                raise ValueError("manifest is not an object")
            required = {
                "schema",
                "property_levels",
                "spec_sha256",
                "bridge_sha256",
                "dejavu_sha256",
                "monitor_sha256",
            }
            if set(manifest) != required:
                raise ValueError("manifest field set is invalid")
            if manifest["schema"] != 1 or manifest["property_levels"] != [
                "intra_iteration",
                "inter_iteration",
                "run_level",
            ]:
                raise ValueError("manifest schema/property levels are invalid")
            if self._sha256(self.dejavu_jar) != manifest["dejavu_sha256"]:
                raise ValueError("DejaVu runtime hash mismatch")
            if self._sha256(self.monitor_jar) != manifest["monitor_sha256"]:
                raise ValueError("generated monitor hash mismatch")
            with zipfile.ZipFile(self.monitor_jar) as archive:
                embedded = json.loads(
                    archive.read("VQE_MONITOR_BUILD.json").decode("utf-8")
                )
            for key in required - {"monitor_sha256"}:
                if embedded.get(key) != manifest[key]:
                    raise ValueError(f"embedded monitor {key} mismatch")
            repository_root = package_root.parents[1]
            source_checks = {
                "spec_sha256": repository_root / "specs/vqe_runtime.qtl",
                "bridge_sha256": repository_root / "tools/SynchronousBridge.scala",
            }
            for key, source in source_checks.items():
                if source.is_file() and self._sha256(source) != manifest[key]:
                    raise ValueError(f"runtime monitor is stale relative to {source.name}")
        except (OSError, ValueError, KeyError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
            raise DejaVuUnavailable(
                f"cannot establish generated-monitor provenance: {exc}"
            ) from exc
        return {
            "adapter": "synchronous-dejavu-generated-monitor",
            **manifest,
        }

    def _read_stdout(self) -> None:
        assert self._process.stdout is not None
        for line in self._process.stdout:
            cleaned = line.rstrip("\r\n")
            if cleaned.startswith("RV1\t") or cleaned == "RV1":
                try:
                    self._stdout.put_nowait(cleaned)
                except queue.Full:
                    self._stdout_tail.append("<protocol queue overflow>")
            else:
                self._stdout_tail.append(cleaned)

    def _read_stderr(self) -> None:
        if self._process.stderr is None:
            return
        for line in self._process.stderr:
            self._stderr_tail.append(line.rstrip("\r\n"))

    def _diagnostic(self) -> str:
        return (
            f"exit={self._process.poll()}, "
            f"stderr={' | '.join(self._stderr_tail) or '<empty>'}, "
            f"other_stdout={' | '.join(self._stdout_tail) or '<empty>'}"
        )

    def _next_protocol_line(self) -> list[str]:
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise DejaVuProtocolError(
                    f"timed out waiting for DejaVu acknowledgement ({self._diagnostic()})"
                )
            try:
                return self._stdout.get(timeout=remaining).split("\t")
            except queue.Empty as exc:
                raise DejaVuProtocolError(
                    f"timed out waiting for DejaVu acknowledgement ({self._diagnostic()})"
                ) from exc

    def submit(self, event: RuntimeEvent) -> MonitorAck:
        with self._lock:
            if self._closed or self._process.poll() is not None:
                raise DejaVuProtocolError(
                    f"DejaVu monitor is not running ({self._diagnostic()})"
                )
            assert self._process.stdin is not None
            try:
                self._process.stdin.write(event.bridge_line())
                self._process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                raise DejaVuProtocolError(
                    f"cannot submit event to DejaVu ({self._diagnostic()})"
                ) from exc
            reply = self._next_protocol_line()
            if len(reply) < 3:
                raise DejaVuProtocolError(f"malformed DejaVu reply: {reply}")
            try:
                seq = int(reply[1])
            except ValueError as exc:
                raise DejaVuProtocolError(f"invalid DejaVu sequence: {reply}") from exc
            if seq != event.seq:
                raise DejaVuProtocolError(
                    f"DejaVu watermark mismatch: expected {event.seq}, got {seq}"
                )
            if reply[2] == "PASS":
                return MonitorAck(seq, True)
            if reply[2] == "FAIL":
                violations = (
                    tuple(filter(None, reply[3].split("|"))) if len(reply) > 3 else ()
                )
                return MonitorAck(seq, False, violations)
            if reply[2] == "ERROR":
                reason = reply[3] if len(reply) > 3 else "unknown bridge error"
                raise DejaVuProtocolError(reason)
            raise DejaVuProtocolError(f"unknown DejaVu reply: {reply}")

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if self._process.poll() is None and self._process.stdin is not None:
                try:
                    self._process.stdin.write("RV1\tCLOSE\n")
                    self._process.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass
            try:
                self._process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                self._process.terminate()
                try:
                    self._process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait(timeout=1.0)
            self._stdout_thread.join(timeout=1.0)
            self._stderr_thread.join(timeout=1.0)
            for stream in (
                self._process.stdin,
                self._process.stdout,
                self._process.stderr,
            ):
                if stream is not None and not stream.closed:
                    stream.close()

    def __enter__(self) -> "SynchronousDejaVu":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
