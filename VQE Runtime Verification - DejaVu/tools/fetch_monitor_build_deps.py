#!/usr/bin/env python3
"""Fetch and hash-check the pinned Scala monitor-build dependencies."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "tools" / "monitor_build_dependencies.json"
DEFAULT_OUTPUT = ROOT / ".cache" / "dejavu-build" / "scala-2.12.21"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("scala_version") != "2.12.21":
        raise ValueError("unsupported monitor-build dependency manifest")
    artifacts = data.get("artifacts")
    expected = {"scala-compiler", "scala-library", "scala-reflect"}
    if not isinstance(artifacts, dict) or set(artifacts) != expected:
        raise ValueError("dependency manifest must pin exactly three Scala artifacts")
    for name, record in artifacts.items():
        if not isinstance(record, dict) or set(record) != {
            "filename",
            "sha256",
            "url",
        }:
            raise ValueError(f"malformed dependency record {name!r}")
        if not record["url"].startswith("https://repo.maven.apache.org/maven2/"):
            raise ValueError(f"dependency {name!r} is not pinned to Maven Central HTTPS")
        if len(record["sha256"]) != 64:
            raise ValueError(f"dependency {name!r} has a malformed SHA-256")
    return data


def fetch(url: str, destination: Path, expected_sha256: str) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and sha256(destination) == expected_sha256:
        return "already verified"
    if destination.exists():
        raise ValueError(
            f"refusing to replace unverified dependency path: {destination}"
        )
    request = Request(url, headers={"User-Agent": "vqe-dejavu-rebuild/1"})
    with tempfile.NamedTemporaryFile(
        prefix=destination.name + ".",
        suffix=".part",
        dir=destination.parent,
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
        try:
            with urlopen(request, timeout=60) as response:
                while chunk := response.read(1024 * 1024):
                    temporary.write(chunk)
            temporary.flush()
            os.fsync(temporary.fileno())
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
    actual = sha256(temporary_path)
    if actual != expected_sha256:
        temporary_path.unlink(missing_ok=True)
        raise ValueError(
            f"SHA-256 mismatch for {destination.name}: {actual} != {expected_sha256}"
        )
    os.replace(temporary_path, destination)
    return "downloaded and verified"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch pinned Scala 2.12.21 JARs for rebuilding the DejaVu monitor"
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    manifest = load_manifest(args.manifest.resolve())
    output = args.out_dir.resolve()
    for name, record in manifest["artifacts"].items():
        destination = output / record["filename"]
        status = fetch(record["url"], destination, record["sha256"])
        print(f"{name}: {status}: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
