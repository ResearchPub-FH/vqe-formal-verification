"""Non-vacuity audit of the approved experiment (read-only; writes only to _out/nonvacuity).

Logical: witnesses, branch coverage and seeded mutants on the frozen 7-property controller.
Runtime: replays every approved trace with the obligation-counting checker, checks the
completed-run coverage equations, and counts DejaVu antecedent events in the retained
monitor inputs. Uses the experiment's own checker and nuXmv harness. Python >= 3.11 + NumPy.
"""
import gzip, json, re, sys
from collections import Counter
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXP))
from closed_loop.common import file_hash, load_json, save_json
from closed_loop.comparison import SHORT, expected_triggers
from closed_loop.execution import replay
from closed_loop import pre_execution
from closed_loop.pre_execution import check_controller, tool_path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import legacy_controller
from legacy_controller import requirements

# The frozen controller predates the current logical model; check it with its own obligations.
pre_execution.mutants = legacy_controller.mutants
pre_execution.nonvacuity_queries = legacy_controller.nonvacuity_queries
from closed_loop.temporal import PROPERTY_TRIGGERS, PYTHON_COUNTERPARTS

RUN = EXP / "artifacts/approved-experiment"
OUT = Path(__file__).resolve().parent / "_out/nonvacuity"
OUT.mkdir(parents=True, exist_ok=True)
CONTRACTS = ("L1", "L2", "L3", "L4", "N1", "N2", "N3", "N4")

pre_path = RUN / "stage1/pre_execution.json"
pre = load_json(pre_path)
seal = load_json(pre_path.with_suffix(".seal.json"))["sha256"]
assert file_hash(pre_path) == seal, "approved Stage 1 record does not match its seal"
c = pre["configuration"]

# Logical: the frozen controller exactly as Stage 1 checked it.
controller = RUN / "stage1/controller.smv"
assert file_hash(controller) == pre["artifacts"]["stage1/controller.smv"], "frozen controller changed"
frozen = controller.read_text()
names = re.findall(r"^LTLSPEC NAME (\w+) :=", frozen, re.M)
props = [p for p in requirements(c) if p["name"] in names]
assert [p["name"] for p in props] == names, "frozen controller properties are not all in the requirement table"
(OUT / "nuxmv").mkdir(exist_ok=True)
logical = check_controller(tool_path("nuXmv"), OUT / "nuxmv", c, props, frozen)
queries = logical["nonvacuity"]["results"] or []


def monitor_events(tsv):
    """Per-run counts of projected events in a retained DejaVu input file."""
    runs, current = {}, None
    for line in tsv.read_text().splitlines():
        parts = line.split("\t")
        if parts[0] == "RESET":
            current = runs.setdefault(parts[1], Counter())
        elif parts[0] == "EVENT":
            current[parts[2]] += 1
    return runs


runtime = {}
for stage in ("baseline", "faults"):
    report = load_json(RUN / f"stage2/{stage}/results.json")
    tsv = RUN / f"stage2/{stage}/temporal-input.tsv"
    assert file_hash(tsv) == report["temporal_monitor"]["input_sha256"], f"{stage} monitor input changed"
    events = monitor_events(tsv)
    rows, changed, coverage_failures, trigger_mismatches = [], [], [], []
    for approved in report["results"]:
        path = RUN / approved["trace"]
        assert file_hash(path) == approved["trace_sha256"], f"trace changed: {path}"
        result = replay(c, seal, path)
        before = {cid: approved["contracts"][cid]["runtime_verdict"] for cid in CONTRACTS}
        after = {cid: result["contracts"][cid]["runtime_verdict"] for cid in CONTRACTS}
        if before != after:
            changed.append({"run_id": approved["run_id"], "before": before, "after": after})
        triggers = {cid: result["contracts"][cid]["triggers"] for cid in CONTRACTS}
        if result["terminal_reason"] in ("success", "budget") and triggers != expected_triggers(result, c):
            coverage_failures.append(approved["run_id"])
        seen = events[approved["run_id"]]
        monitor = {event: seen.get(event, 0) for event in PYTHON_COUNTERPARTS}
        python = {event: triggers[cid][obligation] for event, (cid, obligation) in PYTHON_COUNTERPARTS.items()}
        if monitor != python:
            trigger_mismatches.append({"run_id": approved["run_id"], "monitor": monitor, "python": python})
        rows.append({"run_id": approved["run_id"], "fault": approved.get("fault"), "verdicts": after, "triggers": triggers,
                     "dejavu_passed": approved["dejavu"]["passed"],
                     "dejavu_triggers": {name: seen.get(event, 0) for name, event in PROPERTY_TRIGGERS.items()}})
    runtime[stage] = {"runs": len(rows), "verdict_changes": changed, "coverage_failures": coverage_failures,
                      "trigger_mismatches": trigger_mismatches,
                      "obligation_totals": {cid: dict(sum((Counter(r["triggers"][cid]) for r in rows), Counter())) for cid in CONTRACTS},
                      "dejavu_exercised_runs": {name: sum(r["dejavu_triggers"][name] > 0 for r in rows) for name in PROPERTY_TRIGGERS},
                      "rows": rows}

