#!/usr/bin/env python3
"""Reconstruct and plot the manuscript's approved probabilistic experiment.

Read-only inputs: frozen configuration, saved Gaussian kernels, Storm log,
400 original compressed traces, and original comparison/analysis outputs.
No VQE execution, kernel fitting, Monte Carlo experiment, or new test is run.

Usage (from any directory):
    python3 plot_probabilistic_results.py [--workspace WORKSPACE] [--output DIR]

Dependencies: Python >= 3.10, NumPy, Matplotlib, pypdf (output verification).
The bootstrap reproduces the original SeedSequence([20260721, 99]), 5,000
resamples, and NumPy's linear percentile rule. All output stays in --output.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
from statistics import NormalDist
import sys
import tempfile

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "vqe-probabilistic-figure-mpl"))
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.legend_handler import HandlerTuple
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, MaxNLocator


EXPERIMENT = Path("2-stage verification (closed-loop)")
APPROVED = EXPERIMENT / "artifacts/approved-experiment"
MANUSCRIPT = Path("Formal_Verification_in_Hybrid_Quantum_Classical_Computing_Systems.pdf")
MODEL_COLOR = "#1AA7FF"      # Bright sky blue, shared by all Gaussian series
EMPIRICAL_COLOR = "#FF9826"  # Bright orange, shared by all empirical series
INK = "#262626"
# Single-column 2x2 layout: (a) over (b) on the left, (c) over (d) on the right.
WIDTH_IN, HEIGHT_IN = 3.5, 3.82
FONT = {"base": 7, "title": 7.5, "axis": 7, "tick": 7, "legend": 7, "value": 7}
INTERVAL_ALPHA = .22


def require(condition, message):
    if not condition:
        raise ValueError(message)


def near(actual, expected, tolerance=1e-12):
    require(abs(float(actual) - float(expected)) <= tolerance,
            f"Value mismatch: {actual!r} vs {expected!r}")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find_workspace(explicit):
    if explicit:
        root = Path(explicit).expanduser().resolve()
        require((root / APPROVED).is_dir(), "Approved experiment not found in --workspace")
        return root
    for parent in Path(__file__).resolve().parents:
        if (parent / APPROVED).is_dir():
            return parent
    raise FileNotFoundError("Use --workspace to identify the original project directory")


def wilson(successes, total):
    """Original two-sided 95% pointwise Wilson interval, including boundaries."""
    z = NormalDist().inv_cdf(0.975)
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return (0.0 if successes == 0 else max(0.0, center - radius),
            1.0 if successes == total else min(1.0, center + radius))


def holm_adjust(pvalues):
    """The manuscript's existing four-comparison, post-audit Holm procedure."""
    ordered = sorted(pvalues.items(), key=lambda item: item[1])
    result, running = {}, 0.0
    for rank, (name, p) in enumerate(ordered):
        running = max(running, min(1.0, (len(ordered) - rank) * p))
        result[name] = running
    return result


def normal_two_sided(z):
    return math.erfc(abs(z) / math.sqrt(2.0))


