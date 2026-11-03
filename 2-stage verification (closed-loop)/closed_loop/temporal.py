"""Build and execute the independent DejaVu temporal projections."""
from __future__ import annotations

import gzip
import json
import os
from pathlib import Path
import subprocess

from .common import ROOT, WORKSPACE, file_hash, load_json, save_json

# The projected event that triggers each property's antecedent.
PROPERTY_TRIGGERS = {
    "L1_groupsBeforeEnergy": "energy",
    "L2_validationsBeforeCommit": "commit",
    "L3_energyAfterBegin": "energy",
    "L3_validationAfterEnergy": "validated",
    "L4_noActivityAfterStop": "stopped",
}
# Python obligations that fire once per corresponding projected event.
PYTHON_COUNTERPARTS = {
    "energy": ("L1", "groups_before_energy"),
    "commit": ("L2", "validations_before_commit"),
    "validated": ("L2", "validation_certified"),
    "stopped": ("L4", "terminal_reason"),
}


def parse_counts(details):
    return {item.split(":")[0]: int(item.split(":")[1]) for item in details.split(",") if item}


def monitor_outcomes(log_text):
    """Per-run violations and submitted-event counts from the bridge output."""
    violations, events = {}, {}
    for line in log_text.splitlines():
        if line.startswith("RESULT\t") or line.startswith("TRIGGERS\t"):
            kind, run_id, details = line.split("\t")
            (violations if kind == "RESULT" else events)[run_id] = parse_counts(details)
    return violations, events


def dejavu_record(violations, events):
    return {"violations": violations, "passed": not violations,
            "triggers": {name: events.get(event, 0) for name, event in PROPERTY_TRIGGERS.items()}}


def build_monitor(directory):
    existing = WORKSPACE / "VQE Runtime Verification - DejaVu"
    pins = load_json(existing / "tools/monitor_build_dependencies.json")
    runtime = existing / "src/vqe_runtime/vendor/dejavu/dejavu.jar"
    if file_hash(runtime) != pins["bundled_dejavu"]["sha256"]:
        raise ValueError("DejaVu runtime does not match the pinned hash")
    dependencies = []
    for name in ("scala-compiler", "scala-library", "scala-reflect"):
        pin = pins["artifacts"][name]
        path = ROOT / ".cache/scala-2.12.21" / pin["filename"]
        if not path.exists() or file_hash(path) != pin["sha256"]:
            raise FileNotFoundError(f"missing pinned monitor dependency: {path}; see README setup")
        dependencies.append(path)
    build = directory / "monitor-build"
    build.mkdir()
    classes = build / "classes"
    classes.mkdir()
    commands = [
        ["java", "-cp", str(runtime), "dejavu.Verify", str(ROOT / "formal/runtime.qtl")],
        ["java", "-cp", os.pathsep.join(map(str, dependencies)), "scala.tools.nsc.Main", "-usejavacp", "-classpath", str(runtime), "-d", str(classes), str(build / "TraceMonitor.scala"), str(ROOT / "formal/ClosedLoopBridge.scala")],
        ["jar", "--create", "--file", str(directory / "runtime-monitor.jar"), "--date=2026-01-01T00:00:00Z", "-C", str(classes), "."],
    ]
    for i, command in enumerate(commands):
        p = subprocess.run(command, cwd=build, capture_output=True, text=True, timeout=180)
        (directory / f"monitor-build-{i}.log").write_text(p.stdout + p.stderr)
        if p.returncode:
            raise RuntimeError(f"DejaVu build failed: inspect monitor-build-{i}.log")
    record = {"runtime_jar": str(runtime), "runtime_sha256": file_hash(runtime),
              "monitor_jar": "stage1/runtime-monitor.jar", "monitor_sha256": file_hash(directory / "runtime-monitor.jar"),
              "specification_sha256": file_hash(ROOT / "formal/runtime.qtl"), "dependency_pins": pins,
              "semantics": "DejaVu checks temporal projections during independent saved-trace replay; Python performs online numeric/protocol gating and replay."}
    save_json(directory / "runtime-monitor.json", record)
    return record


