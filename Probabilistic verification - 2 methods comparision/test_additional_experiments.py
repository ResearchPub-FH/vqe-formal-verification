#!/usr/bin/env python3
"""Consistency tests for the two generated follow-up experiments."""

from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path

import h2_prism_fakebackend_workflow as h2


ROOT = Path(__file__).resolve().parent
ADDITIONAL = ROOT / "artifacts/h2_vqe/additional_experiments"


class ShotSensitivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ADDITIONAL / "shot_sensitivity"
        with (cls.directory / "shot_sensitivity.csv").open(
            newline="", encoding="utf-8"
        ) as handle:
            cls.rows = list(csv.DictReader(handle))

    def test_configurations_and_probabilities(self):
        self.assertEqual(
            [int(row["shots_per_group"]) for row in self.rows],
            [256, 512, 1024, 2048],
        )
        gaussian = [float(row["gaussian_p50"]) for row in self.rows]
        empirical = [float(row["empirical_p50"]) for row in self.rows]
        self.assertEqual(gaussian, sorted(gaussian))
        self.assertEqual(empirical, sorted(empirical))
        for row in self.rows:
            estimate = float(row["empirical_p50"])
            self.assertLessEqual(float(row["empirical_ci95_low"]), estimate)
            self.assertGreaterEqual(float(row["empirical_ci95_high"]), estimate)
            self.assertAlmostEqual(
                float(row["absolute_difference"]),
                abs(float(row["gaussian_p50"]) - estimate),
                places=11,
            )

    def test_compact_traces_match_csv(self):
        for row in self.rows:
            shots = int(row["shots_per_group"])
            with (self.directory / f"empirical_{shots}_runs.jsonl").open(
                encoding="utf-8"
            ) as handle:
                records = [json.loads(line) for line in handle if line.strip()]
            self.assertEqual(len(records), int(row["empirical_runs"]))
            successes = 0
            for expected_run, record in enumerate(records, start=1):
                self.assertEqual(record["run"], expected_run)
                self.assertEqual(record["shots_per_group"], shots)
                self.assertEqual(len(record["final_index"]), 4)
                self.assertTrue(
                    all(0 <= value < h2.GRID_SIZE for value in record["final_index"])
                )
                step = record["success_step"]
                is_success = step is not None
                successes += int(is_success)
                self.assertEqual(record["outcome"] == "success", is_success)
                self.assertEqual(record["updates"], step if is_success else 50)
                exact_energy, _ = h2.state_data(tuple(record["final_index"]))
                final_index_is_success = (
                    exact_energy - h2.GROUND_ENERGY <= h2.CONVERGENCE_TOLERANCE
                )
                self.assertEqual(final_index_is_success, is_success)
            self.assertEqual(successes, int(row["empirical_successes"]))
            self.assertAlmostEqual(
                successes / len(records), float(row["empirical_p50"])
            )

    def test_chart_files(self):
        png = (self.directory / "shot_sensitivity.png").read_bytes()
        svg = (self.directory / "shot_sensitivity.svg").read_text(
            encoding="utf-8"
        )
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertIn("<svg", svg)


class ScalabilityTests(unittest.TestCase):
    def test_counts_and_storm_results(self):
        directory = ADDITIONAL / "model_checking_scalability"
        with (directory / "scalability_results.csv").open(
            newline="", encoding="utf-8"
        ) as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual([int(row["K"]) for row in rows], [10, 20, 30, 40, 50])
        states = [int(row["reachable_states"]) for row in rows]
        transitions = [int(row["transitions"]) for row in rows]
        self.assertEqual(states, sorted(states))
        self.assertEqual(transitions, sorted(transitions))

        with (
            ROOT / "artifacts/h2_vqe/layer1_analytical/analytical_curve.csv"
        ).open(newline="", encoding="utf-8") as handle:
            analytical = {
                int(row["horizon"]): float(row["success_probability"])
                for row in csv.DictReader(handle)
            }
        for row in rows:
            k = int(row["K"])
            self.assertGreater(float(row["dtmc_construction_time_s"]), 0.0)
            self.assertGreaterEqual(float(row["storm_checking_time_s"]), 0.0)
            self.assertGreater(int(row["explicit_model_bytes"]), 0)
            self.assertAlmostEqual(float(row["gaussian_pK"]), analytical[k], places=11)
            self.assertAlmostEqual(
                float(row["storm_result"]), float(row["gaussian_pK"]), places=9
            )
            self.assertLess(float(row["absolute_difference"]), 1e-9)


if __name__ == "__main__":
    unittest.main()
