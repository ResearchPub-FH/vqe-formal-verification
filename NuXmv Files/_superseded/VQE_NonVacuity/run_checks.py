#!/usr/bin/env python3
"""Non-vacuity checks for the standalone VQE nuXmv models; writes only inside this folder.

For every implication property, each antecedent disjunct must be reachable and the
consequent must not hold on its own. Every case branch of next(state) and
next(term_reason) is checked for first-match reachability. Queries are LTL
`G !(...)` / `G (...)` so that input variables (IVAR) are allowed; a FALSE result
means the condition is reachable and nuXmv's counterexample is its witness trace.
Unreachable findings are triaged with the classes agreed for this project.
"""

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
SOURCES = {
    "refined_abort": "VQE_NuXmv_Refinement/vqe_refined_abort.smv",
    "canonical": "claude/vqe_canonical.smv",
}
NA = None  # existential or liveness property: it has no antecedent to witness
UNCONDITIONAL = ()

# One row per property in declaration order: (id, antecedent disjuncts, consequent).
PROPERTIES = {
    "refined_abort": [
        ("A1", ["state = BIND"], "params_ready & !energy_ready & terms_done = 0"),
        ("A2", ["state = EXECUTE_MEASURE"], "circ_ready & params_ready & terms_done <= NTERMS"),
        ("A3", ["state = COMPUTE_ENERGY"], "circ_ready & all_terms_done & !params_ready"),
        ("A4", ["state = CHECK_STOP"], "energy_ready & all_terms_done"),
        ("A5", ["state = OPTIMIZER_STEP"], "energy_ready & all_terms_done & iter < MAX_ITERS"),
        ("A6", ["state = DONE"], "energy_ready & term_reason = DONE_CONVERGED"),
        ("A7", ["state = ABORT"], "term_reason != NO_TERM & term_reason != DONE_CONVERGED"),
        ("A8", ["!terminal"], "term_reason = NO_TERM"),
        ("A9", ["state = ABORT"], "!circ_ready & !params_ready"),
        ("B1", ["state = S_INIT"], "X (state = BIND)"),
        ("B2", ["state = BIND & !bind_error & params_ready"], "X (state = EXECUTE_MEASURE)"),
        ("B3", ["state = BIND & bind_error", "state = BIND & !params_ready"], "X (state = ABORT & term_reason = ABORT_BIND_ERROR)"),
        ("B4", ["state = EXECUTE_MEASURE & qpu_error"], "X (state = ABORT & term_reason = ABORT_QPU_ERROR)"),
        ("B5", ["state = EXECUTE_MEASURE & !qpu_error & !all_terms_done"], "X (state = EXECUTE_MEASURE)"),
        ("B6", ["state = EXECUTE_MEASURE & !qpu_error & all_terms_done"], "X (state = COMPUTE_ENERGY)"),
        ("B7", ["state = COMPUTE_ENERGY & energy_error", "state = COMPUTE_ENERGY & !all_terms_done"], "X (state = ABORT & term_reason = ABORT_ENERGY_ERROR)"),
        ("B8", ["state = COMPUTE_ENERGY & !energy_error & all_terms_done"], "X (state = CHECK_STOP)"),
        ("B9", ["state = CHECK_STOP & converged"], "X (state = DONE & term_reason = DONE_CONVERGED)"),
        ("B10", ["state = CHECK_STOP & !converged & iter = MAX_ITERS"], "X (state = ABORT & term_reason = ABORT_MAX_ITERS)"),
        ("B11", ["state = CHECK_STOP & !converged & iter < MAX_ITERS"], "X (state = OPTIMIZER_STEP)"),
        ("B12", ["state = OPTIMIZER_STEP & optimizer_error"], "X (state = ABORT & term_reason = ABORT_OPTIMIZER_ERROR)"),
        ("B13", ["state = OPTIMIZER_STEP & !optimizer_error"], "X (state = BIND)"),
        ("B14a", ["state = DONE"], "X (state = DONE)"),
        ("B14b", ["state = ABORT"], "X (state = ABORT)"),
        ("C1", ["state = EXECUTE_MEASURE"], "params_ready"),
        ("C2", ["state = OPTIMIZER_STEP"], "energy_ready"),
        ("C3", ["state = BIND & iter > 0"], "!energy_ready"),
        ("C4", ["state = OPTIMIZER_STEP & !optimizer_error"], "X (state = BIND & params_ready & !energy_ready & terms_done = 0)"),
        ("C5", ["state = EXECUTE_MEASURE & !qpu_error & all_terms_done"], "X (!params_ready)"),
        ("C6", ["state = DONE"], "energy_ready"),
        ("D1", NA, None), ("D2", NA, None), ("D3", NA, None), ("D4", NA, None), ("D5", NA, None),
        ("D6", NA, None), ("D7", NA, None), ("D8", NA, None),
        ("D9", ["state = DONE"], "X (state = DONE)"),
        ("D10", ["state = ABORT"], "X (state = ABORT)"),
        ("D11", ["state = ABORT & term_reason = ABORT_MAX_ITERS"], "iter = MAX_ITERS"),
    ],
    "canonical": [
        ("R1", ["state = EXECUTE_MEASURE"], "circ_ready"),
        ("R2", ["state = EXECUTE_MEASURE"], "params_ready"),
        ("R3", ["state = COMPUTE_ENERGY"], "all_terms_done"),
        ("R4", ["state = CHECK_STOP"], "energy_ready"),
        ("R5", ["state = OPTIMIZER_STEP"], "energy_ready"),
        ("F1", UNCONDITIONAL, None), ("F2", UNCONDITIONAL, None), ("F3", UNCONDITIONAL, None),
        ("F4", ["state = EXECUTE_MEASURE"], "bound_version = theta_version"),
        ("F5", ["state = CHECK_STOP"], "energy_version = bound_version"),
        ("F6", ["state = BIND & iter > 0"], "!energy_ready"),
        ("F7", ["state = OPTIMIZER_STEP & !opt_err"], "X (params_ready & !energy_ready)"),
        ("F8", ["state = BIND"], "terms_done = 0"),
        ("T1", NA, None),
        ("T2a", ["state = DONE"], "X (state = DONE)"),
        ("T2b", ["state = ABORT"], "X (state = ABORT)"),
        ("T3", ["state = DONE"], "term_reason = DONE_CONVERGED & energy_ready"),
        ("T4", UNCONDITIONAL, None),
        ("T5", NA, None),
        ("E1", ["state = ABORT"], "term_reason != NO_TERM & term_reason != DONE_CONVERGED"),
        ("E2", ["state = BIND & bind_err"], "X (state = ABORT & term_reason = ABORT_BIND_ERR)"),
        ("E3", ["state = EXECUTE_MEASURE & qpu_err"], "X (state = ABORT & term_reason = ABORT_QPU_ERR)"),
        ("E4", ["state = COMPUTE_ENERGY & energy_err"], "X (state = ABORT & term_reason = ABORT_ENERGY_ERR)"),
        ("E5", ["state = OPTIMIZER_STEP & opt_err"], "X (state = ABORT & term_reason = ABORT_OPT_ERR)"),
        ("E6", ["state = CHECK_STOP & !converged & iter = MAX_ITERS"], "X (state = ABORT & term_reason = ABORT_MAX_ITERS)"),
        ("E7a", ["state = DONE"], "G !(state = ABORT)"),
        ("E7b", ["state = ABORT"], "G !(state = DONE)"),
        ("E8a", NA, None), ("E8b", NA, None), ("E8c", NA, None), ("E8d", NA, None), ("E8e", NA, None),
    ],
}
SPEC_COUNTS = {"refined_abort": 41, "canonical": 32}

