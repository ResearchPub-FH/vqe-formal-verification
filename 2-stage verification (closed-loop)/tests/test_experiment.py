from __future__ import annotations

import copy
from fractions import Fraction
import gzip
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import numpy as np

from closed_loop.checker import reconstruct, exact_error
from closed_loop.common import ROOT, digest, file_hash, read_config, save_json, source_hashes, validate_config, validate_frozen
from closed_loop.comparison import wilson, mean_interval
from closed_loop.execution import execute_run, replay, replay_matches, remove_evidence
from closed_loop.logical import apply_mutant, model, mutants, requirements
from closed_loop.physics import build_gaussian, candidate_indices, ideal_success, measurement_data
from closed_loop.pre_execution import check_controller, tool_path
from closed_loop import temporal
from closed_loop.temporal import dejavu_record, monitor_outcomes


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.c = read_config(ROOT / "config/h2.json")
        self.c.update(maximum_updates=3, checkpoints=[1, 3], runs=2, fault_runs=1)
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def run_trace(self, fault=None):
        path = self.directory / f"{fault or 'normal'}.gz"
        result = execute_run(self.c, "test", [123, 0, 4], "frozen", path, fault)
        return path, result

    def mutate(self, events, name="mutated"):
        path = self.directory / f"{name}.gz"
        with gzip.open(path, "wt") as stream:
            for e in events:
                stream.write(json.dumps(e) + "\n")
        return replay(self.c, "frozen", path)

    def events(self, path):
        with gzip.open(path, "rt") as stream:
            return [json.loads(line) for line in stream]

    def test_baseline_and_replay_have_identical_verdicts(self):
        path, result = self.run_trace()
        self.assertTrue(replay_matches(result, replay(self.c, "frozen", path)))
        self.assertTrue(all(r["runtime_verdict"] == "AGREEMENT" for r in result["contracts"].values()))
        self.assertEqual(result["physical_shots"], result["updates"] * 9 * 1024)

    def test_controlled_faults_have_distinct_classifications(self):
        for fault, cid, verdict in [("premature_update", "L2", "DISAGREEMENT"), ("corrupt_energy", "N2", "DISAGREEMENT"), ("coefficient_swap", "N2", "DISAGREEMENT"), ("shot_mismatch", "N3", "ASSUMPTION_MISMATCH")]:
            with self.subTest(fault=fault):
                path, result = self.run_trace(fault)
                self.assertEqual(result["contracts"][cid]["runtime_verdict"], verdict)
                self.assertEqual(result["terminal_reason"], "contract_abort")
                self.assertEqual(result["updates"], 0)
                self.assertTrue(replay_matches(result, replay(self.c, "frozen", path)))

    def test_trigger_counts_cover_every_obligation(self):
        _, result = self.run_trace()
        u = result["updates"]
        self.assertGreater(u, 0)
        expected = {
            "L1": {"groups_before_energy": 3 * u},
            "L2": {"validation_certified": 3 * u, "validations_before_commit": u},
            "L3": {"evaluation_identity_current": 15 * u, "commit_identity_current": u},
            "L4": {"terminal_reason": 1},
            "N1": {"expectation_reconstructed": 12 * u},
            "N2": {"energy_reconstructed": 3 * u},
            "N3": {"allocation_checked": 9 * u, "cumulative_total_checked": u + 1},
            "N4": {"candidates_generated": u, "selection_checked": u},
        }
        self.assertEqual({cid: row["triggers"] for cid, row in result["contracts"].items()}, expected)

    def test_unexercised_obligation_is_inconclusive_not_agreement(self):
        source, _ = self.run_trace()
        events = self.events(source)
        first_commit = next(i for i, e in enumerate(events) if e["type"] == "optimizer_commit")
        result = self.mutate(events[:first_commit], "no-commit")
        for cid, obligation in (("L2", "validations_before_commit"), ("N4", "selection_checked")):
            with self.subTest(contract=cid):
                row = result["contracts"][cid]
                self.assertGreater(row["checks"], 0)  # the former checks-only guard would have agreed
                self.assertEqual(row["triggers"][obligation], 0)
                self.assertEqual(row["runtime_verdict"], "INCONCLUSIVE")
                self.assertIn(f"obligation {obligation} not exercised (0 triggers)", [i["message"] for i in row["inconclusive"]])

    def test_fault_verdict_vectors_mark_unexercised_contracts(self):
        short = {"AGREEMENT": "A", "DISAGREEMENT": "D", "ASSUMPTION_MISMATCH": "M", "INCONCLUSIVE": "I"}
        expected = {"coefficient_swap": "AIIAADAI", "corrupt_energy": "AIIAADAI",
                    "premature_update": "IDIAIIII", "shot_mismatch": "IIIAIIMI"}
        for fault, vector in expected.items():
            with self.subTest(fault=fault):
                _, result = self.run_trace(fault)
                self.assertEqual("".join(short[result["contracts"][cid]["runtime_verdict"]] for cid in ("L1", "L2", "L3", "L4", "N1", "N2", "N3", "N4")), vector)

    def test_missing_raw_counts_cannot_pass_numeric_verification(self):
        source, _ = self.run_trace()
        dest = self.directory / "missing.gz"
        remove_evidence(source, dest)
        result = replay(self.c, "frozen", dest)
        self.assertEqual(result["contracts"]["N1"]["runtime_verdict"], "INCONCLUSIVE")
        self.assertEqual(result["contracts"]["L1"]["runtime_verdict"], "DISAGREEMENT")
        for cid in ("N2", "N3", "N4", "L2"):
            self.assertEqual(result["contracts"][cid]["runtime_verdict"], "INCONCLUSIVE")
        for cid in ("L3", "L4"):
            self.assertEqual(result["contracts"][cid]["runtime_verdict"], "AGREEMENT")

    def test_group_parity_and_exact_energy(self):
        # Each group is deterministic outcome 10. ZI=-1, ZZ=-1, YZ=-1, XX=-1.
        exps, terms, energy = reconstruct([[0, 0, 1024, 0]] * 3, self.c)
        self.assertEqual(exps, {term: Fraction(-1) for term in ("ZI", "ZZ", "YZ", "XX")})
        self.assertEqual(energy, Fraction(-1697, 10000))
        self.assertEqual(terms["ZI"], Fraction(398, 1000))

    def test_stale_evaluation_identity_is_detected(self):
        source, _ = self.run_trace()
        events = self.events(source)
        next(e for e in events if e["type"] == "evaluation")["evaluation_id"] = "another-run:u9:c0"
        self.assertEqual(self.mutate(events)["contracts"]["L3"]["runtime_verdict"], "DISAGREEMENT")

    def test_optimizer_cannot_use_unchecked_energy(self):
        source, _ = self.run_trace()
        events = self.events(source)
        next(e for e in events if e["type"] == "optimizer_commit")["energies_used"][0] += 0.1
        self.assertEqual(self.mutate(events)["contracts"]["N2"]["runtime_verdict"], "DISAGREEMENT")

    def test_optimizer_cannot_use_unchecked_integer_score(self):
        source, _ = self.run_trace()
        events = self.events(source)
        next(e for e in events if e["type"] == "optimizer_commit")["scores_used"][0] += 1
        self.assertEqual(self.mutate(events)["contracts"]["N2"]["runtime_verdict"], "DISAGREEMENT")

    def test_real_reference_preserves_float_rounding_error(self):
        self.assertGreater(exact_error(0.1, Fraction(1, 10)), 0)
        self.assertLess(exact_error(0.1, Fraction(1, 10)), Fraction(1, 10**12))

    def test_optimizer_tolerance_does_not_double_through_intermediate_values(self):
        source, _ = self.run_trace()
        events = self.events(source)
        evaluation = next(e for e in events if e["type"] == "evaluation")
        evaluation["energy"] += 0.75e-12
        commit = next(e for e in events if e["type"] == "optimizer_commit")
        commit["energies_used"][0] += 1.5e-12
        self.assertEqual(self.mutate(events)["contracts"]["N2"]["runtime_verdict"], "DISAGREEMENT")

    def test_nan_energy_is_rejected(self):
        source, _ = self.run_trace()
        events = self.events(source)
        next(e for e in events if e["type"] == "evaluation")["energy"] = float("nan")
        self.assertEqual(self.mutate(events)["contracts"]["N2"]["runtime_verdict"], "DISAGREEMENT")

    def test_no_activity_after_termination(self):
        source, _ = self.run_trace()
        events = self.events(source)
        duplicate = copy.deepcopy(events[-1])
        duplicate["seq"] += 1
        events.append(duplicate)
        self.assertEqual(self.mutate(events)["contracts"]["L4"]["runtime_verdict"], "DISAGREEMENT")

    def test_truncated_trace_is_inconclusive(self):
        source, _ = self.run_trace()
        self.assertEqual(self.mutate(self.events(source)[:-1])["contracts"]["L4"]["runtime_verdict"], "INCONCLUSIVE")

    def test_duplicate_groups_are_not_counted_twice(self):
        source, result = self.run_trace()
        events = self.events(source)
        position = next(i for i, e in enumerate(events) if e["type"] == "measurement")
        events.insert(position + 1, copy.deepcopy(events[position]))
        for seq, e in enumerate(events, 1):
            e["seq"] = seq
        replayed = self.mutate(events)
        self.assertEqual(replayed["physical_shots"], result["physical_shots"])
        self.assertEqual(replayed["contracts"]["L1"]["runtime_verdict"], "DISAGREEMENT")

    def test_every_mutant_edits_the_generated_controller_once(self):
        text = model(self.c)
        for mutant in mutants(self.c):
            with self.subTest(mutant=mutant["name"]):
                self.assertNotEqual(apply_mutant(text, mutant), text)
        self.assertEqual({m["contract"] for m in mutants(self.c)}, {p["contract"] for p in requirements(self.c)})

    def test_logical_gate_requires_witnesses_and_mutant_kills(self):
        try:
            nuxmv = tool_path("nuXmv")
        except FileNotFoundError:
            self.skipTest("nuXmv unavailable")
        full = self.directory / "full"
        full.mkdir()
        result = check_controller(nuxmv, full, self.c, requirements(self.c), model(self.c))
        self.assertEqual(result["status"], "PROVED")
        self.assertTrue(all(q["as_expected"] for q in result["nonvacuity"]["results"]))
        self.assertIn(False, [q["holds"] for q in result["nonvacuity"]["results"] if q["kind"] == "branch"])  # defensive default
        self.assertTrue(all(m["killed"] for m in result["mutation"]))
        # Without the success-reason and abort-cause properties, success-to-abort survives.
        original = [p for p in requirements(self.c) if p["name"] not in {"T5_success_reason", "T7_abort_reason", "E5_abort_only_on_error"}]
        weak = self.directory / "weak"
        weak.mkdir()
        result = check_controller(nuxmv, weak, self.c, original, model(self.c, original))
        self.assertEqual(result["status"], "WEAK_SPECIFICATION")
        self.assertEqual([m["mutant"] for m in result["mutation"] if not m["killed"]], ["M11_success_as_abort"])

    def test_monitor_triggers_are_parsed_per_property(self):
        log = "TRIGGERS\tr1\tactivity:9,commit:2,energy:6,stopped:1,validated:6\nRESULT\tr1\t\nTRIGGERS\tr2\tactivity:1,stopped:1\nRESULT\tr2\tL4_noActivityAfterStop:1\n"
        violations, events = monitor_outcomes(log)
        self.assertEqual(violations, {"r1": {}, "r2": {"L4_noActivityAfterStop": 1}})
        record = dejavu_record(violations["r2"], events["r2"])
        self.assertFalse(record["passed"])
        self.assertEqual(record["triggers"], {"L1_groupsBeforeEnergy": 0, "L2_validationsBeforeCommit": 0,
                                              "L3_energyAfterBegin": 0, "L3_validationAfterEnergy": 0, "L4_noActivityAfterStop": 1})

    def test_projection_drift_is_detected(self):
        if not (shutil.which("java") and shutil.which("jar")):
            self.skipTest("Java unavailable")
        try:
            monitor = temporal.build_monitor(self.directory)
        except (FileNotFoundError, RuntimeError, ValueError) as error:
            self.skipTest(f"DejaVu monitor cannot be built here: {error}")
        monitor["monitor_jar"] = "runtime-monitor.jar"
        path, result = self.run_trace()
        result["trace"] = path.name
        original = temporal.project
        def without_commit(e):
            return ((name, args) for name, args in original(e) if name != "commit")
        temporal.verify_traces(self.directory, self.directory, [copy.deepcopy(result)], monitor)
        temporal.project = without_commit
        self.addCleanup(setattr, temporal, "project", original)
        with self.assertRaisesRegex(RuntimeError, "projection drift"):
            temporal.verify_traces(self.directory, self.directory, [result], monitor)

    def test_grid_wrap_and_tie_order(self):
        candidates = candidate_indices([0, 15, 3, 4], 0, 16)
        self.assertEqual(candidates[1], [15, 15, 3, 4])
        self.assertEqual(candidates[2], [1, 15, 3, 4])

    def test_circuit_measurements_and_hamiltonian_match(self):
        indices = [[0, 0, 0, 0], [3, 11, 6, 14], [15, 15, 15, 15]]
        energy, probabilities = measurement_data(indices, 16)
        self.assertTrue(np.allclose(probabilities.sum(axis=2), 1))
        self.assertTrue(np.all(np.isfinite(energy)))
        # At zero angles the declared gate sequence produces |q1 q0> = |01>.
        self.assertTrue(np.allclose(probabilities[0, 0], [0, 1, 0, 0], atol=1e-12))
        self.assertAlmostEqual(float(energy[0]), -0.3867, places=12)

    def test_gaussian_forward_result_matches_explicit_path_enumeration(self):
        c = dict(self.c, grid_size=3, initial_index=[0, 1, 2, 0])
        kernels, success, result = build_gaussian(c)
        mass = {tuple(c["initial_index"]): 1.0}
        cumulative = 0.0
        for step in range(c["maximum_updates"] + 1):
            cumulative += sum(p for index, p in mass.items() if success[index])
            mass = {index: p for index, p in mass.items() if not success[index]}
            self.assertAlmostEqual(cumulative, result["success_cdf"][step], places=12)
            if step == c["maximum_updates"]:
                break
            next_mass = {}
            coord = step % 4
            for index, p in mass.items():
                for choice, dest in enumerate(candidate_indices(index, coord, 3)):
                    key = tuple(dest)
                    next_mass[key] = next_mass.get(key, 0) + p * kernels[coord, choice][index]
            mass = next_mass

    def test_invalid_configuration_is_rejected(self):
        for key, value in [("grid_size", 2), ("shots_per_group", 0), ("environment", "unmodeled-noise"), ("initial_index", [0, 0, 0, 99])]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_config(dict(self.c, **{key: value}))

    def test_frozen_stage1_detects_changed_evidence(self):
        d = self.directory / "stage1"
        d.mkdir()
        evidence = d / "proof.log"
        evidence.write_text("original proof")
        record = {"configuration": self.c, "configuration_digest": digest(self.c), "sources": source_hashes(), "artifacts": {"stage1/proof.log": file_hash(evidence)}, "ready_for_execution": True}
        path = d / "pre_execution.json"
        save_json(path, record)
        save_json(path.with_suffix(".seal.json"), {"sha256": file_hash(path)})
        validate_frozen(self.directory)
        evidence.write_text("replaced proof")
        with self.assertRaisesRegex(ValueError, "evidence changed"):
            validate_frozen(self.directory)

    def test_wilson_and_conditional_mean_boundaries(self):
        self.assertEqual(wilson(0, 400)[0], 0)
        self.assertEqual(wilson(400, 400)[1], 1)
        self.assertIsNone(wilson(0, 0))
        self.assertIsNone(mean_interval([], self.c))
        self.assertEqual(mean_interval([7, 7, 7], self.c), [7, 7])


if __name__ == "__main__":
    unittest.main()
