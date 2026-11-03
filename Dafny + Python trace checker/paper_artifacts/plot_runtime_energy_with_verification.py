#!/usr/bin/env python3
"""Draw a Runtime VQE energy figure with per-iteration verification status.

The figure is intended for paper use. It shows:

* reported VQE energy by optimizer iteration;
* reference ground energy, when present in the trace;
* one verification marker per iteration, derived from ``trace_checker``.

No best-so-far line is drawn.
"""

import argparse
import html
import math
from pathlib import Path
from typing import Any, Dict, List, Sequence, Set

from trace_checker import Violation, check_record, check_trace, load_trace


def escape_text(value: Any) -> str:
    return html.escape(str(value), quote=True)


def fmt_float(value: float, digits: int = 4) -> str:
    return f"{float(value):.{digits}g}"


def energy_values(records: Sequence[Dict[str, Any]]) -> List[float]:
    return [float(record["reported_energy"]) for record in records]


def nice_ticks(low: float, high: float, count: int = 6) -> List[float]:
    if low == high:
        return [low]
    step = (high - low) / max(1, count - 1)
    return [low + step * index for index in range(count)]


def violations_by_line(violations: Sequence[Violation]) -> Dict[int, Set[str]]:
    grouped: Dict[int, Set[str]] = {}
    for violation in violations:
        grouped.setdefault(violation.line, set()).add(violation.property)
    return grouped


