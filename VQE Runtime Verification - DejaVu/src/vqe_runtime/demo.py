from __future__ import annotations

import math
from pathlib import Path

from .config import RuntimeConfig
from .report import VerificationReport
from .session import (
    RuntimeSession,
    TermObservation,
    TerminationReason,
)


_COUNTS_ONES = {
    "t0": 750,  # expectation -0.5
    "t1": 250,  # expectation +0.5
    "t2": 500,  # expectation  0.0
    "t3": 900,  # expectation -0.8
}


def _demo_observations(config: RuntimeConfig) -> tuple[TermObservation, ...]:
    observations: list[TermObservation] = []
    for term in config.hamiltonian.terms:
        ones = _COUNTS_ONES.get(term.term_id, config.shots_per_term // 2)
        expectation = 1.0 - 2.0 * ones / config.shots_per_term
        observations.append(
            TermObservation(term.term_id, expectation, config.shots_per_term, ones)
        )
    return tuple(observations)


def _energy(config: RuntimeConfig, observations: tuple[TermObservation, ...]) -> float:
    by_id = {item.term_id: item for item in observations}
    return math.fsum(
        term.coeff_int
        * by_id[term.term_id].expectation
        / config.hamiltonian.coeff_scale
        for term in config.hamiltonian.terms
    )


def run_demo(
    config: RuntimeConfig,
    *,
    trace_path: str | Path,
    report_path: str | Path,
    run_id: str = "h2-three-level-demo",
) -> VerificationReport:
    if config.mode != "demo":
        raise ValueError("run_demo requires execution.mode = 'demo'")
    observations = _demo_observations(config)
    energy = _energy(config, observations)
    theta = (0.1, -0.2)
    with RuntimeSession(
        config,
        run_id=run_id,
        trace_path=trace_path,
        report_path=report_path,
        overwrite=True,
    ) as session:
        for iteration in range(config.max_iterations):
            session.begin_iteration(theta, evaluation_id=f"eval{iteration}")
            session.bind_parameters()
            session.authorize_job(f"submission{iteration}")
            session.mark_job_submitted(f"localJob{iteration}")
            session.observe_terms(observations)
            session.seal_measurements()
            session.aggregate_energy(energy)
            converged = session.check_convergence()
            session.authorize_objective_release()
            if not converged and iteration + 1 < config.max_iterations:
                next_theta = (theta[0] + 0.05, theta[1] - 0.05)
                session.authorize_optimizer_update(next_theta)
                session.mark_optimizer_updated(next_theta)
            else:
                next_theta = theta
            session.close_iteration()
            if converged:
                session.finish(TerminationReason.CONVERGED)
                break
            theta = next_theta
        else:
            session.finish(TerminationReason.MAX_ITERATIONS)
        return session.seal_run()
