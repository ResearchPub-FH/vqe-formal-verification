"""Independent runtime reconstruction from counts and the frozen manifest.

This module never calls the execution energy/scoring routine. Numeric validity
events are accepted only after checking their underlying measurements.
"""
from __future__ import annotations

import math
from fractions import Fraction
from .common import CONTRACTS, digest
from .physics import ideal_success

# Core obligations per contract, counted where their antecedent is evaluated.
# A contract cannot agree unless each of its obligations fired at least once;
# an unexercised obligation is INCONCLUSIVE rather than a vacuous AGREEMENT.
OBLIGATIONS = {
    "L1": ("groups_before_energy",),
    "L2": ("validation_certified", "validations_before_commit"),
    "L3": ("evaluation_identity_current", "commit_identity_current"),
    "L4": ("terminal_reason",),
    "N1": ("expectation_reconstructed",),
    "N2": ("energy_reconstructed",),
    "N3": ("allocation_checked", "cumulative_total_checked"),
    "N4": ("candidates_generated", "selection_checked"),
}


def finite(x):
    return type(x) in (int, float) and math.isfinite(x)


def exact_error(observed, expected):
    """Retain floating-point rounding error relative to the rational reference."""
    return abs(Fraction(observed) - expected) if finite(observed) else None


def expected_candidates(index, coordinate, grid):
    result = []
    for step in (0, -1, 1):
        candidate = list(index)
        candidate[coordinate] = (candidate[coordinate] + step) % grid
        result.append(candidate)
    return result


def reconstruct(group_counts, c):
    expectations = {}
    for group_id, terms in enumerate(c["measurement_groups"]):
        counts = group_counts[group_id]
        total = sum(counts)
        for term in terms:
            # Basis rotations map each non-identity Pauli to a measured Z bit.
            mask = sum(1 << (1 - j) for j, pauli in enumerate(term) if pauli != "I")
            signed = sum(n * (-1 if (outcome & mask).bit_count() % 2 else 1) for outcome, n in enumerate(counts))
            expectations[term] = Fraction(signed, total)
    coefficients = c["hamiltonian"]["terms"]
    scale = c["hamiltonian"]["coefficient_scale"]
    contributions = {term: Fraction(coefficients[term], scale) * expectation for term, expectation in expectations.items()}
    return expectations, contributions, sum(contributions.values(), Fraction(0))


