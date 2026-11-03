#!/usr/bin/env python3
"""Measure deterministic H2 verification overhead and DejaVu scaling.

The primary experiment compares the same deterministic H2 workload in three
conditions: an uninstrumented loop, RuntimeSession with the Python test/shadow
monitor, and RuntimeSession with the real synchronous DejaVu monitor.  The
scaling experiment keeps the H2 Hamiltonian and event protocol fixed while
increasing the number of non-converging evaluations.

Every measured run, gate acknowledgement, and RSS sample is written to CSV.
The JSON summary contains only derived statistics; the CSV files remain the
source data.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from vqe_runtime.config import RuntimeConfig, load_config  # noqa: E402
from vqe_runtime.dejavu import (  # noqa: E402
    AlwaysPassMonitor,
    MonitorAck,
    SynchronousDejaVu,
)
from vqe_runtime.events import RuntimeEvent  # noqa: E402
from vqe_runtime.session import (  # noqa: E402
    RuntimeSession,
    TermObservation,
    TerminationReason,
)


RUN_FIELDS = (
    "experiment",
    "condition",
    "phase",
    "repetition",
    "run_id",
    "configured_evaluations",
    "completed_evaluations",
    "event_count",
    "trace_bytes",
    "status",
    "terminal_reason",
    "startup_seconds",
    "session_seconds",
    "close_seconds",
    "end_to_end_seconds",
    "python_peak_rss_bytes",
    "jvm_peak_rss_bytes",
    "combined_peak_rss_bytes",
)

GATE_FIELDS = (
    "experiment",
    "condition",
    "phase",
    "repetition",
    "run_id",
    "configured_evaluations",
    "seq",
    "event",
    "latency_seconds",
)

MEMORY_FIELDS = (
    "experiment",
    "condition",
    "phase",
    "repetition",
    "run_id",
    "configured_evaluations",
    "elapsed_seconds",
    "role",
    "pid",
    "rss_bytes",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _command_output(command: Sequence[str]) -> str:
    completed = subprocess.run(
        list(command), check=False, capture_output=True, text=True
    )
    return (completed.stdout + completed.stderr).strip()


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _distribution(values: Iterable[float]) -> dict[str, float | int | None]:
    samples = [float(value) for value in values]
    return {
        "count": len(samples),
        "min": min(samples) if samples else None,
        "p50": _percentile(samples, 0.50),
        "p95": _percentile(samples, 0.95),
        "max": max(samples) if samples else None,
        "mean": statistics.fmean(samples) if samples else None,
    }


def _relative_percent(instrumented: float | None, baseline: float | None) -> float | None:
    if instrumented is None or baseline is None or baseline == 0:
        return None
    return (instrumented - baseline) / baseline * 100.0


def _parse_scales(raw: str) -> list[int]:
    values: list[int] = []
    for item in raw.split(","):
        stripped = item.strip()
        if not stripped:
            continue
        value = int(stripped)
        if value < 1:
            raise argparse.ArgumentTypeError("scales must be positive integers")
        if value not in values:
            values.append(value)
    if not values:
        raise argparse.ArgumentTypeError("at least one scale is required")
    return sorted(values)


def _write_csv(path: Path, fields: Sequence[str], rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fields))
        writer.writeheader()
        writer.writerows(rows)


class _MemorySampler:
    def __init__(self, *, interval_seconds: float = 0.05) -> None:
        self.interval_seconds = interval_seconds
        self.origin = time.perf_counter()
        self.rows: list[dict[str, Any]] = []
        self._roles: dict[int, str] = {os.getpid(): "python"}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def add_process(self, pid: int, role: str) -> None:
        with self._lock:
            self._roles[pid] = role
        self._sample_once()

    def start(self) -> None:
        self._sample_once()
        self._thread.start()

    def stop(self) -> list[dict[str, Any]]:
        self._stop.set()
        self._thread.join(timeout=max(1.0, self.interval_seconds * 4))
        self._sample_once()
        return list(self.rows)

    def _sample_once(self) -> None:
        with self._lock:
            roles = dict(self._roles)
        if not roles:
            return
        command = ["ps", "-o", "pid=", "-o", "rss="]
        for pid in roles:
            command.extend(["-p", str(pid)])
        try:
            completed = subprocess.run(
                command, check=False, capture_output=True, text=True
            )
        except OSError:
            # Sandboxed smoke tests may prohibit process inspection.  The
            # benchmark still runs, but its RSS fields remain zero; a publishable
            # run must use an environment in which `ps` can inspect both PIDs.
            return
        elapsed = time.perf_counter() - self.origin
        for raw in completed.stdout.splitlines():
            parts = raw.split()
            if len(parts) != 2:
                continue
            try:
                pid = int(parts[0])
                rss_bytes = int(parts[1]) * 1024
            except ValueError:
                continue
            self.rows.append(
                {
                    "elapsed_seconds": elapsed,
                    "role": roles.get(pid, "unknown"),
                    "pid": pid,
                    "rss_bytes": rss_bytes,
                }
            )

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self._sample_once()


def _observations(
    config: RuntimeConfig, *, scaling_index: int | None = None
) -> tuple[TermObservation, ...]:
    # These ratios reproduce the deterministic H2 fixture.  The scaling sweep
    # alternates between the low and high sides of the t0 count domain while
    # moving inward by one count per pair.  Consecutive energies remain well
    # outside the convergence tolerance and every evaluation receives a fresh
    # energy identity, which exercises the relation-domain growth under test.
    ratios = {"t0": 0.75, "t1": 0.25, "t2": 0.50, "t3": 0.90}
    if {term.term_id for term in config.hamiltonian.terms} != set(ratios):
        raise ValueError("the benchmark requires the repository's four-term H2 manifest")
    result: list[TermObservation] = []
    for term in config.hamiltonian.terms:
        if term.term_id == "t0" and scaling_index is not None:
            lower = round(config.shots_per_term * 0.10)
            upper = round(config.shots_per_term * 0.90)
            offset = scaling_index // 2
            ones = lower + offset if scaling_index % 2 == 0 else upper - offset
            if ones < 0 or ones > config.shots_per_term or lower + offset >= upper - offset:
                raise ValueError(
                    "scaling sweep exhausted the distinct deterministic count domain"
                )
        else:
            ones = round(config.shots_per_term * ratios[term.term_id])
        expectation = 1.0 - 2.0 * ones / config.shots_per_term
        result.append(
            TermObservation(term.term_id, expectation, config.shots_per_term, ones)
        )
    return tuple(result)


def _energy(config: RuntimeConfig, observations: Sequence[TermObservation]) -> float:
    by_id = {item.term_id: item for item in observations}
    return math.fsum(
        term.coeff_int
        * by_id[term.term_id].expectation
        / config.hamiltonian.coeff_scale
        for term in config.hamiltonian.terms
    )


def _execute_verified_workload(
    session: RuntimeSession, config: RuntimeConfig, *, scaling: bool
) -> None:
    theta = (0.1, -0.2)
    for iteration in range(config.max_iterations):
        observations = _observations(
            config, scaling_index=iteration if scaling else None
        )
        energy = _energy(config, observations)
        session.begin_iteration(theta, evaluation_id=f"eval{iteration}")
        session.bind_parameters()
        session.authorize_job(f"submission{iteration}")
        session.mark_job_submitted(f"localJob{iteration}")
        session.observe_terms(observations)
        session.seal_measurements()
        session.aggregate_energy(energy)
        converged = session.check_convergence()
        session.authorize_objective_release()
        if not converged and iteration + 1 < config.max_iterations:
            next_theta = (theta[0] + 0.001, theta[1] - 0.001)
            session.authorize_optimizer_update(next_theta)
            session.mark_optimizer_updated(next_theta)
        else:
            next_theta = theta
        session.close_iteration()
        if converged:
            session.finish(TerminationReason.CONVERGED)
            break
        theta = next_theta
    else:
        session.finish(TerminationReason.MAX_ITERATIONS)
    session.seal_run()


def _execute_uninstrumented_workload(config: RuntimeConfig) -> int:
    theta = (0.1, -0.2)
    previous_energy: float | None = None
    stable_count = 0
    completed = 0
    for iteration in range(config.max_iterations):
        observations = _observations(config)
        energy = _energy(config, observations)
        if previous_energy is None:
            converged = False
        else:
            within = abs(energy - previous_energy) <= (
                config.convergence_tolerance + config.energy_abs_tolerance
            )
            stable_count = stable_count + 1 if within else 0
            converged = (
                within
                and iteration + 1 >= config.min_iterations
                and stable_count >= config.convergence_patience
            )
        completed += 1
        if converged:
            break
        theta = (theta[0] + 0.001, theta[1] - 0.001)
        previous_energy = energy
    # Keep the loop result live so an optimizing interpreter could not discard it.
    if not all(math.isfinite(value) for value in theta):
        raise RuntimeError("non-finite uninstrumented parameter")
    return completed


def _peak_by_role(samples: Sequence[dict[str, Any]], role: str) -> int:
    values = [int(row["rss_bytes"]) for row in samples if row["role"] == role]
    return max(values, default=0)


def _run_uninstrumented(
    config: RuntimeConfig,
    *,
    metadata: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    sampler = _MemorySampler()
    sampler.start()
    started = time.perf_counter()
    completed = _execute_uninstrumented_workload(config)
    elapsed = time.perf_counter() - started
    memory = sampler.stop()
    python_peak = _peak_by_role(memory, "python")
    run = {
        **metadata,
        "completed_evaluations": completed,
        "event_count": 0,
        "trace_bytes": 0,
        "status": "not_applicable",
        "terminal_reason": "not_applicable",
        "startup_seconds": 0.0,
        "session_seconds": elapsed,
        "close_seconds": 0.0,
        "end_to_end_seconds": elapsed,
        "python_peak_rss_bytes": python_peak,
        "jvm_peak_rss_bytes": 0,
        "combined_peak_rss_bytes": python_peak,
    }
    return run, [], memory


def _run_session(
    config: RuntimeConfig,
    *,
    metadata: dict[str, Any],
    real_monitor: bool,
    scaling: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    gate_rows: list[dict[str, Any]] = []
    sampler = _MemorySampler()
    sampler.start()
    total_started = time.perf_counter()
    startup_started = total_started
    monitor: AlwaysPassMonitor | SynchronousDejaVu
    if real_monitor:
        monitor = SynchronousDejaVu(
            timeout_seconds=config.monitor_timeout_seconds,
            bits_per_variable=config.bits_per_variable,
        )
        sampler.add_process(monitor._process.pid, "dejavu_jvm")
        original_submit: Callable[[RuntimeEvent], MonitorAck] = monitor.submit

        def timed_submit(event: RuntimeEvent) -> MonitorAck:
            gate_started = time.perf_counter()
            acknowledgement = original_submit(event)
            gate_rows.append(
                {
                    "seq": event.seq,
                    "event": event.name,
                    "latency_seconds": time.perf_counter() - gate_started,
                }
            )
            return acknowledgement

        monitor.submit = timed_submit  # type: ignore[method-assign]
    else:
        monitor = AlwaysPassMonitor()
    startup_seconds = time.perf_counter() - startup_started

    session_seconds = 0.0
    close_seconds = 0.0
    report = None
    trace_bytes = 0
    with tempfile.TemporaryDirectory(prefix="vqe-overhead-") as directory:
        trace_path = Path(directory) / "trace.jsonl"
        report_path = Path(directory) / "report.json"
        session_started = time.perf_counter()
        session = RuntimeSession(
            config,
            run_id=str(metadata["run_id"]),
            trace_path=trace_path,
            report_path=report_path,
            monitor=monitor,
            overwrite=True,
        )
        try:
            _execute_verified_workload(session, config, scaling=scaling)
            report = session.report
        finally:
            session_seconds = time.perf_counter() - session_started
            close_started = time.perf_counter()
            session.close()
            close_seconds = time.perf_counter() - close_started
        trace_bytes = trace_path.stat().st_size

    elapsed = time.perf_counter() - total_started
    memory = sampler.stop()
    python_peak = _peak_by_role(memory, "python")
    jvm_peak = _peak_by_role(memory, "dejavu_jvm")
    run = {
        **metadata,
        "completed_evaluations": report.iterations if report is not None else 0,
        "event_count": report.event_count if report is not None else 0,
        "trace_bytes": trace_bytes,
        "status": report.status.value if report is not None else "error",
        "terminal_reason": report.terminal_reason if report is not None else "error",
        "startup_seconds": startup_seconds,
        "session_seconds": session_seconds,
        "close_seconds": close_seconds,
        "end_to_end_seconds": elapsed,
        "python_peak_rss_bytes": python_peak,
        "jvm_peak_rss_bytes": jvm_peak,
        "combined_peak_rss_bytes": python_peak + jvm_peak,
    }
    return run, gate_rows, memory


def _decorate_rows(
    rows: Iterable[dict[str, Any]], metadata: dict[str, Any]
) -> list[dict[str, Any]]:
    return [{**metadata, **row} for row in rows]


def _primary_summary(
    runs: Sequence[dict[str, Any]], gates: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    measured = [row for row in runs if row["phase"] == "measured"]
    conditions: dict[str, Any] = {}
    for condition in ("uninstrumented", "python_shadow", "dejavu"):
        selected = [row for row in measured if row["condition"] == condition]
        selected_gates = [
            row
            for row in gates
            if row["phase"] == "measured" and row["condition"] == condition
        ]
        conditions[condition] = {
            "end_to_end_seconds": _distribution(
                float(row["end_to_end_seconds"]) for row in selected
            ),
            "session_seconds": _distribution(
                float(row["session_seconds"]) for row in selected
            ),
            "startup_seconds": _distribution(
                float(row["startup_seconds"]) for row in selected
            ),
            "gate_latency_seconds": _distribution(
                float(row["latency_seconds"]) for row in selected_gates
            ),
            "peak_rss_bytes": _distribution(
                float(row["combined_peak_rss_bytes"]) for row in selected
            ),
            "events_per_evaluation": _distribution(
                float(row["event_count"]) / int(row["completed_evaluations"])
                for row in selected
                if int(row["completed_evaluations"]) > 0
            ),
            "trace_bytes_per_evaluation": _distribution(
                float(row["trace_bytes"]) / int(row["completed_evaluations"])
                for row in selected
                if int(row["completed_evaluations"]) > 0
            ),
        }
    base = conditions["uninstrumented"]["end_to_end_seconds"]["p50"]
    shadow = conditions["python_shadow"]["end_to_end_seconds"]["p50"]
    dejavu = conditions["dejavu"]["end_to_end_seconds"]["p50"]
    return {
        "conditions": conditions,
        "relative_overhead_percent": {
            "python_shadow_vs_uninstrumented_p50": _relative_percent(shadow, base),
            "dejavu_vs_uninstrumented_p50": _relative_percent(dejavu, base),
            "dejavu_vs_python_shadow_p50": _relative_percent(dejavu, shadow),
        },
    }


def _scaling_summary(
    runs: Sequence[dict[str, Any]], gates: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    scales = sorted({int(row["configured_evaluations"]) for row in runs})
    for scale in scales:
        selected_runs = [
            row for row in runs if int(row["configured_evaluations"]) == scale
        ]
        selected_gates = [
            row for row in gates if int(row["configured_evaluations"]) == scale
        ]
        convergence_gates = [
            row for row in selected_gates if row["event"] == "nextConvergenceChecked"
        ]
        result.append(
            {
                "evaluations": scale,
                "runs": len(selected_runs),
                "events": [int(row["event_count"]) for row in selected_runs],
                "end_to_end_seconds": _distribution(
                    float(row["end_to_end_seconds"]) for row in selected_runs
                ),
                "gate_latency_seconds": _distribution(
                    float(row["latency_seconds"]) for row in selected_gates
                ),
                "next_convergence_checked_latency_seconds": _distribution(
                    float(row["latency_seconds"]) for row in convergence_gates
                ),
                "jvm_peak_rss_bytes": _distribution(
                    float(row["jvm_peak_rss_bytes"]) for row in selected_runs
                ),
                "combined_peak_rss_bytes": _distribution(
                    float(row["combined_peak_rss_bytes"]) for row in selected_runs
                ),
                "statuses": [str(row["status"]) for row in selected_runs],
            }
        )
    return result


def _metadata(
    *, experiment: str, condition: str, phase: str, repetition: int, evaluations: int
) -> dict[str, Any]:
    run_id = f"bench-{experiment}-{condition}-{phase}-{repetition}-n{evaluations}"
    return {
        "experiment": experiment,
        "condition": condition,
        "phase": phase,
        "repetition": repetition,
        "run_id": run_id,
        "configured_evaluations": evaluations,
    }


def _environment(config_path: Path, argv: Sequence[str]) -> dict[str, Any]:
    important = (
        ROOT / "data/h2_hamiltonian.json",
        ROOT / "specs/vqe_runtime.qtl",
        ROOT / "tools/SynchronousBridge.scala",
        ROOT / "tools/benchmark_overhead.py",
        ROOT / "src/vqe_runtime/vendor/dejavu/dejavu.jar",
        ROOT / "src/vqe_runtime/vendor/dejavu/vqe-three-level-monitor.jar",
        config_path,
    )
    return {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "command": list(argv),
        "cwd": str(Path.cwd()),
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "java_version": _command_output(["java", "-version"]),
        "pip_freeze": _command_output([sys.executable, "-m", "pip", "freeze"]).splitlines(),
        "sha256": {str(path.relative_to(ROOT)): _sha256(path) for path in important},
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark deterministic H2 verification overhead and DejaVu scaling"
    )
    parser.add_argument(
        "--config", type=Path, default=ROOT / "configs/h2_demo.toml"
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--repetitions", type=int, default=30)
    parser.add_argument("--scaling-repetitions", type=int, default=1)
    parser.add_argument(
        "--scales", type=_parse_scales, default=_parse_scales("10,25,50,75,100,150,200,300,400")
    )
    parser.add_argument("--stop-jvm-rss-mb", type=float, default=1800.0)
    parser.add_argument("--stop-gate-p95-seconds", type=float, default=2.0)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--skip-primary", action="store_true")
    parser.add_argument("--skip-scaling", action="store_true")
    args = parser.parse_args()
    if args.warmups < 0 or args.repetitions < 1 or args.scaling_repetitions < 1:
        parser.error("warmups must be nonnegative and repetitions must be positive")
    out_dir = args.out_dir.resolve()
    if out_dir.exists() and any(out_dir.iterdir()):
        parser.error(f"output directory is not empty: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    config_path = args.config.resolve()
    config = load_config(config_path)
    if config.mode != "demo":
        parser.error("the overhead benchmark requires the deterministic demo config")

    run_rows: list[dict[str, Any]] = []
    gate_rows: list[dict[str, Any]] = []
    memory_rows: list[dict[str, Any]] = []

    if not args.skip_primary:
        conditions = ["uninstrumented", "python_shadow", "dejavu"]
        random_source = random.Random(args.seed)
        for phase, repetitions in (("warmup", args.warmups), ("measured", args.repetitions)):
            for repetition in range(1, repetitions + 1):
                order = list(conditions)
                random_source.shuffle(order)
                for condition in order:
                    meta = _metadata(
                        experiment="primary",
                        condition=condition,
                        phase=phase,
                        repetition=repetition,
                        evaluations=config.max_iterations,
                    )
                    if condition == "uninstrumented":
                        run, gates, memory = _run_uninstrumented(config, metadata=meta)
                    else:
                        run, gates, memory = _run_session(
                            config,
                            metadata=meta,
                            real_monitor=condition == "dejavu",
                            scaling=False,
                        )
                    run_rows.append(run)
                    gate_rows.extend(_decorate_rows(gates, meta))
                    memory_rows.extend(_decorate_rows(memory, meta))

    stopped_early: dict[str, Any] | None = None
    if not args.skip_scaling:
        for scale in args.scales:
            scaled_config = replace(
                config,
                max_iterations=scale,
                min_iterations=min(config.min_iterations, scale),
                shot_budget=(
                    scale
                    * len(config.hamiltonian.terms)
                    * config.shots_per_term
                ),
            )
            scale_runs: list[dict[str, Any]] = []
            scale_gates: list[dict[str, Any]] = []
            for repetition in range(1, args.scaling_repetitions + 1):
                meta = _metadata(
                    experiment="scaling",
                    condition="dejavu",
                    phase="measured",
                    repetition=repetition,
                    evaluations=scale,
                )
                run, gates, memory = _run_session(
                    scaled_config,
                    metadata=meta,
                    real_monitor=True,
                    scaling=True,
                )
                run_rows.append(run)
                decorated_gates = _decorate_rows(gates, meta)
                gate_rows.extend(decorated_gates)
                memory_rows.extend(_decorate_rows(memory, meta))
                scale_runs.append(run)
                scale_gates.extend(decorated_gates)
            jvm_peak = max(int(row["jvm_peak_rss_bytes"]) for row in scale_runs)
            p95 = _percentile(
                [float(row["latency_seconds"]) for row in scale_gates], 0.95
            )
            if jvm_peak > args.stop_jvm_rss_mb * 1024 * 1024:
                stopped_early = {
                    "after_evaluations": scale,
                    "reason": "jvm_rss_limit",
                    "observed_bytes": jvm_peak,
                    "limit_bytes": args.stop_jvm_rss_mb * 1024 * 1024,
                }
                break
            if p95 is not None and p95 > args.stop_gate_p95_seconds:
                stopped_early = {
                    "after_evaluations": scale,
                    "reason": "gate_p95_limit",
                    "observed_seconds": p95,
                    "limit_seconds": args.stop_gate_p95_seconds,
                }
                break

    _write_csv(out_dir / "runs.csv", RUN_FIELDS, run_rows)
    _write_csv(out_dir / "gate_latencies.csv", GATE_FIELDS, gate_rows)
    _write_csv(out_dir / "memory_samples.csv", MEMORY_FIELDS, memory_rows)
    environment = _environment(config_path, [sys.executable, *sys.argv])
    (out_dir / "environment.json").write_text(
        json.dumps(environment, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    primary_runs = [row for row in run_rows if row["experiment"] == "primary"]
    primary_gates = [row for row in gate_rows if row["experiment"] == "primary"]
    scaling_runs = [row for row in run_rows if row["experiment"] == "scaling"]
    scaling_gates = [row for row in gate_rows if row["experiment"] == "scaling"]
    summary = {
        "schema_version": 1,
        "created_utc": environment["created_utc"],
        "config": config.as_dict(),
        "primary": _primary_summary(primary_runs, primary_gates)
        if primary_runs
        else None,
        "scaling": _scaling_summary(scaling_runs, scaling_gates),
        "stopped_early": stopped_early,
        "raw_files": ["runs.csv", "gate_latencies.csv", "memory_samples.csv"],
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
