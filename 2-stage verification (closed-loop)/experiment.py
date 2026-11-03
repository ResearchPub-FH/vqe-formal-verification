#!/usr/bin/env python3
"""Reproducible CLI for the two-stage VQE experiment."""
from __future__ import annotations

import argparse
from pathlib import Path

from closed_loop.common import ROOT, read_config
from closed_loop.pre_execution import run_pre_execution
from closed_loop.execution import run_baseline, run_faults
from closed_loop.comparison import compare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["all", "pre", "execute", "faults", "compare", "audit"])
    parser.add_argument("--config", type=Path, default=ROOT / "config/h2.json")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/primary")
    args = parser.parse_args()
    if args.command in ("all", "pre"):
        run_pre_execution(read_config(args.config), args.output)
    if args.command in ("all", "execute"):
        run_baseline(args.output)
    if args.command in ("all", "faults"):
        run_faults(args.output)
    if args.command in ("all", "compare", "audit"):
        result = compare(args.output, full_replay=True)
        print(f"Report: {args.output.resolve() / 'comparison/REPORT.md'}")
        print(f"Primary success: {result['successes']}/{result['baseline_runs']}; online/replay agreement: {result['online_replay_agreement']}")


if __name__ == "__main__":
    main()
