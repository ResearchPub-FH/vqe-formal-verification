#!/usr/bin/env python3
"""Run the H2 P(50) shot-count sensitivity study.

The analytical series uses the Born-derived Gaussian optimizer kernel.  The
empirical series consists of direct adaptive executions on the same noisy
FakeJakarta snapshot used by the baseline artifact.  No empirical DTMC is
constructed.

The 1024-shot baseline trace is reused by default when the requested run count
matches the existing artifact.  Use ``--rerun-1024`` to execute it again.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

import h2_prism_fakebackend_workflow as h2


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = (
    ROOT / "artifacts/h2_vqe/additional_experiments/shot_sensitivity"
)
DEFAULT_BASELINE_TRACE = (
    ROOT / "artifacts/h2_vqe/layer4_empirical/fakebackend_runs.jsonl"
)
SHOT_COUNTS = (256, 512, 1024, 2048)
HORIZON = 50


def single_shot_moments():
    """Return exact grid means and pre-division single-shot variances."""
    shape = (h2.GRID_SIZE,) * 4
    means = np.empty(shape)
    single_shot_variances = np.empty(shape)
    for index in np.ndindex(shape):
        energy, probabilities = h2.state_data(index)
        means[index] = energy
        single_shot_variances[index] = sum(
            np.dot(probability, values * values)
            - np.dot(probability, values) ** 2
            for probability, values in zip(probabilities, h2.GROUP_VALUES)
        ) / 10000.0**2
    return means, single_shot_variances


def gaussian_p50(means, single_shot_variances, shots):
    """Evaluate the Gaussian DTMC property P(F<=50 success)."""
    variances = single_shot_variances / shots
    kernels = [
        h2.selection_kernel(means, variances, coordinate)
        for coordinate in range(4)
    ]
    success = means - h2.GROUND_ENERGY <= h2.CONVERGENCE_TOLERANCE
    curves = h2.propagate_analytical(kernels, success)
    return float(curves["success"][HORIZON])


def score_counts(counts, values, shots):
    if sum(counts.values()) != shots:
        raise RuntimeError(f"Expected {shots} shots, got {sum(counts.values())}")
    score = 0
    for bitstring, count in counts.items():
        bits = bitstring.replace(" ", "")
        if len(bits) != 2:
            raise RuntimeError(f"Expected a two-bit outcome, got {bitstring!r}")
        score += int(count) * int(values[int(bits, 2)])
    return score


def compact_record(record, shots):
    step = record.get("success_step")
    outcome = "success" if step is not None else "not_converged_by_50"
    raw_index = record.get("index", record.get("final_index"))
    if raw_index is None:
        raise ValueError("Empirical record has no final index")
    return {
        "run": int(record["run"]),
        "shots_per_group": shots,
        "outcome": outcome,
        "success_step": None if step is None else int(step),
        "updates": int(record.get("updates", step or HORIZON)),
        "final_index": [int(value) for value in raw_index],
    }


def read_records(path, shots, expected_runs):
    records = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                raw_record = json.loads(line)
                recorded_shots = raw_record.get("shots_per_group")
                if recorded_shots is not None and int(recorded_shots) != shots:
                    raise ValueError(
                        f"{path} records {recorded_shots} shots, expected {shots}"
                    )
                records.append(compact_record(raw_record, shots))
    if len(records) != expected_runs:
        raise ValueError(
            f"{path} contains {len(records)} runs; expected {expected_runs}"
        )
    return records


def write_records(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def execute_fakebackend(backend, parameters, circuits, shots, runs):
    """Run direct adaptive noisy executions for one shot configuration."""
    simulator_rng = np.random.default_rng(h2.SEED)
    records = [
        {
            "run": run + 1,
            "index": np.array(h2.INITIAL_INDEX, dtype=int),
            "success_step": None,
            "updates": 0,
        }
        for run in range(runs)
    ]

    for step in range(HORIZON):
        active = [record for record in records if record["success_step"] is None]
        if not active:
            break
        coordinate = step % 4
        work = []
        candidates_by_run = {}
        scores_by_run = {}
        for record in active:
            run_id = record["run"]
            candidates = h2.candidate_indices(record["index"], coordinate)
            candidates_by_run[run_id] = candidates
            scores_by_run[run_id] = [0, 0, 0]
            for candidate_number, candidate in enumerate(candidates):
                for group_number, circuit in enumerate(circuits):
                    work.append(
                        (
                            run_id,
                            candidate_number,
                            group_number,
                            h2.bind_circuit(circuit, parameters, candidate),
                        )
                    )

        for start in range(0, len(work), h2.MAX_CIRCUITS_PER_FAKE_JOB):
            chunk = work[start : start + h2.MAX_CIRCUITS_PER_FAKE_JOB]
            seed = int(simulator_rng.integers(1, np.iinfo(np.int32).max))
            result = backend.run(
                [entry[3] for entry in chunk],
                shots=shots,
                seed_simulator=seed,
            ).result()
            if not getattr(result, "success", True):
                raise RuntimeError("FakeBackend returned an unsuccessful job")
            for local_index, (
                run_id,
                candidate_number,
                group_number,
                _,
            ) in enumerate(chunk):
                scores_by_run[run_id][candidate_number] += score_counts(
                    result.get_counts(local_index),
                    h2.GROUP_VALUES[group_number],
                    shots,
                )

        for record in active:
            candidates = candidates_by_run[record["run"]]
            choice = int(np.argmin(scores_by_run[record["run"]]))
            record["index"] = candidates[choice]
            record["updates"] += 1
            exact_energy, _ = h2.state_data(tuple(record["index"]))
            if exact_energy - h2.GROUND_ENERGY <= h2.CONVERGENCE_TOLERANCE:
                record["success_step"] = step + 1

        successes = sum(record["success_step"] is not None for record in records)
        print(
            f"  shots={shots:4d}, update={step + 1:2d}/{HORIZON}: "
            f"success={successes}, running={runs - successes}",
            flush=True,
        )

    return [
        {
            "run": record["run"],
            "shots_per_group": shots,
            "outcome": (
                "success"
                if record["success_step"] is not None
                else "not_converged_by_50"
            ),
            "success_step": record["success_step"],
            "updates": record["updates"],
            "final_index": [int(value) for value in record["index"]],
        }
        for record in records
    ]


def empirical_summary(records):
    successes = sum(record["success_step"] is not None for record in records)
    runs = len(records)
    estimate = successes / runs
    low, high = h2.wilson_interval(successes, runs)
    return successes, estimate, low, high


def write_csv(path, rows):
    fieldnames = [
        "shots_per_group",
        "gaussian_p50",
        "empirical_successes",
        "empirical_runs",
        "empirical_p50",
        "empirical_ci95_low",
        "empirical_ci95_high",
        "absolute_difference",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_readme(output_dir, rows, runs, reused_baseline):
    table = [
        "| Shots/group | Gaussian P(50) | Empirical P(50) | 95% Wilson CI |",
        "|---:|---:|---:|---:|",
    ]
    for row in rows:
        table.append(
            "| {shots_per_group} | {gaussian_p50:.6f} | "
            "{empirical_p50:.6f} ({empirical_successes}/{empirical_runs}) | "
            "[{empirical_ci95_low:.6f}, {empirical_ci95_high:.6f}] |".format(
                **row
            )
        )
    reuse_note = (
        "The 1024-shot point reuses the existing 400-run baseline trace."
        if reused_baseline
        else "All four empirical points were executed by this study."
    )
    text = f"""# Shot-count sensitivity of P(50)