summary = {
    "approved_stage1_seal": seal,
    "logical": {"status": logical["status"], "properties": [{k: p[k] for k in ("name", "contract", "holds")} for p in logical["properties"]],
                "queries": len(queries), "queries_as_expected": sum(q["as_expected"] for q in queries),
                "unexpected_queries": [q for q in queries if not q["as_expected"]],
                "unreachable_defensive_branches": [q["branch"] for q in queries if q["kind"] == "branch" and not q["expected"] and not q["holds"]],
                "mutants": [{k: m[k] for k in ("mutant", "target_contract", "killed", "detected_by", "failing_properties", "failing_witnesses")} for m in logical["mutation"]]},
    "runtime": {stage: {k: v for k, v in data.items() if k != "rows"} for stage, data in runtime.items()},
}
save_json(OUT / "nonvacuity_audit.json", summary | {"runs": {stage: data["rows"] for stage, data in runtime.items()}})

lg, base, faults = summary["logical"], runtime["baseline"], runtime["faults"]
lines = ["# Non-vacuity audit of the approved experiment", "",
         f"Read-only over `artifacts/approved-experiment` (Stage 1 seal `{seal}`). Generated by `audit/nonvacuity_audit.py`.", "",
         "## Logical: frozen 7-property controller", "",
         f"Status under the new gate: **{lg['status']}**. Properties holding: {sum(p['holds'] is True for p in lg['properties'])}/{len(lg['properties'])}. "
         f"Non-vacuity queries with the expected result: {lg['queries_as_expected']}/{lg['queries']}. "
         f"Defensive branches unreachable: {', '.join(f'`{b}`' for b in lg['unreachable_defensive_branches']) or 'none'}.", "",
         "| Seeded mutant | Target | Killed | Failing properties | Failing witnesses |", "|---|---|---|---|---|"]
for m in lg["mutants"]:
    lines.append(f"| {m['mutant']} | {m['target_contract']} | {m['killed']} | {', '.join(m['failing_properties']) or '—'} | {', '.join(m['failing_witnesses']) or '—'} |")
lines += ["", "A mutant caught only by witnesses passes every property; without the witness check it would have been accepted.", "",
          "## Runtime: baseline", "",
          f"{base['runs']} traces replayed. Verdict changes under obligation counting: {len(base['verdict_changes'])}. "
          f"Completed runs violating the coverage equations: {len(base['coverage_failures'])}. "
          f"DejaVu/Python trigger mismatches: {len(base['trigger_mismatches'])}.", "",
          "| Contract | Obligation totals |", "|---|---|"]
for cid in CONTRACTS:
    lines.append(f"| {cid} | " + "; ".join(f"{k}: {v:,}" for k, v in base["obligation_totals"][cid].items()) + " |")
lines += ["", "| DejaVu property | Baseline runs exercised |", "|---|---:|"]
for name, n in base["dejavu_exercised_runs"].items():
    lines.append(f"| {name} | {n}/{base['runs']} |")
lines += ["", "## Runtime: faults", "",
          f"{faults['runs']} traces replayed; {len(faults['verdict_changes'])} change verdict. DejaVu/Python trigger mismatches: {len(faults['trigger_mismatches'])}.", "",
          "| Fault | " + " | ".join(CONTRACTS) + " | DejaVu result | DejaVu properties exercised |", "|---|" + "---|" * (len(CONTRACTS) + 2)]
for fault in sorted({r["fault"] for r in faults["rows"]}):
    tested = [r for r in faults["rows"] if r["fault"] == fault]
    cells = []
    for cid in CONTRACTS:
        counts = Counter(r["verdicts"][cid] for r in tested)
        cells.append(", ".join(f"{SHORT[v]}{'' if len(counts) == 1 else f':{n}'}" for v, n in sorted(counts.items())))
    passed = Counter("PASS" if r["dejavu_passed"] else "FAIL" for r in tested)
    exercised = sorted({name for r in tested for name, n in r["dejavu_triggers"].items() if n})
    lines.append(f"| {fault} | " + " | ".join(cells) + f" | {', '.join(f'{k}:{v}' for k, v in passed.items())} | {', '.join(exercised) or 'none'} |")
lines += ["", "Cells use the approved traces with obligation counting: an obligation that never fired is INCONCLUSIVE (I) instead of a vacuous AGREEMENT.", ""]
(OUT / "REPORT.md").write_text("\n".join(lines))
print("\n".join(lines))
