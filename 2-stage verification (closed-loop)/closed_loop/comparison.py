from __future__ import annotations

from collections import Counter
import csv
import math
from pathlib import Path
from statistics import NormalDist
import numpy as np

from .common import CONTRACTS, file_hash, load_json, save_json, shots_per_update, utc_now, validate_frozen
from .execution import replay, replay_matches
from .temporal import PROPERTY_TRIGGERS, dejavu_record, monitor_outcomes

SHORT = {"AGREEMENT": "A", "DISAGREEMENT": "D", "ASSUMPTION_MISMATCH": "M", "INCONCLUSIVE": "I"}


def expected_triggers(result, c):
    """Obligation counts implied by a completed run's number of updates."""
    u, groups = result["updates"], len(c["measurement_groups"])
    terms = sum(len(g) for g in c["measurement_groups"])
    return {"L1": {"groups_before_energy": 3 * u},
            "L2": {"validation_certified": 3 * u, "validations_before_commit": u},
            "L3": {"evaluation_identity_current": 3 * (groups + 2) * u, "commit_identity_current": u},
            "L4": {"terminal_reason": 1},
            "N1": {"expectation_reconstructed": 3 * terms * u},
            "N2": {"energy_reconstructed": 3 * u},
            "N3": {"allocation_checked": 3 * groups * u, "cumulative_total_checked": u + 1},
            "N4": {"candidates_generated": u, "selection_checked": u}}


def wilson(successes, total):
    if total == 0:
        return None
    z = NormalDist().inv_cdf(0.975)
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [0.0 if successes == 0 else max(0.0, center - radius),
            1.0 if successes == total else min(1.0, center + radius)]


def mean_interval(values, c):
    if len(values) < 2:
        return None
    rng = np.random.default_rng(np.random.SeedSequence([c["seed"], 99]))
    data = np.asarray(values, dtype=float)
    means = data[rng.integers(0, len(data), size=(c["bootstrap_samples"], len(data)))].mean(axis=1)
    return [float(x) for x in np.quantile(means, [0.025, 0.975])]


def aggregate_status(counts):
    for verdict in ("DISAGREEMENT", "ASSUMPTION_MISMATCH", "INCONCLUSIVE"):
        if counts.get(verdict, 0):
            return verdict
    return "AGREEMENT" if counts.get("AGREEMENT", 0) else "INCONCLUSIVE"


