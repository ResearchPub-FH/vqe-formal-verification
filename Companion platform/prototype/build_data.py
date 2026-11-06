"""Collect the prototype's data bundle from the delivered closed-loop run (merged-model-01)
and the ibm_marrakesh hardware pair (VQE Runtime Verification - DejaVu/artifacts/hardware_pair_hrzy).

Reads only existing evidence; runs no verification tool. Writes data.js next to this file,
which defines window.VQE_DATA for index.html.
"""
from __future__ import annotations

import csv
import gzip
import json
import re
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
CLOSED = PROJECT / "2-stage verification (closed-loop)"
RUN = CLOSED / "artifacts" / "merged-model-01"
DEJAVU = PROJECT / "VQE Runtime Verification - DejaVu"
HW = DEJAVU / "artifacts" / "hardware_pair_hrzy" / "pair01"
sys.path.insert(0, str(CLOSED))

from closed_loop import logical, physics  # noqa: E402

TERMS = ["YZ", "ZI", "ZZ", "XX"]


def read_trace(path):
    with gzip.open(path, "rt") as stream:
        return [json.loads(line) for line in stream]


def energy(expectations, coefficients):
    return sum(coefficients[t] * expectations[t] for t in TERMS) / 10000


def run_summary(events):
    """Per-update view of one baseline run, plus the event skeleton used to animate modes."""
    updates, current = [], None
    skeleton = []
    for e in events:
        kind = e["type"]
        skeleton.append([kind, e.get("update", 0), e.get("candidate", -1), e.get("group", -1)])
        if kind == "update_start":
            current = {"update": e["update"], "coordinate": e["coordinate"], "index": e["index"],
                       "candidates": [{"index": c, "groups": [None] * 3} for c in e["candidates"]]}
        elif kind == "measurement":
            current["candidates"][e["candidate"]]["groups"][e["group"]] = e["counts"]
        elif kind == "evaluation":
            cand = current["candidates"][e["candidate"]]
            cand.update(expectations=e["expectations"], contributions=e["contributions"],
                        energy=e["energy"], score=e["score"])
        elif kind == "optimizer_commit":
            current.update(choice=e["choice"], index_after=e["index_after"], shots=e["physical_shots"],
                           ideal_after=physics.point(tuple(e["index_after"]), 16)[0])
            updates.append(current)
    terminal = events[-1]
    start = events[0]["index"]
    return {"run_id": events[0]["run_id"], "start_index": start,
            "ideal_start": physics.point(tuple(start), 16)[0],
            "updates": updates, "terminal": {k: terminal[k] for k in ("reason", "updates", "physical_shots", "index")},
            "skeleton": skeleton}


def swapped_choices(updates, coefficients):
    """The fault 'coefficient_swap' exchanges the YZ and XX coefficients (closed_loop/execution.py)."""
    swapped = dict(coefficients, YZ=coefficients["XX"], XX=coefficients["YZ"])
    rows = []
    for u in updates:
        right = [c["energy"] for c in u["candidates"]]
        wrong = [energy(c["expectations"], swapped) for c in u["candidates"]]
        rows.append({"update": u["update"], "correct": right, "swapped": wrong,
                     "choice": u["choice"], "swapped_choice": min(range(3), key=lambda i: (wrong[i], i))})
    return {"swapped_coefficients": swapped, "rows": rows}


