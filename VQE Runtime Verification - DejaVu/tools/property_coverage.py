#!/usr/bin/env python3
"""Report which DejaVu properties a recorded trace actually exercised.

Almost every property in ``specs/vqe_runtime.qtl`` has the form
``Forall ... . (trigger(...) -> history)``: it passes vacuously when its trigger
never occurs. For each trace this tool counts each property's trigger events and
classifies the property as

- EXERCISED: a trigger occurred (and any nested antecedent occurred too);
- NOT_APPLICABLE: the recorded configuration rules every trigger out;
- NOT_EXERCISED: applicable, but no trigger occurred;
- NESTED_NOT_EXERCISED: the trigger occurred, but the inner antecedent of a
  nested implication never did, so its consequent was never required.

The tool is offline and uses only the standard library. It never changes a
verdict; it reports how much of a PASS is backed by exercised obligations.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "specs/vqe_runtime.qtl"
OUT = ROOT / "artifacts/validation"

# Properties whose consequent is itself an implication, with that inner antecedent.
NESTED = {
    "intra_allDeclaredTermsObserved": "termExpected",
    "inter_closeAfterCommittedUpdate": "optimizerUpdateIntent",
    "run_failureRequiresAbortAtClose": "criticalFail",
}

# Trigger events that only a particular recorded configuration can produce.
APPLICABILITY = {
    "optimizerOpaqueConfigured": ("optimizer_protocol", "opaque"),
    "opaqueOptimizerAdvanced": ("optimizer_protocol", "opaque"),
    "optimizerAskTellConfigured": ("optimizer_protocol", "ask-tell"),
    "optimizerUpdateIntent": ("optimizer_protocol", "ask-tell"),
    "optimizerUpdated": ("optimizer_protocol", "ask-tell"),
    "runOptimizerStopped": ("allow_optimizer_stopped", True),
}


def _strip_outer(text: str) -> str:
    text = text.strip()
    while text.startswith("(") and _closing(text, 0) == len(text) - 1:
        text = text[1:-1].strip()
    return text


def _closing(text: str, start: int) -> int:
    depth = 0
    for i in range(start, len(text)):
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        if depth == 0:
            return i
    raise ValueError(f"unbalanced parentheses: {text!r}")


def _split_implication(text: str) -> tuple[str, str] | None:
    """Split at the top-level '->', if there is one."""
    depth = 0
    for i in range(len(text) - 1):
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        if depth == 0 and text[i:i + 2] == "->":
            return text[:i], text[i + 2:]
    return None


def _predicates(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"([A-Za-z_]\w*)\s*\(", text)))


def parse_spec(path: Path = SPEC) -> dict[str, dict[str, Any]]:
    """Each property's outer trigger predicates and nested inner antecedent."""
    text = re.sub(r"//[^\n]*", "", path.read_text())
    properties = {}
    for match in re.finditer(r"prop\s+(\w+)\s*:(.*?)(?=\bprop\s+\w+\s*:|\Z)", text, re.S):
        name, body = match.group(1), match.group(2)
        body = re.sub(r"^\s*(?:Forall\s+\w+\s*\.\s*)+", "", body)
        split = _split_implication(_strip_outer(body))
        if split is None:
            raise ValueError(f"{name}: not a trigger-shaped implication")
        antecedent, consequent = split
        triggers = _predicates(antecedent)
        inner = _split_implication(_strip_outer(consequent))
        nested = None
        if inner is not None:
            inner_predicates = _predicates(inner[0])
            if len(inner_predicates) != 1:
                raise ValueError(f"{name}: nested antecedent has {inner_predicates}")
            nested = inner_predicates[0]
        properties[name] = {"triggers": triggers, "nested": nested}
    detected = {name: p["nested"] for name, p in properties.items() if p["nested"]}
    if detected != NESTED:
        raise ValueError(f"nested implications changed: {detected}")
    return properties


def load_trace(path: Path) -> tuple[Counter, dict[str, Any]]:
    counts: Counter = Counter()
    execution: dict[str, Any] = {}
    with path.open() as stream:
        for line in stream:
            event = json.loads(line)
            counts[event["event"]] += 1
            if event["event"] == "runStarted":
                execution = event["payload"]["config"]["execution"]
    if "runStarted" not in counts:
        raise ValueError(f"{path}: trace has no runStarted event")
    return counts, execution


