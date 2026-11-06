from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HAS_QISKIT = importlib.util.find_spec("qiskit") is not None
HAS_RUNTIME = importlib.util.find_spec("qiskit_ibm_runtime") is not None


def _load_tool():
    for path in (ROOT / "src", ROOT / "tools"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    import run_hardware_pair

    return run_hardware_pair


def _run(run_id: str, fidelities: list[float], client: float) -> dict:
    return {
        "run_id": run_id,
        "setup_seconds": 1.0,
        "finalize_seconds": 0.5,
        "evaluations": [
            {
                "fidelity": fidelity,
                "client_seconds": client,
                "evaluation_seconds": client + 10.0,
                "submit_seconds": 1.0,
                "result_wait_seconds": 8.5,
                "metadata_seconds": 0.5,
            }
            for fidelity in fidelities
        ],
    }


class CumulativeHoldTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tool = _load_tool()

    def test_early_stop_holds_values_at_later_bounds(self) -> None:
        run = _run("early", [0.9, 0.8, 0.7], client=0.1)
        at_three = self.tool.cumulative_at(run, 3)
        at_ten = self.tool.cumulative_at(run, 10)
        self.assertFalse(at_three["held"])
        self.assertTrue(at_ten["held"])
        self.assertEqual(at_ten["evaluations_used"], 3)
        for key in ("mean_fidelity", "cumulative_infidelity", "client_seconds", "ibm_seconds"):
            self.assertEqual(at_three[key], at_ten[key])

    def test_changes_are_verified_minus_unverified(self) -> None:
        unverified = _run("u", [0.9, 0.9], client=0.1)
        verified = _run("v", [0.8, 0.8], client=0.4)
        row = self.tool.pair_rows(unverified, verified, bounds=(2,))[0]
        self.assertAlmostEqual(row["fidelity_change"], -0.1)
        self.assertAlmostEqual(row["added_seconds"], 0.6)

    def test_client_time_excludes_ibm_time(self) -> None:
        at_two = self.tool.cumulative_at(_run("u", [0.9, 0.9], client=0.1), 2)
        self.assertAlmostEqual(at_two["client_seconds"], 1.7)
        self.assertAlmostEqual(at_two["ibm_seconds"], 20.0)


class QpuLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tool = _load_tool()

    def test_cap_stops_before_a_job_could_pass_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.json"
            ledger = self.tool.QpuLedger(path, cap_seconds=6.0)
            ledger.require_room()
            ledger.record("r", "j1", {"metrics": {"usage": {"qpu_charge_time_seconds": 3}}})
            ledger.require_room()
            ledger.record("r", "j2", {})
            self.assertEqual(ledger.charged_seconds, 6.0)
            with self.assertRaises(self.tool.QpuCapReached):
                ledger.require_room()
            self.assertEqual(json.loads(path.read_text())[1]["reported"], False)
            self.assertEqual(self.tool.QpuLedger(path, 6.0).charged_seconds, 6.0)


@unittest.skipUnless(HAS_QISKIT and HAS_RUNTIME, "requires the qiskit extra")
class CompiledCircuitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tool = _load_tool()

    def test_compiled_circuits_keep_the_h_rz_y_distributions(self) -> None:
        from qiskit_ibm_runtime.fake_provider import FakeMarrakesh
        from vqe_runtime.config import load_config

        config = load_config(self.tool.PAIR_CONFIG)
        ansatz, logical = self.tool.build_ansatz(config)
        self.assertEqual(ansatz.num_parameters, 4)
        self.assertEqual(ansatz.decompose().count_ops().get("cx"), 1)
        compiled = self.tool.compile_circuits(config, ansatz, logical, FakeMarrakesh().target)
        error = self.tool.compiled_equivalence_error(compiled, logical)
        self.assertLess(error, self.tool.EQUIVALENCE_TOLERANCE)

    def test_simulator_launcher_uses_the_hardware_pair_circuit(self) -> None:
        import benchmark_sampler_hrzy as launcher
        from qiskit_ibm_runtime.fake_provider import FakeMarrakesh
        from vqe_runtime.config import load_config

        config = load_config(ROOT / "configs/h2_statevector.toml")
        ansatz, circuits = launcher.make_circuits(config)
        self.assertEqual(dict(ansatz.count_ops()), {"h": 4, "rz": 4, "y": 4, "cx": 1})

        pair_config = load_config(self.tool.PAIR_CONFIG)
        pair_ansatz, pair_logical = self.tool.build_ansatz(pair_config)
        compiled = self.tool.compile_circuits(
            pair_config, pair_ansatz, pair_logical, FakeMarrakesh().target
        )
        error = self.tool.compiled_equivalence_error(compiled, circuits)
        self.assertLess(error, self.tool.EQUIVALENCE_TOLERANCE)

        record = launcher.provenance(
            config,
            ansatz=ansatz,
            circuits=circuits,
            circuit_hashes=("unused",) * len(circuits),
            initial_theta=(0.0, 0.0, 0.0, 0.0),
        )
        self.assertEqual(record["ansatz"]["su2_gates"], ["h", "rz", "y"])


if __name__ == "__main__":
    unittest.main()
