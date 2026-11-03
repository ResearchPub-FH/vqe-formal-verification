from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEPENDENCY_MANIFEST = ROOT / "tools" / "monitor_build_dependencies.json"
DEFAULT_DEPENDENCY_DIRECTORY = (
    ROOT / ".cache" / "dejavu-build" / "scala-2.12.21"
)


def run(command: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_dependency_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise SystemExit("unsupported monitor-build dependency manifest")
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, dict):
        raise SystemExit("monitor-build dependency manifest has no artifacts table")
    return data


def resolve_scala_jar(
    explicit: Path | None,
    dependency_directory: Path,
    manifest: dict[str, Any],
    artifact: str,
) -> Path:
    record = manifest["artifacts"].get(artifact)
    if not isinstance(record, dict):
        raise SystemExit(f"dependency manifest does not pin {artifact}")
    path = explicit or dependency_directory / record["filename"]
    resolved = path.resolve()
    if not resolved.is_file():
        raise SystemExit(
            f"missing {artifact}: {resolved}; run tools/fetch_monitor_build_deps.py"
        )
    actual = sha256(resolved)
    if actual != record["sha256"]:
        raise SystemExit(
            f"{artifact} SHA-256 mismatch: {actual} != {record['sha256']}"
        )
    return resolved


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the synchronous VQE DejaVu monitor")
    parser.add_argument(
        "--dejavu-jar",
        type=Path,
        default=ROOT / "src/vqe_runtime/vendor/dejavu/dejavu.jar",
    )
    parser.add_argument("--scala-compiler", type=Path)
    parser.add_argument("--scala-library", type=Path)
    parser.add_argument("--scala-reflect", type=Path)
    parser.add_argument(
        "--dependency-manifest",
        type=Path,
        default=DEFAULT_DEPENDENCY_MANIFEST,
    )
    parser.add_argument(
        "--dependency-directory",
        type=Path,
        default=DEFAULT_DEPENDENCY_DIRECTORY,
    )
    parser.add_argument("--spec", type=Path, default=Path("specs/vqe_runtime.qtl"))
    parser.add_argument("--bridge", type=Path, default=Path("tools/SynchronousBridge.scala"))
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("src/vqe_runtime/vendor/dejavu/vqe-three-level-monitor.jar"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="external runtime manifest (defaults beside --out)",
    )
    args = parser.parse_args()
    dependency_manifest = load_dependency_manifest(
        args.dependency_manifest.resolve()
    )
    scala_compiler = resolve_scala_jar(
        args.scala_compiler,
        args.dependency_directory,
        dependency_manifest,
        "scala-compiler",
    )
    scala_library = resolve_scala_jar(
        args.scala_library,
        args.dependency_directory,
        dependency_manifest,
        "scala-library",
    )
    scala_reflect = resolve_scala_jar(
        args.scala_reflect,
        args.dependency_directory,
        dependency_manifest,
        "scala-reflect",
    )
    dejavu_pin = dependency_manifest.get("bundled_dejavu", {})
    if sha256(args.dejavu_jar.resolve()) != dejavu_pin.get("sha256"):
        raise SystemExit("bundled DejaVu JAR does not match the dependency manifest")
    inputs = (
        args.dejavu_jar,
        scala_compiler,
        scala_library,
        scala_reflect,
        args.spec,
        args.bridge,
    )
    for path in inputs:
        if not path.resolve().is_file():
            raise SystemExit(f"missing build input: {path}")

    with tempfile.TemporaryDirectory(prefix="vqe-dejavu-build-") as temp:
        build = Path(temp)
        run(
            [
                "java",
                "-cp",
                str(args.dejavu_jar.resolve()),
                "dejavu.Verify",
                str(args.spec.resolve()),
            ],
            cwd=build,
        )
        classes = build / "classes"
        classes.mkdir()
        compiler_cp = ":".join(
            str(path.resolve())
            for path in (
                scala_compiler,
                scala_library,
                scala_reflect,
            )
        )
        run(
            [
                "java",
                "-cp",
                compiler_cp,
                "scala.tools.nsc.Main",
                "-usejavacp",
                "-classpath",
                str(args.dejavu_jar.resolve()),
                "-d",
                str(classes),
                str(build / "TraceMonitor.scala"),
                str(args.bridge.resolve()),
            ]
        )
        metadata = {
            "schema": 1,
            "property_levels": ["intra_iteration", "inter_iteration", "run_level"],
            "spec_sha256": sha256(args.spec.resolve()),
            "bridge_sha256": sha256(args.bridge.resolve()),
            "dejavu_sha256": sha256(args.dejavu_jar.resolve()),
        }
        (classes / "VQE_MONITOR_BUILD.json").write_text(
            json.dumps(metadata, sort_keys=True) + "\n", encoding="utf-8"
        )
        args.out.parent.mkdir(parents=True, exist_ok=True)
        run(
            [
                "jar",
                "--create",
                "--file",
                str(args.out.resolve()),
                "--date=2026-01-01T00:00:00Z",
                "-C",
                str(classes),
                ".",
            ]
        )
        runtime_manifest = dict(metadata)
        runtime_manifest["monitor_sha256"] = sha256(args.out.resolve())
        manifest_path = args.manifest or args.out.with_name("monitor-manifest.json")
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(runtime_manifest, sort_keys=True) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
