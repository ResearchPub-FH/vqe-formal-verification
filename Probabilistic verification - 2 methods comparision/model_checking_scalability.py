#!/usr/bin/env python3
"""Measure reachable-DTMC construction and Storm checking as K increases.

K is the maximum number of optimizer updates.  For each value, this script
constructs a time-unrolled DTMC from the initial parameter index.  Only
nonzero-probability states reachable by depth K are emitted.  Successful paths
are merged into one absorbing success state and non-successful paths at depth K
enter one absorbing timeout state.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import statistics
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np

import h2_prism_fakebackend_workflow as h2


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = (
    ROOT / "artifacts/h2_vqe/additional_experiments/model_checking_scalability"
)
K_VALUES = (10, 20, 30, 40, 50)
CHUNK_SIZE = 50_000


def topology_and_kernels():
    """Build the fixed 1024-shot Gaussian kernel and flat successor maps."""
    _, _, kernels, success = h2.build_analytical_data()
    shape = (h2.GRID_SIZE,) * 4
    grid_states = h2.GRID_SIZE**4
    flat_grid = np.arange(grid_states, dtype=np.int64).reshape(shape)
    destinations = []
    flat_kernels = []
    for coordinate in range(4):
        destinations.append(
            (
                flat_grid.ravel(),
                np.roll(flat_grid, 1, axis=coordinate).ravel(),
                np.roll(flat_grid, -1, axis=coordinate).ravel(),
            )
        )
        flat_kernels.append(
            tuple(probabilities.ravel() for probabilities in kernels[coordinate])
        )
    initial_flat = int(np.ravel_multi_index(h2.INITIAL_INDEX, shape))
    return flat_kernels, destinations, success.ravel(), initial_flat, kernels


def build_levels(k, flat_kernels, destinations, success, initial_flat):
    """Return sorted reachable non-success grid indices at every depth."""
    if success[initial_flat]:
        return [np.empty(0, dtype=np.int64)], True
    levels = [np.asarray([initial_flat], dtype=np.int64)]
    success_reachable = False
    for depth in range(k):
        coordinate = depth % 4
        sources = levels[-1]
        next_parts = []
        for choice in range(3):
            probabilities = flat_kernels[coordinate][choice][sources]
            nonzero = probabilities > 0.0
            if not np.any(nonzero):
                continue
            child = destinations[coordinate][choice][sources[nonzero]]
            child_success = success[child]
            if np.any(child_success):
                success_reachable = True
            if np.any(~child_success):
                next_parts.append(child[~child_success])
        if next_parts:
            levels.append(np.unique(np.concatenate(next_parts)))
        else:
            levels.append(np.empty(0, dtype=np.int64))
    return levels, success_reachable


def write_lines(handle, lines):
    if lines:
        handle.write("".join(lines))


def export_unrolled_model(
    model_dir,
    k,
    flat_kernels,
    destinations,
    success,
    initial_flat,
):
    """Construct and export one reachable, time-unrolled Storm explicit DTMC."""
    started = time.perf_counter()
    levels, success_reachable = build_levels(
        k, flat_kernels, destinations, success, initial_flat
    )
    offsets = []
    total_active_states = 0
    for level in levels:
        offsets.append(total_active_states)
        total_active_states += len(level)

    success_id = total_active_states if success_reachable else None
    timeout_id = total_active_states + int(success_reachable)
    state_count = timeout_id + 1
    transition_count = 0

    model_dir.mkdir(parents=True, exist_ok=True)
    tra_path = model_dir / f"h2_gaussian_k{k}.tra"
    lab_path = model_dir / f"h2_gaussian_k{k}.lab"
    with tra_path.open("w", encoding="utf-8") as handle:
        handle.write("dtmc\n")
        for depth in range(k):
            coordinate = depth % 4
            sources = levels[depth]
            next_level = levels[depth + 1]
            next_offset = offsets[depth + 1]
            for start in range(0, len(sources), CHUNK_SIZE):
                stop = min(start + CHUNK_SIZE, len(sources))
                source_chunk = sources[start:stop]
                source_ids = offsets[depth] + np.arange(start, stop)
                success_probability = np.zeros(len(source_chunk))
                edge_sources = []
                edge_destinations = []
                edge_probabilities = []
                for choice in range(3):
                    probabilities = flat_kernels[coordinate][choice][source_chunk]
                    nonzero = probabilities > 0.0
                    child = destinations[coordinate][choice][source_chunk]
                    child_success = success[child] & nonzero
                    success_probability += np.where(
                        child_success, probabilities, 0.0
                    )
                    running = nonzero & ~success[child]
                    if not np.any(running):
                        continue
                    running_children = child[running]
                    positions = np.searchsorted(next_level, running_children)
                    if (
                        np.any(positions >= len(next_level))
                        or np.any(next_level[positions] != running_children)
                    ):
                        raise AssertionError("A reachable successor is missing")
                    destination_ids = next_offset + positions
                    edge_sources.append(source_ids[running])
                    edge_destinations.append(destination_ids)
                    edge_probabilities.append(probabilities[running])
                    transition_count += int(np.count_nonzero(running))

                reaches_success = success_probability > 0.0
                if np.any(reaches_success):
                    if success_id is None:
                        raise AssertionError("Missing success terminal state")
                    count = int(np.count_nonzero(reaches_success))
                    edge_sources.append(source_ids[reaches_success])
                    edge_destinations.append(
                        np.full(count, success_id, dtype=np.int64)
                    )
                    edge_probabilities.append(
                        success_probability[reaches_success]
                    )
                    transition_count += int(np.count_nonzero(reaches_success))
                if edge_sources:
                    all_sources = np.concatenate(edge_sources)
                    all_destinations = np.concatenate(edge_destinations)
                    all_probabilities = np.concatenate(edge_probabilities)
                    order = np.lexsort((all_destinations, all_sources))
                    lines = [
                        f"{int(all_sources[index])} "
                        f"{int(all_destinations[index])} "
                        f"{float(all_probabilities[index]):.17g}\n"
                        for index in order
                    ]
                    write_lines(handle, lines)

        terminal_level = levels[k]
        lines = [
            f"{offsets[k] + index} {timeout_id} 1\n"
            for index in range(len(terminal_level))
        ]
        write_lines(handle, lines)
        transition_count += len(terminal_level)
        if success_id is not None:
            handle.write(f"{success_id} {success_id} 1\n")
            transition_count += 1
        handle.write(f"{timeout_id} {timeout_id} 1\n")
        transition_count += 1

    with lab_path.open("w", encoding="utf-8") as handle:
        handle.write("#DECLARATION\ninit success timeout\n#END\n")
        if not success[initial_flat]:
            handle.write("0 init\n")
        if success_id is not None:
            handle.write(f"{success_id} success\n")
        handle.write(f"{timeout_id} timeout\n")

    construction_time = time.perf_counter() - started
    return {
        "tra_path": tra_path,
        "lab_path": lab_path,
        "state_count": state_count,
        "transition_count": transition_count,
        "construction_time_s": construction_time,
        "tra_bytes": tra_path.stat().st_size,
        "lab_bytes": lab_path.stat().st_size,
        "level_state_counts": [int(len(level)) for level in levels],
    }


def parse_storm_output(output):
    result_match = re.search(
        r"Result \(for initial states\):\s*([-+0-9.eE]+)", output
    )
    time_match = re.search(r"Time for model checking:\s*([0-9.]+)s", output)
    states_match = re.search(r"States:\s*([0-9]+)", output)
    transitions_match = re.search(r"Transitions:\s*([0-9]+)", output)
    if not all((result_match, time_match, states_match, transitions_match)):
        raise RuntimeError(f"Could not parse Storm output:\n{output}")
    return {
        "result": float(result_match.group(1)),
        "checking_time_s": float(time_match.group(1)),
        "state_count": int(states_match.group(1)),
        "transition_count": int(transitions_match.group(1)),
    }


def run_storm(storm, model, repetitions):
    command = [
        storm,
        "--explicit",
        str(model["tra_path"]),
        str(model["lab_path"]),
        "--prop",
        'P=? [ F "success" ]',
    ]
    measurements = []
    for repetition in range(repetitions):
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
        parsed = parse_storm_output(completed.stdout + completed.stderr)
        if parsed["state_count"] != model["state_count"]:
            raise AssertionError("Storm state count differs from exported count")
        if parsed["transition_count"] != model["transition_count"]:
            raise AssertionError("Storm transition count differs from exported count")
        measurements.append(parsed)
        print(
            f"    Storm repetition {repetition + 1}/{repetitions}: "
            f"check={parsed['checking_time_s']:.3f}s, "
            f"P={parsed['result']:.12g}",
            flush=True,
        )
    return {
        "result": measurements[-1]["result"],
        "checking_time_s": statistics.median(
            measurement["checking_time_s"] for measurement in measurements
        ),
        "checking_times_s": [
            measurement["checking_time_s"] for measurement in measurements
        ],
    }


def write_results(output_dir, rows, metadata):
    output_dir.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "K",
        "reachable_states",
        "transitions",
        "dtmc_construction_time_s",
        "storm_checking_time_s",
        "gaussian_pK",
        "storm_result",
        "absolute_difference",
        "explicit_model_bytes",
    ]
    with (output_dir / "scalability_results.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    table = [
        "| K | Reachable states | Transitions | DTMC construction | Storm checking time |",
        "|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        storm_seconds = float(row["storm_checking_time_s"])
        storm_text = (
            "<0.001 s" if storm_seconds == 0.0 else f"{storm_seconds:.3f} s"
        )
        table.append(
            f"| {row['K']} | {int(row['reachable_states']):,} | "
            f"{int(row['transitions']):,} | "
            f"{float(row['dtmc_construction_time_s']):.3f} s | "
            f"{storm_text} |"
        )
    text = f"""# Model-checking scalability versus K

