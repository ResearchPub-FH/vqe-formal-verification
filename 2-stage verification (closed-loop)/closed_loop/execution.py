from __future__ import annotations

import gzip
import json
import math
from pathlib import Path
import numpy as np

from .common import canonical, digest, file_hash, save_json, utc_now, validate_frozen
from .checker import RuntimeChecker
from .physics import GROUP_VALUES, candidate_indices, ideal_success, point
from .temporal import verify_traces

FAULTS = ("premature_update", "corrupt_energy", "coefficient_swap", "shot_mismatch", "missing_evidence")
EIGENVALUES = {"ZI": [1, 1, -1, -1], "ZZ": [1, -1, -1, 1], "YZ": [1, -1, -1, 1], "XX": [1, -1, -1, 1]}


def execution_values(groups, c, swap=False):
    shots = sum(groups[0])
    expectations = {}
    for group, terms in enumerate(c["measurement_groups"]):
        for term in terms:
            expectations[term] = float(np.dot(groups[group], EIGENVALUES[term]) / shots)
    coefficients = dict(c["hamiltonian"]["terms"])
    if swap:
        coefficients["YZ"], coefficients["XX"] = coefficients["XX"], coefficients["YZ"]
    contributions = {term: coefficients[term] * value / 10000 for term, value in expectations.items()}
    if swap:
        score = round(math.fsum(contributions.values()) * shots * 10000)
    else:
        score = sum(int(np.dot(counts, GROUP_VALUES[group])) for group, counts in enumerate(groups))
    return {"expectations": expectations, "coefficients": coefficients, "contributions": contributions,
            "score": score, "energy": score / (shots * 10000)}


