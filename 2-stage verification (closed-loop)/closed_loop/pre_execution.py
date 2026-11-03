from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path
import numpy as np

from .common import ROOT, WORKSPACE, CONTRACTS, CONTRACT_LIBRARY, digest, file_hash, save_json, source_hashes, utc_now
from .logical import apply_mutant, model, mutants, nonvacuity_queries, requirements
from .physics import build_gaussian, export_dtmc
from .temporal import build_monitor

SPECIFICATION = re.compile(r"^-- (?:specification|invariant) (.+?)\s+is (true|false)\s*$", re.M)


def command_record(command, logfile, timeout=300, cwd=ROOT):
    started = time.perf_counter()
    try:
        completed = subprocess.run([str(x) for x in command], capture_output=True, text=True, timeout=timeout, cwd=cwd)
        text = completed.stdout + completed.stderr
        code = completed.returncode
    except (OSError, subprocess.TimeoutExpired) as error:
        text, code = str(error), None
    Path(logfile).write_text(text)
    return {"command": [str(x) for x in command], "exit_code": code,
            "elapsed_seconds": time.perf_counter() - started, "log": str(logfile)}, text


def tool_path(name):
    bundled = {
        "nuXmv": WORKSPACE / "NuXmv Files/nuXmv/bin/nuXmv",
        "dafny": WORKSPACE / "Dafny + Python trace checker/dafny/dafny",
    }
    if name in bundled and bundled[name].is_file():
        return str(bundled[name])
    found = shutil.which(name)
    if found:
        return found
    raise FileNotFoundError(f"required verifier is unavailable: {name}")


def normalized(formula):
    """nuXmv reprints formulas with its own spacing, parentheses and set syntax."""
    return re.sub(r"[\s(){}]", "", formula).replace(",", "union")


def nuxmv_failed(record, text):
    # nuXmv can exit 0 after a parser or command error, so inspect the output too.
    return record["exit_code"] != 0 or bool(re.search(r"aborting|syntax error|cannot build|undefined", text, re.I))


def check_requirements(nuxmv, smv, log, props):
    """Batch-check the LTL properties. Output order differs from declaration order, so match by formula."""
    record, text = command_record([nuxmv, smv], log)
    printed = {normalized(formula): result == "true" for formula, result in SPECIFICATION.findall(text)}
    record["properties"] = [{"name": p["name"], "contract": p["contract"], "formula": p["formula"],
                             "holds": printed.get(normalized(p["formula"]))} for p in props]
    record["tool_ok"] = not nuxmv_failed(record, text) and len(printed) == len(props) and all(p["holds"] is not None for p in record["properties"])
    record["established"] = record["tool_ok"] and all(p["holds"] for p in record["properties"])
    return record


def check_queries(nuxmv, directory, smv_name, queries, stem):
    """Check CTL queries in one nuXmv session; each command prints its own result in order."""
    script = directory / f"{stem}.cmd"
    script.write_text("\n".join([f"read_model -i {smv_name}", "go"] + [f'check_ctlspec -p "{q["formula"]}"' for q in queries] + ["quit"]) + "\n")
    record, text = command_record([nuxmv, "-s", "-source", script.name], directory / f"{stem}.log", cwd=directory)
    found = SPECIFICATION.findall(text)
    matched = len(found) == len(queries) and all(normalized(f) == normalized(q["formula"]) for (f, _), q in zip(found, queries))
    record["results"] = [{**q, "holds": r == "true", "as_expected": (r == "true") == q["expected"]}
                         for (_, r), q in zip(found, queries)] if matched and not nuxmv_failed(record, text) else None
    return record


