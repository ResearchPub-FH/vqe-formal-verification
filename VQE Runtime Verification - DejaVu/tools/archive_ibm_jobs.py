#!/usr/bin/env python3
"""Archive sanitized IBM Runtime job metrics and Estimator result metadata."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from vqe_runtime.events import load_events  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "tolist"):
        return _jsonable(value.tolist())
    return repr(value)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Archive completed IBM Estimator job metrics for a VQE trace"
    )
    parser.add_argument("trace", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--instance", default="test")
    args = parser.parse_args()

    trace = args.trace.resolve()
    events, errors = load_events(trace)
    if errors:
        raise SystemExit("cannot read trace: " + "; ".join(errors))
    submitted = [event for event in events if event.name == "jobSubmitted"]
    if not submitted:
        raise SystemExit("trace contains no IBM jobSubmitted events")

    from qiskit_ibm_runtime import QiskitRuntimeService

    service = QiskitRuntimeService(instance=args.instance)
    jobs: list[dict[str, Any]] = []
    for event in submitted:
        job_id = str(event.payload["external_job_id"])
        job = service.job(job_id)
        result = job.result()
        pub = result[0]
        data = pub.data
        fields = list(data.keys()) if hasattr(data, "keys") else []
        jobs.append(
            {
                "iteration": int(event.args[2]),
                "evaluation_id": event.args[3],
                "job_id": job_id,
                "status": str(job.status()),
                "metrics": _jsonable(job.metrics()),
                "usage_estimation": _jsonable(job.usage_estimation),
                "result_metadata": _jsonable(getattr(result, "metadata", None)),
                "pub_metadata": _jsonable(getattr(pub, "metadata", None)),
                "data": {
                    field: _jsonable(getattr(data, field))
                    for field in fields
                },
            }
        )

    qpu_seconds = sum(
        int(job["metrics"].get("usage", {}).get("qpu_charge_time_seconds", 0))
        for job in jobs
    )
    circuit_ns = sum(
        int(job["metrics"].get("circuits_execution_time_ns", 0)) for job in jobs
    )
    document = {
        "schema_version": 1,
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "trace": str(trace.relative_to(ROOT)),
        "trace_sha256": _sha256(trace),
        "instance": args.instance,
        "job_count": len(jobs),
        "total_qpu_charge_time_seconds": qpu_seconds,
        "total_circuits_execution_time_ns": circuit_ns,
        "jobs": jobs,
    }
    destination = args.output.resolve()
    if destination.exists():
        raise SystemExit(f"refusing to overwrite {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: document[key] for key in document if key != "jobs"}, indent=2))


if __name__ == "__main__":
    main()