def audit_results(output, pre, seal, report, full_replay=False):
    c = pre["configuration"]
    if report["pre_execution_digest"] != seal or report["configuration_digest"] != pre["configuration_digest"]:
        raise ValueError("Stage 2 results do not refer to this frozen Stage 1 record")
    ids = [r["run_id"] for r in report["results"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate runtime result identities")
    for result in report["results"]:
        path = Path(output) / result["trace"]
        if file_hash(path) != result["trace_sha256"]:
            raise ValueError(f"runtime evidence changed: {path}")
        if "control_trace" in result and file_hash(Path(output) / result["control_trace"]) != result["control_trace_sha256"]:
            raise ValueError("fault control trace changed")
        if full_replay and not replay_matches(result, replay(c, seal, path)):
            raise ValueError(f"saved runtime verdict does not match replay: {path}")
    temporal = report.get("temporal_monitor")
    if temporal is None:
        raise ValueError("missing independent DejaVu replay evidence")
    directory = (Path(output) / report["results"][0]["trace"]).parent
    if file_hash(directory / "temporal-input.tsv") != temporal["input_sha256"] or file_hash(directory / "dejavu.log") != temporal["log_sha256"]:
        raise ValueError("DejaVu replay input or log changed")
    observed, events = monitor_outcomes((directory / "dejavu.log").read_text())
    if set(observed) != set(ids) or set(events) != set(ids):
        raise ValueError("DejaVu log has missing or unexpected runs")
    for result in report["results"]:
        expected = dejavu_record(observed[result["run_id"]], events[result["run_id"]])
        if {key: result["dejavu"].get(key) for key in expected} != expected:
            raise ValueError("saved temporal result differs from DejaVu log")


def compare(output, full_replay=True):
    output = Path(output).resolve()
    pre, seal = validate_frozen(output)
    c = pre["configuration"]
    baseline = load_json(output / "stage2/baseline/results.json")
    audit_results(output, pre, seal, baseline, full_replay)
    if baseline["started_at"] < pre["frozen_at"]:
        raise ValueError("runtime execution predates the frozen Stage 1 result")
    results = baseline["results"]
    if len(results) != c["runs"]:
        raise ValueError("runtime result count differs from the frozen configuration")
    for r in results:
        if r["terminal_reason"] in ("success", "budget") and {cid: row["triggers"] for cid, row in r["contracts"].items()} != expected_triggers(r, c):
            raise ValueError(f"runtime obligation coverage differs from the completed-run equations: {r['run_id']}")
    rows = []
    for cid in CONTRACTS:
        if cid.startswith("P"):
            continue
        counts = dict(Counter(r["contracts"][cid]["runtime_verdict"] for r in results))
        rows.append({"contract": cid, "description": CONTRACTS[cid],
                     "stage1": pre["contracts"][cid]["pre_execution_verdict"],
                     "runtime_counts": counts, "runtime_checks": sum(r["contracts"][cid]["checks"] for r in results),
                     "runtime_triggers": {name: sum(r["contracts"][cid]["triggers"][name] for r in results) for name in results[0]["contracts"][cid]["triggers"]},
                     "verdict_agreement": aggregate_status(counts)})
    all_counts = Counter(r["contracts"][cid]["runtime_verdict"] for r in results for cid in r["contracts"])
    eligibility = "ASSUMPTION_MISMATCH" if all_counts["ASSUMPTION_MISMATCH"] else "INCONCLUSIVE" if any(r["terminal_reason"] not in ("success", "budget") for r in results) or all_counts["DISAGREEMENT"] or all_counts["INCONCLUSIVE"] else None
    probabilities = []
    for k in c["checkpoints"]:
        successes = sum(r["success_step"] is not None and r["success_step"] <= k for r in results)
        observed = successes / len(results)
        interval = wilson(successes, len(results))
        predicted = pre["probabilistic"]["storm"]["results"][str(k)]
        verdict = eligibility or ("AGREEMENT" if interval[0] <= predicted <= interval[1] else "DISAGREEMENT")
        probabilities.append({"contract": f"P1@{k}", "update_bound": k, "primary": k == c["maximum_updates"],
                              "model_probability": predicted, "runtime_successes": successes, "runtime_runs": len(results),
                              "runtime_probability": observed, "wilson_95": interval,
                              "absolute_difference": abs(predicted - observed), "verdict_agreement": verdict})
    successful_updates = [r["success_step"] for r in results if r["success_step"] is not None]
    interval = mean_interval(successful_updates, c)
    empirical_mean = float(np.mean(successful_updates)) if successful_updates else None
    means = []
    for cid, scale, key in [("P2", 1, "expected_updates_given_success"), ("P3", shots_per_update(c), "expected_shots_given_success")]:
        predicted = pre["probabilistic"][key]
        empirical = None if empirical_mean is None else empirical_mean * scale
        scaled_interval = None if interval is None else [v * scale for v in interval]
        verdict = eligibility or ("INCONCLUSIVE" if scaled_interval is None or predicted is None else "AGREEMENT" if scaled_interval[0] <= predicted <= scaled_interval[1] else "DISAGREEMENT")
        means.append({"contract": cid, "model_mean": predicted, "runtime_mean": empirical,
                      "bootstrap_95": scaled_interval, "successful_runs": len(successful_updates), "verdict_agreement": verdict})
    fault_path = output / "stage2/faults/results.json"
    faults = None
    if fault_path.exists():
        fault_report = load_json(fault_path)
        audit_results(output, pre, seal, fault_report, full_replay)
        faults = []
        for fault in sorted(set(r["fault"] for r in fault_report["results"])):
            tested = [r for r in fault_report["results"] if r["fault"] == fault]
            detected = sum(r["contracts"][r["expected_contract"]]["runtime_verdict"] == r["expected_verdict"] for r in tested)
            faults.append({"fault": fault, "runs": len(tested), "detected_as_expected": detected,
                           "expected_contract": tested[0]["expected_contract"], "expected_verdict": tested[0]["expected_verdict"],
                           "scope": tested[0]["fault_scope"],
                           "verdict_vector": {cid: dict(Counter(r["contracts"][cid]["runtime_verdict"] for r in tested)) for cid in tested[0]["contracts"]}})
    logical = pre["logical"]
    queries = logical["nonvacuity"]["results"] or []
    report = {
        "generated_at": utc_now(), "pre_execution_digest": seal, "configuration_digest": pre["configuration_digest"],
        "two_stages": ["pre-execution verification", "runtime verification and verdict agreement"],
        "logical_nonvacuity": {
            "status": logical["status"], "properties": len(logical["properties"]),
            "properties_holding": sum(p["holds"] is True for p in logical["properties"]),
            "queries": len(queries), "queries_as_expected": sum(q["as_expected"] for q in queries),
            "unreachable_defensive_branches": [q["branch"] for q in queries if q["kind"] == "branch" and not q["expected"] and not q["holds"]],
            "mutants": [{key: m[key] for key in ("mutant", "target_contract", "killed", "detected_by")} for m in logical["mutation"]]},
        "trigger_coverage": "every completed baseline run matches the update-count equations",
        "dejavu_property_triggers": {"exercised_runs": baseline["temporal_monitor"]["exercised_runs"], "totals": baseline["temporal_monitor"]["trigger_totals"]},
        "logical_numeric": rows, "probability_comparison": probabilities, "conditional_means": means,
        "fault_detection": faults, "baseline_runs": len(results),
        "successes": len(successful_updates), "total_physical_shots": sum(r["physical_shots"] for r in results),
        "maximum_energy_reconstruction_error": max(r["max_energy_error"] for r in results),
        "maximum_expectation_reconstruction_error": max(r["max_expectation_error"] for r in results),
        "online_replay_agreement": all(r["online_replay_agreement"] for r in results),
        "dejavu_baseline_passed": baseline["temporal_monitor"]["passed_runs"],
        "probabilistic_eligibility": eligibility or "APPLICABLE_UNDER_DECLARED_APPROXIMATION",
        "mean_absolute_probability_difference": float(np.mean([r["absolute_difference"] for r in probabilities])),
        "result_files": {"baseline": file_hash(output / "stage2/baseline/results.json"), "faults": file_hash(fault_path) if fault_path.exists() else None},
        "interpretation": "Probabilistic AGREEMENT means statistical compatibility, not equality of distributions. Supporting intervals are marginal; no joint confidence claim. P3 scales P2 by the fixed shots per update.",
    }
    directory = output / "comparison"
    directory.mkdir(exist_ok=True)
    save_json(directory / "verdict_agreement.json", report)
    with (directory / "probabilities.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["update_bound", "model_probability", "runtime_probability", "lower_95", "upper_95", "absolute_difference", "verdict_agreement"])
        writer.writeheader()
        for r in probabilities:
            writer.writerow({k: r[k] for k in ("update_bound", "model_probability", "runtime_probability", "absolute_difference", "verdict_agreement")} | {"lower_95": r["wilson_95"][0], "upper_95": r["wilson_95"][1]})
    write_report(directory / "REPORT.md", report, pre)
    return report


def write_report(path, report, pre):
    c = pre["configuration"]
    lines = ["# Two-stage verification: results", "",
             f"Configuration: `{pre['configuration_digest']}`. Stage 1 record: `{report['pre_execution_digest']}`.", "",
             f"Executed {report['baseline_runs']} baseline runs; {report['successes']} reached the declared ideal-energy target by {c['maximum_updates']} updates.",
             f"Physical shots: {report['total_physical_shots']:,}. Online/replay agreement: {report['online_replay_agreement']}.",
             f"Independent DejaVu temporal replay: {report['dejavu_baseline_passed']}/{report['baseline_runs']} passed.", ""]
    nv = report["logical_nonvacuity"]
    lines += ["## Logical non-vacuity (Stage 1)", "",
              f"NuXmv status {nv['status']}: {nv['properties_holding']}/{nv['properties']} properties hold; "
              f"{nv['queries_as_expected']}/{nv['queries']} antecedent-witness, consequent-probe and branch queries have their expected result.",
              f"Defensive branches confirmed unreachable: {', '.join(f'`{b}`' for b in nv['unreachable_defensive_branches']) or 'none'}.", "",
              "| Seeded mutant | Target contract | Killed | Detected by |", "|---|---|---|---|"]
    for m in nv["mutants"]:
        lines.append(f"| {m['mutant']} | {m['target_contract']} | {m['killed']} | {', '.join(m['detected_by']) or 'none'} |")
    lines += ["", "## Logical and numeric contract matching", "",
              "Each obligation counts the runtime events at which its antecedent was evaluated. A contract with an unexercised obligation is INCONCLUSIVE, never a vacuous AGREEMENT. "
              f"Coverage: {report['trigger_coverage']}.", "",
              "| Contract | Stage 1 | Runtime verdict counts | Checks | Triggered obligations | Verdict agreement |",
              "|---|---|---|---:|---|---|"]
    for r in report["logical_numeric"]:
        counts = ", ".join(f"{v}: {n}" for v, n in sorted(r["runtime_counts"].items()))
        triggers = "<br>".join(f"{name}: {n:,}" for name, n in r["runtime_triggers"].items())
        lines.append(f"| {r['contract']}: {r['description']} | {r['stage1']} | {counts} | {r['runtime_checks']} | {triggers} | {r['verdict_agreement']} |")
    dv = report["dejavu_property_triggers"]
    lines += ["", "| DejaVu property | Runs exercised | Antecedent events |", "|---|---:|---:|"]
    for name, runs in dv["exercised_runs"].items():
        lines.append(f"| {name} | {runs}/{report['baseline_runs']} | {dv['totals'][name]:,} |")
    lines += ["", f"Maximum energy reconstruction error: {report['maximum_energy_reconstruction_error']:.6g} (allowed {c['energy_tolerance']:.6g}).",
              f"Maximum expectation reconstruction error: {report['maximum_expectation_reconstruction_error']:.6g}.", "",
              "## Probabilistic contract matching", "",
              "| Update bound | Gaussian/Storm probability | Runtime successes | Runtime probability | 95% Wilson interval | Verdict agreement |",
              "|---:|---:|---:|---:|---|---|"]
    for r in report["probability_comparison"]:
        lo, hi = r["wilson_95"]
        lines.append(f"| {r['update_bound']}{' (primary)' if r['primary'] else ''} | {r['model_probability']:.6f} | {r['runtime_successes']}/{r['runtime_runs']} | {r['runtime_probability']:.6f} | [{lo:.6f}, {hi:.6f}] | {r['verdict_agreement']} |")
    lines += ["", "| Contract | Model conditional mean | Runtime conditional mean | 95% bootstrap interval | Verdict agreement |",
              "|---|---:|---:|---|---|"]
    for r in report["conditional_means"]:
        lines.append(f"| {r['contract']} | {r['model_mean']} | {r['runtime_mean']} | {r['bootstrap_95']} | {r['verdict_agreement']} |")
    lines += ["", report["interpretation"], "", "Conditional means come from Python propagation of the same Gaussian DTMC; Storm independently checks the listed bounded reachability probabilities. No reward-query result is claimed.", "",
              "## Controlled faults", "", "| Fault | Contract | Expected verdict | Detected/tested | Scope |", "|---|---|---|---:|---|"]
    for r in report["fault_detection"] or []:
        lines.append(f"| {r['fault']} | {r['expected_contract']} | {r['expected_verdict']} | {r['detected_as_expected']}/{r['runs']} | {r['scope']} |")
    if report["fault_detection"]:
        contracts = list(report["fault_detection"][0]["verdict_vector"])
        lines += ["", "Full verdict vector (A agreement, D disagreement, M assumption mismatch, I inconclusive, including unexercised obligations):", "",
                  "| Fault | " + " | ".join(contracts) + " |", "|---|" + "---|" * len(contracts)]
        for r in report["fault_detection"]:
            cells = [", ".join(f"{SHORT[v]}{'' if len(counts) == 1 else f':{n}'}" for v, n in sorted(counts.items())) for counts in r["verdict_vector"].values()]
            lines.append(f"| {r['fault']} | " + " | ".join(cells) + " |")
    lines += ["", "## Assumptions and boundaries", ""] + [f"- {a}" for a in pre["assumptions"]]
    lines += ["", "The run records and compressed traces remain under `stage2/`. Verifier output, generated models, Gaussian kernels, and the sealed assurance record remain under `stage1/`. Corrections require a new Stage 1 output directory; old evidence is retained.", ""]
    Path(path).write_text("\n".join(lines))