# Triage of findings known to be unreachable, with the reason for each class.
TRIAGE = {
    ("refined_abort", "B3", 1): ("redundant_disjunct", "A1 proves params_ready holds in BIND, so the !params_ready disjunct cannot occur."),
    ("refined_abort", "B7", 1): ("redundant_disjunct", "A3 proves all_terms_done holds in COMPUTE_ENERGY, so the !all_terms_done disjunct cannot occur."),
    ("refined_abort", "next(state)", 13): ("intended_dead_guard", "A5 proves OPTIMIZER_STEP only occurs below MAX_ITERS; the bound is enforced at CHECK_STOP."),
    ("refined_abort", "next(state)", 16): ("intended_dead_guard", "Defensive default: the earlier guards cover every state."),
    ("refined_abort", "next(term_reason)", 6): ("intended_dead_guard", "Mirror of the dead OPTIMIZER_STEP-at-bound branch of next(state)."),
    ("canonical", "next(state)", 15): ("intended_dead_guard", "Defensive default: the earlier guards cover every state."),
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest():
    """SHA-256 of every pre-existing file in the nuXmv project outside this folder."""
    return {str(p.relative_to(PROJECT)): digest(p) for p in sorted(PROJECT.rglob("*"))
            if p.is_file() and p.name != ".DS_Store" and HERE not in p.parents}


def run(nuxmv, name, commands):
    script = HERE / "commands" / (name + ".cmd")
    log = HERE / "results" / (name + ".log")
    script.write_text("\n".join(commands + ["quit"]) + "\n")
    completed = subprocess.run([str(nuxmv), "-s", "-source", str(script)], cwd=HERE, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, timeout=300)
    log.write_text(completed.stdout)
    return completed.returncode, completed.stdout


def verdicts(output):
    return re.findall(r"^-- (?:specification|invariant) (.+?)\s+is (true|false)\s*$", output, re.M)


def checked_run(nuxmv, name, commands, expected):
    code, output = run(nuxmv, name, commands)
    # nuXmv can exit 0 after a parser or command error, so inspect the output too.
    if code != 0 or re.search(r"aborting|syntax error|cannot build|undefined|contains input variables", output, re.I):
        raise RuntimeError(f"nuXmv command failed; see results/{name}.log")
    values = verdicts(output)
    if len(values) != expected:
        raise RuntimeError(f"expected {expected} results in results/{name}.log, found {len(values)}")
    return values


def case_branches(text, variable):
    """(guard, value) pairs of a next(variable) case block, in first-match order."""
    block = re.search(r"next\(\s*" + re.escape(variable) + r"\s*\)\s*:=\s*case(.*?)esac\s*;", text, re.S)
    body = re.sub(r"--[^\n]*", "", block.group(1))
    branches = []
    for item in body.split(";"):
        item = " ".join(item.split())
        if item:
            guard, value = item.rsplit(" : ", 1)
            branches.append((guard, value))
    return branches


def queries_for(model, text):
    rows = []
    for pid, antecedents, consequent in PROPERTIES[model]:
        if antecedents is NA or antecedents == UNCONDITIONAL:
            rows.append({"model": model, "item": pid, "index": "", "kind": "existential/liveness" if antecedents is NA else "unconditional invariant",
                         "condition": "", "query": ""})
            continue
        for i, antecedent in enumerate(antecedents):
            rows.append({"model": model, "item": pid, "index": i, "kind": "antecedent", "condition": antecedent,
                         "query": f"G !({antecedent})"})
        rows.append({"model": model, "item": pid, "index": "", "kind": "consequent probe", "condition": consequent,
                     "query": f"G ({consequent})"})
    for variable in ("state", "term_reason"):
        earlier = []
        for i, (guard, value) in enumerate(case_branches(text, variable)):
            first_match = " & ".join([f"({guard})"] + [f"!({g})" for g in earlier])
            rows.append({"model": model, "item": f"next({variable})", "index": i, "kind": "branch",
                         "condition": f"{guard} : {value}", "query": f"G !({first_match})"})
            earlier.append(guard)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nuxmv", type=Path, default=PROJECT / "nuXmv/bin/nuXmv")
    args = parser.parse_args()
    nuxmv = args.nuxmv.resolve()
    for directory in ("snapshots", "commands", "results"):
        (HERE / directory).mkdir(exist_ok=True)
    before = manifest()
    (HERE / "original_files_before.json").write_text(json.dumps(before, indent=2) + "\n")

    rows, models = [], {}
    for model, source in SOURCES.items():
        snapshot = HERE / "snapshots" / (model + ".smv")
        snapshot.write_bytes((PROJECT / source).read_bytes())
        if digest(snapshot) != before[source]:
            raise RuntimeError(f"snapshot differs from source: {model}")
        text = snapshot.read_text()
        specs = len(re.findall(r"^\s*(?:INVARSPEC|LTLSPEC|CTLSPEC)\b", text, re.M))
        if specs != SPEC_COUNTS[model] or len(PROPERTIES[model]) != specs:
            raise RuntimeError(f"{model}: {specs} specifications, table has {len(PROPERTIES[model])}")
        setup = [f'read_model -i "snapshots/{model}.smv"', "go"]
        original = checked_run(nuxmv, model + "_properties", setup + ["check_invar", "check_ltlspec", "check_ctlspec"], specs)
        model_rows = queries_for(model, text)
        checked = [r for r in model_rows if r["query"]]
        values = checked_run(nuxmv, model + "_nonvacuity", setup + [f'check_ltlspec -p "{r["query"]}"' for r in checked], len(checked))
        for row, (printed, value) in zip(checked, values):
            if re.sub(r"[\s()]", "", printed) != re.sub(r"[\s()]", "", row["query"]):
                raise RuntimeError(f"{model}: result order differs at {row['query']}")
            # FALSE means the condition (or the consequent's negation) is reachable.
            row["result"] = "reachable" if value == "false" else "unreachable"
            row["result"] = {"antecedent": row["result"], "branch": row["result"],
                             "consequent probe": "falsifiable" if value == "false" else "invariant"}[row["kind"]]
            row["class"], row["rationale"] = "", ""
            if row["result"] in ("unreachable", "invariant"):
                key = (model, row["item"], row["index"])
                row["class"], row["rationale"] = TRIAGE.get(key, ("needs_investigation", "Not in the triage table."))
        for row in model_rows:
            row.setdefault("result", "n/a")
            row.setdefault("class", "")
            row.setdefault("rationale", "")
        rows += model_rows
        models[model] = {"source": source, "source_sha256": before[source],
                         "original_properties": len(original), "original_properties_true": sum(v == "true" for _, v in original),
                         "queries": len(checked),
                         "findings": [{k: r[k] for k in ("item", "index", "kind", "condition", "result", "class")} for r in checked if r["class"]]}
        found = models[model]["findings"]
        print(f"{model}: {models[model]['original_properties_true']}/{specs} original properties true; "
              f"{len(checked)} queries; {len(found)} unreachable/invariant findings "
              f"({sum(f['class'] == 'needs_investigation' for f in found)} need investigation).", flush=True)

    after = manifest()
    changed = sorted(k for k in before if after.get(k) != before[k])
    added = sorted(k for k in after if k not in before)
    integrity = {"method": "SHA-256 of every file in NuXmv Files outside VQE_NonVacuity, excluding .DS_Store",
                 "files_checked": len(before), "changed_or_missing": changed, "new_files_outside_isolated_folder": added}
    (HERE / "original_files_after.json").write_text(json.dumps(after, indent=2) + "\n")
    (HERE / "results/integrity.json").write_text(json.dumps(integrity, indent=2) + "\n")
    fields = ["model", "item", "index", "kind", "condition", "query", "result", "class", "rationale"]
    with (HERE / "results/witnesses.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: r[k] for k in fields} for r in rows)
    summary = {"run_utc": datetime.now(timezone.utc).isoformat(), "nuXmv": str(nuxmv), "nuXmv_sha256": digest(nuxmv),
               "engine": "BDD LTL model checking of G !(condition) / G (consequent) queries",
               "models": models, "integrity": integrity}
    (HERE / "results/summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    if changed or added:
        raise RuntimeError("original project integrity check failed; see results/integrity.json")
    pending = [f for m in models.values() for f in m["findings"] if f["class"] == "needs_investigation"]
    if pending:
        sys.exit(f"{len(pending)} findings need investigation; see results/witnesses.csv")
    print(f"All findings triaged; {len(before)} original files unchanged.")


if __name__ == "__main__":
    main()
