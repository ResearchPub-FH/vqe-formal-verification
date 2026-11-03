#!/usr/bin/env python3
"""Generate paper-ready Runtime VQE figures and verification summaries.

The script consumes one JSONL trace emitted by ``instrumented_vqe.py`` and
produces:

* an SVG energy-vs-iteration figure with a reference-energy line;
* a Markdown report summarizing per-iteration and cross-iteration checks.

It intentionally uses only the Python standard library plus the local
``trace_checker`` module, so it can run in the same environment as the checker.
"""

import argparse
import html
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Set

from trace_checker import (
    PROPERTY_NAMES,
    REQUIRED_FIELDS,
    Violation,
    check_record,
    check_trace,
    load_trace,
)


PROPERTY_DESCRIPTIONS = {
    "schema": "schema and finite values",
    "term_completeness": "all Pauli terms present exactly once",
    "expectation_domain": "expectations remain in [-1, 1]",
    "shot_consistency": "shot accounting and budget consistency",
    "energy_computation": "term energies and aggregate energy",
    "parameter_bounds": "optimizer parameters inside bounds",
    "convergence_check": "energy deltas and convergence flags",
    "layout_consistency": "ansatz and Hamiltonian layout match",
    "optimizer_freshness": "current theta and energy consumed",
    "trace_sequence": "iteration order and cumulative state",
}

PER_ITERATION_PROPERTIES = (
    "schema",
    "term_completeness",
    "expectation_domain",
    "shot_consistency",
    "energy_computation",
    "parameter_bounds",
    "convergence_check",
    "layout_consistency",
    "optimizer_freshness",
)

CROSS_ITERATION_PROPERTIES = (
    "trace_sequence",
    "shot_consistency",
    "convergence_check",
)