def execute_run(c, run_id, seed_words, pre_digest, trace_path, fault=None):
    """Execute the fixed circuit's ideal Born law, with independent count draws.

Failures are observed at the protected boundary; the controller stops after a
detected violation. Only the premature-update fault emits an illegal commit.
"""
    trace_path = Path(trace_path)
    if trace_path.exists():
        raise FileExistsError(f"refusing to overwrite {trace_path}")
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(np.random.SeedSequence(seed_words))
    checker = RuntimeChecker(c, run_id, pre_digest)
    index = list(c["initial_index"])
    seq = 0
    actual_shots = 0
    updates = 0
    reason = None

    with gzip.open(trace_path, "wt", encoding="utf-8") as stream:
        def emit(kind, **data):
            nonlocal seq
            seq += 1
            e = {"seq": seq, "type": kind, "run_id": run_id, "configuration_digest": digest(c), **data}
            stream.write(canonical(e) + "\n")
            return checker.consume(e)

        emit("run_start", pre_execution_digest=pre_digest, index=index, seed_words=seed_words, injected_fault=fault)
        if ideal_success(index, c):
            reason = "success"
        for u in range(1, c["maximum_updates"] + 1):
            if reason:
                break
            coordinate = c["coordinate_schedule"][(u - 1) % 4]
            candidates = candidate_indices(index, coordinate, c["grid_size"])
            if not emit("update_start", update=u, index=index, coordinate=coordinate, candidates=candidates):
                reason = "contract_abort"
                break
            if fault == "premature_update" and u == 1:
                emit("optimizer_commit", update=u, choice=0, index_after=index, energies_used=[], evaluation_ids=[], physical_shots=0)
                reason = "contract_abort"
                break
            values = []
            for candidate, params in enumerate(candidates):
                context = {"update": u, "candidate": candidate, "index": params,
                           "theta": [2 * math.pi * z / c["grid_size"] for z in params],
                           "evaluation_id": f"{run_id}:u{u}:c{candidate}"}
                _, probabilities = point(tuple(params), c["grid_size"])
                counts_by_group = []
                for group in range(3):
                    shots = max(1, c["shots_per_group"] // 2) if fault == "shot_mismatch" else c["shots_per_group"]
                    counts = rng.multinomial(shots, probabilities[group]).tolist()
                    actual_shots += shots
                    counts_by_group.append(counts)
                    if not emit("measurement", **context, group=group, counts=counts, shots=shots):
                        reason = "contract_abort"
                        break
                if reason:
                    break
                value = execution_values(counts_by_group, c, swap=fault == "coefficient_swap" and u == 1 and candidate == 0)
                if fault == "corrupt_energy" and u == 1 and candidate == 0:
                    value["energy"] += 0.125
                if not emit("evaluation", **context, **value):
                    reason = "contract_abort"
                    break
                if not emit("numeric_valid", **context):
                    reason = "contract_abort"
                    break
                values.append(value)
            if reason:
                break
            scores_used = [value["score"] for value in values]
            choice = min(range(3), key=lambda j: scores_used[j])
            selected = candidates[choice]
            accepted = emit("optimizer_commit", update=u, choice=choice, index_after=selected,
                            energies_used=[value["energy"] for value in values],
                            scores_used=scores_used,
                            evaluation_ids=[f"{run_id}:u{u}:c{j}" for j in range(3)], physical_shots=actual_shots)
            index = selected
            updates = u
            if not accepted:
                reason = "contract_abort"
                break
            if ideal_success(index, c):
                reason = "success"
                break
        reason = reason or "budget"
        emit("terminal", reason=reason, updates=updates, index=index, physical_shots=actual_shots)
    result = checker.result()
    result["seed_words"] = seed_words
    result["injected_fault"] = fault
    result["trace_sha256"] = file_hash(trace_path)
    return result


def replay(c, pre_digest, trace_path):
    checker = None
    with gzip.open(trace_path, "rt", encoding="utf-8") as stream:
        for line in stream:
            e = json.loads(line)
            if checker is None:
                checker = RuntimeChecker(c, e["run_id"], pre_digest)
            checker.consume(e)
    if checker is None:
        raise ValueError("empty trace")
    return checker.result()


def replay_matches(online, offline):
    return all(online[key] == value for key, value in offline.items())


def run_baseline(output, progress=print):
    output = Path(output)
    pre, pre_digest = validate_frozen(output)
    c = pre["configuration"]
    directory = output / "stage2" / "baseline"
    if directory.exists():
        raise FileExistsError("baseline directory already exists; use a new output for a new experiment")
    directory.mkdir(parents=True)
    started = utc_now()
    results = []
    for i in range(c["runs"]):
        run_id = f"baseline-{i:04d}"
        trace = directory / f"{run_id}.jsonl.gz"
        result = execute_run(c, run_id, [c["seed"], 0, i], pre_digest, trace)
        offline = replay(c, pre_digest, trace)
        result["online_replay_agreement"] = replay_matches(result, offline)
        if not result["online_replay_agreement"]:
            raise RuntimeError(f"online/replay discrepancy for {run_id}")
        result["trace"] = str(trace.relative_to(output))
        results.append(result)
        if (i + 1) % 25 == 0 or i + 1 == c["runs"]:
            progress(f"Stage 2: {i + 1}/{c['runs']} runs; {sum(r['success_step'] is not None for r in results)} successes", flush=True)
    progress("Stage 2: independently replaying temporal contracts with DejaVu", flush=True)
    temporal = verify_traces(output, directory, results, pre["runtime_monitor"])
    report = {"started_at": started, "completed_at": utc_now(), "pre_execution_digest": pre_digest, "temporal_monitor": temporal,
              "configuration_digest": pre["configuration_digest"], "results": results}
    save_json(directory / "results.json", report)
    return report


def remove_evidence(source, destination):
    removed = False
    with gzip.open(source, "rt") as src, gzip.open(destination, "wt") as dst:
        for line in src:
            e = json.loads(line)
            if e["type"] == "measurement" and not removed:
                del e["counts"]
                removed = True
            dst.write(canonical(e) + "\n")
    if not removed:
        raise ValueError("source trace has no measurement to remove")


def run_faults(output, progress=print):
    output = Path(output)
    pre, pre_digest = validate_frozen(output)
    c = pre["configuration"]
    directory = output / "stage2" / "faults"
    if directory.exists():
        raise FileExistsError("fault results already exist; use a new experiment output")
    directory.mkdir(parents=True)
    expected = {"premature_update": ("L2", "DISAGREEMENT"), "corrupt_energy": ("N2", "DISAGREEMENT"),
                "coefficient_swap": ("N2", "DISAGREEMENT"), "shot_mismatch": ("N3", "ASSUMPTION_MISMATCH"),
                "missing_evidence": ("N1", "INCONCLUSIVE")}
    results = []
    for fault_index, fault in enumerate(FAULTS):
        for i in range(c["fault_runs"]):
            run_id = f"{fault}-{i:03d}"
            trace = directory / f"{run_id}.jsonl.gz"
            seed_words = [c["seed"], 1 + fault_index, i]
            if fault == "missing_evidence":
                source = directory / f"{run_id}-complete.jsonl.gz"
                original = execute_run(c, run_id, seed_words, pre_digest, source)
                if any(row["runtime_verdict"] != "AGREEMENT" for row in original["contracts"].values()):
                    raise RuntimeError("missing-evidence control trace was not valid")
                remove_evidence(source, trace)
                result = replay(c, pre_digest, trace)
                result["control_trace"] = str(source.relative_to(output))
                result["control_trace_sha256"] = file_hash(source)
                result["fault_scope"] = "saved-trace mutation; no execution mutation"
            else:
                result = execute_run(c, run_id, seed_words, pre_digest, trace, fault)
                result["online_replay_agreement"] = replay_matches(result, replay(c, pre_digest, trace))
                result["fault_scope"] = "controlled execution"
            cid, verdict = expected[fault]
            result.update({"fault": fault, "expected_contract": cid, "expected_verdict": verdict,
                           "detected_as_expected": result["contracts"][cid]["runtime_verdict"] == verdict,
                           "trace": str(trace.relative_to(output)), "trace_sha256": file_hash(trace)})
            result["probabilistic_applicability"] = "ASSUMPTION_MISMATCH" if fault == "shot_mismatch" else "INCONCLUSIVE"
            results.append(result)
        progress(f"Fault {fault}: {sum(r['detected_as_expected'] for r in results if r['fault'] == fault)}/{c['fault_runs']} expected verdicts", flush=True)
    progress("Fault tests: replaying temporal contracts with DejaVu", flush=True)
    temporal = verify_traces(output, directory, results, pre["runtime_monitor"])
    report = {"pre_execution_digest": pre_digest, "configuration_digest": pre["configuration_digest"], "completed_at": utc_now(), "results": results, "temporal_monitor": temporal}
    save_json(directory / "results.json", report)
    return report
