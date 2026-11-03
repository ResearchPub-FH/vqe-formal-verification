#!/usr/bin/env python3
"""Execute Storm cost-reward queries on the unchanged audited Gaussian DTMC.

All new models, queries, logs and comparisons are written to --output. The
audited experiment is read-only. Requires Python 3, NumPy and the Storm CLI.

For T = first-success iteration and p = Pr(T <= K), the reward r(s)=1 in
non-success states and 0 in absorbing success states gives

    C = R=? [ C<=K ] = E[min(T,K)].

Consequently E[T | T<=K] = (C-K*(1-p))/p. This exact identity removes the
cost of budget-exhausted paths; it does not claim native conditional-reward
syntax. The shot reward is evaluated by a separate real Storm invocation.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time

import numpy as np


PROB_ATOL = 1e-12
ITERATION_ATOL = 1e-10
NUMBER = r"([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
RESULT = re.compile(
    r'Model checking property "([^\"]+)":.*?'
    r'Result \(for initial states\):\s*' + NUMBER, re.S
)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def close(actual, expected, atol, context):
    require(math.isfinite(actual) and math.isfinite(expected), context + ": non-finite")
    require(abs(actual - expected) <= atol,
            f"{context}: {actual:.17g} != {expected:.17g}; atol={atol}")


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, allow_nan=False) + "\n")


def labels_from(path):
    initial, success = [], set()
    for line in path.read_text().splitlines():
        parts = line.split()
        if parts and parts[0].isdigit():
            state = int(parts[0])
            if "init" in parts[1:]:
                initial.append(state)
            if "success" in parts[1:]:
                success.add(state)
    require(len(initial) == 1, "Expected exactly one initial state")
    return initial[0], success


def write_rewards(path, state_count, success_states, scale):
    # Storm's explicit state-reward format has one state/value pair per line.
    # Charge before each optimizer transition, never after success absorption.
    with path.open("w") as f:
        for state in range(state_count):
            f.write(f"{state} {0 if state in success_states else scale}\n")


def invoke(storm, transitions, labels, rewards, bounds, directory, unit):
    properties = directory / f"{unit}.props"
    lines = []
    for k in bounds:
        lines.extend([f'"P1_{k}": P=? [ F<={k} "success" ];',
                      f'"cost_{k}": R=? [ C<={k} ];'])
    properties.write_text("\n".join(lines) + "\n")
    command = [storm, "--explicit", str(transitions), str(labels),
               "--staterew", str(rewards), "--prop", str(properties),
               "--precision", "1e-12"]
    started = time.perf_counter()
    proc = subprocess.run(command, capture_output=True, text=True, timeout=600)
    elapsed = time.perf_counter() - started
    text = proc.stdout + proc.stderr
    logfile = directory / f"storm-{unit}.log"
    logfile.write_text(text)
    metadata = {"command": command, "exit_code": proc.returncode,
                "elapsed_seconds": elapsed, "log": str(logfile)}
    save(directory / f"storm-{unit}-command.json", metadata)
    require(proc.returncode == 0, f"Storm failed; inspect {logfile}")
    require("Reward Models:" in text and "Reward Models:  none" not in text,
            f"Storm did not load a reward model: {logfile}")
    require("ERROR" not in text, f"Storm reported an error: {logfile}")
    found = RESULT.findall(text)
    values = {name: float(value) for name, value in found}
    expected_names = {f"{name}_{k}" for k in bounds for name in ("P1", "cost")}
    require(len(found) == len(expected_names) and set(values) == expected_names,
            f"Missing, duplicate or unexpected Storm query result: {logfile}")
    metadata["results"] = values
    return metadata


def conditional(cost, probability, bound, scale):
    if probability == 0:
        return None
    return (cost - scale * bound * (1 - probability)) / probability


def toy_model(directory, masses, bound):
    """Construct exact finite chains with a declared first-success distribution."""
    directory.mkdir()
    success_states, rows = set(), []
    if masses == {0: 1.0}:
        rows = [(0, 0, 1.0)]
        success_states.add(0)
        state_count = 1
    else:
        require(0 not in masses, "Initial success toy must have probability one")
        next_state = 1
        for t, probability in sorted(masses.items()):
            require(1 <= t <= bound and probability > 0, "Invalid toy first hit")
            chain = list(range(next_state, next_state + t))
            next_state += t
            rows.append((0, chain[0], probability))
            rows.extend((a, b, 1.0) for a, b in zip(chain[:-1], chain[1:]))
            rows.append((chain[-1], chain[-1], 1.0))
            success_states.add(chain[-1])
        failure_probability = 1 - sum(masses.values())
        if failure_probability > 0:
            rows.extend([(0, next_state, failure_probability),
                         (next_state, next_state, 1.0)])
            next_state += 1
        state_count = next_state
    transitions, labels = directory / "model.tra", directory / "model.lab"
    transitions.write_text("dtmc\n" + "".join(
        f"{s} {t} {p:.17g}\n" for s, t, p in sorted(rows)))
    lab = ["#DECLARATION", "init success", "#END"]
    for state in range(state_count):
        tags = (["init"] if state == 0 else []) + (["success"] if state in success_states else [])
        if tags:
            lab.append(f"{state} {' '.join(tags)}")
    labels.write_text("\n".join(lab) + "\n")
    return transitions, labels, state_count, success_states


def check_reward_semantics(storm, directory, shots):
    directory.mkdir()
    cases = [("initial_success", {0: 1.0}),
             ("first_iteration_success", {1: 1.0}),
             ("success_at_bound", {50: 1.0}),
             ("ninety_percent_at_twenty", {20: .9}),
             ("mixed_first_success_times", {20: .3, 40: .6}),
             ("no_success", {})]
    checked = []
    for name, masses in cases:
        k = 50
        case_directory = directory / name
        tra, lab, states, success = toy_model(case_directory, masses, k)
        probability = sum(masses.values())
        numerator = sum(t * p for t, p in masses.items())
        expected_cost = numerator + k * (1 - probability)
        for unit, scale in [("iterations", 1), ("shots", shots)]:
            reward_file = case_directory / f"{unit}.rew"
            write_rewards(reward_file, states, success, scale)
            result = invoke(storm, tra, lab, reward_file, [k], case_directory, unit)
            p, cost = result["results"][f"P1_{k}"], result["results"][f"cost_{k}"]
            close(p, probability, PROB_ATOL, f"{name} {unit} probability")
            close(cost, scale * expected_cost, scale * ITERATION_ATOL,
                  f"{name} {unit} bounded reward")
            mean = conditional(cost, p, k, scale)
            if probability:
                close(mean, scale * numerator / probability, scale * ITERATION_ATOL,
                      f"{name} {unit} conditional mean")
            else:
                require(mean is None, "Zero-probability conditional mean must be undefined")
            checked.append({"case": name, "unit": unit, "status": "PASS",
                            "success_probability": p, "storm_cost": cost,
                            "conditional_mean": mean})
    return checked


def reconstruct_python(config, kernel_file, original):
    with np.load(kernel_file) as z:
        kernels, success = z["kernels"], z["success"]
    shape = (config["grid_size"],) * config["parameter_count"]
    require(success.shape == shape, "Success-mask shape differs from configuration")
    require(kernels.shape == (len(config["coordinate_schedule"]),
                              len(config["candidate_order"]), *shape),
            "Kernel shape differs from configuration")
    mass = np.zeros(shape)
    mass[tuple(config["initial_index"])] = 1
    cdf = [float(mass[success].sum())]
    mass[success] = 0
    for k in range(config["maximum_updates"]):
        coordinate = config["coordinate_schedule"][k % len(config["coordinate_schedule"])]
        p = kernels[coordinate]
        mass = mass * p[0] + np.roll(mass * p[1], -1, axis=coordinate) + np.roll(mass * p[2], 1, axis=coordinate)
        cdf.append(cdf[-1] + float(mass[success].sum()))
        mass[success] = 0
        close(cdf[-1] + float(mass.sum()), 1.0, 1e-12, "Python probability conservation")
    cdf = np.asarray(cdf)
    first = np.diff(np.r_[0., cdf])
    require(np.allclose(cdf, original["success_cdf"], rtol=0, atol=PROB_ATOL),
            "Reconstructed Python CDF differs from audited results")
    means = [None if p == 0 else float(np.dot(np.arange(k + 1), first[:k + 1]) / p)
             for k, p in enumerate(cdf)]
    costs = [float(np.dot(np.arange(k + 1), first[:k + 1]) + k * (1 - p))
             for k, p in enumerate(cdf)]
    close(means[-1], original["expected_updates_given_success"], ITERATION_ATOL,
          "Saved Python conditional iterations")
    close(costs[-1], original["expected_total_updates"], ITERATION_ATOL,
          "Saved Python all-run iterations")
    return cdf, means, costs, success


def inspect_transitions(path, state_count, success_states, expected_edges):
    counts = np.zeros(state_count, dtype=np.int64)
    row_sums = np.zeros(state_count)
    edges = 0
    with path.open() as f:
        require(next(f).strip() == "dtmc", "Expected explicit DTMC header")
        for line in f:
            source, target, value = line.split()
            source, target, value = int(source), int(target), float(value)
            require(0 <= source < state_count and 0 <= target < state_count,
                    "Transition references an unexpected state")
            require(math.isfinite(value) and value > 0, "Invalid transition probability")
            if source in success_states:
                require(source == target and value == 1, "Success state is not absorbing")
            counts[source] += 1
            row_sums[source] += value
            edges += 1
    require(np.all(counts > 0), "Some states have no transitions")
    require(np.max(np.abs(row_sums - 1)) < 1e-12, "Non-stochastic transition row")
    require(edges == expected_edges, "Transition count differs from saved model")
    require(all(counts[s] == 1 for s in success_states), "Invalid success self-loop")
    return {"states": state_count, "transitions": edges,
            "success_states": len(success_states),
            "maximum_row_sum_error": float(np.max(np.abs(row_sums - 1)))}


def report_text(result):
    primary = [r for r in result["comparisons"] if r["k"] == result["configuration"]["iteration_bound"]]
    lines = ["# Storm reward validation", "", f"Status: **{result['status']}**", "",
             "Executed Storm bounded cumulative-reward queries on the unchanged audited Gaussian DTMC.",
             "Both iteration and shot costs are evaluated by Storm in separate runs.", "",
             "## Primary comparison", "",
             "| Quantity | Storm-derived | Saved Python | Absolute difference |",
             "|---|---:|---:|---:|"]
    for row in primary:
        label = "Conditional mean " + row["unit"]
        lines.append(f"| {label} | {row['storm_conditional_mean']:.15g} | {row['saved_python_primary_mean']:.15g} | {row['absolute_difference_saved']:.6g} |")
    lines.extend(["", "## Reward and conditioning semantics", "",
                  "Let T be the first-success iteration and K the configured bound. Each non-success state has reward 1 (iterations) or S (shots), and absorbing success states have reward 0.",
                  "Storm computes `P=? [ F<=K \"success\" ]` and `R=? [ C<=K ]`.",
                  "The latter is the all-run bounded cost C = E[min(T,K)] (or S times it), including budget-exhausted paths.",
                  "The conditional mean is obtained from Storm outputs as `(C - scale*K*(1-p))/p`.",
                  "This follows from C = E[T*1(T<=K)] + K*Pr(T>K), with the same scale for shots.",
                  "Only scalar arithmetic is performed outside Storm to obtain the resource mean. Python propagation is used separately as the comparison reference.",
                  "This is not a claim that a native conditional-reward query was executed. Zero-probability conditional means are reported as undefined.", "",
                  "## Validation", "",
                  f"- {len(result['semantic_tests'])} analytic toy-model/unit checks passed, including initial success, first-step success, success exactly at the bound, mixed first-hit times, budget exhaustion and zero success probability.",
                  "- All original configured reachability checkpoints were rechecked; resource means were compared wherever bounded-success probability is nonzero.",
                  "- Both reward calculations agree with saved Python values and a fresh propagation of the retained kernel within the declared numerical tolerances.",
                  "- Absorbing success states, stochastic transition rows and exported state labels were checked before attaching rewards.",
                  "- SHA-256 checks confirm every referenced original input stayed unchanged.", "",
                  "## Scope and provenance", "",
                  f"- Current verification tool: `{result['storm_version']}`.",
                  f"- Original probability log: `{result['original_storm_version']}`. The newly executed queries are supplementary results, not part of that earlier run.",
                  "- This checks agreement of calculations on the same Gaussian abstraction; it does not measure Gaussian approximation error or add empirical VQE runs.",
                  "- Manuscript, figures, empirical traces, original implementation and original verifier outputs were not edited.",
                  "- Raw logs, commands, reward files and query files are retained beside this report.", "",
                  "## References", "",
                  "- Storm reward semantics: https://www.stormchecker.org/documentation/background/properties.html",
                  "- Explicit model/reward input: https://www.stormchecker.org/documentation/usage/running-storm.html", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "run")
    parser.add_argument("--storm", default=shutil.which("storm"))
    args = parser.parse_args()
    require(args.storm is not None, "Storm CLI unavailable; provide --storm")
    workspace, output = args.workspace.resolve(), args.output.resolve()
    experiment = workspace / "2-stage verification (closed-loop)" / "artifacts" / "approved-experiment"
    require(not output.is_relative_to(experiment), "Output must be outside original experiment")
    output.mkdir(parents=True, exist_ok=False)
    stage1 = experiment / "stage1"
    inputs = [stage1 / name for name in ["configuration.json", "quantitative.json", "gaussian-kernels.npz",
              "gaussian.tra", "gaussian.lab", "gaussian.props", "storm.log", "pre_execution.json"]]
    physics = workspace / "2-stage verification (closed-loop)" / "closed_loop" / "physics.py"
    inputs.append(physics)
    before = {str(p): sha256(p) for p in inputs}
    save(output / "input_hashes_before.json", before)
    config = json.loads((stage1 / "configuration.json").read_text())
    original = json.loads((stage1 / "quantitative.json").read_text())
    shots = len(config["candidate_order"]) * len(config["measurement_groups"]) * config["shots_per_group"]
    bound = config["maximum_updates"]
    bounds = sorted(set(config["checkpoints"]) | {bound})
    print("Checking reward counting and conditioning on analytic toy DTMCs...", flush=True)
    semantic_tests = check_reward_semantics(args.storm, output / "semantic-tests", shots)
    print("Reconstructing the original Python first-success calculation...", flush=True)
    cdf, means, costs, success_mask = reconstruct_python(config, stage1 / "gaussian-kernels.npz", original)
    initial, success_states = labels_from(stage1 / "gaussian.lab")
    expected_success = set(np.flatnonzero(np.tile(success_mask.ravel(), len(config["coordinate_schedule"])) ).tolist())
    require(success_states == expected_success, "Exported success labels differ from retained mask")
    require(initial == int(np.ravel_multi_index(config["initial_index"], success_mask.shape)),
            "Exported initial state differs from configuration")
    model = inspect_transitions(stage1 / "gaussian.tra", original["dtmc_states"], success_states, original["transitions"])
    runs, comparisons = {}, []
    for unit, scale, saved_key in [("iterations", 1, "expected_updates_given_success"),
                                   ("shots", shots, "expected_shots_given_success")]:
        print(f"Running Storm cumulative {unit} rewards at K={bounds}...", flush=True)
        reward_file = output / f"{unit}.rew"
        write_rewards(reward_file, model["states"], success_states, scale)
        run = invoke(args.storm, stage1 / "gaussian.tra", stage1 / "gaussian.lab", reward_file,
                     bounds, output, unit)
        runs[unit] = run
        for k in bounds:
            p, cost = run["results"][f"P1_{k}"], run["results"][f"cost_{k}"]
            close(p, float(cdf[k]), PROB_ATOL, f"K={k} {unit} probability")
            close(p, original["storm"]["results"][str(k)], PROB_ATOL,
                  f"K={k} {unit} original Storm probability")
            close(cost, scale * costs[k], scale * ITERATION_ATOL, f"K={k} {unit} cumulative cost")
            mean = conditional(cost, p, k, scale)
            python_mean = None if means[k] is None else scale * means[k]
            difference = None if mean is None else abs(mean - python_mean)
            if mean is None:
                require(python_mean is None, "Zero-probability comparison mismatch")
            else:
                close(mean, python_mean, scale * ITERATION_ATOL, f"K={k} {unit} conditional mean")
            row = {"k": k, "unit": unit, "success_probability": p,
                   "storm_all_run_cost": cost, "python_all_run_cost": scale * costs[k],
                   "budget_exhausted_cost_contribution": scale * k * (1 - p),
                   "storm_success_weighted_cost": cost - scale * k * (1 - p),
                   "storm_conditional_mean": mean, "recomputed_python_conditional_mean": python_mean,
                   "absolute_difference_recomputed": difference, "status": "PASS"}
            if k == bound:
                saved_mean = original[saved_key]
                close(mean, saved_mean, scale * ITERATION_ATOL, f"Saved primary {unit} mean")
                row.update(saved_python_primary_mean=saved_mean,
                           absolute_difference_saved=abs(mean - saved_mean))
            comparisons.append(row)
    for k in bounds:
        close(runs["shots"]["results"][f"cost_{k}"],
              shots * runs["iterations"]["results"][f"cost_{k}"], shots * ITERATION_ATOL,
              f"K={k} independently queried shot/iteration scaling")
    after = {str(p): sha256(p) for p in inputs}
    save(output / "input_hashes_after.json", after)
    require(before == after, "An original input changed while validation was running")
    version = subprocess.run([args.storm, "--version"], capture_output=True, text=True, check=True).stdout.splitlines()[0]
    original_version = (stage1 / "storm.log").read_text().splitlines()[0]
    result = {"status": "PASS", "created_utc": datetime.now(timezone.utc).isoformat(),
              "configuration": {"source": str(stage1 / "configuration.json"),
                                "name": config["name"], "iteration_bound": bound,
                                "checkpoints": bounds, "shots_per_iteration": shots},
              "storm_version": version, "original_storm_version": original_version,
              "python_version": platform.python_version(), "numpy_version": np.__version__,
              "tolerances": {"probability_absolute": PROB_ATOL,
                             "iterations_absolute": ITERATION_ATOL,
                             "shots_absolute": shots * ITERATION_ATOL},
              "model": model, "original_inputs_unchanged": before == after,
              "input_hashes": before, "script_sha256": sha256(Path(__file__)),
              "semantic_tests": semantic_tests, "storm_runs": runs, "comparisons": comparisons,
              "conditional_mean_method": "(Storm bounded cumulative cost - scale*K*(1-Storm success probability)) / Storm success probability",
              "reproduction": {"executable": sys.executable, "arguments": sys.argv}}
    save(output / "results.json", result)
    fields = list(dict.fromkeys(key for row in comparisons for key in row))
    with (output / "comparison.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(comparisons)
    (output / "REPORT.md").write_text(report_text(result))
    save(output / "manifest.json", {str(p.relative_to(output)): sha256(p)
                                     for p in sorted(output.rglob("*")) if p.is_file()})
    print(json.dumps({"status": result["status"], "primary_results":
                      [row for row in comparisons if row["k"] == bound],
                      "report": str(output / "REPORT.md")}, indent=2))


if __name__ == "__main__":
    main()