def reconstruct(workspace):
    """Extract original observations and reproduce previously adopted analyses."""
    run = workspace / APPROVED
    sources = {}

    def record(path, role):
        relative = str(path.relative_to(workspace))
        sources[relative] = {"sha256": sha256(path), "role": role}
        return path

    def read(relative, role):
        path = record(workspace / relative, role)
        return json.loads(path.read_text())

    cfg = read(APPROVED / "stage1/configuration.json", "Frozen experimental configuration")
    pre = read(APPROVED / "stage1/pre_execution.json", "Original pre-execution assurance record")
    seal = read(APPROVED / "stage1/pre_execution.seal.json", "SHA-256 seal of assurance record")
    q = read(APPROVED / "stage1/quantitative.json", "Saved iteration-level Gaussian CDF and model summaries")
    baseline = read(APPROVED / "stage2/baseline/results.json", "Original 400-run index and trace hashes")
    original = read(APPROVED / "comparison/verdict_agreement.json", "Original checkpoint counts and marginal bootstrap intervals")
    complete = read(APPROVED / "completion_audit.json", "Completion record and original result-file hashes")
    prior = read(EXPERIMENT / "paper/data/derived_results.json", "Previously adopted post-audit p-values and original figure data")

    require(cfg == pre["configuration"], "Configuration differs from original assurance record")
    canonical = json.dumps(cfg, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    require(digest == pre["configuration_digest"] == baseline["configuration_digest"], "Configuration hash mismatch")
    require(sha256(run / "stage1/pre_execution.json") == seal["sha256"] == baseline["pre_execution_digest"], "Assurance seal mismatch")
    require(sha256(run / "stage2/baseline/results.json") == complete["baseline_result_sha256"], "Original baseline index changed")
    require(sha256(run / "comparison/verdict_agreement.json") == complete["result_sha256"], "Original comparison changed")
    require(complete["status"] == "COMPLETE", "Experiment was not completed")
    require(baseline["started_at"] > pre["frozen_at"], "Baseline predates assurance record")
    require(cfg["runs"] == len(baseline["results"]) == 400, "Expected 400 original runs")
    require(cfg["maximum_updates"] == 50 and cfg["success_gap"] == 0.02, "Success definition or horizon changed")
    require(cfg["environment"] == "ideal-born-finite-shot", "Different execution environment")
    require(cfg["shots_per_group"] == 1024 and cfg["bootstrap_samples"] == 5000, "Sampling/bootstrap configuration changed")
    require(cfg["seed"] == 20260721 and cfg["candidate_order"] == ["current", "minus", "plus"], "Original seed/candidate configuration changed")
    require(cfg["measurement_groups"] == [["ZI", "ZZ"], ["YZ"], ["XX"]], "Measurement grouping changed")
    require(cfg["grid_size"] == 16 and cfg["initial_index"] == [3, 11, 6, 14], "Original grid/initial point changed")
    require(cfg["coordinate_schedule"] == [0, 1, 2, 3], "Coordinate schedule changed")
    shots_per_iteration = len(cfg["candidate_order"]) * len(cfg["measurement_groups"]) * cfg["shots_per_group"]
    require(shots_per_iteration == 9216, "Unexpected physical shots per iteration")
    K, n = cfg["maximum_updates"], cfg["runs"]

    kernel_path = record(run / "stage1/gaussian-kernels.npz", "Retained transition kernel and ideal-energy success mask")
    with np.load(kernel_path) as data:
        kernels, success = data["kernels"], data["success"]
    require(kernels.shape == (4, 3, 16, 16, 16, 16), "Unexpected kernel shape")
    require(np.all(np.isfinite(kernels)) and np.min(kernels) >= 0, "Invalid transition probabilities")
    require(np.max(np.abs(kernels.sum(axis=1) - 1)) < 1e-12, "Transition rows do not normalize")
    require(not success[tuple(cfg["initial_index"])], "Initial point unexpectedly satisfies success")

    # Propagate ONLY the retained transition probabilities. No circuit execution,
    # new transition-kernel computation, or stochastic simulation occurs here.
    mass = np.zeros(success.shape)
    mass[tuple(cfg["initial_index"])] = 1.0
    model_cdf = [float(mass[success].sum())]
    mass[success] = 0.0
    for update in range(K):
        coordinate = cfg["coordinate_schedule"][update % len(cfg["coordinate_schedule"]) ]
        p = kernels[coordinate]
        mass = mass * p[0] + np.roll(mass * p[1], -1, axis=coordinate) + np.roll(mass * p[2], 1, axis=coordinate)
        model_cdf.append(model_cdf[-1] + float(mass[success].sum()))
        mass[success] = 0.0
        near(model_cdf[-1] + float(mass.sum()), 1.0, 2e-12)
    model_cdf = np.asarray(model_cdf)
    require(np.allclose(model_cdf, q["success_cdf"], rtol=0, atol=1e-14), "Saved Gaussian CDF was not reproduced")

    # Read every event in all 400 original traces. Verify both the first hit in
    # the retained success set and the terminal summary; count physical shots.
    run_rows, times, seen_streams = [], [], set()
    for index, result in enumerate(baseline["results"]):
        require(result["run_id"] == f"baseline-{index:04d}" and result["injected_fault"] is None, "Unexpected run identity")
        require(result["seed_words"] == [cfg["seed"], 0, index], "Unexpected seed stream")
        seen_streams.add(tuple(result["seed_words"]))
        trace = record(run / result["trace"], "Original finite-shot execution trace")
        require(sha256(trace) == result["trace_sha256"], f"Trace hash mismatch: {trace}")
        terminal = None
        commits = measurements = physical_shots = evaluations = 0
        first_hit = None
        with gzip.open(trace, "rt") as handle:
            for sequence, line in enumerate(handle, start=1):
                event = json.loads(line)
                require(terminal is None, "Event occurs after terminal closure")
                require(event["seq"] == sequence and event["run_id"] == result["run_id"], "Trace event identity mismatch")
                require(event["configuration_digest"] == digest, "Event configuration mismatch")
                if event["type"] == "run_start":
                    require(event["seed_words"] == result["seed_words"] and event["index"] == cfg["initial_index"], "Run initialization differs")
                elif event["type"] == "measurement":
                    require(sum(event["counts"]) == event["shots"] == cfg["shots_per_group"], "Physical shot record mismatch")
                    physical_shots += event["shots"]
                    measurements += 1
                elif event["type"] == "evaluation":
                    evaluations += 1
                elif event["type"] == "optimizer_commit":
                    require(first_hit is None, "Execution continues after first success")
                    commits += 1
                    require(event["update"] == commits, "Commit index mismatch")
                    if success[tuple(event["index_after"])]:
                        first_hit = commits
                elif event["type"] == "terminal":
                    terminal = event
        require(terminal is not None and terminal["reason"] in ("success", "budget"), "Unexpected termination")
        require(terminal["updates"] == result["updates"] == commits, "Terminal update count mismatch")
        require(terminal["physical_shots"] == result["physical_shots"] == physical_shots == commits * shots_per_iteration, "Shot total mismatch")
        require(evaluations == 3 * commits and measurements == 9 * commits, "Incomplete evaluation/measurement records")
        t = commits if terminal["reason"] == "success" else None
        require(t == first_hit == result["success_step"], "First-success record mismatch")
        require(terminal["reason"] == result["terminal_reason"], "Termination label mismatch")
        if t is None:
            require(commits == K, "Non-success run did not exhaust the configured budget")
        times.append(-1 if t is None else t)
        run_rows.append({"run_id": result["run_id"], "seed_words": result["seed_words"],
                         "first_success_iteration": t, "terminal_reason": terminal["reason"],
                         "iterations_used": commits, "physical_shots": physical_shots})
    require(len(seen_streams) == n, "Duplicate seed stream")
    times = np.asarray(times, dtype=int)
    successful = times[times >= 0].astype(float)
    require(len(successful) == 366 and np.sum(times < 0) == 34, "Manuscript success/budget counts differ")

    k = np.arange(K + 1)
    counts = np.array([np.sum((times >= 0) & (times <= step)) for step in k], dtype=int)
    empirical = counts / n
    intervals = np.array([wilson(int(count), n) for count in counts])
    residual = 100 * (empirical - model_cdf)
    residual_interval = 100 * (intervals - model_cdf[:, None])
    model_first = np.diff(np.r_[0.0, model_cdf])
    require(np.min(model_first) >= -1e-14, "Non-monotone model first-passage distribution")
    model_mean = float(np.dot(k, model_first) / model_cdf[-1])
    near(model_mean, q["expected_updates_given_success"])

    storm_path = record(run / "stage1/storm.log", "Original Storm 1.13.0 bounded-reachability output")
    properties_path = record(run / "stage1/gaussian.props", "The five Storm bounded-success queries (no rewards)")
    storm_text = storm_path.read_text()
    storm_values = [float(value) for value in re.findall(r"Result \(for initial states\):\s*([-+0-9.eE]+)", storm_text)]
    require(len(storm_values) == len(cfg["checkpoints"]), "Unexpected Storm query count")
    require("Reward Models:  none" in storm_text, "Inspect changed Storm reward provenance")
    require(properties_path.read_text().count("P=?") == 5, "Unexpected property file")
    checkpoints, pvalues = [], {}
    for step, value in zip(cfg["checkpoints"], storm_values):
        near(value, q["storm"]["results"][str(step)], 1e-15)
        near(value, model_cdf[step], 1e-14)
        old = next(row for row in original["probability_comparison"] if row["update_bound"] == step)
        require(old["runtime_successes"] == counts[step] and old["runtime_runs"] == n, "Original checkpoint count mismatch")
        require(np.allclose(old["wilson_95"], intervals[step], rtol=0, atol=1e-14), "Original Wilson interval changed")
        row = {"k": step, "gaussian": float(model_cdf[step]), "storm": value,
               "empirical": float(empirical[step]), "successes": int(counts[step]), "n": n,
               "wilson_95": intervals[step].tolist(), "residual_pp": float(residual[step])}
        if 0 < value < 1:
            pvalues[f"P1@{step}"] = normal_two_sided((empirical[step] - value) / math.sqrt(value * (1 - value) / n))
        checkpoints.append(row)
    require(set(pvalues) == {"P1@30", "P1@40", "P1@50"}, "Changed statistical comparison family")

    # Reproduce the original bootstrap exactly, with the original integer seed
    # schedule and 366 successful observations. Budget paths are excluded.
    rng = np.random.default_rng(np.random.SeedSequence([cfg["seed"], 99]))
    bootstrap = successful[rng.integers(0, len(successful), size=(cfg["bootstrap_samples"], len(successful)))].mean(axis=1)
    bootstrap_ci = np.quantile(bootstrap, [0.025, 0.975], method="linear").tolist()
    empirical_mean = float(successful.mean())
    require(bootstrap_ci == original["conditional_means"][0]["bootstrap_95"], "Original bootstrap was not exactly reproduced")
    near(empirical_mean, original["conditional_means"][0]["runtime_mean"])
    se = float(successful.std(ddof=1) / math.sqrt(len(successful)))
    pvalues["P2"] = normal_two_sided((empirical_mean - model_mean) / se)
    adjusted = holm_adjust(pvalues)
    for name in pvalues:
        prior_row = prior["P2"] if name == "P2" else next(row for row in prior["probability_comparison"] if row["k"] == int(name[3:]))
        near(pvalues[name], prior_row["p_raw"])
        near(adjusted[name], prior_row["p_holm"])
    p2 = {"model_mean": model_mean, "empirical_mean": empirical_mean,
          "empirical_bootstrap_95": bootstrap_ci, "successful_runs": len(successful),
          "bootstrap_resamples": cfg["bootstrap_samples"], "bootstrap_seed_words": [cfg["seed"], 99],
          "p_raw": pvalues["P2"], "p_holm": adjusted["P2"],
          "model_outside_marginal_interval": not bootstrap_ci[0] <= model_mean <= bootstrap_ci[1]}
    p3 = {"model_mean": model_mean * shots_per_iteration,
          "empirical_mean": empirical_mean * shots_per_iteration,
          "empirical_bootstrap_95": [value * shots_per_iteration for value in bootstrap_ci],
          "shots_per_iteration": shots_per_iteration, "derived_from": "P2; not an independent test"}
    near(p3["model_mean"], q["expected_shots_given_success"], 1e-8)
    require(p3["empirical_bootstrap_95"] == original["conditional_means"][1]["bootstrap_95"], "Original shot bootstrap interval changed")
    near(p3["empirical_mean"], original["conditional_means"][1]["runtime_mean"], 1e-8)
    require(p2["model_outside_marginal_interval"] and p2["p_raw"] < .05 < p2["p_holm"], "Statistical qualifications changed")

    # Disjoint windows chosen at existing manuscript checkpoint boundaries.
    # They are descriptive aggregates of exact first hits, not inference from
    # sparse checkpoints. T=0 has zero probability for this initial point.
    grouped = []
    for lower, upper in [(1, 20), (21, 30), (31, 40), (41, 50)]:
        count = int(np.sum((times >= lower) & (times <= upper)))
        grouped.append({"category": f"{lower}-{upper}", "lower": lower, "upper": upper,
                        "model_probability": float(model_first[lower:upper + 1].sum()),
                        "empirical_count": count, "empirical_probability": count / n})
    grouped.append({"category": "No success by K=50", "lower": None, "upper": None,
                    "model_probability": float(1 - model_cdf[K]),
                    "empirical_count": int(np.sum(times < 0)), "empirical_probability": float(np.sum(times < 0) / n)})
    near(sum(row["model_probability"] for row in grouped), 1.0)
    near(sum(row["empirical_probability"] for row in grouped), 1.0)
    require(sum(row["empirical_count"] for row in grouped) == n, "First-success categories do not partition executions")

    # Numerical values reported in Table X / the task are validation targets,
    # never the source of computed observations, intervals, or plotted arrays.
    reported = {10: (0.00, 0.00), 20: (0.00, 0.00), 30: (38.39, 42.25), 40: (75.63, 76.75), 50: (92.80, 91.50)}
    for step, (model_percent, empirical_percent) in reported.items():
        near(100 * model_cdf[step], model_percent, 0.00501)
        near(100 * empirical[step], empirical_percent, 0.00501)
    for value, reported_value in zip(bootstrap_ci, [31.579, 32.995]):
        near(value, reported_value, 0.000501)
    near(model_mean, 33.111, .000501)
    near(empirical_mean, 32.290, .000501)
    near(p3["model_mean"], 305152.7, .0501)
    near(p3["empirical_mean"], 297581.1, .0501)
    for value, reported_value in zip(p3["empirical_bootstrap_95"], [291034.2, 304077.6]):
        near(value, reported_value, .0501)
    near(100 * intervals[K, 0], 88.36, .00501)
    near(100 * intervals[K, 1], 93.85, .00501)
    near(residual[K], -1.30, .00501)
    near(p2["p_raw"], .024, .000501)
    near(p2["p_holm"], .094, .000501)

    original_csv = record(workspace / EXPERIMENT / "paper/data/probability_figure_points.csv", "All 51 points underlying the original figure")
    original_points = list(csv.DictReader(original_csv.open()))
    require(len(original_points) == K + 1, "Original point count changed")
    for step, row in enumerate(original_points):
        for key, value in {"k": step, "model_probability": model_cdf[step], "empirical_probability": empirical[step],
                           "successes": counts[step], "n": n, "wilson_low": intervals[step, 0], "wilson_high": intervals[step, 1]}.items():
            near(float(row[key]), value, 1e-13)
    # The paper PDF is hashed for provenance only; it now lives in ~/Downloads rather than the workspace root.
    manuscript = MANUSCRIPT if (workspace / MANUSCRIPT).exists() else \
        Path(os.path.relpath(Path.home() / "Downloads" / MANUSCRIPT.name, workspace))
    provenance_files = [
        (manuscript, "Authoritative supplied manuscript; Table X, probabilistic evaluation and interpretation"),
        (EXPERIMENT / "paper/manuscript_review3/tables/probabilistic_results.tex", "Existing Table X-equivalent numerical rows"),
        (EXPERIMENT / "paper/scripts/figures/probability_comparison.py", "Original discrete CDF plotting conventions"),
        (EXPERIMENT / "paper/scripts/extract_results.py", "Original bootstrap and post-audit four-test implementation"),
        (EXPERIMENT / "audit/stats_recompute.py", "Existing statistical-method provenance; inspected, not executed"),
        (EXPERIMENT / "closed_loop/physics.py", "Gaussian kernel, ideal-energy predicate and first-passage semantics"),
        (EXPERIMENT / "closed_loop/comparison.py", "Original Wilson/bootstrap comparison methodology"),
        (EXPERIMENT / "closed_loop/execution.py", "Recorded finite-shot execution and stop-rule semantics"),
    ]
    for relative, role in provenance_files:
        record(workspace / relative, role)

    # A later merged-controller archive retains the same trajectories; do not
    # pool these re-gated records as an additional 400 independent observations.
    merged_path = workspace / EXPERIMENT / "artifacts/merged-model-01/stage2/baseline/results.json"
    if merged_path.exists():
        merged = json.loads(record(merged_path, "Later merged-controller rerun; provenance cross-check only, not pooled").read_text())["results"]
        fields = ["seed_words", "success_step", "terminal_reason", "updates", "physical_shots"]
        require(len(merged) == n and all(all(a[key] == b[key] for key in fields) for a, b in zip(merged, baseline["results"])), "Merged-model trajectories differ")

    rows = [{"k": int(step), "model_probability": float(model_cdf[step]), "empirical_probability": float(empirical[step]),
             "successes": int(counts[step]), "n": n, "wilson_low": float(intervals[step, 0]), "wilson_high": float(intervals[step, 1]),
             "residual_pp": float(residual[step]), "residual_low_pp": float(residual_interval[step, 0]),
             "residual_high_pp": float(residual_interval[step, 1]), "model_first_success_probability": float(model_first[step])} for step in k]
    statistics = {"configuration": cfg, "configuration_sha256": digest, "n": n, "successes": len(successful), "budget_exhausted": int(np.sum(times < 0)),
                  "checkpoints": checkpoints, "conditional_iterations": p2, "conditional_shots": p3,
                  "existing_post_audit_tests": {key: {"p_raw": pvalues[key], "p_holm": adjusted[key]} for key in pvalues},
                  "first_success_groups": grouped, "storm_propagation_max_difference": float(max(abs(value - model_cdf[step]) for step, value in zip(cfg["checkpoints"], storm_values))),
                  "first_success_source": "Exact original per-run records, cross-checked against every optimizer successor and retained success mask",
                  "intervals": "Pointwise 95% Wilson (a,b); original 95% percentile bootstrap, 5000 resamples (d). No simultaneous band.",
                  "resource_provenance": "Gaussian-kernel first-passage propagation. The saved Storm log contains reachability queries and no reward model.",
                  "conclusion_scope": "Statistical compatibility at the tested resolution under the existing post-audit four-comparison Holm analysis; no equivalence margin/test or certified approximation-error bound."}
    return rows, run_rows, statistics, sources


def configure_style():
    plt.rcParams.update({
        "font.family": "STIXGeneral", "mathtext.fontset": "stix", "font.size": FONT["base"],
        "axes.titlesize": FONT["title"], "axes.labelsize": FONT["axis"],
        "xtick.labelsize": FONT["tick"], "ytick.labelsize": FONT["tick"],
        "legend.fontsize": FONT["legend"], "axes.spines.top": False, "axes.spines.right": False,
        "axes.edgecolor": INK, "text.color": INK, "axes.labelcolor": INK,
        "xtick.color": INK, "ytick.color": INK, "axes.linewidth": .6,
        "xtick.major.width": .6, "ytick.major.width": .6, "xtick.major.size": 3, "ytick.major.size": 3,
        "lines.linewidth": 1.25, "pdf.fonttype": 42, "ps.fonttype": 42,
        "svg.fonttype": "none", "hatch.linewidth": .55,
        "savefig.facecolor": "white", "figure.facecolor": "white",
        "axes.formatter.useoffset": False,
    })


def make_figure(rows, statistics):
    configure_style()
    k = np.asarray([row["k"] for row in rows])
    model = 100 * np.asarray([row["model_probability"] for row in rows])
    empirical = 100 * np.asarray([row["empirical_probability"] for row in rows])
    low = 100 * np.asarray([row["wilson_low"] for row in rows])
    high = 100 * np.asarray([row["wilson_high"] for row in rows])
    delta = np.asarray([row["residual_pp"] for row in rows])
    delta_low = np.asarray([row["residual_low_pp"] for row in rows])
    delta_high = np.asarray([row["residual_high_pp"] for row in rows])
    points = statistics["checkpoints"]
    n = statistics["n"]
    K = statistics["configuration"]["maximum_updates"]

    fig = plt.figure(figsize=(WIDTH_IN, HEIGHT_IN))

    def place(left, top, width, height):
        """Axes from inches, with top measured down from the figure's top edge."""
        return fig.add_axes([left / WIDTH_IN, 1 - (top + height) / HEIGHT_IN, width / WIDTH_IN, height / HEIGHT_IN])

    left_x, left_w, right_x, right_w = .36, 1.2, 2.02, 1.4
    row1_top, row1_h, row2_top, row2_h = .44, 1.08, 2.24, 1.14
    title_x = (.03, 1.7)
    a = place(left_x, row1_top, left_w, row1_h)
    c = place(right_x, row1_top, right_w, row1_h)
    b = place(left_x, row2_top, left_w, row2_h)
    d = place(title_x[1], row2_top, right_x + right_w - title_x[1], 1.52)
    for ax, x, letter, title in [(a, title_x[0], "a", "Success probability comparison"), (c, title_x[1], "c", "First-success outcomes"),
                                  (b, title_x[0], "b", "Discrepancy comparison"), (d, title_x[1], "d", "Conditional resource consumption")]:
        top = row1_top if ax in (a, c) else row2_top
        fig.text(x / WIDTH_IN, 1 - (top - .06) / HEIGHT_IN, f"({letter})  {title}",
                 fontweight="bold", fontsize=FONT["title"], va="bottom")

    # One legend for both columns: each entry shows the series' line (a, b) and bar (c) glyphs.
    model_handles = (Line2D([], [], color=MODEL_COLOR, lw=1.4),
                     Patch(facecolor="white", edgecolor=MODEL_COLOR, hatch="///", linewidth=.7))
    empirical_handles = (Line2D([], [], color=EMPIRICAL_COLOR, lw=1.4, ls="--"),
                         Patch(facecolor=EMPIRICAL_COLOR, edgecolor=EMPIRICAL_COLOR))
    fig.legend([model_handles, empirical_handles], ["Gaussian DTMC", f"Empirical runs ($n={n}$)"],
               handler_map={tuple: HandlerTuple(ndivide=None, pad=.5)}, loc="upper center",
               bbox_to_anchor=(.5, 1 - .02 / HEIGHT_IN), ncol=2, frameon=False, fontsize=FONT["legend"],
               handlelength=2.6, handletextpad=.4, columnspacing=1.6, borderaxespad=0)

    a.fill_between(k, low, high, step="post", color=EMPIRICAL_COLOR, alpha=INTERVAL_ALPHA, lw=0)
    a.step(k, model, where="post", color=MODEL_COLOR, lw=1.2)
    a.step(k, empirical, where="post", color=EMPIRICAL_COLOR, lw=1.1, ls="--")
    a.plot([p["k"] for p in points], [100 * p["storm"] for p in points], ls="none", marker="D", ms=3,
           mfc="white", mec=INK, mew=.6, zorder=5, clip_on=False)
    a.plot(50, empirical[-1], marker="o", ms=2.6, color=EMPIRICAL_COLOR, clip_on=False, zorder=6)
    a.set(xlim=(0, 50), ylim=(-1, 101), xlabel="Optimizer iteration $k$", ylabel="Success probability (%)")
    a.set_xticks([0, 10, 20, 30, 40, 50])
    a.set_yticks([0, 25, 50, 75, 100])

    b.axhline(0, color=INK, lw=.6, zorder=2)
    b.fill_between(k, delta_low, delta_high, step="post", color=EMPIRICAL_COLOR, alpha=INTERVAL_ALPHA, lw=0)
    b.step(k, delta, where="post", color=EMPIRICAL_COLOR, lw=1.1, ls="--", zorder=3)
    b.plot(50, delta[-1], marker="o", ms=2.6, color=EMPIRICAL_COLOR, clip_on=False, zorder=4)
    b.set(xlim=(0, 50), ylim=(-6, 11), xlabel="Optimizer iteration $k$",
          ylabel="$\\Delta P(k)$ (percentage points)")
    b.set_xticks([0, 10, 20, 30, 40, 50])
    b.set_yticks([-5, 0, 5, 10])

    groups = statistics["first_success_groups"]
    # The no-success category sits slightly apart so its label clears "41-50".
    positions = np.array([0, 1, 2, 3, 4.15])
    model_mass = 100 * np.asarray([row["model_probability"] for row in groups])
    empirical_mass = 100 * np.asarray([row["empirical_probability"] for row in groups])
    width = .36
    c.bar(positions - width / 2, model_mass, width=width, facecolor="white", edgecolor=MODEL_COLOR,
          hatch="///", linewidth=.6, zorder=3)
    bars = c.bar(positions + width / 2, empirical_mass, width=width, color=EMPIRICAL_COLOR,
                 edgecolor=EMPIRICAL_COLOR, linewidth=.4, zorder=3)
    # Counts sit above the taller bar of each pair so they never overlap the hatched model bar.
    for bar, row, top in zip(bars, groups, np.maximum(model_mass, empirical_mass)):
        c.annotate(str(row["empirical_count"]), (bar.get_x() + bar.get_width() / 2, top),
                   xytext=(0, 1.5), textcoords="offset points", ha="center", va="bottom", fontsize=FONT["value"])
    c.set_xticks(positions, ["1-20", "21-30", "31-40", "41-50", "No\nsuccess\nby $K=50$"])
    c.tick_params(axis="x", labelsize=FONT["tick"], length=0, pad=3)
    c.set(xlim=(-.6, 4.72), ylim=(0, 70), ylabel="Outcome probability (%)", xlabel="First-success iteration window")
    c.set_yticks([0, 10, 20, 30, 40, 50, 60])
    c.axvline(3.575, color="#929292", lw=.5, ls=":")

    # Two aligned point/interval views of the same success-conditioned sample.
    # Shots are a deterministic rescaling of iterations, not an extra test.
    d.set_axis_off()
    d.text(0, 1, f"Success by $K={K}$ only ($n={statistics['successes']}$)",
           transform=d.transAxes, fontsize=FONT["value"], va="top")
    shots_per_iteration = statistics["conditional_shots"]["shots_per_iteration"]
    for key, bottom, label, multiplier, number_format in [
        ("conditional_iterations", .66, "Conditional mean iterations", 1, ".3f"),
        ("conditional_shots", .225, "Conditional mean shots", shots_per_iteration, ",.1f"),
    ]:
        resource_ax = d.inset_axes([.3, bottom, .69, .222])
        result = statistics[key]
        model_mean, mean = result["model_mean"], result["empirical_mean"]
        ci_low, ci_high = result["empirical_bootstrap_95"]
        resource_ax.vlines(model_mean, -.45, 1.15, color=MODEL_COLOR, lw=.6, ls=":", zorder=1)
        resource_ax.plot(model_mean, 1.15, marker="s", ms=3.4, color=MODEL_COLOR, ls="none", zorder=3)
        resource_ax.errorbar(mean, .15, xerr=np.asarray([[mean - ci_low], [ci_high - mean]]),
                             fmt="o", ms=3.2, color=EMPIRICAL_COLOR, elinewidth=1, capsize=2, capthick=.7, zorder=3)
        for value, ypos, offset in [(model_mean, 1.15, 3), (mean, .15, 3.5)]:
            resource_ax.annotate(format(value, number_format), (value, ypos), xytext=(0, offset),
                                 textcoords="offset points", ha="center", fontsize=FONT["value"])
        resource_ax.set(xlim=(31.2 * multiplier, 33.90 * multiplier), ylim=(-.45, 1.95), xlabel=label)
        resource_ax.set_yticks([1.15, .15], ["Gaussian", "Empirical"])
        if multiplier == 1:
            resource_ax.set_xticks([31.5, 32.5, 33.5])
        else:
            resource_ax.xaxis.set_major_locator(MaxNLocator(nbins=3, steps=[1, 2, 2.5, 5, 10]))
            resource_ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.0f}"))
        resource_ax.tick_params(axis="y", length=0, labelsize=FONT["tick"], pad=2)
        resource_ax.tick_params(axis="x", labelsize=FONT["tick"], pad=1.5, length=2)
        resource_ax.xaxis.label.set_size(FONT["axis"])
        resource_ax.xaxis.labelpad = 1.5
        for name in ["left", "top", "right"]:
            resource_ax.spines[name].set_visible(False)
    for ax in [a, b, c]:
        ax.tick_params(length=2, pad=2)
        ax.xaxis.labelpad = 2
        ax.yaxis.labelpad = 2
        ax.set_axisbelow(True)
        ax.grid(axis="y", color="#d8d8d8", lw=.4, alpha=.7)
    c.tick_params(axis="x", length=0)
    for label in c.get_xticklabels():
        label.set_linespacing(.95)
    fig.align_ylabels([a, b])
    return fig