def applicable(predicate: str, execution: dict[str, Any]) -> bool:
    if predicate not in APPLICABILITY:
        return True
    key, value = APPLICABILITY[predicate]
    return execution.get(key) == value


def classify(properties: dict[str, dict[str, Any]], counts: Counter, execution: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = {}
    for name, p in properties.items():
        live = [t for t in p["triggers"] if applicable(t, execution)]
        fired = sum(counts[t] for t in live)
        if not live:
            status = "NOT_APPLICABLE"
        elif fired == 0:
            status = "NOT_EXERCISED"
        elif p["nested"] and counts[p["nested"]] == 0:
            status = "NESTED_NOT_EXERCISED"
        else:
            status = "EXERCISED"
        rows[name] = {
            "status": status,
            "trigger_counts": {t: counts[t] for t in p["triggers"]},
            "inapplicable_triggers": [t for t in p["triggers"] if t not in live],
            "unfired_triggers": [t for t in live if counts[t] == 0],
            "nested_antecedent": p["nested"],
            "nested_count": counts[p["nested"]] if p["nested"] else None,
        }
    return rows


def report(trace: Path, properties: dict[str, dict[str, Any]]) -> dict[str, Any]:
    counts, execution = load_trace(trace)
    rows = classify(properties, counts, execution)
    summary = dict(Counter(row["status"] for row in rows.values()))
    return {"trace": str(trace), "specification": str(SPEC.relative_to(ROOT)), "properties": len(rows),
            "configuration": {k: execution.get(k) for k in ("optimizer_protocol", "allow_optimizer_stopped", "max_iterations")},
            "summary": summary, "events": dict(sorted(counts.items())), "rows": rows}


def markdown(result: dict[str, Any]) -> str:
    lines = [f"# DejaVu property coverage: `{Path(result['trace']).name}`", "",
             f"Configuration: {', '.join(f'{k} = {v}' for k, v in result['configuration'].items())}.", "",
             "| Status | Properties |", "|---|---:|"]
    for status in ("EXERCISED", "NOT_APPLICABLE", "NOT_EXERCISED", "NESTED_NOT_EXERCISED"):
        lines.append(f"| {status} | {result['summary'].get(status, 0)} |")
    lines += ["", "A PASS on a NOT_EXERCISED or NESTED_NOT_EXERCISED property is vacuous for this trace; "
              "NOT_APPLICABLE properties cannot fire under the recorded configuration.", "",
              "| Property | Status | Trigger events | Detail |", "|---|---|---|---|"]
    order = {"NOT_EXERCISED": 0, "NESTED_NOT_EXERCISED": 1, "NOT_APPLICABLE": 2, "EXERCISED": 3}
    for name, row in sorted(result["rows"].items(), key=lambda item: (order[item[1]["status"]], item[0])):
        counts = ", ".join(f"{t}: {n}" for t, n in row["trigger_counts"].items())
        detail = []
        if row["inapplicable_triggers"]:
            detail.append("not applicable: " + ", ".join(row["inapplicable_triggers"]))
        if row["unfired_triggers"] and row["status"] == "EXERCISED":
            detail.append("disjuncts never fired: " + ", ".join(row["unfired_triggers"]))
        if row["nested_antecedent"]:
            detail.append(f"nested antecedent {row['nested_antecedent']}: {row['nested_count']}")
        lines.append(f"| {name} | {row['status']} | {counts} | {'; '.join(detail)} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("traces", nargs="+", type=Path)
    parser.add_argument("--output-dir", type=Path, default=OUT)
    args = parser.parse_args()
    properties = parse_spec()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for trace in args.traces:
        result = report(trace, properties)
        stem = args.output_dir / f"property_coverage_{trace.stem}"
        stem.with_suffix(".json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        stem.with_suffix(".md").write_text(markdown(result))
        print(f"{trace.name}: {result['properties']} properties; "
              + ", ".join(f"{k} {v}" for k, v in sorted(result["summary"].items())))


if __name__ == "__main__":
    main()