def _escape_text(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _fmt_float(value: Any, digits: int = 6) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if not math.isfinite(number):
        return "n/a"
    return f"{number:.{digits}g}"


def _markdown_escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _group_violations(violations: Iterable[Violation]) -> Dict[int, Set[str]]:
    grouped: Dict[int, Set[str]] = {}
    for violation in violations:
        grouped.setdefault(violation.line, set()).add(violation.property)
    return grouped


def _line_violations_for_records(
    records: Sequence[Dict[str, Any]], tolerance: float
) -> Dict[int, Set[str]]:
    grouped: Dict[int, Set[str]] = {}
    for index, record in enumerate(records, 1):
        for violation in check_record(record, index, tolerance):
            grouped.setdefault(index, set()).add(violation.property)
    return grouped


def _close(left: float, right: float, tolerance: float) -> bool:
    scale = max(1.0, abs(left), abs(right))
    return abs(left - right) <= tolerance * scale


def _is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _cross_iteration_violations(
    records: Sequence[Dict[str, Any]], tolerance: float
) -> List[Violation]:
    """Recompute only trace-level checks from ``trace_checker.check_trace``."""
    if not records:
        return [Violation("schema", 0, "trace contains no records")]

    violations: List[Violation] = []
    baseline = records[0]
    previous_budget = 0

    def add(property_name: str, line: int, condition: bool, message: str) -> None:
        if not condition:
            violations.append(Violation(property_name, line, message))

    for index, record in enumerate(records):
        line = index + 1
        if REQUIRED_FIELDS - set(record):
            continue
        add(
            "trace_sequence",
            line,
            record["iter"] == index,
            "iter must be contiguous and equal {}, found {!r}".format(
                index, record["iter"]
            ),
        )
        add(
            "trace_sequence",
            line,
            record["run_id"] == baseline["run_id"]
            and record["system"] == baseline["system"],
            "run_id and system must remain constant across a trace",
        )
        add(
            "trace_sequence",
            line,
            record["schema_version"] == baseline["schema_version"]
            and record["expected_term_count"] == baseline["expected_term_count"]
            and record["shot_budget"] == baseline["shot_budget"],
            "schema, Hamiltonian term count, and shot budget must remain constant",
        )
        add(
            "trace_sequence",
            line,
            record["parameter_count"] == baseline["parameter_count"]
            and record["max_iterations"] == baseline["max_iterations"]
            and record["min_iterations"] == baseline["min_iterations"]
            and record["convergence_patience"] == baseline["convergence_patience"]
            and _close(
                float(record["convergence_tolerance"]),
                float(baseline["convergence_tolerance"]),
                tolerance,
            ),
            "parameter count, max_iterations, convergence tolerance, and convergence policy must remain constant",
        )

        shots = record["shots"]
        if isinstance(shots, list) and all(type(value) is int and value >= 0 for value in shots):
            expected_budget = previous_budget + sum(shots)
            add(
                "shot_consistency",
                line,
                record["budget_used"] == expected_budget,
                "budget_used must equal cumulative shots {}, found {!r}".format(
                    expected_budget, record["budget_used"]
                ),
            )
            previous_budget = expected_budget

        if index == 0:
            add(
                "convergence_check",
                line,
                record["stable_delta_count"] == 0,
                "first record must use stable_delta_count 0",
            )
            continue

        previous = records[index - 1]
        if REQUIRED_FIELDS - set(previous):
            continue
        add(
            "convergence_check",
            line,
            record["previous_energy_available"] is True
            and _is_finite_number(previous.get("reported_energy"))
            and _close(
                float(record["previous_energy"]),
                float(previous["reported_energy"]),
                tolerance,
            ),
            "previous_energy must equal the prior record's reported_energy",
        )
        expected_stable_count = (
            int(previous["stable_delta_count"]) + 1
            if record["delta_within_tolerance"]
            else 0
        )
        add(
            "convergence_check",
            line,
            record["stable_delta_count"] == expected_stable_count,
            "stable_delta_count must equal {}, found {!r}".format(
                expected_stable_count, record["stable_delta_count"]
            ),
        )

    return violations


def _contract_status(properties: Sequence[str], failed: Set[str]) -> str:
    relevant_failures = [name for name in properties if name in failed]
    if not relevant_failures:
        return "PASS"
    return "FAIL: " + ", ".join(relevant_failures)


def _energy_values(records: Sequence[Dict[str, Any]]) -> List[float]:
    values: List[float] = []
    for record in records:
        values.append(float(record["reported_energy"]))
    return values


def _best_so_far(values: Sequence[float]) -> List[float]:
    best: List[float] = []
    current = math.inf
    for value in values:
        current = min(current, value)
        best.append(current)
    return best


def _nice_ticks(low: float, high: float, count: int = 6) -> List[float]:
    if not math.isfinite(low) or not math.isfinite(high):
        return [0.0]
    if low == high:
        return [low]
    step = (high - low) / max(1, count - 1)
    return [low + step * index for index in range(count)]


def render_energy_svg(
    records: Sequence[Dict[str, Any]],
    *,
    title: str,
    include_best_so_far: bool,
) -> str:
    if not records:
        raise ValueError("cannot render an empty trace")

    energies = _energy_values(records)
    reference = records[0].get("reference_ground_energy")
    reference_value = float(reference) if reference is not None else None
    best = _best_so_far(energies)

    all_y = list(energies)
    if include_best_so_far:
        all_y.extend(best)
    if reference_value is not None:
        all_y.append(reference_value)
    y_min = min(all_y)
    y_max = max(all_y)
    padding = max(0.05, 0.12 * (y_max - y_min if y_max != y_min else 1.0))
    y_min -= padding
    y_max += padding

    width = 1200
    height = 760
    left = 125
    right = 80
    top = 115
    bottom = 170
    plot_w = width - left - right
    plot_h = height - top - bottom

    def x_for(index: int) -> float:
        if len(records) == 1:
            return left + plot_w / 2.0
        return left + plot_w * index / (len(records) - 1)

    def y_for(value: float) -> float:
        return top + (y_max - value) * plot_h / (y_max - y_min)

    def polyline(values: Sequence[float]) -> str:
        return " ".join(
            f"{x_for(index):.3f},{y_for(value):.3f}"
            for index, value in enumerate(values)
        )

    ticks = _nice_ticks(y_min, y_max)
    tick_count = min(8, len(records))
    if len(records) <= tick_count:
        x_ticks = list(range(len(records)))
    else:
        x_ticks = sorted(
            {
                round(index * (len(records) - 1) / (tick_count - 1))
                for index in range(tick_count)
            }
        )

    lines: List[str] = [
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<style>",
        ".title{font:700 30px -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;fill:#152145}",
        ".axis{stroke:#7b7f89;stroke-width:1.7}",
        ".grid{stroke:#dfe5f0;stroke-width:1}",
        ".tick{font:500 23px -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;fill:#586278}",
        ".label{font:600 20px -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;fill:#586278}",
        ".legend{font:600 22px -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;fill:#586278}",
        ".energy{fill:none;stroke:#18275b;stroke-width:7;stroke-linecap:round;stroke-linejoin:round}",
        ".best{fill:none;stroke:#7b61ff;stroke-width:4;stroke-dasharray:10 9;stroke-linecap:round;stroke-linejoin:round}",
        ".reference{fill:none;stroke:#0fa37f;stroke-width:6;stroke-linecap:round;stroke-linejoin:round}",
        "</style>",
        '<rect x="28" y="28" width="1144" height="704" fill="white" stroke="#bfd0ef" stroke-width="2"/>',
        f'<text class="title" x="78" y="92">{_escape_text(title)}</text>',
    ]

    for tick in ticks:
        y = y_for(tick)
        lines.append(f'<line class="grid" x1="{left}" y1="{y:.3f}" x2="{width-right}" y2="{y:.3f}"/>')
        lines.append(
            f'<text class="tick" x="{left-22}" y="{y+8:.3f}" text-anchor="end">'
            f'{_escape_text(_fmt_float(tick, 4))}</text>'
        )

    axis_y = y_for(0.0) if y_min <= 0.0 <= y_max else top + plot_h
    lines.append(f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}"/>')
    lines.append(f'<line class="axis" x1="{left}" y1="{axis_y:.3f}" x2="{width-right}" y2="{axis_y:.3f}"/>')

    for index in x_ticks:
        x = x_for(index)
        lines.append(f'<line class="axis" x1="{x:.3f}" y1="{axis_y:.3f}" x2="{x:.3f}" y2="{axis_y+8:.3f}"/>')
        lines.append(
            f'<text class="tick" x="{x:.3f}" y="{top+plot_h+42}" text-anchor="middle">'
            f'iter {index}</text>'
        )

    if reference_value is not None:
        ref_points = [reference_value] * len(records)
        lines.append(f'<polyline class="reference" points="{polyline(ref_points)}"/>')
        for index, value in enumerate(ref_points):
            lines.append(f'<circle cx="{x_for(index):.3f}" cy="{y_for(value):.3f}" r="8" fill="#0fa37f"/>')

    if include_best_so_far:
        lines.append(f'<polyline class="best" points="{polyline(best)}"/>')

    lines.append(f'<polyline class="energy" points="{polyline(energies)}"/>')
    for index, value in enumerate(energies):
        lines.append(f'<circle cx="{x_for(index):.3f}" cy="{y_for(value):.3f}" r="10" fill="#18275b"/>')

    legend_y = height - 92
    legend_x = left + 190
    lines.append(f'<line class="energy" x1="{legend_x}" y1="{legend_y}" x2="{legend_x+45}" y2="{legend_y}"/>')
    lines.append(f'<circle cx="{legend_x+22}" cy="{legend_y}" r="8" fill="#18275b"/>')
    lines.append(f'<text class="legend" x="{legend_x+58}" y="{legend_y+8}">reported energy</text>')
    legend_x += 270
    if reference_value is not None:
        lines.append(f'<line class="reference" x1="{legend_x}" y1="{legend_y}" x2="{legend_x+45}" y2="{legend_y}"/>')
        lines.append(f'<circle cx="{legend_x+22}" cy="{legend_y}" r="8" fill="#0fa37f"/>')
        lines.append(f'<text class="legend" x="{legend_x+58}" y="{legend_y+8}">reference ground energy</text>')
        legend_x += 360
    if include_best_so_far:
        lines.append(f'<line class="best" x1="{legend_x}" y1="{legend_y}" x2="{legend_x+45}" y2="{legend_y}"/>')
        lines.append(f'<text class="legend" x="{legend_x+58}" y="{legend_y+8}">best so far</text>')

    lines.append("</svg>")
    return "\n".join(lines)


def render_markdown_report(
    trace_path: Path,
    records: Sequence[Dict[str, Any]],
    result_valid: bool,
    all_violations: Sequence[Violation],
    record_failures: Dict[int, Set[str]],
    cross_violations: Sequence[Violation],
    tolerance: float,
) -> str:
    if not records:
        return "# Qiskit Runtime VQE Verification Report\n\nTrace contains no records.\n"

    first = records[0]
    last = records[-1]
    energies = _energy_values(records)
    best_energy = min(energies)
    best_index = energies.index(best_energy)
    backend = first.get("run_id", "n/a")
    total_shots = last.get("budget_used", "n/a")
    reference = first.get("reference_ground_energy")
    violation_counts = Counter(violation.property for violation in all_violations)
    cross_failures = {violation.property for violation in cross_violations}
    per_iteration_failed_records = sum(
        1
        for failed in record_failures.values()
        if any(name in failed for name in PER_ITERATION_PROPERTIES)
    )

    lines: List[str] = [
        "# Qiskit Runtime VQE Verification Report",
        "",
        "## Execution Summary",
        "",
        "| Item | Value |",
        "|---|---:|",
        f"| Trace | `{_markdown_escape(trace_path)}` |",
        f"| Run id | `{_markdown_escape(backend)}` |",
        f"| System | `{_markdown_escape(first.get('system', 'n/a'))}` |",
        f"| Records / optimizer evaluations | {len(records)} |",
        f"| Hamiltonian Pauli terms | {first.get('expected_term_count', 'n/a')} |",
        f"| Parameters | {first.get('parameter_count', 'n/a')} |",
        f"| Estimator kind | `{_markdown_escape(first.get('estimator_kind', 'n/a'))}` |",
        f"| Shots used | {total_shots} |",
        f"| Initial energy | {_fmt_float(energies[0], 10)} Ha |",
        f"| Final energy | {_fmt_float(energies[-1], 10)} Ha |",
        f"| Best observed energy | {_fmt_float(best_energy, 10)} Ha at iter {best_index} |",
        f"| Reference ground energy | {_fmt_float(reference, 10)} Ha |",
        f"| Checker result | {'PASS' if result_valid else 'FAIL'} |",
        "",
        "## Runtime Verification Summary",
        "",
        "| Verification level | Scope | Result |",
        "|---|---|---|",
        "| Per iteration | schema, term completeness, expectation domain, shot consistency, energy computation, parameter bounds, convergence, layout, optimizer freshness | "
        + ("PASS" if per_iteration_failed_records == 0 else f"FAIL in {per_iteration_failed_records}/{len(records)} records")
        + " |",
        "| Cross iteration | contiguous iteration index, constant run/system/term count, cumulative shots, previous-energy linkage, stable convergence counter | "
        + ("PASS" if not cross_failures else "FAIL: " + ", ".join(sorted(cross_failures)))
        + " |",
        "| Full trace | all checker properties | "
        + ("PASS" if result_valid else f"FAIL: {len(all_violations)} violation(s)")
        + " |",
        "",
        "## Per-Iteration Verification",
        "",
        "| Iter | Energy (Ha) | Delta | Stable Count | Converged | Per-Iteration Checks |",
        "|---:|---:|---:|---:|---|---|",
    ]

    for index, record in enumerate(records, 1):
        failed = record_failures.get(index, set())
        lines.append(
            "| {iter} | {energy} | {delta} | {stable}/{patience} | {converged} | {status} |".format(
                iter=record.get("iter", index - 1),
                energy=_fmt_float(record.get("reported_energy"), 10),
                delta=_fmt_float(record.get("energy_delta"), 6),
                stable=record.get("stable_delta_count", "n/a"),
                patience=record.get("convergence_patience", "n/a"),
                converged=record.get("converged", "n/a"),
                status=_contract_status(PER_ITERATION_PROPERTIES, failed),
            )
        )

    lines.extend(
        [
            "",
            "## Contract Matrix",
            "",
            "| Contract | Result | Violations |",
            "|---|---|---:|",
        ]
    )
    for property_name in PROPERTY_NAMES:
        count = violation_counts[property_name]
        lines.append(
            "| {} | {} | {} |".format(
                PROPERTY_DESCRIPTIONS[property_name],
                "PASS" if count == 0 else "FAIL",
                count,
            )
        )

    lines.extend(
        [
            "",
            "## Reporting Note",
            "",
            "Each Qiskit Runtime optimizer evaluation submits one Estimator job containing "
            "one PUB with the full Hamiltonian observable list. The verifier checks the "
            "returned expectation vector after it is expanded into term-level trace "
            "fields. The verification result is trace consistency, not a proof of "
            "global VQE convergence or backend physical correctness.",
            "",
        ]
    )

    if all_violations:
        lines.extend(["## Violations", ""])
        for violation in all_violations:
            lines.append(
                "- line {} [{}] {}".format(
                    violation.line, violation.property, violation.message
                )
            )
        lines.append("")

    lines.append(f"Checker tolerance: `{tolerance}`.")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path, help="JSONL trace from instrumented_vqe.py")
    parser.add_argument(
        "--figure",
        type=Path,
        default=Path("paper_artifacts/runtime_energy.svg"),
        help="output SVG path",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("paper_artifacts/runtime_verification_report.md"),
        help="output Markdown report path",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="figure title; default is derived from the trace system",
    )
    parser.add_argument(
        "--best-so-far",
        action="store_true",
        help="include a dashed best-observed-energy line",
    )
    parser.add_argument("--tolerance", type=float, default=1e-9)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records, load_violations = load_trace(args.trace)
    if not records:
        raise SystemExit("trace has no records: {}".format(args.trace))

    trace_result = check_trace(args.trace, args.tolerance)
    record_failures = _line_violations_for_records(records, args.tolerance)
    cross_violations = _cross_iteration_violations(records, args.tolerance)
    for violation in load_violations:
        record_failures.setdefault(violation.line, set()).add(violation.property)

    system = records[0].get("system", "VQE")
    run_id = str(records[0].get("run_id", ""))
    execution_label = "Qiskit Runtime" if "qiskit-runtime" in run_id else "VQE"
    default_title = "{} {} - reported energy by iteration (Ha)".format(
        str(system).upper(), execution_label
    )
    figure = render_energy_svg(
        records,
        title=args.title or default_title,
        include_best_so_far=args.best_so_far,
    )
    args.figure.parent.mkdir(parents=True, exist_ok=True)
    args.figure.write_text(figure, encoding="utf-8")

    report = render_markdown_report(
        args.trace,
        records,
        trace_result.valid,
        trace_result.violations,
        record_failures,
        cross_violations,
        args.tolerance,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")

    print("wrote {}".format(args.figure))
    print("wrote {}".format(args.report))
    print(
        "{} {} ({} records, {} violation(s))".format(
            "PASS" if trace_result.valid else "FAIL",
            args.trace,
            trace_result.records,
            len(trace_result.violations),
        )
    )
    return 0 if trace_result.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