def save_csv(path, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def verify_output(pdf, svg):
    """Verify exact print dimensions, embedded fonts, and vector-only graphics."""
    from pypdf import PdfReader
    page = PdfReader(pdf).pages[0]
    near(float(page.mediabox.width), WIDTH_IN * 72, 1e-7)
    near(float(page.mediabox.height), HEIGHT_IN * 72, 1e-7)
    resources = page["/Resources"].get_object()
    images = []

    def walk_xobjects(resource_dict):
        for name, reference in resource_dict.get("/XObject", {}).items():
            obj = reference.get_object()
            if obj.get("/Subtype") == "/Image":
                images.append(str(name))
            if "/Resources" in obj:
                walk_xobjects(obj["/Resources"].get_object())

    walk_xobjects(resources)
    require(not images, "Raster image objects found in figure PDF")
    svg_text = svg.read_text()
    require("<image" not in svg_text, "Raster image found in SVG")
    fonts = list(resources.get("/Font", {}).values())
    require(fonts, "No PDF fonts found")
    return {"pdf_width_inches": WIDTH_IN, "pdf_height_inches": HEIGHT_IN,
            "raster_images_in_pdf": len(images), "raster_images_in_svg": 0,
            "pdf_font_objects": len(fonts), "svg_text_preserved": "<text" in svg_text}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", help="Original project containing the approved experiment")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--dpi", type=int, default=600, help="High-resolution PNG export (default 600)")
    args = parser.parse_args()
    workspace = find_workspace(args.workspace)
    output = args.output.expanduser().resolve()
    # Protect original source trees from an accidental --output selection.
    require(output != workspace and not output.is_relative_to(workspace / EXPERIMENT), "Choose a separate output directory")
    output.mkdir(parents=True, exist_ok=True)
    data = output / "data"
    validation = output / "validation"
    data.mkdir(exist_ok=True)
    validation.mkdir(exist_ok=True)
    rows, runs, statistics, sources = reconstruct(workspace)
    save_csv(data / "iteration_results.csv", rows)
    save_csv(data / "grouped_first_success.csv", statistics["first_success_groups"])
    save_csv(data / "run_first_success.csv", runs)
    save_json(data / "verified_statistics.json", statistics)
    save_json(data / "source_manifest.json", {"workspace": str(workspace), "sources": sources})
    fig = make_figure(rows, statistics)
    base = output / "probabilistic-results-four-panel"
    fig.savefig(base.with_suffix(".pdf"), metadata={"Title": "Gaussian-DTMC predictions and empirical VQE executions", "Author": ""})
    fig.savefig(base.with_suffix(".svg"), metadata={"Title": "Gaussian-DTMC predictions and empirical VQE executions", "Creator": "Matplotlib"})
    fig.savefig(base.with_suffix(".png"), dpi=args.dpi)
    fig.savefig(validation / "print-size-100dpi.png", dpi=100)
    fig.savefig(validation / "inspection-150dpi.png", dpi=150)
    plt.close(fig)
    checks = verify_output(base.with_suffix(".pdf"), base.with_suffix(".svg"))
    checks.update({"status": "PASS", "trace_hashes_verified": 400, "unique_original_seed_streams": 400,
                   "exact_per_run_first_hits_verified": True, "raw_measurement_shot_totals_verified": True,
                   "saved_gaussian_kernel_repropagated": True, "iteration_points_checked_against_original_figure": len(rows),
                   "storm_reachability_queries_verified": len(statistics["checkpoints"]),
                   "original_bootstrap_endpoints_exactly_reproduced": True,
                   "reported_table_X_values_checked": True,
                   "original_post_audit_four_test_pvalues_reproduced": True,
                   "outcome_partition_counts": [row["empirical_count"] for row in statistics["first_success_groups"]],
                   "model_outcome_partition_sum": sum(row["model_probability"] for row in statistics["first_success_groups"]),
                   "empirical_outcome_partition_sum": sum(row["empirical_probability"] for row in statistics["first_success_groups"]),
                   "new_VQE_experiments": 0, "new_stochastic_model_experiments": 0,
                   "minimum_font_size_points": min(FONT.values()), "png_dpi": args.dpi,
                   "font_sizes_points": FONT,
                   "series_colors": {"Gaussian": MODEL_COLOR, "Empirical": EMPIRICAL_COLOR},
                   "legends_in_panels": [], "global_legend": True,
                   "conditional_resources_plotted": ["iterations", "physical shots"],
                   "empirical_labels_consistent": True,
                   "versions": {"python": sys.version.split()[0], "numpy": np.__version__, "matplotlib": matplotlib.__version__}})
    # Verify that every referenced original source still has its initial hash.
    for relative, entry in sources.items():
        require(sha256(workspace / relative) == entry["sha256"], f"Source changed during build: {relative}")
    checks["referenced_source_files_unchanged"] = len(sources)
    save_json(validation / "checks.json", checks)
    print(json.dumps({"figure": str(base), "checks": checks, "P2": statistics["conditional_iterations"]}, indent=2))


if __name__ == "__main__":
    main()