def project(e):
    r = e["run_id"]
    yield "activity", [r]
    kind = e["type"]
    if kind == "update_start":
        yield "begin", [r, e["update"]]
    elif kind == "measurement":
        yield ["groupZero", "groupOne", "groupTwo"][e["group"]], [r, e["update"], e["candidate"]]
    elif kind == "evaluation":
        yield "energy", [r, e["update"], e["candidate"]]
    elif kind == "numeric_valid":
        yield "validated", [r, e["update"], e["candidate"]]
        yield ["validZero", "validOne", "validTwo"][e["candidate"]], [r, e["update"]]
    elif kind == "optimizer_commit":
        yield "commit", [r, e["update"]]
    elif kind == "terminal":
        yield "stopped", [r]


def verify_traces(output, directory, results, monitor):
    runtime = Path(monitor["runtime_jar"])
    jar = Path(output) / monitor["monitor_jar"]
    if file_hash(runtime) != monitor["runtime_sha256"] or file_hash(jar) != monitor["monitor_sha256"]:
        raise ValueError("runtime monitor provenance mismatch")
    input_path = directory / "temporal-input.tsv"
    with input_path.open("w") as f:
        for result in results:
            f.write(f"RESET\t{result['run_id']}\n")
            with gzip.open(Path(output) / result["trace"], "rt") as stream:
                for line in stream:
                    e = json.loads(line)
                    for name, args in project(e):
                        f.write("\t".join(["EVENT", str(e["seq"]), name] + [str(v) for v in args]) + "\n")
            f.write("END\n")
    with input_path.open() as stdin:
        p = subprocess.run(["java", "-Xmx2g", "-cp", os.pathsep.join([str(jar), str(runtime)]), "ClosedLoopBridge"], stdin=stdin, capture_output=True, text=True, timeout=600)
    (directory / "dejavu.log").write_text(p.stdout + p.stderr)
    if p.returncode:
        raise RuntimeError("DejaVu replay failed; inspect dejavu.log")
    outcomes, events = monitor_outcomes(p.stdout)
    if set(outcomes) != {r["run_id"] for r in results} or set(events) != set(outcomes):
        raise RuntimeError("DejaVu did not return exactly one result for every trace")
    for result in results:
        run_id = result["run_id"]
        result["dejavu"] = dejavu_record(outcomes[run_id], events[run_id])
        for name, count in outcomes[run_id].items():
            cid = name.split("_")[0]
            if cid not in result["contracts"] or result["contracts"][cid]["runtime_verdict"] != "DISAGREEMENT":
                raise RuntimeError(f"DejaVu/Python temporal disagreement: {run_id} {name} ({count})")
        # The monitor must have seen the antecedent events Python checked; otherwise
        # its properties could pass vacuously because the projection dropped them.
        observed = {event: events[run_id].get(event, 0) for event in PYTHON_COUNTERPARTS}
        expected = {event: result["contracts"][cid]["triggers"][obligation] for event, (cid, obligation) in PYTHON_COUNTERPARTS.items()}
        result["dejavu"]["trigger_agreement"] = observed == expected
        if observed != expected and not any(row["violations"] for row in result["contracts"].values()):
            raise RuntimeError(f"DejaVu/Python trigger mismatch (projection drift): {run_id} monitor={observed} python={expected}")
    return {"tool": "DejaVu", "input_sha256": file_hash(input_path), "log_sha256": file_hash(directory / "dejavu.log"),
            "passed_runs": sum(not v for v in outcomes.values()), "total_runs": len(results),
            "exercised_runs": {name: sum(r["dejavu"]["triggers"][name] > 0 for r in results) for name in PROPERTY_TRIGGERS},
            "trigger_totals": {name: sum(r["dejavu"]["triggers"][name] for r in results) for name in PROPERTY_TRIGGERS}}