def hardware_pair(coefficients):
    """The ibm_marrakesh pair (unverified then verified run, one declared configuration).

    Energies are recomputed from the recorded per-term expectations with the declared
    coefficients (checked against the recorded energy) and with YZ and XX swapped. The
    pattern search accepts a probe iff its energy is below the incumbent's by more than
    the improvement tolerance; a flip marks a probe whose accept/reject decision would
    differ under the swapped coefficients, with the incumbent held on the recorded path.
    """
    config = tomllib.loads((DEJAVU / "configs" / "h2_ibm_sampler_50.toml").read_text())
    tolerance = config["optimizer"]["improvement_tolerance"]
    swapped = dict(coefficients, YZ=coefficients["XX"], XX=coefficients["YZ"])
    report = json.loads((HW / "pair_report.json").read_text())
    props = json.loads((HW / "property_report.json").read_text())
    runs = {}
    for condition in report["order"]:
        rows = [json.loads(line) for line in (HW / condition / "evaluations.jsonl").read_text().splitlines()]
        expectations = [{t["pauli"]: t["expectation"] for t in r["terms"]} for r in rows]
        declared = [energy(e, coefficients) for e in expectations]
        for r, e in zip(rows, declared):
            assert abs(r["energy"] - e) < 1e-12, (condition, r["evaluation"])
        other = [energy(e, swapped) for e in expectations]
        incumbent, accepted, flips = 0, [True], []
        for k in range(1, len(rows)):
            take = declared[k] < declared[incumbent] - tolerance
            if take != (other[k] < other[incumbent] - tolerance):
                flips.append(k)
            accepted.append(take)
            if take:
                incumbent = k
        summary = report["energy"][condition]
        runs[condition] = {"run_id": report[condition]["run_id"], "declared": declared, "swapped": other,
                           "accepted": accepted, "flips": flips, "theta": [r["theta"] for r in rows],
                           "terminal": report[condition]["terminal_reason"], "best_measured": summary["best_measured"],
                           "exact_at_final": summary["exact_at_final"], "ibm_seconds": report[condition]["ibm_seconds"]}
    return {"backend": report["backend"], "qubits": report["logical_to_physical"], "order": report["order"],
            "evaluations": config["execution"]["max_iterations"], "shots_per_term": config["execution"]["shots_per_term"],
            "optimizer": config["optimizer"]["name"], "initial_step": config["optimizer"]["initial_step"],
            "runs": runs,
            "verified_monitor": {"online": props["online_status"], "replay": props["replay_status"],
                                 "obeyed_online": props["obeyed_online"], "obeyed_replay": props["obeyed_replay"],
                                 "properties": len(props["rows"]), "events": props["events_online"],
                                 "coverage": props["coverage"]}}


def squash(formula):
    return re.sub(r"[\s()]", "", formula).replace("union", ",").replace("in{", "in").replace("}", "")


def parse_counterexamples(log_text, props):
    """Counterexample traces from a nuXmv log, keyed by property name."""
    by_formula = {squash(p["formula"]): p["name"] for p in props}
    out = {}
    lines = log_text.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"-- (?:invariant|specification) (.*) is false$", lines[i].strip())
        if not m:
            i += 1
            continue
        name = by_formula.get(squash(m.group(1)))
        steps, values, loop_at = [], {}, None
        i += 1
        while i < len(lines) and not re.match(r"-- (invariant|specification) ", lines[i].strip()):
            line = lines[i].strip()
            if line.startswith("-> State:"):
                steps.append(None)
            elif line.startswith("-- Loop starts here"):
                loop_at = len(steps)
            elif steps and "=" in line and not line.startswith("--") and not line.startswith("->"):
                key, value = [part.strip() for part in line.split("=", 1)]
                values[key] = value
                steps[-1] = dict(values)
            i += 1
        steps = [s for s in steps if s]
        if name:
            out[name] = {"steps": compress(steps), "length": len(steps), "loop_at": loop_at}
    return out


KEEP = ["state", "iter", "cands_done", "terms_done", "circ_ready", "params_ready", "energy_ready",
        "bound_version", "bound_cand", "energy_version", "term_reason", "converged", "error",
        "bind_fails", "measure_fails", "energy_fails", "optimizer_fails", "qpu_error"]


def compress(steps):
    """Keep the first iteration and the last one in full; summarize the repeated middle."""
    slim = [{k: s[k] for k in KEEP if k in s} for s in steps]
    checks = [i for i, s in enumerate(slim) if s["state"] == "CHECK_STOP"]
    if len(slim) <= 40 or len(checks) < 4:
        return slim
    head_end, tail_start = checks[1] + 1, checks[-2]
    skipped = slim[head_end:tail_start]
    marker = {"skip": True, "steps": len(skipped),
              "from_iter": int(slim[head_end]["iter"]), "to_iter": int(slim[tail_start]["iter"])}
    return slim[:head_end] + [marker] + slim[tail_start:]


def property_class(name):
    return {"R": "Readiness", "F": "Freshness", "T": "Termination", "E": "Failure handling"}[name[0]]