def render_svg(
    records: Sequence[Dict[str, Any]],
    passed: Sequence[bool],
    title: str,
) -> str:
    if not records:
        raise ValueError("cannot render an empty trace")
    if len(records) != len(passed):
        raise ValueError("verification status length must match records")

    energies = energy_values(records)
    reference = records[0].get("reference_ground_energy")
    reference_value = float(reference) if reference is not None else None

    all_y = list(energies)
    if reference_value is not None:
        all_y.append(reference_value)
    y_min = min(all_y)
    y_max = max(all_y)
    padding = max(0.05, 0.12 * (y_max - y_min if y_max != y_min else 1.0))
    y_min -= padding
    y_max += padding

    width = 1200
    height = 820
    left = 125
    right = 80
    top = 115
    plot_bottom = 590
    verification_y = 655
    legend_y = 742
    plot_w = width - left - right
    plot_h = plot_bottom - top

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
        ".reference{fill:none;stroke:#0fa37f;stroke-width:6;stroke-linecap:round;stroke-linejoin:round}",
        ".verifyLine{stroke:#dfe5f0;stroke-width:2}",
        ".verifyText{font:700 17px -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;fill:white}",
        "</style>",
        '<rect x="28" y="28" width="1144" height="764" fill="white" stroke="#bfd0ef" stroke-width="2"/>',
        f'<text class="title" x="78" y="92">{escape_text(title)}</text>',
    ]

    for tick in nice_ticks(y_min, y_max):
        y = y_for(tick)
        lines.append(
            f'<line class="grid" x1="{left}" y1="{y:.3f}" x2="{width-right}" y2="{y:.3f}"/>'
        )
        lines.append(
            f'<text class="tick" x="{left-22}" y="{y+8:.3f}" text-anchor="end">'
            f'{escape_text(fmt_float(tick))}</text>'
        )

    axis_y = y_for(0.0) if y_min <= 0.0 <= y_max else plot_bottom
    lines.append(f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{plot_bottom}"/>')
    lines.append(f'<line class="axis" x1="{left}" y1="{axis_y:.3f}" x2="{width-right}" y2="{axis_y:.3f}"/>')

    for index in x_ticks:
        x = x_for(index)
        lines.append(
            f'<line class="axis" x1="{x:.3f}" y1="{axis_y:.3f}" x2="{x:.3f}" y2="{axis_y+8:.3f}"/>'
        )
        lines.append(
            f'<text class="tick" x="{x:.3f}" y="{plot_bottom+42}" text-anchor="middle">'
            f'iter {index}</text>'
        )

    if reference_value is not None:
        reference_points = [reference_value] * len(records)
        lines.append(f'<polyline class="reference" points="{polyline(reference_points)}"/>')
        for index, value in enumerate(reference_points):
            lines.append(
                f'<circle cx="{x_for(index):.3f}" cy="{y_for(value):.3f}" r="8" fill="#0fa37f"/>'
            )

    lines.append(f'<polyline class="energy" points="{polyline(energies)}"/>')
    for index, value in enumerate(energies):
        lines.append(
            f'<circle cx="{x_for(index):.3f}" cy="{y_for(value):.3f}" r="10" fill="#18275b"/>'
        )

    lines.append(
        f'<text class="label" x="{left-5}" y="{verification_y+7}" text-anchor="end">verified</text>'
    )
    lines.append(
        f'<line class="verifyLine" x1="{left}" y1="{verification_y}" x2="{width-right}" y2="{verification_y}"/>'
    )
    for index, ok in enumerate(passed):
        x = x_for(index)
        color = "#0fa37f" if ok else "#c23b3b"
        marker = "OK" if ok else "X"
        lines.append(f'<circle cx="{x:.3f}" cy="{verification_y}" r="13" fill="{color}"/>')
        lines.append(
            f'<text class="verifyText" x="{x:.3f}" y="{verification_y+6}" text-anchor="middle">'
            f'{marker}</text>'
        )

    legend_x = left + 170
    lines.append(f'<line class="energy" x1="{legend_x}" y1="{legend_y}" x2="{legend_x+45}" y2="{legend_y}"/>')
    lines.append(f'<circle cx="{legend_x+22}" cy="{legend_y}" r="8" fill="#18275b"/>')
    lines.append(f'<text class="legend" x="{legend_x+58}" y="{legend_y+8}">reported energy</text>')
    legend_x += 290
    if reference_value is not None:
        lines.append(f'<line class="reference" x1="{legend_x}" y1="{legend_y}" x2="{legend_x+45}" y2="{legend_y}"/>')
        lines.append(f'<circle cx="{legend_x+22}" cy="{legend_y}" r="8" fill="#0fa37f"/>')
        lines.append(f'<text class="legend" x="{legend_x+58}" y="{legend_y+8}">reference ground energy</text>')
        legend_x += 390
    lines.append(f'<circle cx="{legend_x+20}" cy="{legend_y}" r="10" fill="#0fa37f"/>')
    lines.append(f'<text class="verifyText" x="{legend_x+20}" y="{legend_y+6}" text-anchor="middle">OK</text>')
    lines.append(f'<text class="legend" x="{legend_x+42}" y="{legend_y+8}">iteration verification pass</text>')

    lines.append("</svg>")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path, help="JSONL trace from instrumented_vqe.py")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("paper_artifacts/h2_runtime_energy_verified.svg"),
        help="output SVG path",
    )
    parser.add_argument(
        "--title",
        default="H2 Qiskit Runtime - reported energy by iteration (Ha)",
        help="figure title",
    )
    parser.add_argument("--tolerance", type=float, default=1e-9)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records, load_violations = load_trace(args.trace)
    if load_violations:
        for violation in load_violations:
            print(
                "load violation line {} [{}] {}".format(
                    violation.line, violation.property, violation.message
                )
            )
    if not records:
        raise SystemExit("trace has no records: {}".format(args.trace))

    trace_result = check_trace(args.trace, args.tolerance)
    line_failures = violations_by_line(trace_result.violations)
    for index, record in enumerate(records, 1):
        for violation in check_record(record, index, args.tolerance):
            line_failures.setdefault(index, set()).add(violation.property)

    passed = [not line_failures.get(index) for index in range(1, len(records) + 1)]
    svg = render_svg(records, passed, args.title)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg, encoding="utf-8")

    passed_count = sum(1 for ok in passed if ok)
    print("wrote {}".format(args.output))
    print(
        "verification markers: {}/{} iterations pass; full trace {}".format(
            passed_count,
            len(passed),
            "PASS" if trace_result.valid else "FAIL",
        )
    )
    return 0 if trace_result.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
