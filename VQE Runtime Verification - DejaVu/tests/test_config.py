from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from vqe_runtime.config import TermSpec, load_config, load_hamiltonian


ROOT = Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    def test_config_digest_is_deterministic_and_hamiltonian_is_bound(self):
        left = load_config(ROOT / "configs/h2_demo.toml")
        right = load_config(ROOT / "configs/h2_demo.toml")
        self.assertEqual(left.digest, right.digest)
        self.assertEqual(left.hamiltonian.num_qubits, 2)
        self.assertEqual(len(left.hamiltonian.terms), 4)
        self.assertEqual(left.hamiltonian.coefficient_bound, 0.9883)

    def test_cli_style_override_changes_resolved_hash(self):
        baseline = load_config(ROOT / "configs/h2_demo.toml")
        changed = load_config(
            ROOT / "configs/h2_demo.toml",
            convergence_tolerance=0.002,
        )
        self.assertNotEqual(baseline.digest, changed.digest)

    def test_boolean_is_not_accepted_as_integer(self):
        config = load_config(ROOT / "configs/h2_demo.toml")
        with self.assertRaises(ValueError):
            replace(config, max_iterations=True)

    def test_impossible_shot_budget_is_rejected(self):
        config = load_config(ROOT / "configs/h2_demo.toml")
        with self.assertRaises(ValueError):
            replace(config, shot_budget=1)

    def test_non_string_config_identity_is_rejected(self):
        config = load_config(ROOT / "configs/h2_demo.toml")
        with self.assertRaises(ValueError):
            replace(config, system=123)

    def test_monitor_unsafe_term_id_is_rejected_at_load_time(self):
        with self.assertRaises(ValueError):
            TermSpec("t/0", "ZI", 1)

    def test_hamiltonian_does_not_coerce_schema_types(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hamiltonian.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "coeff_scale": 100,
                        "terms": [
                            {"term_id": 1, "pauli": "ZI", "coeff_int": 2}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_hamiltonian(path)

    def test_unknown_config_key_is_rejected(self):
        source = (ROOT / "configs/h2_demo.toml").read_text(encoding="utf-8")
        source = source.replace(
            'hamiltonian = "../data/h2_hamiltonian.json"',
            f'hamiltonian = "{ROOT / "data/h2_hamiltonian.json"}"',
        ).replace("seed = 7", "seed = 7\nsead = 8")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.toml"
            path.write_text(source, encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(path)

    def test_unknown_none_override_is_not_silently_ignored(self):
        with self.assertRaises(ValueError):
            load_config(ROOT / "configs/h2_demo.toml", misspelled=None)

    def test_legacy_estimator_profiles_keep_archived_trace_digests(self):
        expected = {
            "h2_statevector_estimator_legacy.toml": (
                "9a2c01406359167dc9ffbaa67a767f9a1e752cd8b0875cf13ae7c25830ee4d20"
            ),
            "h2_ibm_runtime_50.toml": (
                "2f19ada4f01eaf2b7740df025b28902137358e66e84f4fa4a6e2503fb47736d3"
            ),
        }
        for filename, digest in expected.items():
            with self.subTest(filename=filename):
                self.assertEqual(load_config(ROOT / "configs" / filename).digest, digest)

    def test_statevector_and_hardware_sampler_profiles_are_comparable(self):
        statevector = load_config(ROOT / "configs/h2_statevector.toml")
        hardware = load_config(ROOT / "configs/h2_ibm_sampler_50.toml")
        self.assertEqual(statevector.schema_version, 2)
        self.assertEqual(hardware.schema_version, 2)
        self.assertTrue(statevector.is_sampler_mode)
        self.assertTrue(hardware.is_sampler_mode)
        for field in (
            "parameter_count",
            "max_iterations",
            "shots_per_term",
            "shot_budget",
            "seed",
            "optimizer_protocol",
            "allow_optimizer_stopped",
            "parameter_lower",
            "parameter_upper",
            "energy_abs_tolerance",
            "expectation_abs_tolerance",
            "convergence_tolerance",
            "min_iterations",
            "convergence_patience",
            "require_raw_counts",
            "sampler",
            "optimizer",
        ):
            self.assertEqual(getattr(statevector, field), getattr(hardware, field), field)
        self.assertEqual(statevector.max_iterations, 50)
        self.assertEqual(statevector.shots_per_term, 1024)
        self.assertEqual(statevector.shot_budget, 204800)
        self.assertEqual(
            [term.pauli for term in statevector.hamiltonian.terms],
            ["YZ", "ZI", "ZZ", "XX"],
        )

    def test_hardware_preflight_changes_only_bounded_lifecycle_fields(self):
        full = load_config(ROOT / "configs/h2_ibm_sampler_50.toml")
        preflight = load_config(ROOT / "configs/h2_ibm_sampler_preflight.toml")
        self.assertEqual(preflight.max_iterations, 1)
        self.assertEqual(preflight.shot_budget, 4096)
        self.assertEqual(preflight.min_iterations, 1)
        self.assertEqual(preflight.convergence_patience, 1)
        self.assertEqual(
            replace(
                preflight,
                max_iterations=full.max_iterations,
                shot_budget=full.shot_budget,
                min_iterations=full.min_iterations,
                convergence_patience=full.convergence_patience,
            ).as_dict(include_source=False),
            full.as_dict(include_source=False),
        )

    def test_sampler_modes_require_schema2_raw_counts_and_ask_tell(self):
        config = load_config(ROOT / "configs/h2_statevector.toml")
        for changes in (
            {"schema_version": 1},
            {"require_raw_counts": False},
            {"optimizer_protocol": "opaque"},
            {"allow_optimizer_stopped": True},
            {"shot_budget": config.shot_budget + 1},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    replace(config, **changes)


if __name__ == "__main__":
    unittest.main()