def check_controller(nuxmv, directory, c, props, text):
    """Requirements, non-vacuity witnesses, branch coverage, and seeded-mutant kills for one controller."""
    control = directory / "controller.smv"
    control.write_text(text)
    logical = check_requirements(nuxmv, control, directory / "nuxmv.log", props)
    logical["nonvacuity"] = check_queries(nuxmv, directory, control.name, nonvacuity_queries(c, props), "nuxmv-witnesses")
    property_queries = nonvacuity_queries(c, props, branches=False)
    logical["mutation"] = []
    for mutant in mutants(c):
        stem = f"mutant-{mutant['name']}"
        smv = directory / f"{stem}.smv"
        smv.write_text(apply_mutant(text, mutant))
        requirement_run = check_requirements(nuxmv, smv, directory / f"{stem}.log", props)
        witness_run = check_queries(nuxmv, directory, smv.name, property_queries, f"{stem}-witnesses")
        failing = [p for p in requirement_run["properties"] if p["holds"] is False]
        vacuous = [q for q in witness_run["results"] or [] if not q["as_expected"]]
        detected = sorted({x["contract"] for x in failing + vacuous})
        logical["mutation"].append({
            "mutant": mutant["name"], "target_contract": mutant["contract"], "edits": mutant["edits"],
            "failing_properties": [p["name"] for p in failing], "failing_witnesses": [q["id"] for q in vacuous],
            "detected_by": detected, "killed": mutant["contract"] in detected,
            "tool_ok": requirement_run["tool_ok"] and witness_run["results"] is not None,
            "logs": [requirement_run["log"], witness_run["log"]]})
    witnesses = logical["nonvacuity"]["results"]
    witnesses_ok = witnesses is not None and all(q["as_expected"] for q in witnesses)
    mutation_tools_ok = all(m["tool_ok"] for m in logical["mutation"])
    mutation_ok = mutation_tools_ok and all(m["killed"] for m in logical["mutation"]) and \
        {p["contract"] for p in props} <= {m["target_contract"] for m in logical["mutation"]}
    if logical["established"] and witnesses_ok and mutation_ok:
        logical["status"] = "PROVED"
    elif logical["established"] and witnesses is not None and not witnesses_ok:
        logical["status"] = "VACUOUS"
    elif logical["established"] and witnesses_ok and mutation_tools_ok:
        logical["status"] = "WEAK_SPECIFICATION"
    else:
        logical["status"] = "NOT_ESTABLISHED"
    return logical


