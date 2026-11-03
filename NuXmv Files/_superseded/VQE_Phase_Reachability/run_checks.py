#!/usr/bin/env python3
"""Verify byte-identical VQE snapshots; write only inside this isolated folder."""

import argparse
import csv
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
PHASES = {
    "BIND": "BIND",
    "MEASURE": "EXECUTE_MEASURE",
    "AGGREGATE": "COMPUTE_ENERGY",
    "CHECK_STOP": "CHECK_STOP",
    "OPTIMIZE": "OPTIMIZER_STEP",
    "DONE": "DONE",
}
MODELS = ("baseline", "refined_abort", "canonical")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(nuxmv, name, commands):
    script = HERE / "commands" / (name + ".cmd")
    log = HERE / "results" / (name + ".log")
    script.write_text("\n".join(commands + ["quit"]) + "\n")
    completed = subprocess.run(
        [str(nuxmv), "-s", "-source", str(script)],
        cwd=HERE,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=60,
        check=False,
    )
    log.write_text(completed.stdout)
    return completed.returncode, completed.stdout


def verdicts(output):
    return re.findall(r"^-- specification (.+)\s+is (true|false)\s*$", output, re.M)


def checked_run(nuxmv, name, commands):
    code, output = run(nuxmv, name, commands)
    if code != 0 or re.search(r"aborting|syntax error|cannot build|undefined", output, re.I):
        raise RuntimeError(f"nuXmv command failed; see results/{name}.log")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nuxmv", type=Path, default=PROJECT / "nuXmv/bin/nuXmv")
    args = parser.parse_args()
    nuxmv = args.nuxmv.resolve()
    for directory in ("commands", "results"):
        (HERE / directory).mkdir(exist_ok=True)

    before = json.loads((HERE / "original_files_before.json").read_text())
    sources = json.loads((HERE / "sources.json").read_text())
    for name, source in sources.items():
        if digest(HERE / "snapshots" / (name + ".smv")) != before[source]:
            raise RuntimeError(f"Snapshot changed: {name}")

    (HERE / "reachability_properties.smv").write_text(
        "-- Reference property fragment; commands inject these queries without editing a model.\n"
        + "\n".join(
            f"CTLSPEC NAME reachable_{label.lower()} := EF (state = {state});"
            for label, state in PHASES.items()
        ) + "\n"
    )
    rows = []
    model_results = {}
    for name in MODELS:
        setup = [f'read_model -i "snapshots/{name}.smv"', "go"]
        checks = [f'check_ctlspec -p "EF (state = {state})"' for state in PHASES.values()]
        distances = [
            f'check_compute -p "MIN [state = S_INIT, state = {state}]"'
            for state in PHASES.values()
        ]
        output = checked_run(
            nuxmv, name + "_reachability",
            setup + ["check_fsm", "print_reachable_states"] + checks + distances,
        )
        values = verdicts(output)
        if len(values) != 6:
            raise RuntimeError(f"Expected six CTL results for {name}; found {values}")
        depths = re.findall(r"^-- the result of .*? is (\d+)\s*$", output, re.M)
        if len(depths) != 6:
            raise RuntimeError(f"Expected six MIN results; see {name}_reachability.log")
        total = "The transition relation is total" in output
        if not total:
            raise RuntimeError(f"Totality was not confirmed for {name}")
        reach = re.search(r"reachable states:\s*([^\n]+)", output, re.I)
        for (label, state), (_, value), depth in zip(PHASES.items(), values, depths):
            rows.append({
                "model": name, "phase": label,
                "formula": f"EF (state = {state})",
                "result": value.upper(), "minimum_transitions": int(depth),
            })

        # Intentionally false AG queries generate finite counterexamples that
        # are positive reachability witnesses for the corresponding EF query.
        witness_commands = [
            f'check_ctlspec -p "AG !(state = {state})"' for state in PHASES.values()
        ]
        witness_commands.append('check_ctlspec -p "AG !(state = DONE & iter > 0)"')
        witness_output = checked_run(nuxmv, name + "_witnesses", setup + witness_commands)
        witness_values = verdicts(witness_output)
        if len(witness_values) != 7 or any(value != "false" for _, value in witness_values):
            raise RuntimeError(f"Expected seven positive witness traces for {name}")
        if witness_output.count("Trace Type: Counterexample") != 7:
            raise RuntimeError(f"Missing witness trace for {name}")

        # One execution can visit all six phases in order, including an
        # optimization before subsequently terminating.
        nested = "EF (state = DONE)"
        for state in reversed(list(PHASES.values())[:-1]):
            nested = f"EF (state = {state} & {nested})"
        supplemental_commands = [f'check_ctlspec -p "{nested}"']
        if name != "baseline":
            supplemental_commands.append('check_ctlspec -p "EF (state = ABORT)"')
        extra = checked_run(nuxmv, name + "_supplemental", setup + supplemental_commands)
        extra_values = verdicts(extra)
        if len(extra_values) != len(supplemental_commands) or any(v != "true" for _, v in extra_values):
            raise RuntimeError(f"Supplemental reachability did not pass for {name}")
        model_results[name] = {
            "source": sources[name],
            "source_sha256": before[sources[name]],
            "transition_relation_total": total,
            "reachable_states_output": reach.group(1) if reach else None,
            "ordered_all_six_phases": True,
            "abort_reachable": True if name != "baseline" else None,
            "witness_count": 7,
        }
        print(f"{name}: {sum(v == 'true' for _, v in values)}/6 EF properties TRUE; seven witness traces saved.", flush=True)

    # Preserve and diagnose the older source exactly as supplied. Its INIT
    # enumeration token is reserved in the installed nuXmv parser.
    legacy_code, legacy_output = run(nuxmv, "legacy_parse", ['read_model -i "snapshots/legacy.smv"'])
    legacy_parse_error = "syntax error" in legacy_output.lower()
    if not legacy_parse_error:
        raise RuntimeError("Legacy parse outcome changed; inspect results/legacy_parse.log")

    after = {}
    changed = []
    for relative, old_digest in before.items():
        path = PROJECT / relative
        after[relative] = digest(path) if path.is_file() else None
        if after[relative] != old_digest:
            changed.append(relative)
    added_outside = sorted(
        str(p.relative_to(PROJECT))
        for p in PROJECT.rglob("*")
        if p.is_file() and p.name != ".DS_Store"
        and not p.is_relative_to(HERE)
        and str(p.relative_to(PROJECT)) not in before
    )
    integrity = {
        "method": "SHA-256 of every pre-existing regular file, excluding .DS_Store",
        "files_checked": len(before), "changed_or_missing": changed,
        "new_files_outside_isolated_folder": added_outside,
        "snapshots_byte_identical": True,
    }
    (HERE / "original_files_after.json").write_text(json.dumps(after, indent=2) + "\n")
    (HERE / "results/integrity.json").write_text(json.dumps(integrity, indent=2) + "\n")
    if changed or added_outside:
        raise RuntimeError("Original project integrity check failed; see results/integrity.json")

    summary = {
        "run_utc": datetime.now(timezone.utc).isoformat(),
        "nuXmv": str(nuxmv), "nuXmv_sha256": digest(nuxmv),
        "version": "2.1.0", "engine": "BDD CTL model checking (unbounded EF)",
        "MAX_ITERS": 5, "NTERMS": 3,
        "queries": rows, "models": model_results,
        "legacy": {"source": sources["legacy"], "status": "PARSE_ERROR", "exit_code": legacy_code},
        "integrity": integrity,
    }
    (HERE / "results/summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    with (HERE / "results/reachability.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    if any(row["result"] != "TRUE" for row in rows):
        raise SystemExit("Some phases were not reachable; inspect results/reachability.csv")
    print(f"All 18 requested EF checks passed; {len(before)} original files unchanged.")


if __name__ == "__main__":
    main()
