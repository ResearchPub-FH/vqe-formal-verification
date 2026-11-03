#!/usr/bin/env python3
"""Create reproducible CSV/JSON summaries for paired H2 Sampler runs.

The script is deliberately offline.  It strictly reloads both raw-evidence
sidecars, independently recomputes parity expectations and Hamiltonian energy,
checks the ask/tell parameter chain, and writes presentation-ready tables.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from vqe_runtime.evidence import load_evidence  # noqa: E402
from vqe_runtime.events import RuntimeEvent, load_events  # noqa: E402
from vqe_runtime.sampling import (  # noqa: E402
    expectation_from_negative_count,
    negative_eigenvalue_count,
)


TERM_ORDER = ("t0", "t1", "t2", "t3")
PAULI_ORDER = ("YZ", "ZI", "ZZ", "XX")
SHOTS_PER_TERM = 1024
PUBS_PER_EVALUATION = 4
MAX_EVALUATIONS = 50
MAX_SHOTS = 204800
ABS_TOLERANCE = 1e-12


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return value


def _one(events: list[RuntimeEvent], name: str, iteration: int) -> RuntimeEvent:
    matches = [
        event
        for event in events
        if event.name == name
        and len(event.args) > 2
        and event.args[2] == str(iteration)
    ]
    if len(matches) != 1:
        raise ValueError(
            f"iteration {iteration} requires exactly one {name}; observed {len(matches)}"
        )
    return matches[0]


def _close(value: float, expected: float) -> bool:
    return math.isclose(value, expected, rel_tol=0.0, abs_tol=ABS_TOLERANCE)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _job_summary(record: dict[str, Any]) -> dict[str, Any]:
    metadata = record.get("job_metadata") or {}
    metrics = metadata.get("metrics") or {}
    timestamps = metrics.get("timestamps") or {}
    usage = metrics.get("usage") or {}
    estimate = metadata.get("usage_estimation") or {}
    return {
        "iteration": record["iteration"],
        "evaluation_id": record["evaluation_id"],
        "job_id": record["external_job_id"],
        "backend": record["backend"],
        "status": metadata.get("status"),
        "created_utc": timestamps.get("created") or metadata.get("creation_date"),
        "running_utc": timestamps.get("running"),
        "finished_utc": timestamps.get("finished"),
        "circuits_execution_time_ns": metrics.get("circuits_execution_time_ns"),
        "qpu_charge_time_seconds": usage.get("qpu_charge_time_seconds"),
        "quantum_seconds_estimate": estimate.get("quantum_seconds"),
        "metrics": metrics,
        "usage_estimation": estimate,
    }


def _analyze_run(
    *,
    label: str,
    trace_path: Path,
    evidence_path: Path,
    online_path: Path,
    replay_path: Path,
    coefficients: dict[str, float],
) -> dict[str, Any]:
    online = _read_json(online_path)
    replay = _read_json(replay_path)
    _require(online.get("status") == "pass", f"{label} online report is not PASS")
    _require(replay.get("status") == "pass", f"{label} replay report is not PASS")
    _require(
        all(
            online.get("levels", {}).get(level, {}).get("status") == "pass"
            and replay.get("levels", {}).get(level, {}).get("status") == "pass"
            for level in ("intra_iteration", "inter_iteration", "run_level")
        ),
        f"{label} does not pass all three verification levels",
    )
    _require(
        online.get("terminal_reason") == replay.get("terminal_reason"),
        f"{label} online/replay terminal reasons differ",
    )
    _require(
        online.get("config_hash") == replay.get("config_hash"),
        f"{label} online/replay configuration hashes differ",
    )

    events, trace_errors = load_events(trace_path)
    _require(not trace_errors, f"{label} trace errors: {trace_errors}")
    run_id = str(online["run_id"])
    config_hash = str(online["config_hash"])
    loaded = load_evidence(
        evidence_path,
        expected_run_id=run_id,
        expected_config_hash=config_hash,
    )
    _require(loaded.ok, f"{label} evidence errors: {loaded.errors}")
    _require(loaded.manifest is not None, f"{label} evidence is not sealed")
    records = list(loaded.records)

    _require(len(records) == MAX_EVALUATIONS * PUBS_PER_EVALUATION, f"{label} PUB count")
    _require(loaded.manifest["record_count"] == len(records), f"{label} manifest count")
    _require(
        loaded.manifest["total_observed_shots"] == MAX_SHOTS,
        f"{label} manifest shot total",
    )

    records_by_iteration: dict[int, list[dict[str, Any]]] = {}
    for record in records:
        iteration = int(record["iteration"])
        records_by_iteration.setdefault(iteration, []).append(record)

    iteration_rows: list[dict[str, Any]] = []
    pub_rows: list[dict[str, Any]] = []
    job_by_id: dict[str, dict[str, Any]] = {}
    all_expectations_reconstruct = True
    all_energies_reconstruct = True
    all_counts_sum = True
    all_shots_exact = True
    fixed_layouts: set[tuple[int, ...]] = set()
    best_so_far = math.inf

    for iteration in range(MAX_EVALUATIONS):
        bound = _one(events, "parametersBound", iteration)
        submitted = _one(events, "jobSubmitted", iteration)
        closed = _one(events, "iterationClosed", iteration)
        iteration_records = sorted(
            records_by_iteration.get(iteration, []), key=lambda item: item["pub_index"]
        )
        _require(len(iteration_records) == PUBS_PER_EVALUATION, f"{label} eval {iteration} PUBs")
        _require(
            tuple(record["term_id"] for record in iteration_records) == TERM_ORDER,
            f"{label} eval {iteration} term order",
        )
        _require(
            tuple(record["pauli"] for record in iteration_records) == PAULI_ORDER,
            f"{label} eval {iteration} Pauli order",
        )

        expectations: dict[str, float] = {}
        for record in iteration_records:
            counts_total = sum(record["counts"].values())
            all_counts_sum &= counts_total == SHOTS_PER_TERM
            all_shots_exact &= (
                record["requested_shots"] == SHOTS_PER_TERM
                and record["observed_shots"] == SHOTS_PER_TERM
            )
            negative = negative_eigenvalue_count(record["counts"], record["pauli"])
            reconstructed = expectation_from_negative_count(negative, SHOTS_PER_TERM)
            all_expectations_reconstruct &= (
                negative == record["negative_eigenvalue_count"]
                and _close(reconstructed, float(record["expectation"]))
            )
            expectations[record["term_id"]] = reconstructed
            layout = record["physical_layout"]["logical_to_physical"]
            fixed_layouts.add(tuple(int(item) for item in layout))
            if record["external_job_id"] not in job_by_id:
                job_by_id[record["external_job_id"]] = _job_summary(record)
            pub_rows.append(
                {
                    "run": label,
                    "iteration": iteration,
                    "evaluation_id": record["evaluation_id"],
                    "submission_id": record["submission_id"],
                    "job_id": record["external_job_id"],
                    "pub_index": record["pub_index"],
                    "term_id": record["term_id"],
                    "pauli": record["pauli"],
                    "requested_shots": record["requested_shots"],
                    "observed_shots": record["observed_shots"],
                    "count_sum": counts_total,
                    "negative_eigenvalue_count": negative,
                    "expectation": reconstructed,
                    "counts_json": json.dumps(record["counts"], sort_keys=True),
                    "raw_shot_data_sha256": record["raw_shot_data_sha256"],
                    "raw_evidence_sha256": record["raw_evidence_sha256"],
                    "parameterized_circuit_qpy_sha256": record[
                        "parameterized_circuit_qpy_sha256"
                    ],
                    "executable_circuit_qpy_sha256": record[
                        "executable_circuit_qpy_sha256"
                    ],
                    "logical_to_physical": json.dumps(layout),
                    "submitted_at_utc": record["submitted_at_utc"],
                    "retrieved_at_utc": record["retrieved_at_utc"],
                }
            )

        energy = sum(coefficients[term_id] * expectations[term_id] for term_id in TERM_ORDER)
        recorded_energy = float(closed.payload["energy"])
        all_energies_reconstruct &= _close(energy, recorded_energy)
        best_so_far = min(best_so_far, recorded_energy)
        job = job_by_id[str(submitted.payload["external_job_id"])]
        theta = list(bound.payload["theta"])
        iteration_rows.append(
            {
                "run": label,
                "iteration": iteration,
                "evaluation_id": closed.payload["evaluation_id"],
                "job_id": submitted.payload["external_job_id"],
                "theta_0": theta[0],
                "theta_1": theta[1],
                "theta_2": theta[2],
                "theta_3": theta[3],
                "theta_hash": bound.payload["theta_hash"],
                "expectation_YZ": expectations["t0"],
                "expectation_ZI": expectations["t1"],
                "expectation_ZZ": expectations["t2"],
                "expectation_XX": expectations["t3"],
                "energy": recorded_energy,
                "best_energy_so_far": best_so_far,
                "converged": bool(closed.payload["converged"]),
                "physical_shots": sum(item["observed_shots"] for item in iteration_records),
                "qpu_charge_time_seconds": job.get("qpu_charge_time_seconds"),
                "created_utc": job.get("created_utc"),
                "running_utc": job.get("running_utc"),
                "finished_utc": job.get("finished_utc"),
            }
        )

    intents = [event for event in events if event.name == "optimizerUpdateIntent"]
    commits = [event for event in events if event.name == "optimizerUpdated"]
    ask_tell_chain_valid = len(intents) == len(commits) == MAX_EVALUATIONS - 1
    for iteration in range(MAX_EVALUATIONS - 1):
        intent = _one(events, "optimizerUpdateIntent", iteration)
        commit = _one(events, "optimizerUpdated", iteration)
        successor = _one(events, "parametersBound", iteration + 1)
        ask_tell_chain_valid &= (
            intent.seq < commit.seq < successor.seq
            and intent.payload == commit.payload
            and commit.payload["next_theta_hash"] == successor.payload["theta_hash"]
            and commit.payload["next_theta"] == successor.payload["theta"]
        )

    terminal_names = [
        event.name
        for event in events
        if event.name in {"runConverged", "runMaxIterations", "runOptimizerStopped"}
    ]
    terminal_valid = terminal_names == ["runMaxIterations"] and events[-1].name == "runClosed"
    job_ids = [row["job_id"] for row in iteration_rows]
    unique_jobs = len(job_ids) == len(set(job_ids)) == MAX_EVALUATIONS
    fixed_layout = len(fixed_layouts) == 1

    acceptance = {
        "strict_raw_sidecar_validation": loaded.ok,
        "sealed_manifest_matches_records": (
            loaded.manifest["record_count"] == 200
            and loaded.manifest["total_observed_shots"] == MAX_SHOTS
        ),
        "each_pub_has_exactly_1024_observed_shots": all_shots_exact,
        "every_count_dictionary_sums_to_1024": all_counts_sum,
        "packed_and_ordered_shots_match_archived_hashes": loaded.ok,
        "all_expectations_reconstruct_from_odd_parity": all_expectations_reconstruct,
        "all_energies_reconstruct_from_four_expectations": all_energies_reconstruct,
        "physical_shot_budget_not_exceeded": (
            sum(row["physical_shots"] for row in iteration_rows) == MAX_SHOTS
        ),
        "online_and_replay_verdicts_agree": (
            online["status"] == replay["status"] == "pass"
            and online["terminal_reason"] == replay["terminal_reason"]
        ),
        "explicit_ask_tell_chain_valid": ask_tell_chain_valid,
        "all_job_ids_unique": unique_jobs,
        "fixed_physical_layout_across_all_pubs": fixed_layout,
        "truthful_max_iteration_termination": terminal_valid,
    }
    _require(all(acceptance.values()), f"{label} acceptance failure: {acceptance}")

    qpu_charge = sum(
        int(job.get("qpu_charge_time_seconds") or 0) for job in job_by_id.values()
    )
    quantum_seconds = sum(
        float(job.get("quantum_seconds_estimate") or 0.0) for job in job_by_id.values()
    )
    best_row = min(iteration_rows, key=lambda item: item["energy"])
    return {
        "label": label,
        "run_id": run_id,
        "config_hash": config_hash,
        "trace_event_count": len(events),
        "evaluations": len(iteration_rows),
        "pubs": len(records),
        "physical_shots": sum(row["physical_shots"] for row in iteration_rows),
        "job_count": len(job_by_id),
        "initial_energy": iteration_rows[0]["energy"],
        "final_energy": iteration_rows[-1]["energy"],
        "best_energy": best_row["energy"],
        "best_energy_iteration": best_row["iteration"],
        "terminal_reason": online["terminal_reason"],
        "online_status": online["status"],
        "replay_status": replay["status"],
        "verified_levels": {
            level: online["levels"][level]["status"]
            for level in ("intra_iteration", "inter_iteration", "run_level")
        },
        "physical_layouts": [list(value) for value in sorted(fixed_layouts)],
        "qpu_charge_time_seconds": qpu_charge,
        "quantum_seconds_estimate": quantum_seconds,
        "evidence_manifest_sha256": loaded.manifest["manifest_sha256"],
        "acceptance_criteria": acceptance,
        "iteration_rows": iteration_rows,
        "pub_rows": pub_rows,
        "jobs": sorted(job_by_id.values(), key=lambda item: item["iteration"]),
        "paths": {
            "trace": str(trace_path.relative_to(ROOT)),
            "evidence": str(evidence_path.relative_to(ROOT)),
            "online_report": str(online_path.relative_to(ROOT)),
            "replay_report": str(replay_path.relative_to(ROOT)),
        },
        "sha256": {
            "trace": _sha256(trace_path),
            "evidence": _sha256(evidence_path),
            "online_report": _sha256(online_path),
            "replay_report": _sha256(replay_path),
        },
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    _require(bool(rows), f"refusing to write empty CSV {path}")
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--hardware-trace",
        type=Path,
        default=ROOT / "artifacts/traces/h2_ibm_marrakesh_sampler_20260907.jsonl",
    )
    parser.add_argument(
        "--hardware-evidence",
        type=Path,
        default=ROOT / "artifacts/evidence/h2_ibm_marrakesh_sampler_20260907.jsonl",
    )
    parser.add_argument(
        "--hardware-online",
        type=Path,
        default=ROOT / "artifacts/reports/h2_ibm_marrakesh_sampler_20260907_online.json",
    )
    parser.add_argument(
        "--hardware-replay",
        type=Path,
        default=ROOT / "artifacts/reports/h2_ibm_marrakesh_sampler_20260907_replay.json",
    )
    parser.add_argument(
        "--statevector-trace",
        type=Path,
        default=ROOT / "artifacts/traces/h2_statevector_sampler_20260907.jsonl",
    )
    parser.add_argument(
        "--statevector-evidence",
        type=Path,
        default=ROOT / "artifacts/evidence/h2_statevector_sampler_20260907.jsonl",
    )
    parser.add_argument(
        "--statevector-online",
        type=Path,
        default=ROOT / "artifacts/reports/h2_statevector_sampler_20260907_online.json",
    )
    parser.add_argument(
        "--statevector-replay",
        type=Path,
        default=ROOT / "artifacts/reports/h2_statevector_sampler_20260907_replay.json",
    )
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        raise SystemExit(f"refusing to overwrite existing output directory {output_dir}")
    output_dir.mkdir(parents=True)

    hamiltonian = _read_json(ROOT / "data/h2_hamiltonian.json")
    scale = int(hamiltonian["coeff_scale"])
    coefficients = {
        str(term["term_id"]): int(term["coeff_int"]) / scale
        for term in hamiltonian["terms"]
    }
    hardware = _analyze_run(
        label="ibm_marrakesh",
        trace_path=args.hardware_trace.resolve(),
        evidence_path=args.hardware_evidence.resolve(),
        online_path=args.hardware_online.resolve(),
        replay_path=args.hardware_replay.resolve(),
        coefficients=coefficients,
    )
    statevector = _analyze_run(
        label="statevector_sampler",
        trace_path=args.statevector_trace.resolve(),
        evidence_path=args.statevector_evidence.resolve(),
        online_path=args.statevector_online.resolve(),
        replay_path=args.statevector_replay.resolve(),
        coefficients=coefficients,
    )

    _require(
        hardware["iteration_rows"][0]["theta_hash"]
        == statevector["iteration_rows"][0]["theta_hash"],
        "comparator runs do not share the same initial parameters",
    )
    _require(
        [row["pauli"] for row in hardware["pub_rows"][:4]]
        == [row["pauli"] for row in statevector["pub_rows"][:4]],
        "comparator runs do not share the same term order",
    )

    _write_csv(output_dir / "hardware_evaluations.csv", hardware.pop("iteration_rows"))
    _write_csv(output_dir / "hardware_pubs.csv", hardware.pop("pub_rows"))
    hardware_jobs = hardware.pop("jobs")
    _write_csv(output_dir / "statevector_evaluations.csv", statevector.pop("iteration_rows"))
    _write_csv(output_dir / "statevector_pubs.csv", statevector.pop("pub_rows"))
    statevector.pop("jobs")

    (output_dir / "hardware_jobs.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source": "deduplicated job metadata embedded in raw evidence",
                "job_count": len(hardware_jobs),
                "jobs": hardware_jobs,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    summary = {
        "schema_version": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "hamiltonian": {
            "expression": "0.3980 YZ - 0.3980 ZI - 0.0113 ZZ + 0.1810 XX",
            "coefficients": coefficients,
            "source": "data/h2_hamiltonian.json",
            "sha256": _sha256(ROOT / "data/h2_hamiltonian.json"),
        },
        "fixed_design": {
            "evaluations": MAX_EVALUATIONS,
            "pubs_per_evaluation": PUBS_PER_EVALUATION,
            "shots_per_term": SHOTS_PER_TERM,
            "maximum_pubs": MAX_EVALUATIONS * PUBS_PER_EVALUATION,
            "maximum_physical_shots": MAX_SHOTS,
            "term_order": list(PAULI_ORDER),
            "optimizer_protocol": "ask-tell-pattern-search-v1",
        },
        "hardware": hardware,
        "statevector": statevector,
        "comparison": {
            "same_initial_theta": True,
            "same_ansatz_measurement_optimizer_and_budget": True,
            "hardware_minus_statevector_best_energy": (
                hardware["best_energy"] - statevector["best_energy"]
            ),
            "hardware_minus_statevector_final_energy": (
                hardware["final_energy"] - statevector["final_energy"]
            ),
            "interpretation": (
                "The two sampled optimization paths are comparable by design but may "
                "diverge after noisy objective values change ask/tell decisions."
            ),
        },
    }
    summary_path = output_dir / "campaign_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    paths = sorted(path for path in output_dir.iterdir() if path.is_file())
    checksum_lines = [f"{_sha256(path)}  {path.name}" for path in paths]
    (output_dir / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "hardware_acceptance": all(hardware["acceptance_criteria"].values()),
                "statevector_acceptance": all(statevector["acceptance_criteria"].values()),
                "hardware_best_energy": hardware["best_energy"],
                "statevector_best_energy": statevector["best_energy"],
                "hardware_qpu_charge_time_seconds": hardware[
                    "qpu_charge_time_seconds"
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