Here `K` is the maximum number of optimizer updates.  Each row is a separately
constructed, time-unrolled 1024-shot Gaussian DTMC.  A state records both the
parameter-grid point and its update depth.  Only nonzero-probability states
reachable from the fixed initial index are emitted; successful paths share one
absorbing state, and paths still running at depth `K` share one absorbing
timeout state.

{chr(10).join(table)}

DTMC construction time covers reachable-state exploration and serialization to
Storm's explicit transition/label format.  It excludes the one-time,
K-independent calculation of the 65,536-state Born/Gaussian kernel.  Storm time
is the median of {metadata['storm_repetitions']} tool-reported model-checking
times and excludes Storm's explicit-model parsing/construction phase.

The checked unbounded property `P=? [ F \"success\" ]` on each truncated model
is equivalent to `P=? [ F<=K \"success\" ]` on the homogeneous DTMC.  Every
Storm result was compared with the independent NumPy propagation; the maximum
absolute difference was {metadata['maximum_probability_difference']:.3g}.
"""
    (output_dir / "README.md").write_text(text, encoding="utf-8")
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--k", type=int, action="append", dest="k_values")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--storm", default=shutil.which("storm"))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--keep-models",
        action="store_true",
        help="Retain the large explicit models below the output directory.",
    )
    args = parser.parse_args()
    args.k_values = sorted(set(args.k_values or K_VALUES))
    if any(k < 1 or k > h2.MAX_STEPS for k in args.k_values):
        parser.error(f"Every K must be in [1, {h2.MAX_STEPS}]")
    if args.repetitions < 1:
        parser.error("--repetitions must be positive")
    if not args.storm:
        parser.error("Storm was not found; pass its path with --storm")
    return args


def main():
    args = parse_args()
    print("Preparing the fixed 1024-shot Gaussian kernel...")
    (
        flat_kernels,
        destinations,
        success,
        initial_flat,
        kernels,
    ) = topology_and_kernels()
    curves = h2.propagate_analytical(kernels, success.reshape((h2.GRID_SIZE,) * 4))

    temporary = None
    if args.keep_models:
        models_root = args.output_dir.resolve() / "models"
        models_root.mkdir(parents=True, exist_ok=True)
    else:
        temporary = tempfile.TemporaryDirectory(prefix="h2_scalability_")
        models_root = Path(temporary.name)

    rows = []
    detailed = {}
    try:
        for k in args.k_values:
            print(f"Constructing reachable time-unrolled DTMC for K={k}...")
            model = export_unrolled_model(
                models_root / f"k{k}",
                k,
                flat_kernels,
                destinations,
                success,
                initial_flat,
            )
            print(
                f"  states={model['state_count']:,}, "
                f"transitions={model['transition_count']:,}, "
                f"construction={model['construction_time_s']:.3f}s"
            )
            storm_result = run_storm(args.storm, model, args.repetitions)
            reference = float(curves["success"][k])
            difference = abs(reference - storm_result["result"])
            if difference > 1e-9:
                raise AssertionError(
                    f"Storm P({k}) differs from propagation by {difference}"
                )
            row = {
                "K": k,
                "reachable_states": model["state_count"],
                "transitions": model["transition_count"],
                "dtmc_construction_time_s": f"{model['construction_time_s']:.9g}",
                "storm_checking_time_s": f"{storm_result['checking_time_s']:.9g}",
                "gaussian_pK": f"{reference:.12g}",
                "storm_result": f"{storm_result['result']:.12g}",
                "absolute_difference": f"{difference:.12g}",
                "explicit_model_bytes": model["tra_bytes"] + model["lab_bytes"],
            }
            rows.append(row)
            detailed[str(k)] = {
                "level_state_counts": model["level_state_counts"],
                "storm_checking_times_s": storm_result["checking_times_s"],
                "transition_bytes": model["tra_bytes"],
                "label_bytes": model["lab_bytes"],
            }
    finally:
        if temporary is not None:
            temporary.cleanup()

    version = subprocess.run(
        [args.storm, "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    version_match = re.search(r"Storm\s+([^\s]+)", version)
    metadata = {
        "K_values": args.k_values,
        "shots_per_group": h2.SHOTS_PER_GROUP,
        "grid_size_per_parameter": h2.GRID_SIZE,
        "storm_version": version_match.group(1) if version_match else version.strip(),
        "storm_repetitions": args.repetitions,
        "storm_time_statistic": "median tool-reported model-checking time",
        "kernel_precomputation_excluded_from_construction_time": True,
        "maximum_probability_difference": max(
            float(row["absolute_difference"]) for row in rows
        ),
        "models_retained": args.keep_models,
        "details": detailed,
    }
    write_results(args.output_dir.resolve(), rows, metadata)
    print(f"Wrote {args.output_dir.resolve() / 'scalability_results.csv'}")


if __name__ == "__main__":
    main()
