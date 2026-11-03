from __future__ import annotations

import argparse
import json
from pathlib import Path

from .checker import check_trace
from .config import load_config
from .demo import run_demo
from .qiskit_runner import run_qiskit
from .report import Status
from .sampler_runner import SAMPLER_MODES, run_sampled_vqe
from .session import VerificationAbort


def _overrides(args: argparse.Namespace) -> dict[str, object]:
    return {
        "mode": getattr(args, "mode", None),
        "system": getattr(args, "system", None),
        "backend": getattr(args, "backend", None),
        "max_iterations": getattr(args, "maxiter", None),
        "shots_per_term": getattr(args, "shots", None),
        "shot_budget": getattr(args, "shot_budget", None),
        "convergence_tolerance": getattr(args, "convergence_tolerance", None),
        "min_iterations": getattr(args, "min_iterations", None),
        "convergence_patience": getattr(args, "convergence_patience", None),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vqe-dejavu",
        description="Three-level DejaVu runtime verification for VQE",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser("demo", help="run the deterministic H2 example")
    demo.add_argument("--config", type=Path, default=Path("configs/h2_demo.toml"))
    demo.add_argument("--output", type=Path, default=Path("artifacts/traces/h2_demo.jsonl"))
    demo.add_argument("--report", type=Path, default=Path("artifacts/reports/h2_demo.json"))
    demo.add_argument("--run-id", default="h2-three-level-demo")
    demo.add_argument(
        "--mode", choices=["demo", "qiskit-statevector", "qiskit-runtime"]
    )
    demo.add_argument("--system")
    demo.add_argument("--backend")
    demo.add_argument("--maxiter", type=int)
    demo.add_argument("--shots", type=int)
    demo.add_argument("--shot-budget", type=int)
    demo.add_argument("--convergence-tolerance", type=float)
    demo.add_argument("--min-iterations", type=int)
    demo.add_argument("--convergence-patience", type=int)
    demo.add_argument(
        "--stop-on-convergence",
        action="store_true",
        help="accepted for parity with the Dafny runner; the demo always stops on convergence",
    )

    run = subparsers.add_parser(
        "run", help="execute the configured demo, statevector, or IBM Runtime profile"
    )
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--report", type=Path, required=True)
    run.add_argument("--run-id", required=True)
    run.add_argument(
        "--mode",
        choices=[
            "demo",
            "qiskit-statevector",
            "qiskit-runtime",
            "qiskit-statevector-sampler",
            "qiskit-runtime-sampler",
        ],
    )
    run.add_argument("--system")
    run.add_argument("--backend")
    run.add_argument("--maxiter", type=int)
    run.add_argument("--shots", type=int)
    run.add_argument("--shot-budget", type=int)
    run.add_argument("--convergence-tolerance", type=float)
    run.add_argument("--min-iterations", type=int)
    run.add_argument("--convergence-patience", type=int)
    run.add_argument("--stop-on-convergence", action="store_true")
    run.add_argument(
        "--evidence-output",
        type=Path,
        help="required explicit raw-evidence JSONL sidecar for SamplerV2 modes",
    )

    check = subparsers.add_parser("check", help="replay and verify an event JSONL trace")
    check.add_argument("trace", type=Path)
    check.add_argument("--config", type=Path, required=True)
    check.add_argument("--report", type=Path)
    check.add_argument(
        "--evidence",
        type=Path,
        help="explicit raw-evidence JSONL sidecar required by SamplerV2 traces",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command in {"demo", "run"}:
            config = load_config(args.config, **_overrides(args))
            if config.mode == "demo":
                report = run_demo(
                    config,
                    trace_path=args.output,
                    report_path=args.report,
                    run_id=args.run_id,
                )
            elif config.mode in SAMPLER_MODES:
                if args.evidence_output is None:
                    raise ValueError(
                        "SamplerV2 modes require --evidence-output PATH"
                    )
                report = run_sampled_vqe(
                    config,
                    trace_path=args.output,
                    report_path=args.report,
                    evidence_path=args.evidence_output,
                    run_id=args.run_id,
                )
            else:
                report = run_qiskit(
                    config,
                    trace_path=args.output,
                    report_path=args.report,
                    run_id=args.run_id,
                )
        else:
            config = load_config(args.config)
            report = check_trace(
                config,
                args.trace,
                report_path=args.report,
                evidence_path=args.evidence,
            )
    except (ValueError, VerificationAbort) as exc:
        print(f"ERROR: {exc}")
        return 2
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    return 0 if report.status == Status.PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
