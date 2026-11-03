"""Minimal ask/tell-shaped integration sketch.

Replace `backend_evaluate` and `optimizer_propose` with application code. The
ordering shows where the verification gates belong relative to side effects.
"""

from __future__ import annotations

import math
from pathlib import Path

from vqe_runtime import (
    RuntimeSession,
    TermObservation,
    TerminationReason,
    load_config,
)


ROOT = Path(__file__).resolve().parents[1]


def backend_evaluate(
    shots: int, iteration: int
) -> tuple[str, tuple[TermObservation, ...]]:
    counts = (750, 250, 500, 900)
    term_ids = ("t0", "t1", "t2", "t3")
    observations = tuple(
        TermObservation(term_id, 1.0 - 2.0 * ones / shots, shots, ones)
        for term_id, ones in zip(term_ids, counts)
    )
    return f"exampleBackendJob{iteration}", observations


def optimizer_propose(theta: tuple[float, ...]) -> tuple[float, ...]:
    return tuple(value * 0.9 for value in theta)


def main() -> None:
    config = load_config(ROOT / "configs/h2_demo.toml")
    theta = (0.1, -0.2)
    with RuntimeSession(
        config,
        run_id="instrumented-loop-example",
        trace_path=ROOT / "artifacts/traces/instrumented_loop.jsonl",
        report_path=ROOT / "artifacts/reports/instrumented_loop.json",
        overwrite=True,
    ) as session:
        for iteration in range(config.max_iterations):
            session.begin_iteration(theta)
            session.bind_parameters()
            session.authorize_job(f"submission{iteration}")

            job_id, terms = backend_evaluate(config.shots_per_term, iteration)
            session.mark_job_submitted(job_id)
            session.observe_terms(terms)
            session.seal_measurements()

            by_id = {item.term_id: item for item in terms}
            energy = math.fsum(
                term.coeff_int
                * by_id[term.term_id].expectation
                / config.hamiltonian.coeff_scale
                for term in config.hamiltonian.terms
            )
            session.aggregate_energy(energy)
            converged = session.check_convergence()
            verified_energy = session.authorize_objective_release()

            if converged:
                session.close_iteration()
                session.finish(TerminationReason.CONVERGED)
                break

            if iteration + 1 < config.max_iterations:
                next_theta = optimizer_propose(theta)  # side-effect-free preview
                session.authorize_optimizer_update(next_theta)
                # Commit the precomputed update atomically here.
                _ = verified_energy
                session.mark_optimizer_updated(next_theta)
            else:
                next_theta = theta
            session.close_iteration()
            theta = next_theta
        else:
            session.finish(TerminationReason.MAX_ITERATIONS)
        report = session.seal_run()
        print(report.as_dict()["status"])


if __name__ == "__main__":
    main()
