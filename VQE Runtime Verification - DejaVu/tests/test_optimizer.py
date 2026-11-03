from __future__ import annotations

from dataclasses import replace
import math
import unittest

from vqe_runtime.optimizer import (
    AskTellPatternSearch,
    ConsumedUpdateToken,
    InvalidUpdateToken,
    OptimizerProtocolError,
    StaleUpdateToken,
)


class AskTellPatternSearchTests(unittest.TestCase):
    def optimizer(self, *, dimension: int = 2) -> AskTellPatternSearch:
        return AskTellPatternSearch(
            dimension,
            lower_bounds=-1.0,
            upper_bounds=1.0,
            initial_step=0.5,
        )

    def test_preview_is_pure_and_deterministic(self):
        optimizer = self.optimizer()

        first_theta, first_token = optimizer.preview_update((0.0, 0.0), 1.0)
        second_theta, second_token = optimizer.preview_update((0.0, 0.0), 1.0)

        self.assertEqual(first_theta, (0.5, 0.0))
        self.assertEqual(second_theta, first_theta)
        self.assertIsNot(first_token, second_token)
        self.assertEqual(optimizer.generation, 0)
        self.assertEqual(optimizer.evaluation_count, 0)
        self.assertIsNone(optimizer.expected_theta)
        self.assertIsNone(optimizer.incumbent_theta)
        self.assertIsNone(optimizer.incumbent_energy)
        self.assertEqual(optimizer.step_sizes, (0.5, 0.5))

    def test_commit_is_the_mutation_boundary(self):
        optimizer = self.optimizer()
        next_theta, token = optimizer.preview_update((0.0, 0.0), 1.0)

        optimizer.commit_update(token, authorized_theta=next_theta)

        self.assertEqual(optimizer.generation, 1)
        self.assertEqual(optimizer.evaluation_count, 1)
        self.assertEqual(optimizer.expected_theta, next_theta)
        self.assertEqual(optimizer.incumbent_theta, (0.0, 0.0))
        self.assertEqual(optimizer.incumbent_energy, 1.0)

    def test_coordinate_search_accepts_only_improving_trials(self):
        optimizer = self.optimizer()
        theta, token = optimizer.preview_update((0.0, 0.0), 1.0)
        optimizer.commit_update(token, authorized_theta=theta)

        # +x improves, so it becomes the incumbent and search advances to +y.
        theta, token = optimizer.preview_update(theta, 0.5)
        self.assertEqual(theta, (0.5, 0.5))
        optimizer.commit_update(token, authorized_theta=theta)
        self.assertEqual(optimizer.incumbent_theta, (0.5, 0.0))
        self.assertEqual(optimizer.incumbent_energy, 0.5)

        # +y fails, so the next trial is -y from the unchanged incumbent.
        theta, token = optimizer.preview_update(theta, 0.75)
        self.assertEqual(theta, (0.5, -0.5))
        optimizer.commit_update(token, authorized_theta=theta)
        self.assertEqual(optimizer.incumbent_theta, (0.5, 0.0))

    def test_step_shrinks_after_a_complete_unsuccessful_sweep(self):
        optimizer = self.optimizer(dimension=1)
        theta, token = optimizer.preview_update((0.0,), 0.0)
        optimizer.commit_update(token, authorized_theta=theta)
        self.assertEqual(theta, (0.5,))

        theta, token = optimizer.preview_update(theta, 1.0)
        optimizer.commit_update(token, authorized_theta=theta)
        self.assertEqual(theta, (-0.5,))
        self.assertEqual(optimizer.step_sizes, (0.5,))

        theta, token = optimizer.preview_update(theta, 1.0)
        self.assertEqual(theta, (0.25,))
        optimizer.commit_update(token, authorized_theta=theta)
        self.assertEqual(optimizer.step_sizes, (0.25,))

    def test_candidates_are_clipped_to_bounds_and_never_repeat_incumbent(self):
        optimizer = AskTellPatternSearch(
            1,
            lower_bounds=-1.0,
            upper_bounds=1.0,
            initial_step=0.5,
        )
        theta, token = optimizer.preview_update((0.9,), 0.0)
        self.assertEqual(theta, (1.0,))
        optimizer.commit_update(token, authorized_theta=theta)

        # The outward + move at the upper bound is skipped after improvement.
        theta, _ = optimizer.preview_update(theta, -1.0)
        self.assertEqual(theta, (0.5,))
        self.assertGreaterEqual(theta[0], -1.0)
        self.assertLessEqual(theta[0], 1.0)

    def test_preview_requires_the_committed_candidate(self):
        optimizer = self.optimizer()
        theta, token = optimizer.preview_update((0.0, 0.0), 1.0)
        optimizer.commit_update(token, authorized_theta=theta)

        with self.assertRaisesRegex(
            OptimizerProtocolError, "previously committed candidate"
        ):
            optimizer.preview_update((0.4, 0.0), 0.5)

        self.assertEqual(optimizer.generation, 1)
        self.assertEqual(optimizer.evaluation_count, 1)

    def test_token_reuse_is_rejected_without_mutation(self):
        optimizer = self.optimizer()
        theta, token = optimizer.preview_update((0.0, 0.0), 1.0)
        optimizer.commit_update(token, authorized_theta=theta)

        with self.assertRaises(ConsumedUpdateToken):
            optimizer.commit_update(token, authorized_theta=theta)

        self.assertEqual(optimizer.generation, 1)
        self.assertEqual(optimizer.evaluation_count, 1)

    def test_alternate_token_becomes_stale_after_commit(self):
        optimizer = self.optimizer()
        theta, chosen = optimizer.preview_update((0.0, 0.0), 1.0)
        _, alternate = optimizer.preview_update((0.0, 0.0), 1.0)
        optimizer.commit_update(chosen, authorized_theta=theta)

        with self.assertRaises(StaleUpdateToken):
            optimizer.commit_update(alternate, authorized_theta=theta)

        self.assertEqual(optimizer.generation, 1)

    def test_foreign_and_non_tokens_are_rejected(self):
        first = self.optimizer()
        second = self.optimizer()
        theta, foreign_token = first.preview_update((0.0, 0.0), 1.0)

        for value in (foreign_token, object(), None):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(InvalidUpdateToken):
                    second.commit_update(value, authorized_theta=theta)

        self.assertEqual(second.generation, 0)

    def test_altered_token_is_rejected(self):
        optimizer = self.optimizer()
        theta, token = optimizer.preview_update((0.0, 0.0), 1.0)
        altered_transition = replace(token.transition, next_theta=(0.75, 0.0))
        altered_token = replace(token, transition=altered_transition)

        with self.assertRaises(InvalidUpdateToken):
            optimizer.commit_update(altered_token, authorized_theta=theta)

        self.assertEqual(optimizer.generation, 0)
        self.assertEqual(optimizer.evaluation_count, 0)

    def test_commit_requires_the_exact_verifier_authorized_proposal(self):
        optimizer = self.optimizer()
        theta, token = optimizer.preview_update((0.0, 0.0), 1.0)

        with self.assertRaisesRegex(InvalidUpdateToken, "authorized theta"):
            optimizer.commit_update(token, authorized_theta=(theta[0], -0.25))

        self.assertEqual(optimizer.generation, 0)
        self.assertEqual(optimizer.evaluation_count, 0)

    def test_dimension_domain_and_finite_energy_are_enforced(self):
        optimizer = self.optimizer()
        invalid_calls = (
            ((0.0,), 1.0),
            ((0.0, 0.0, 0.0), 1.0),
            ((1.1, 0.0), 1.0),
            ((math.nan, 0.0), 1.0),
            ((0.0, 0.0), math.inf),
        )
        for theta, energy in invalid_calls:
            with self.subTest(theta=theta, energy=energy):
                with self.assertRaises(ValueError):
                    optimizer.preview_update(theta, energy)

        self.assertEqual(optimizer.generation, 0)

    def test_constructor_rejects_invalid_dimensions_bounds_and_steps(self):
        invalid_arguments = (
            dict(dimension=0, lower_bounds=-1.0, upper_bounds=1.0),
            dict(dimension=True, lower_bounds=-1.0, upper_bounds=1.0),
            dict(dimension=2, lower_bounds=(-1.0,), upper_bounds=(1.0, 1.0)),
            dict(dimension=1, lower_bounds=1.0, upper_bounds=1.0),
            dict(dimension=1, lower_bounds=-1.0, upper_bounds=math.inf),
            dict(
                dimension=1,
                lower_bounds=-1.0,
                upper_bounds=1.0,
                initial_step=0.0,
            ),
            dict(
                dimension=1,
                lower_bounds=-1.0,
                upper_bounds=1.0,
                step_shrink=1.0,
            ),
            dict(
                dimension=1,
                lower_bounds=-1.0,
                upper_bounds=1.0,
                improvement_tolerance=-1.0,
            ),
        )
        for arguments in invalid_arguments:
            with self.subTest(arguments=arguments):
                with self.assertRaises(ValueError):
                    AskTellPatternSearch(**arguments)

    def test_four_parameter_search_operates_for_fifty_evaluations(self):
        optimizer = AskTellPatternSearch(
            4,
            lower_bounds=(-math.pi,) * 4,
            upper_bounds=(math.pi,) * 4,
            initial_step=(0.4,) * 4,
        )
        theta = (0.1, -0.2, 0.3, -0.4)

        for _ in range(50):
            energy = sum((value - 0.25) ** 2 for value in theta)
            theta, token = optimizer.preview_update(theta, energy)
            optimizer.commit_update(token, authorized_theta=theta)
            self.assertTrue(all(-math.pi <= value <= math.pi for value in theta))

        self.assertEqual(optimizer.generation, 50)
        self.assertEqual(optimizer.evaluation_count, 50)
        self.assertEqual(optimizer.expected_theta, theta)
        self.assertIsNotNone(optimizer.incumbent_energy)


if __name__ == "__main__":
    unittest.main()