class RuntimeChecker:
    def __init__(self, config, run_id, pre_digest):
        self.c = config
        self.run_id = run_id
        self.pre_digest = pre_digest
        self.config_digest = digest(config)
        self.seq = 0
        self.started = False
        self.closed = False
        self.index = list(config["initial_index"])
        self.updates = 0
        self.active = None
        self.physical_shots = 0
        self.shot_evidence_complete = True
        self.terminal_reason = None
        self.success_step = None
        self.max_energy_error = 0.0
        self.max_expectation_error = 0.0
        self.rows = {key: {"checks": 0, "violations": [], "assumption_mismatches": [], "inconclusive": []} for key in CONTRACTS if not key.startswith("P")}
        self.triggers = {key: dict.fromkeys(OBLIGATIONS[key], 0) for key in self.rows}

    def fire(self, cid, obligation):
        self.triggers[cid][obligation] += 1

    def issue(self, cid, kind, message):
        bucket = self.rows[cid][kind]
        if len(bucket) < 100:
            bucket.append({"seq": self.seq, "message": message})

    def require(self, cid, condition, message, kind="violations"):
        self.rows[cid]["checks"] += 1
        if not condition:
            self.issue(cid, kind, message)
        return bool(condition)

    def problems(self):
        return sum(len(row[kind]) for row in self.rows.values() for kind in ("violations", "assumption_mismatches", "inconclusive"))

    def consume(self, e):
        before = self.problems()
        expected_seq = self.seq + 1
        self.seq = e.get("seq", expected_seq)
        self.require("L3", type(self.seq) is int and self.seq == expected_seq, "nonconsecutive event sequence")
        self.require("L3", e.get("run_id") == self.run_id, "run identity mismatch")
        self.require("L3", e.get("configuration_digest") == self.config_digest, "configuration digest differs from Stage 1", "assumption_mismatches")
        if self.closed:
            self.require("L4", False, "event after terminal event")
            return False
        self.rows["L4"]["checks"] += 1
        kind = e.get("type")
        try:
            handler = getattr(self, "on_" + str(kind))
        except AttributeError:
            self.require("L3", False, f"unknown event type: {kind}")
            return False
        if kind != "run_start" and not self.started:
            self.require("L3", False, "event before run_start")
            return False
        try:
            handler(e)
        except (KeyError, TypeError, ValueError, ZeroDivisionError, IndexError, OverflowError) as error:
            self.require("L3", False, f"malformed {kind} event: {type(error).__name__}: {error}")
        return self.problems() == before

    def on_run_start(self, e):
        self.require("L3", not self.started and self.seq == 1, "run_start must occur once at the beginning")
        self.require("L3", e.get("pre_execution_digest") == self.pre_digest, "wrong Stage 1 record", "assumption_mismatches")
        self.require("N4", e.get("index") == self.index, "incorrect initial parameter index")
        self.started = True

    def on_update_start(self, e):
        self.require("L2", self.active is None or self.active["committed"], "previous update was not committed")
        u = e["update"]
        self.require("L3", type(u) is int and u == self.updates + 1, "incorrect update number")
        self.require("L4", self.updates < self.c["maximum_updates"] and not ideal_success(self.index, self.c), "continued after declared stopping condition")
        self.require("L3", e["index"] == self.index, "stale update parameter state")
        coord = self.c["coordinate_schedule"][self.updates % 4]
        candidates = expected_candidates(self.index, coord, self.c["grid_size"])
        self.fire("N4", "candidates_generated")
        self.require("N4", e["coordinate"] == coord and e["candidates"] == candidates, "wrong coordinate/candidate generation")
        self.active = {"update": u, "candidates": candidates, "measurements": {}, "evaluations": {}, "validated": set(), "validation_events": set(), "committed": False}

    def context(self, e):
        if not self.require("L3", self.active is not None and not self.active["committed"], "no open update for evaluation"):
            return None
        candidate = e.get("candidate")
        if not self.require("N4", type(candidate) is int and 0 <= candidate < 3, "invalid candidate identity"):
            return None
        u = self.active["update"]
        self.fire("L3", "evaluation_identity_current")
        self.require("L3", e.get("update") == u and e.get("evaluation_id") == f"{self.run_id}:u{u}:c{candidate}", "stale/mismatched evaluation identity")
        self.require("L3", e.get("index") == self.active["candidates"][candidate], "measurement/evaluation belongs to wrong parameters")
        theta = e.get("theta")
        angles = [2 * math.pi * z / self.c["grid_size"] for z in self.active["candidates"][candidate]]
        self.require("N4", isinstance(theta, list) and len(theta) == 4 and all(finite(x) and abs(x - y) <= 1e-12 for x, y in zip(theta, angles)), "bound angles do not match the declared grid indices")
        return candidate

    def on_measurement(self, e):
        candidate = self.context(e)
        if candidate is None:
            return
        group = e.get("group")
        if not self.require("L1", type(group) is int and 0 <= group < 3, "unknown measurement group"):
            return
        key = (candidate, group)
        if not self.require("L1", key not in self.active["measurements"] and candidate not in self.active["evaluations"], "duplicate or late measurement"):
            return
        counts = e.get("counts")
        if counts is None:
            self.require("L1", False, "required raw measurement evidence is missing")
            self.issue("N1", "inconclusive", "raw counts unavailable")
            self.active["measurements"][key] = None
            self.shot_evidence_complete = False
            if type(e.get("shots")) is int and e["shots"] >= 0:
                self.physical_shots += e["shots"]
            self.issue("N3", "inconclusive", "reported shot total cannot be certified without raw counts")
            return
        valid = isinstance(counts, list) and len(counts) == 4 and all(type(n) is int and n >= 0 for n in counts) and sum(counts) > 0
        if not self.require("N1", valid, "invalid raw outcome counts", "assumption_mismatches"):
            self.active["measurements"][key] = None
            self.shot_evidence_complete = False
            if type(e.get("shots")) is int and e["shots"] >= 0:
                self.physical_shots += e["shots"]
            return
        shots = sum(counts)
        self.require("N1", type(e.get("shots")) is int and e["shots"] == shots, "shot metadata disagrees with raw counts", "assumption_mismatches")
        self.fire("N3", "allocation_checked")
        self.require("N3", shots == self.c["shots_per_group"], "physical shots differ from the frozen allocation", "assumption_mismatches")
        self.physical_shots += shots
        self.rows["N3"]["checks"] += 1
        self.active["measurements"][key] = counts

    def on_evaluation(self, e):
        candidate = self.context(e)
        if candidate is None:
            return
        self.require("L1", candidate not in self.active["evaluations"], "duplicate energy evaluation")
        groups = [self.active["measurements"].get((candidate, g)) for g in range(3)]
        self.fire("L1", "groups_before_energy")
        if not self.require("L1", all(x is not None for x in groups), "aggregation lacks complete raw measurements"):
            self.issue("N2", "inconclusive", "cannot reconstruct energy without all group counts")
            self.active["evaluations"][candidate] = {"exact_energy": None, "exact_score": None,
                "reported_energy": e.get("energy"), "valid": False, "incomplete": True}
            return
        expectations, contributions, energy = reconstruct(groups, self.c)
        before = self.problems()
        coefficients = self.c["hamiltonian"]["terms"]
        self.require("N2", e.get("coefficients") == coefficients, "coefficient-to-term association differs from the frozen Hamiltonian")
        self.require("N1", set(e.get("expectations", {})) == set(expectations), "expectation term set is incomplete")
        self.require("N2", set(e.get("contributions", {})) == set(contributions), "contribution term set is incomplete")
        for term, expected in expectations.items():
            self.fire("N1", "expectation_reconstructed")
            observed = e.get("expectations", {}).get(term)
            error = exact_error(observed, expected)
            if error is not None:
                self.max_expectation_error = max(self.max_expectation_error, float(error))
            self.require("N1", error is not None and error <= Fraction(str(self.c["expectation_tolerance"])) and -1 <= expected <= 1, f"{term} expectation disagrees with raw parity counts")
            contribution = e.get("contributions", {}).get(term)
            contribution_error = exact_error(contribution, contributions[term])
            self.require("N2", contribution_error is not None and contribution_error <= Fraction(str(self.c["energy_tolerance"])), f"{term} contribution is incorrect")
        observed = e.get("energy")
        error = exact_error(observed, energy)
        if error is not None:
            self.max_energy_error = max(self.max_energy_error, float(error))
        self.fire("N2", "energy_reconstructed")
        self.require("N2", error is not None and error <= Fraction(str(self.c["energy_tolerance"])), "candidate energy differs from exact rational reconstruction")
        score = energy * self.c["hamiltonian"]["coefficient_scale"] * sum(groups[0])
        self.require("N2", type(e.get("score")) is int and e["score"] == score, "candidate selection score is incorrect")
        self.active["evaluations"][candidate] = {"exact_energy": energy, "exact_score": score, "reported_energy": observed, "valid": before == self.problems(), "incomplete": False}

    def on_numeric_valid(self, e):
        candidate = self.context(e)
        if candidate is None:
            return
        evaluation = self.active["evaluations"].get(candidate)
        self.fire("L2", "validation_certified")
        if not self.require("L2", evaluation is not None and candidate not in self.active["validation_events"], "numeric validity lacks a unique preceding evaluation"):
            return
        self.active["validation_events"].add(candidate)
        if evaluation["incomplete"]:
            self.issue("L2", "inconclusive", "cannot certify numeric validity because measurement evidence is incomplete")
        elif self.require("L2", evaluation["valid"], "numeric validity follows a failed numeric check"):
            self.active["validated"].add(candidate)

    def on_optimizer_commit(self, e):
        self.fire("L2", "validations_before_commit")
        if not self.require("L2", self.active is not None and not self.active["committed"], "commit lacks a unique open update"):
            return
        self.fire("L3", "commit_identity_current")
        self.require("L3", e.get("update") == self.active["update"], "commit uses a stale update")
        if not self.require("L2", self.active["validation_events"] == {0, 1, 2}, "optimizer committed before all three numeric validation events"):
            return
        evaluations = self.active["evaluations"]
        choice = e.get("choice")
        self.fire("N4", "selection_checked")
        if not self.require("N4", type(choice) is int and 0 <= choice < 3, "invalid selected candidate identity"):
            return
        incomplete = any(v["incomplete"] for v in evaluations.values())
        if incomplete:
            self.issue("L2", "inconclusive", "commit ordering was observed but one numeric certificate is uncheckable")
            self.issue("N4", "inconclusive", "cannot determine the minimum-energy candidate without complete measurements")
        else:
            self.require("L2", self.active["validated"] == {0, 1, 2}, "optimizer committed after a failed numeric check")
            expected_choice = min(range(3), key=lambda j: evaluations[j]["exact_energy"])
            self.require("N4", choice == expected_choice, "candidate selection or tie priority is incorrect")
        self.require("N4", e.get("index_after") == self.active["candidates"][choice], "optimizer successor is not the selected grid state")
        self.require("L3", e.get("evaluation_ids") == [f"{self.run_id}:u{self.active['update']}:c{j}" for j in range(3)], "optimizer references stale energy identities")
        used = e.get("energies_used")
        known = [j for j in range(3) if evaluations[j]["exact_energy"] is not None]
        if incomplete:
            self.issue("N2", "inconclusive", "some optimizer inputs lack complete reference measurements")
        good = isinstance(used, list) and len(used) == 3 and all(finite(used[j]) and exact_error(used[j], evaluations[j]["exact_energy"]) <= Fraction(str(self.c["energy_tolerance"])) for j in known)
        self.require("N2", good, "optimizer inputs differ from checked candidate energies")
        scores_used = e.get("scores_used")
        self.require("N2", isinstance(scores_used, list) and len(scores_used) == 3 and all(type(scores_used[j]) is int and scores_used[j] == evaluations[j]["exact_score"] for j in known), "optimizer selection scores differ from checked candidate scores")
        if self.shot_evidence_complete:
            self.fire("N3", "cumulative_total_checked")
            self.require("N3", type(e.get("physical_shots")) is int and e["physical_shots"] == self.physical_shots, "cumulative physical shot count is incorrect")
        else:
            self.issue("N3", "inconclusive", "cumulative physical shots depend on missing or invalid count evidence")
        # Follow the observed transition even when its optimality is inconclusive;
        # missing evidence must not invent stale-state violations at later steps.
        self.index = list(self.active["candidates"][choice])
        self.updates += 1
        self.active["committed"] = True
        if ideal_success(self.index, self.c) and self.success_step is None:
            self.success_step = self.updates

    def on_terminal(self, e):
        self.fire("L4", "terminal_reason")
        reason = e.get("reason")
        if reason == "success":
            self.require("L4", ideal_success(self.index, self.c), "success termination lacks the declared energy quality")
            if self.updates == 0:
                self.success_step = 0
        elif reason == "budget":
            self.require("L4", self.updates == self.c["maximum_updates"] and not ideal_success(self.index, self.c), "incorrect budget termination")
        elif reason == "contract_abort":
            self.require("L4", self.problems() > 0, "contract abort without a detected problem")
        else:
            self.require("L4", False, "unknown termination reason")
        self.require("L3", e.get("index") == self.index and e.get("updates") == self.updates, "terminal state disagrees with observed commits")
        if self.shot_evidence_complete:
            self.fire("N3", "cumulative_total_checked")
            self.require("N3", e.get("physical_shots") == self.physical_shots, "terminal shot total differs from raw evidence")
        else:
            self.issue("N3", "inconclusive", "terminal physical shot total cannot be fully certified")
        self.closed = True
        self.terminal_reason = reason

    def result(self):
        if not self.closed and not self.rows["L4"]["inconclusive"]:
            self.issue("L4", "inconclusive", "trace has no terminal event")
        rows = {}
        for cid, data in self.rows.items():
            unexercised = [{"seq": self.seq, "message": f"obligation {name} not exercised (0 triggers)"}
                           for name, count in self.triggers[cid].items() if count == 0]
            data = {**data, "inconclusive": data["inconclusive"] + unexercised, "triggers": dict(self.triggers[cid])}
            verdict = "DISAGREEMENT" if data["violations"] else "ASSUMPTION_MISMATCH" if data["assumption_mismatches"] else "INCONCLUSIVE" if data["inconclusive"] or data["checks"] == 0 else "AGREEMENT"
            rows[cid] = {**data, "runtime_verdict": verdict}
        return {"run_id": self.run_id, "events": self.seq, "updates": self.updates,
                "success_step": self.success_step, "terminal_reason": self.terminal_reason,
                "physical_shots": self.physical_shots, "shot_evidence_complete": self.shot_evidence_complete, "max_energy_error": self.max_energy_error,
                "max_expectation_error": self.max_expectation_error, "contracts": rows}