`P(50)` denotes `P(F<=50 \"success\")`.  Each shot count is the number of
shots allocated to each of the three commuting measurement groups for every
candidate evaluation.  The Gaussian series uses ideal Born moments and a
finite-shot Gaussian approximation.  The empirical series uses {runs} direct
adaptive executions on the noisy FakeJakarta snapshot.  {reuse_note}

{chr(10).join(table)}

The empirical intervals are two-sided 95% Wilson binomial intervals.  Compact
per-run traces are stored in `empirical_<shots>_runs.jsonl`; they contain the
terminal step and final parameter index but omit the large per-update histories.
`shot_sensitivity.csv` is the source for the PNG and SVG line charts.
"""
    (output_dir / "README.md").write_text(text, encoding="utf-8")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=h2.RUNS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--baseline-trace", type=Path, default=DEFAULT_BASELINE_TRACE)
    parser.add_argument(
        "--rerun-1024",
        action="store_true",
        help="Do not reuse the existing 1024-shot baseline trace.",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Rerun shot configurations even when compact traces already exist.",
    )
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    return args


def main():
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Computing Gaussian P(50) values...")
    means, single_shot_variances = single_shot_moments()
    gaussian = {
        shots: gaussian_p50(means, single_shot_variances, shots)
        for shots in SHOT_COUNTS
    }

    all_records = {}
    reused_baseline = False
    existing_configuration = output_dir / "configuration.json"
    if existing_configuration.exists() and not args.no_resume:
        try:
            reused_baseline = bool(
                json.loads(existing_configuration.read_text(encoding="utf-8")).get(
                    "baseline_1024_reused", False
                )
            )
        except (OSError, ValueError, TypeError):
            reused_baseline = False
    need_backend = False
    for shots in SHOT_COUNTS:
        compact_path = output_dir / f"empirical_{shots}_runs.jsonl"
        if compact_path.exists() and not args.no_resume:
            try:
                all_records[shots] = read_records(compact_path, shots, args.runs)
                print(f"Reusing {compact_path}")
                continue
            except ValueError as error:
                print(f"Cannot resume {compact_path}: {error}")
        if (
            shots == 1024
            and not args.rerun_1024
            and args.baseline_trace.exists()
        ):
            try:
                all_records[shots] = read_records(
                    args.baseline_trace, shots, args.runs
                )
                write_records(compact_path, all_records[shots])
                reused_baseline = True
                print(f"Reused baseline trace {args.baseline_trace}")
                continue
            except ValueError as error:
                print(f"Cannot reuse baseline trace: {error}")
        need_backend = True

    if need_backend:
        backend_root = output_dir / "backend_setup"
        backend, parameters, circuits, backend_metadata = (
            h2.build_fake_backend_circuits(backend_root)
        )
        (output_dir / "backend_metadata.json").write_text(
            json.dumps(backend_metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        for shots in SHOT_COUNTS:
            if shots in all_records:
                continue
            print(
                f"Running {args.runs} direct FakeJakarta executions at "
                f"{shots} shots/group..."
            )
            records = execute_fakebackend(
                backend, parameters, circuits, shots, args.runs
            )
            all_records[shots] = records
            write_records(output_dir / f"empirical_{shots}_runs.jsonl", records)

    rows = []
    for shots in SHOT_COUNTS:
        successes, estimate, low, high = empirical_summary(all_records[shots])
        rows.append(
            {
                "shots_per_group": shots,
                "gaussian_p50": gaussian[shots],
                "empirical_successes": successes,
                "empirical_runs": args.runs,
                "empirical_p50": estimate,
                "empirical_ci95_low": low,
                "empirical_ci95_high": high,
                "absolute_difference": abs(gaussian[shots] - estimate),
            }
        )
        print(
            f"shots={shots:4d}: Gaussian={gaussian[shots]:.6f}, "
            f"empirical={estimate:.6f} ({successes}/{args.runs})"
        )

    formatted_rows = [
        {
            key: (f"{value:.12g}" if isinstance(value, float) else value)
            for key, value in row.items()
        }
        for row in rows
    ]
    write_csv(output_dir / "shot_sensitivity.csv", formatted_rows)
    write_readme(output_dir, rows, args.runs, reused_baseline)
    configuration = {
        "shot_counts_per_group": SHOT_COUNTS,
        "empirical_runs_per_configuration": args.runs,
        "horizon": HORIZON,
        "property": 'P=? [ F<=50 "success" ]',
        "gaussian_semantics": "ideal Born-derived finite-shot Gaussian kernel",
        "empirical_semantics": "direct noisy FakeJakarta adaptive executions",
        "seed": h2.SEED,
        "baseline_1024_reused": reused_baseline,
    }
    (output_dir / "configuration.json").write_text(
        json.dumps(configuration, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
