#!/usr/bin/env python3
"""Convert VQE trace-checking results into a paper-ready Markdown report."""

import argparse
from collections import defaultdict
from pathlib import Path
from typing import DefaultDict, Iterable, List

from trace_checker import PROPERTY_NAMES, TraceResult, check_paths


PROPERTY_DESCRIPTIONS = {
    "schema": "Trace schema and finite-value validity",
    "term_completeness": "All Hamiltonian terms occur exactly once",
    "expectation_domain": "Pauli expectations remain in [-1, 1]",
    "shot_consistency": "Shot counts, count normalization, and shot budget are consistent",
    "energy_computation": "Per-term energies, aggregation, hashes, and bounds are correct",
    "parameter_bounds": "Optimizer parameters remain inside declared bounds",
    "convergence_check": "Energy deltas and convergence flags are internally consistent",
    "layout_consistency": "Ansatz and Hamiltonian use the same layout",
    "optimizer_freshness": "Optimizer consumes current theta and energy",
    "trace_sequence": "Iterations and cumulative state progress consistently",
}


def _escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def render_report(results: Iterable[TraceResult], dafny_status: str) -> str:
    result_list = list(results)
    lines: List[str] = [
        "# VQE Numeric Verification Report",
        "",
        "Dafny static verification status: **{}**.".format(dafny_status),
        "",
        "The runtime checker validates the concrete assumptions consumed by the "
        "Dafny numeric and trace contracts.",
        "",
        "## Trace Summary",
        "",
        "| Trace | Records | Result | Violations |",
        "|---|---:|---|---:|",
    ]
    for result in result_list:
        lines.append(
            "| {} | {} | {} | {} |".format(
                _escape(result.path),
                result.records,
                "PASS" if result.valid else "FAIL",
                len(result.violations),
            )
        )

    lines.extend(
        [
            "",
            "## Contract Matrix",
            "",
            "| Trace | Contract | Result |",
            "|---|---|---|",
        ]
    )
    for result in result_list:
        failed = {violation.property for violation in result.violations}
        for property_name in PROPERTY_NAMES:
            lines.append(
                "| {} | {} | {} |".format(
                    _escape(result.path),
                    PROPERTY_DESCRIPTIONS[property_name],
                    "FAIL" if property_name in failed else "PASS",
                )
            )

    all_violations = [
        (result.path, violation)
        for result in result_list
        for violation in result.violations
    ]
    lines.extend(["", "## Findings", ""])
    if not all_violations:
        lines.append("No runtime contract violations were detected.")
        lines.append("")
    else:
        grouped: DefaultDict[str, List[str]] = defaultdict(list)
        for path, violation in all_violations:
            grouped[violation.property].append(
                "{} line {}: {}".format(path, violation.line, violation.message)
            )
        for property_name in PROPERTY_NAMES:
            if property_name not in grouped:
                continue
            lines.append("### {}".format(PROPERTY_DESCRIPTIONS[property_name]))
            lines.append("")
            for message in grouped[property_name]:
                lines.append("- {}".format(message))
            lines.append("")

    lines.extend(
        [
            "## Assurance Scope",
            "",
            "- Dafny proves deterministic kernels over exact real and integer models.",
            "- The runtime checker connects concrete JSONL records to those proof assumptions.",
            "- This artifact focuses on shot consistency, parameter bounds, convergence "
            "checks, and energy computation.",
            "- Shot noise, backend correctness, floating-point roundoff, and global VQE "
            "convergence require separate probabilistic or numerical analyses.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--tolerance", type=float, default=1e-9)
    parser.add_argument(
        "--dafny-status",
        choices=["verified", "failed", "not-run"],
        default="not-run",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results = check_paths(args.paths, args.tolerance)
    report = render_report(results, args.dafny_status)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report)
    return 0 if all(result.valid for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
