from __future__ import annotations

from dataclasses import replace
import hashlib
import math
from pathlib import Path
import random
import tempfile
import unittest

from vqe_runtime.config import RuntimeConfig, load_config, vector_digest
from vqe_runtime.dejavu import AlwaysPassMonitor
from vqe_runtime.optimizer import AskTellPatternSearch
from vqe_runtime.report import Status
from vqe_runtime.session import (
    RuntimeSession,
    TermObservation,
    TerminationReason,
    VerificationAbort,
)


ROOT = Path(__file__).resolve().parents[1]


class SamplerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base_config = load_config(ROOT / "configs/h2_statevector.toml")
        self.temp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _initial_theta(config: RuntimeConfig) -> tuple[float, ...]:
        source = random.Random(config.seed)
        return tuple(
            source.uniform(config.parameter_lower, config.parameter_upper)
            for _ in range(config.parameter_count)
        )

    @classmethod
    def _provenance(cls, config: RuntimeConfig) -> dict[str, object]:
        assert config.sampler is not None
        assert config.optimizer is not None
        initial_theta = cls._initial_theta(config)
        term_count = len(config.hamiltonian.terms)
        return {
            "initial_theta": list(initial_theta),
            "initial_theta_hash": vector_digest(initial_theta),
            "sampler_experiment": {
                "pubs_per_evaluation": term_count,
                "term_order": [term.term_id for term in config.hamiltonian.terms],
                "pauli_order": [term.pauli for term in config.hamiltonian.terms],
                "shots_per_pub": config.shots_per_term,
                "physical_shots_per_evaluation": (
                    term_count * config.shots_per_term
                ),
                "maximum_submitted_pubs": config.max_iterations * term_count,
                "maximum_physical_shots": config.shot_budget,
                "bitstring_order": config.sampler.bitstring_order,
                "raw_evidence_format": config.sampler.raw_evidence_format,
                "sampler_policy": config.sampler.as_dict(),
                "optimizer_policy": config.optimizer.as_dict(),
                "optimizer_gate_order": [
                    "preview_update_no_mutation",
                    "verifier_authorize_exact_theta",
                    "commit_update",
                    "verifier_record_commit",
                ],
                "api_options": {
                    "primitive": "qiskit.primitives.StatevectorSampler",
                    "constructor": {
                        "default_shots": config.shots_per_term,
                        "seed": config.seed,
                    },
                    "run_shots": config.shots_per_term,
                },
            },
        }

    def _config(
        self,
        *,
        max_iterations: int = 3,
        min_iterations: int = 3,
        patience: int = 2,
    ) -> RuntimeConfig:
        return replace(
            self.base_config,
            max_iterations=max_iterations,
            shot_budget=(
                max_iterations
                * len(self.base_config.hamiltonian.terms)
                * self.base_config.shots_per_term
            ),
            min_iterations=min_iterations,
            convergence_patience=patience,
        )

    def _session(self, config: RuntimeConfig, run_id: str) -> RuntimeSession:
        root = Path(self.temp.name)
        return RuntimeSession(
            config,
            run_id=run_id,
            trace_path=root / f"{run_id}.jsonl",
            report_path=root / f"{run_id}.report.json",
            monitor=AlwaysPassMonitor(),
            execution_provenance=self._provenance(config),
            overwrite=True,
        )

    @staticmethod
    def _digest(label: str) -> str:
        return hashlib.sha256(label.encode("utf-8")).hexdigest()

    def _circuit_hashes(self, config: RuntimeConfig) -> dict[str, str]:
        return {
            term.term_id: self._digest(f"parameterized-circuit:{term.term_id}")
            for term in config.hamiltonian.terms
        }

    def _observations(
        self,
        config: RuntimeConfig,
        iteration: int,
        *,
        pub_indices: tuple[int | None, ...] | None = None,
        evidence_hashes: tuple[str | None, ...] | None = None,
    ) -> tuple[TermObservation, ...]:
        negative_counts = (768, 256, 512, 900)
        if pub_indices is None:
            pub_indices = tuple(range(len(config.hamiltonian.terms)))
        if evidence_hashes is None:
            evidence_hashes = tuple(
                self._digest(f"raw:{iteration}:{index}")
                for index in range(len(config.hamiltonian.terms))
            )
        return tuple(
            TermObservation(
                term.term_id,
                1.0 - 2.0 * negative / config.shots_per_term,
                config.shots_per_term,
                negative,
                negative_eigenvalue_count=negative,
                pub_index=pub_index,
                raw_evidence_sha256=evidence_hash,
                executable_circuit_qpy_sha256=self._digest(
                    f"executable:{iteration}:{index}"
                ),
            )
            for index, (term, negative, pub_index, evidence_hash) in enumerate(
                zip(
                    config.hamiltonian.terms,
                    negative_counts,
                    pub_indices,
                    evidence_hashes,
                )
            )
        )

    @staticmethod
    def _energy(
        config: RuntimeConfig, observations: tuple[TermObservation, ...]
    ) -> float:
        return math.fsum(
            term.coeff_int * observation.expectation
            / config.hamiltonian.coeff_scale
            for term, observation in zip(config.hamiltonian.terms, observations)
        )

    def _prepare_measurement(
        self,
        session: RuntimeSession,
        theta: tuple[float, ...],
        iteration: int,
    ) -> tuple[TermObservation, ...]:
        config = session.config
        session.begin_iteration(theta, evaluation_id=f"eval{iteration}")
        session.bind_parameters()
        session.authorize_job(
            f"submission{iteration}",
            pub_indices={
                term.term_id: index
                for index, term in enumerate(config.hamiltonian.terms)
            },
            circuit_hashes=self._circuit_hashes(config),
        )
        session.mark_job_submitted(f"job{iteration}")
        observations = self._observations(config, iteration)
        session.observe_terms(observations)
        session.seal_measurements()
        session.aggregate_energy(self._energy(config, observations))
        return observations

    @staticmethod
    def _optimizer(config: RuntimeConfig) -> AskTellPatternSearch:
        assert config.optimizer is not None
        return AskTellPatternSearch(
            config.parameter_count,
            config.parameter_lower,
            config.parameter_upper,
            initial_step=config.optimizer.initial_step,
            step_shrink=config.optimizer.step_shrink,
            improvement_tolerance=config.optimizer.improvement_tolerance,
        )

    @staticmethod
    def _assert_no_failures(test: unittest.TestCase, session: RuntimeSession) -> None:
        test.assertFalse(
            [
                finding
                for finding in session.report.findings
                if finding.status == Status.FAIL
            ]
        )

    def test_valid_single_iteration_sampler_flow_reaches_exact_budget_terminal(self) -> None:
        config = self._config(max_iterations=1, min_iterations=1, patience=1)
        session = self._session(config, "valid-single")
        try:
            theta = self._initial_theta(config)
            self._prepare_measurement(session, theta, 0)
            self.assertFalse(session.check_convergence())
            session.authorize_objective_release()
            session.close_iteration()
            session.finish(TerminationReason.MAX_ITERATIONS)
            report = session.seal_run()

            self.assertTrue(report.complete)
            self.assertEqual(report.iterations, 1)
            self.assertEqual(report.effective_term_samples, 4 * 1024)
            self.assertEqual(report.terminal_reason, "max_iterations")
            self._assert_no_failures(self, session)
        finally:
            session.close()

    def test_valid_three_iteration_flow_commits_before_each_successor(self) -> None:
        config = self._config(max_iterations=3, min_iterations=3, patience=2)
        session = self._session(config, "valid-multi")
        optimizer = self._optimizer(config)
        theta = self._initial_theta(config)
        try:
            for iteration in range(3):
                self._prepare_measurement(session, theta, iteration)
                converged = session.check_convergence()
                energy = session.authorize_objective_release()
                if iteration < 2:
                    self.assertFalse(converged)
                    next_theta, token = optimizer.preview_update(theta, energy)
                    session.authorize_and_commit_optimizer_update(
                        optimizer, token, next_theta
                    )
                    session.close_iteration()
                    theta = next_theta
                else:
                    self.assertTrue(converged)
                    session.close_iteration()

            session.finish(TerminationReason.CONVERGED)
            report = session.seal_run()
            event_names = [event.name for event in session.journal.events]

            self.assertEqual(optimizer.generation, 2)
            self.assertEqual(report.iterations, 3)
            self.assertEqual(report.effective_term_samples, 3 * 4 * 1024)
            self.assertEqual(event_names.count("optimizerUpdateIntent"), 2)
            self.assertEqual(event_names.count("optimizerUpdated"), 2)
            self._assert_no_failures(self, session)
        finally:
            session.close()

    def test_manifest_rejects_missing_wrong_and_duplicate_pub_indices(self) -> None:
        config = self._config()
        valid = {
            term.term_id: index
            for index, term in enumerate(config.hamiltonian.terms)
        }
        cases = {
            "missing": {key: value for key, value in valid.items() if key != "t0"},
            "wrong": {**valid, "t0": 3},
            "duplicate": {**valid, "t1": 0},
        }
        for label, pub_indices in cases.items():
            with self.subTest(label=label):
                session = self._session(config, f"manifest-{label}")
                try:
                    session.begin_iteration(
                        self._initial_theta(config), evaluation_id="eval0"
                    )
                    session.bind_parameters()
                    with self.assertRaises(VerificationAbort):
                        session.authorize_job(
                            "submission0",
                            pub_indices=pub_indices,
                            circuit_hashes=self._circuit_hashes(config),
                        )
                    self.assertTrue(
                        any(
                            finding.property_id == "intra_pub_assignment"
                            and finding.status == Status.FAIL
                            for finding in session.report.findings
                        )
                    )
                finally:
                    session.close()

    def test_observation_rejects_missing_wrong_and_duplicate_pub_indices(self) -> None:
        config = self._config()
        cases = {
            "missing": (None, 1, 2, 3),
            "wrong": (1, 1, 2, 3),
            "duplicate": (0, 0, 2, 3),
        }
        for label, pub_indices in cases.items():
            with self.subTest(label=label):
                session = self._session(config, f"observation-{label}")
                try:
                    theta = self._initial_theta(config)
                    session.begin_iteration(theta, evaluation_id="eval0")
                    session.bind_parameters()
                    session.authorize_job(
                        "submission0",
                        pub_indices={
                            term.term_id: index
                            for index, term in enumerate(config.hamiltonian.terms)
                        },
                        circuit_hashes=self._circuit_hashes(config),
                    )
                    session.mark_job_submitted("job0")
                    with self.assertRaises(VerificationAbort):
                        session.observe_terms(
                            self._observations(
                                config, 0, pub_indices=pub_indices
                            )
                        )
                    self.assertTrue(
                        any(
                            finding.property_id == "intra_pub_assignment"
                            and finding.status == Status.FAIL
                            for finding in session.report.findings
                        )
                    )
                finally:
                    session.close()

    def test_missing_explicit_negative_parity_is_rejected(self) -> None:
        config = self._config()
        session = self._session(config, "missing-negative-parity")
        try:
            theta = self._initial_theta(config)
            session.begin_iteration(theta, evaluation_id="eval0")
            session.bind_parameters()
            session.authorize_job(
                "submission0",
                pub_indices={
                    term.term_id: index
                    for index, term in enumerate(config.hamiltonian.terms)
                },
                circuit_hashes=self._circuit_hashes(config),
            )
            session.mark_job_submitted("job0")
            with self.assertRaises(VerificationAbort):
                session.observe_term(
                    TermObservation(
                        "t0",
                        -0.5,
                        config.shots_per_term,
                        768,
                        negative_eigenvalue_count=None,
                        pub_index=0,
                        raw_evidence_sha256=self._digest("missing-negative"),
                        executable_circuit_qpy_sha256=self._digest("executable:t0"),
                    )
                )
            self.assertTrue(
                any(
                    finding.property_id == "intra_parity_reconstruction"
                    and finding.status == Status.FAIL
                    for finding in session.report.findings
                )
            )
        finally:
            session.close()

    def test_mismatched_negative_parity_alias_is_rejected(self) -> None:
        config = self._config()
        session = self._session(config, "mismatched-negative-parity")
        try:
            theta = self._initial_theta(config)
            session.begin_iteration(theta, evaluation_id="eval0")
            session.bind_parameters()
            session.authorize_job(
                "submission0",
                pub_indices={
                    term.term_id: index
                    for index, term in enumerate(config.hamiltonian.terms)
                },
                circuit_hashes=self._circuit_hashes(config),
            )
            session.mark_job_submitted("job0")
            with self.assertRaises(VerificationAbort):
                session.observe_term(
                    TermObservation(
                        "t0",
                        -0.5,
                        config.shots_per_term,
                        767,
                        negative_eigenvalue_count=768,
                        pub_index=0,
                        raw_evidence_sha256=self._digest("mismatched-negative"),
                        executable_circuit_qpy_sha256=self._digest("executable:t0"),
                    )
                )
            self.assertTrue(
                any(
                    finding.property_id == "intra_parity_reconstruction"
                    and finding.status == Status.FAIL
                    for finding in session.report.findings
                )
            )
        finally:
            session.close()

    def test_malformed_and_reused_raw_evidence_hashes_are_rejected(self) -> None:
        config = self._config()
        malformed = self._observations(
            config,
            0,
            evidence_hashes=("ABC",) + tuple(
                self._digest(f"valid:{index}") for index in range(1, 4)
            ),
        )
        repeated_hash = self._digest("reused")
        reused = self._observations(
            config,
            0,
            evidence_hashes=(
                repeated_hash,
                repeated_hash,
                self._digest("unique:2"),
                self._digest("unique:3"),
            ),
        )
        for label, observations, property_id in (
            ("malformed", malformed, "intra_raw_evidence_link"),
            ("reused", reused, "inter_raw_evidence_identity_unique"),
        ):
            with self.subTest(label=label):
                session = self._session(config, f"evidence-{label}")
                try:
                    theta = self._initial_theta(config)
                    session.begin_iteration(theta, evaluation_id="eval0")
                    session.bind_parameters()
                    session.authorize_job(
                        "submission0",
                        pub_indices={
                            term.term_id: index
                            for index, term in enumerate(config.hamiltonian.terms)
                        },
                        circuit_hashes=self._circuit_hashes(config),
                    )
                    session.mark_job_submitted("job0")
                    with self.assertRaises(VerificationAbort):
                        session.observe_terms(observations)
                    self.assertTrue(
                        any(
                            finding.property_id == property_id
                            and finding.status == Status.FAIL
                            for finding in session.report.findings
                        )
                    )
                finally:
                    session.close()

    def test_nonterminal_iteration_cannot_close_without_optimizer_commit(self) -> None:
        config = self._config()
        session = self._session(config, "missing-commit")
        try:
            theta = self._initial_theta(config)
            self._prepare_measurement(session, theta, 0)
            self.assertFalse(session.check_convergence())
            session.authorize_objective_release()
            with self.assertRaises(VerificationAbort):
                session.close_iteration()
            self.assertTrue(
                any(
                    finding.property_id == "inter_optimizer_commit_enforcement"
                    and finding.status == Status.FAIL
                    for finding in session.report.findings
                )
            )
        finally:
            session.close()

    def test_atomic_helper_authorizes_before_calling_optimizer_commit(self) -> None:
        config = self._config()
        session = self._session(config, "atomic-order")

        class CommitProbe:
            def __init__(self) -> None:
                self.called = False
                self.last_event_name: str | None = None
                self.authorized_theta: tuple[float, ...] | None = None

            def commit_update(
                self,
                token: object,
                *,
                authorized_theta: tuple[float, ...],
            ) -> None:
                self.called = True
                self.last_event_name = session.journal.events[-1].name
                self.authorized_theta = tuple(authorized_theta)

        probe = CommitProbe()
        try:
            theta = self._initial_theta(config)
            self._prepare_measurement(session, theta, 0)
            self.assertFalse(session.check_convergence())
            session.authorize_objective_release()
            next_theta = tuple(value / 2.0 for value in theta)
            session.authorize_and_commit_optimizer_update(
                probe, object(), next_theta
            )

            self.assertTrue(probe.called)
            self.assertEqual(probe.last_event_name, "optimizerUpdateIntent")
            self.assertEqual(probe.authorized_theta, next_theta)
            self.assertEqual(session.journal.events[-1].name, "optimizerUpdated")
        finally:
            session.abort("testCleanup")
            session.close()

    def test_atomic_helper_rejects_token_for_a_different_parameter_vector(self) -> None:
        config = self._config()
        session = self._session(config, "token-vector-mismatch")
        optimizer = self._optimizer(config)
        try:
            theta = self._initial_theta(config)
            self._prepare_measurement(session, theta, 0)
            self.assertFalse(session.check_convergence())
            energy = session.authorize_objective_release()
            proposed, token = optimizer.preview_update(theta, energy)
            self.assertNotEqual(proposed, theta)

            with self.assertRaises(RuntimeError):
                session.authorize_and_commit_optimizer_update(
                    optimizer, token, theta
                )
            self.assertEqual(optimizer.generation, 0)
        finally:
            session.abort("testCleanup")
            session.close()

    def test_next_iteration_must_bind_exact_committed_parameter_vector(self) -> None:
        config = self._config()
        session = self._session(config, "exact-vector-continuity")
        optimizer = self._optimizer(config)
        try:
            theta = self._initial_theta(config)
            self._prepare_measurement(session, theta, 0)
            self.assertFalse(session.check_convergence())
            energy = session.authorize_objective_release()
            proposed, token = optimizer.preview_update(theta, energy)
            session.authorize_and_commit_optimizer_update(
                optimizer, token, proposed
            )
            session.close_iteration()

            wrong = list(proposed)
            wrong[-1] = wrong[-1] / 2.0
            if tuple(wrong) == proposed:
                wrong[-1] = 0.125
            with self.assertRaises(VerificationAbort):
                session.begin_iteration(tuple(wrong), evaluation_id="eval1")
            self.assertTrue(
                any(
                    finding.property_id == "inter_theta_continuity"
                    and finding.status == Status.FAIL
                    for finding in session.report.findings
                )
            )
        finally:
            session.close()

    def test_converged_iteration_forbids_optimizer_commit_before_mutation(self) -> None:
        config = self._config(max_iterations=2, min_iterations=2, patience=1)
        session = self._session(config, "terminal-update")
        optimizer = self._optimizer(config)
        theta = self._initial_theta(config)
        try:
            self._prepare_measurement(session, theta, 0)
            self.assertFalse(session.check_convergence())
            energy = session.authorize_objective_release()
            theta, token = optimizer.preview_update(theta, energy)
            session.authorize_and_commit_optimizer_update(optimizer, token, theta)
            session.close_iteration()

            self._prepare_measurement(session, theta, 1)
            self.assertTrue(session.check_convergence())
            energy = session.authorize_objective_release()
            proposed, token = optimizer.preview_update(theta, energy)
            generation_before = optimizer.generation
            with self.assertRaises(VerificationAbort):
                session.authorize_and_commit_optimizer_update(
                    optimizer, token, proposed
                )

            self.assertEqual(optimizer.generation, generation_before)
            self.assertTrue(
                any(
                    finding.property_id == "inter_no_successor_after_convergence"
                    and finding.status == Status.FAIL
                    for finding in session.report.findings
                )
            )
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
