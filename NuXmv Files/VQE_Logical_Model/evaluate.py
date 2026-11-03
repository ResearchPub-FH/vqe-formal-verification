"""Layer-wise evaluation of the VQE logical model (Section VI-B).

The model and its obligations come from the two-stage experiment's generator
(2-stage verification (closed-loop)/closed_loop/logical.py), so this folder and
Stage 1 check the same model. For each (MAX_ITERS, NTERMS) bound this script
checks every property, counts reachable states, times the property check
(median of repeated runs), and runs the Stage 1 gate: non-vacuity witnesses,
consequent probes, branch coverage and the seeded mutants.

Run from anywhere with Python 3.8+ and NumPy:  python3 evaluate.py
"""
import csv
import json
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
sys.path.insert(0, str(WORKSPACE / "2-stage verification (closed-loop)"))
from closed_loop.common import ROOT, read_config  # noqa: E402
from closed_loop.logical import bounds, model, mutants, requirements  # noqa: E402
from closed_loop.pre_execution import SPECIFICATION, check_controller, tool_path  # noqa: E402

NUXMV = tool_path("nuXmv")
RESULTS = HERE / "results"
# (MAX_ITERS, NTERMS): the earlier sweep's four pairs, the paper instance (Table II) and its largest variant.
SWEEP = [(3, 2), (5, 3), (10, 5), (20, 10), (50, 3), (50, 10)]
REPEATS = 5


def configuration(k, groups):
    c = read_config(ROOT / "config/h2.json")
    c["maximum_updates"] = k
    c["measurement_groups"] = [["G%d" % i] for i in range(groups)]  # only the count enters the model
    return c


def run(args, cwd):
    started = time.perf_counter()
    text = subprocess.run([str(a) for a in args], capture_output=True, text=True, cwd=cwd).stdout
    return text, time.perf_counter() - started


def evaluate(k, groups, directory):
    directory.mkdir(parents=True, exist_ok=True)
    c = configuration(k, groups)
    props = requirements(c)
    smv = directory / "model.smv"
    smv.write_text(model(c, props))
    times = []
    for _ in range(REPEATS):
        text, seconds = run([NUXMV, smv.name], directory)
        times.append(seconds)
    (directory / "properties.log").write_text(text)
    results = SPECIFICATION.findall(text)
    (directory / "reachable.cmd").write_text("read_model -i model.smv\ngo\nprint_reachable_states\nquit\n")
    reach_text, _ = run([NUXMV, "-source", "reachable.cmd"], directory)
    match = re.search(r"reachable states: (\S+) .*? out of (\S+)", reach_text)
    (directory / "gate").mkdir(exist_ok=True)
    gate = check_controller(NUXMV, directory / "gate", c, props, model(c, props))
    queries = gate["nonvacuity"]["results"] or []
    return {
        "MAX_ITERS": k, "NTERMS": groups, "NCANDS": bounds(c)[2],
        "properties": len(props),
        "kinds": {kind: sum(p["kind"] == kind for p in props) for kind in ("INVARSPEC", "LTLSPEC", "CTLSPEC")},
        "true": sum(r == "true" for _, r in results), "false": sum(r == "false" for _, r in results),
        "check_seconds_median": statistics.median(times), "check_seconds_all": times,
        "reachable_states": float(match[1]) if match else None, "encoded_states": float(match[2]) if match else None,
        "gate_status": gate["status"],
        "nonvacuity_queries": len(queries), "nonvacuity_as_expected": sum(q["as_expected"] for q in queries),
        "unreachable_branches": [q["branch"] for q in queries if q["kind"] == "branch" and not q["holds"]],
        "mutants_killed": sum(m["killed"] for m in gate["mutation"]), "mutants": len(gate["mutation"]),
        "gate": gate,
    }


def main():
    RESULTS.mkdir(exist_ok=True)
    paper = read_config(ROOT / "config/h2.json")
    (HERE / "vqe_logical.smv").write_text(model(paper))
    rows = []
    for k, groups in SWEEP:
        print(f"MAX_ITERS={k} NTERMS={groups}", flush=True)
        rows.append(evaluate(k, groups, RESULTS / f"K{k}_G{groups}"))
    with open(RESULTS / "scaling.csv", "w", newline="") as f:
        fields = ["MAX_ITERS", "NTERMS", "NCANDS", "properties", "true", "false", "check_seconds_median",
                  "reachable_states", "encoded_states", "gate_status", "nonvacuity_as_expected",
                  "nonvacuity_queries", "mutants_killed", "mutants"]
        writer = csv.DictWriter(f, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    instance = next(r for r in rows if (r["MAX_ITERS"], r["NTERMS"]) == bounds(paper)[:2])
    gate = instance["gate"]
    with open(RESULTS / "properties.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "contract", "kind", "formula", "holds"])
        kinds = {p["name"]: p["kind"] for p in requirements(paper)}
        for p in gate["properties"]:
            writer.writerow([p["name"], p["contract"], kinds[p["name"]], p["formula"], p["holds"]])
    with open(RESULTS / "nonvacuity.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "kind", "contract", "formula", "expected", "holds", "as_expected"])
        for q in gate["nonvacuity"]["results"]:
            writer.writerow([q["id"], q["kind"], q.get("contract", ""), q["formula"], q["expected"], q["holds"], q["as_expected"]])
    with open(RESULTS / "mutants.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["mutant", "target_contract", "killed", "detected_by", "failing_properties"])
        for m in gate["mutation"]:
            writer.writerow([m["mutant"], m["target_contract"], m["killed"], " ".join(m["detected_by"]), " ".join(m["failing_properties"])])
    summary = [{key: value for key, value in r.items() if key != "gate"} for r in rows]
    (RESULTS / "summary.json").write_text(json.dumps({"nuXmv": NUXMV, "paper_instance": list(bounds(paper)), "sweep": summary}, indent=1) + "\n")
    for r in summary:
        print(f"({r['MAX_ITERS']},{r['NTERMS']}): {r['true']}/{r['properties']} true, {r['check_seconds_median']:.3f} s, "
              f"{r['reachable_states']:.0f} reachable, gate {r['gate_status']}, "
              f"{r['nonvacuity_as_expected']}/{r['nonvacuity_queries']} queries, {r['mutants_killed']}/{r['mutants']} mutants")


if __name__ == "__main__":
    main()