def run_pre_execution(c, output, progress=print):
    output = Path(output).resolve()
    directory = output / "stage1"
    if directory.exists():
        raise FileExistsError("Stage 1 already exists; use a new output directory to preserve prior evidence")
    tools = {name: tool_path(name) for name in ("nuXmv", "dafny", "storm")}
    directory.mkdir(parents=True)
    source_snapshot = source_hashes()
    started = utc_now()
    save_json(directory / "configuration.json", c)
    progress("Stage 1: building the DejaVu runtime contract projections", flush=True)
    temporal_monitor = build_monitor(directory)
    progress("Stage 1: checking the bounded controller, its non-vacuity witnesses, and seeded mutants with NuXmv", flush=True)
    props = requirements(c)
    logical = check_controller(tools["nuXmv"], directory, c, props, model(c, props))
    progress("Stage 1: proving numeric, group-accounting, and grid kernels with Dafny", flush=True)
    numeric = []
    for file in ("VQELemmas.dfy", "VQENumericKernels.dfy", "GroupGrid.dfy"):
        result, text = command_record([tools["dafny"], "verify", ROOT / "formal" / file, "--verification-time-limit", "60"], directory / f"dafny-{file}.log")
        match = re.search(r"finished with (\d+) verified, (\d+) errors", text)
        result["status"] = "PROVED" if result["exit_code"] == 0 and match and int(match[1]) > 0 and match[2] == "0" else "NOT_ESTABLISHED"
        result["verified_count"] = int(match[1]) if match else 0
        result["source"] = file
        numeric.append(result)
    progress("Stage 1: constructing the Gaussian DTMC from ideal group statistics", flush=True)
    kernels, success, quantitative = build_gaussian(c)
    np.savez_compressed(directory / "gaussian-kernels.npz", kernels=kernels, success=success)
    transitions, labels, edge_count = export_dtmc(directory, c, kernels, success)
    quantitative["transitions"] = edge_count
    properties = directory / "gaussian.props"
    properties.write_text("\n".join(f'"P1_{k}": P=? [ F<={k} "success" ];' for k in c["checkpoints"]) + "\n")
    progress("Stage 1: checking all configured success bounds with Storm", flush=True)
    storm, text = command_record([tools["storm"], "--explicit", transitions, labels, "--prop", properties, "--precision", "1e-12"], directory / "storm.log", timeout=600)
    # Storm 2 appends ". Exact solution." to the value, so stop before a trailing period.
    values = [float(x) for x in re.findall(r"Result \(for initial states\):\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)", text)]
    storm["results"] = dict(zip(map(str, c["checkpoints"]), values))
    differences = [abs(value - quantitative["success_cdf"][k]) for k, value in zip(c["checkpoints"], values)]
    storm["maximum_difference_from_forward_propagation"] = max(differences) if differences else None
    storm["status"] = "ESTABLISHED_FOR_GAUSSIAN_MODEL" if storm["exit_code"] == 0 and len(values) == len(c["checkpoints"]) and max(differences) <= 1e-8 else "NOT_ESTABLISHED"
    quantitative["storm"] = storm
    quantitative["conditional_expectation_provenance"] = "Python forward propagation of the same Gaussian kernel's first-success distribution; checked against Storm at declared checkpoints. These are not Storm reward-query results."
    save_json(directory / "quantitative.json", quantitative)
    numeric_ok = all(result["status"] == "PROVED" for result in numeric)
    contracts = {}
    for cid, description in CONTRACTS.items():
        status = logical["status"] if cid.startswith("L") else ("PROVED" if numeric_ok else "NOT_ESTABLISHED") if cid.startswith("N") else storm["status"]
        contracts[cid] = {**CONTRACT_LIBRARY[cid], "pre_execution_verdict": status}
        if cid.startswith("L"):
            contracts[cid]["witnesses"] = [q["formula"] for q in logical["nonvacuity"]["results"] or [] if q["kind"] == "antecedent" and q["contract"] == cid]
            contracts[cid]["killed_mutants"] = [m["mutant"] for m in logical["mutation"] if cid in m["detected_by"]]
    ready = logical["status"] == "PROVED" and numeric_ok and storm["status"] == "ESTABLISHED_FOR_GAUSSIAN_MODEL"
    if source_snapshot != source_hashes():
        raise RuntimeError("sources changed during Stage 1; rerun in a new output directory")
    artifacts = {str(p.relative_to(output)): file_hash(p) for p in directory.iterdir() if p.is_file()}
    record = {
        "schema_version": 1, "started_at": started, "frozen_at": utc_now(),
        "configuration": c, "configuration_digest": digest(c), "sources": source_snapshot,
        "tool_binaries": {name: {"path": path, "sha256": file_hash(path)} for name, path in tools.items()},
        "contracts": contracts, "logical": logical, "numeric": numeric, "probabilistic": quantitative,
        "runtime_monitor": temporal_monitor,
        "ready_for_execution": ready, "artifacts": artifacts,
        "assumptions": [
            "Logical model abstracts measurements and arithmetic into counters, readiness flags and nondeterministic outcomes; L3's (iteration, candidate) version abstraction is strengthened by concrete runtime identity checks.",
            "Logical non-vacuity is checked on the same bounded abstraction: every antecedent disjunct is reachable, no consequent is invariant on its own, the defensive default branch is unreachable, and each seeded control mutant is detected by its contract.",
            "Dafny verifies real/integer kernels, not the entire Python program or a floating-point compiler refinement. Runtime checks actual observed outputs against exact rational reconstruction within frozen tolerances.",
            "Circuit generation, measurement-basis interpretation, event instrumentation, proof tools, and the independent checker are in the trusted base.",
            "Measurements follow ideal Born probabilities, independent across groups/candidates and executions; within-group correlations are retained.",
            "Gaussian selection is approximate; finite-shot ties use current/minus/plus priority, while the continuous Gaussian model has zero tie probability.",
            "Ideal-energy success is a simulator benchmark oracle, not a hardware-observed stopping certificate.",
            "The 50-update probability is the primary comparison. Other checkpoints and conditional means are supporting marginal comparisons, not a simultaneous-confidence claim.",
        ],
    }
    record_path = directory / "pre_execution.json"
    save_json(record_path, record)
    save_json(record_path.with_suffix(".seal.json"), {"sha256": file_hash(record_path), "frozen_at": record["frozen_at"]})
    progress(f"Stage 1 frozen: ready_for_execution={ready}", flush=True)
    if not ready:
        raise RuntimeError("Stage 1 did not establish all guarantees; inspect saved verifier logs")
    return record