def main():
    config = json.loads((CLOSED / "config" / "h2.json").read_text())
    pre = json.loads((RUN / "stage1" / "pre_execution.json").read_text())
    verdicts = json.loads((RUN / "comparison" / "verdict_agreement.json").read_text())
    props = logical.requirements(config)

    baseline_dir = RUN / "stage2" / "baseline"
    traces = sorted(baseline_dir.glob("baseline-*.jsonl.gz"))
    run = run_summary(read_trace(traces[0]))
    why = swapped_choices(run["updates"], config["hamiltonian"]["terms"])

    first_success = []
    for path in traces:
        with gzip.open(path, "rt") as stream:
            last = json.loads(stream.read().strip().splitlines()[-1])
        first_success.append(last["updates"] if last["reason"] == "success" else None)
    empirical_cdf = [sum(1 for k in first_success if k is not None and k <= bound) / len(first_success)
                     for bound in range(config["maximum_updates"] + 1)]

    mutants = []
    for m in pre["logical"]["mutation"]:
        log = (RUN / "stage1" / f"mutant-{m['mutant']}.log").read_text()
        mutants.append({"name": m["mutant"], "target": m["target_contract"], "detected_by": m["detected_by"],
                        "failing": m["failing_properties"], "killed": m["killed"],
                        "edits": m["edits"], "counterexamples": parse_counterexamples(log, props)})

    nonvacuity = pre["logical"]["nonvacuity"]["results"]
    fault_rows = list(csv.DictReader((CLOSED / "paper" / "data" / "fault_figure_points.csv").open()))
    faults = {}
    for row in fault_rows:
        f = faults.setdefault(row["fault"], {"fault": row["fault"], "runs": int(row["n"]),
                                             "detected": int(row["detected"]), "dejavu_passed": int(row["dejavu_passed"]),
                                             "expected_contract": row["expected_contract"],
                                             "expected_verdict": row["expected_verdict"], "vector": {}})
        f["vector"][row["contract"]] = row["verdict"]

    data = {
        "source": "2-stage verification (closed-loop)/artifacts/merged-model-01",
        "config": {k: config[k] for k in ("hamiltonian", "measurement_groups", "shots_per_group", "grid_size",
                                          "initial_index", "maximum_updates", "success_gap", "runs", "coordinate_schedule")},
        "ground_energy": physics.GROUND_ENERGY,
        "run": run,
        "why": why,
        "branches": logical.state_branches(config),
        "properties": [dict(p, cls=property_class(p["name"]), holds=True) for p in props],
        "nonvacuity": {"queries": len(nonvacuity), "as_expected": sum(1 for q in nonvacuity if q["as_expected"]),
                       "kinds": {k: sum(1 for q in nonvacuity if q["id"].startswith(k)) for k in ("W_", "C_", "B_")}},
        "mutants": mutants,
        "probabilistic": {"model_cdf": pre["probabilistic"]["success_cdf"], "empirical_cdf": empirical_cdf,
                          "checkpoints": verdicts["probability_comparison"],
                          "conditional_means": verdicts["conditional_means"],
                          "dtmc_states": pre["probabilistic"]["dtmc_states"],
                          "transitions": pre["probabilistic"]["transitions"]},
        "contracts": {k: {"description": v["description"], "family": v["family"], "stage1": v["stage1"],
                          "stage2": v["stage2"], "verdict": v["pre_execution_verdict"]}
                      for k, v in pre["contracts"].items()},
        "agreement": verdicts["logical_numeric"],
        "totals": {"runs": verdicts["baseline_runs"], "successes": verdicts["successes"],
                   "shots": verdicts["total_physical_shots"], "dejavu_passed": verdicts["dejavu_baseline_passed"],
                   "online_replay_agreement": verdicts["online_replay_agreement"],
                   "max_energy_error": verdicts["maximum_energy_reconstruction_error"],
                   "stage1_digest": verdicts["pre_execution_digest"], "config_digest": verdicts["configuration_digest"]},
        "faults": list(faults.values()),
        "hardware": hardware_pair(config["hamiltonian"]["terms"]),
    }
    out = HERE / "data.js"
    out.write_text("window.VQE_DATA = " + json.dumps(data, separators=(",", ":")) + ";\n")
    flips = [r["update"] for r in why["rows"] if r["choice"] != r["swapped_choice"]]
    print(f"wrote {out} ({out.stat().st_size // 1024} KB); updates {len(run['updates'])}; swap flips at {flips[:8]}")
    for m in mutants:
        print(m["name"], m["failing"], {k: (v["length"], len(v["steps"])) for k, v in m["counterexamples"].items()})


if __name__ == "__main__":
    main()
