#!/usr/bin/env python3
"""Run simulator fixtures that exercise the DejaVu properties Table VII left unexercised.

The 50-evaluation Sampler runs never converged and never failed, so the
convergence and abort properties passed vacuously. Two local StatevectorSampler
fixtures exercise them through the unmodified runner:

- converging: ``configs/h2_statevector_converging.toml`` (the h2_statevector
  profile with a 100-evaluation budget; convergence policy unchanged) ends in
  ``runConverged``.
- injected backend failure: ``configs/h2_statevector.toml`` with a sampler whose
  job fails on result retrieval at evaluation 12. The runner's own exception
  path emits ``criticalFail``, ``iterationAborted``, ``runAborted`` and
  ``runClosed``.

Each fixture is replayed from its trace and raw evidence, and property coverage
is reported for the fixtures together with the two Table VII traces. Existing
outputs are never overwritten. Requires the Qiskit extra.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import property_coverage  # noqa: E402
from vqe_runtime import sampler_runner  # noqa: E402
from vqe_runtime.checker import check_trace  # noqa: E402
from vqe_runtime.config import load_config  # noqa: E402

FAIL_AT_EVALUATION = 12
INJECTED = "injected backend failure: job result unavailable"
TABLE_VII = ("h2_statevector_sampler_20260907", "h2_ibm_marrakesh_sampler_20260907")
FIXTURES = {
    "converging": {"config": "configs/h2_statevector_converging.toml",
                   "stem": "h2_statevector_sampler_converging_20261025"},
    "injected_failure": {"config": "configs/h2_statevector.toml",
                         "stem": "h2_statevector_sampler_injected_failure_20261025"},
}


class FailingJob:
    """A submitted job whose result retrieval fails, as a lost backend job would."""

    def __init__(self, job):
        self._job = job

    def result(self):
        raise RuntimeError(INJECTED)

    def __getattr__(self, name):
        return getattr(self._job, name)


class FailingSampler:
    def __init__(self, sampler, fail_at):
        self._sampler = sampler
        self._fail_at = fail_at
        self.calls = 0

    def run(self, pubs, **options):
        job = self._sampler.run(pubs, **options)
        self.calls += 1
        return FailingJob(job) if self.calls == self._fail_at else job


def paths(stem):
    return {"trace": ROOT / f"artifacts/traces/{stem}.jsonl",
            "evidence": ROOT / f"artifacts/evidence/{stem}.jsonl",
            "online": ROOT / f"artifacts/reports/{stem}-online.json",
            "replay": ROOT / f"artifacts/reports/{stem}-replay.json"}


def run_fixture(name, spec):
    config = load_config(ROOT / spec["config"])
    out = paths(spec["stem"])
    existing = [str(p) for p in out.values() if p.exists()]
    if existing:
        raise SystemExit(f"refusing to overwrite fixture outputs: {existing}")
    original = sampler_runner._make_sampler
    if name == "injected_failure":
        sampler_runner._make_sampler = lambda config, *, runtime_backend=None: FailingSampler(
            original(config, runtime_backend=runtime_backend), FAIL_AT_EVALUATION)
    try:
        sampler_runner.run_sampled_vqe(config, trace_path=out["trace"], report_path=out["online"],
                                       evidence_path=out["evidence"], run_id=spec["stem"].replace("_", "-"))
        raised = None
    except RuntimeError as error:
        if name != "injected_failure" or str(error) != INJECTED:
            raise
        raised = str(error)
    finally:
        sampler_runner._make_sampler = original
    replay = check_trace(config, out["trace"], report_path=out["replay"], evidence_path=out["evidence"])
    online = json.loads(out["online"].read_text())
    return {"fixture": name, "config": spec["config"], "trace": str(out["trace"].relative_to(ROOT)),
            "injected_exception": raised, "terminal_reason": online["terminal_reason"],
            "online_status": online["status"], "replay_status": replay.as_dict()["status"],
            "online_levels": {k: v["status"] for k, v in online["levels"].items()},
            "replay_levels": {k: v["status"] for k, v in replay.as_dict()["levels"].items()},
            "online_findings": [f for v in online["levels"].values() for f in v["findings"]]}


def corpus(properties, traces):
    results = {Path(t).stem: property_coverage.report(Path(t), properties) for t in traces}
    rank = {"EXERCISED": 0, "NESTED_NOT_EXERCISED": 1, "NOT_EXERCISED": 2, "NOT_APPLICABLE": 3}
    rows = {}
    for name in properties:
        statuses = {stem: r["rows"][name]["status"] for stem, r in results.items()}
        rows[name] = {"status": min(statuses.values(), key=rank.get), "per_trace": statuses,
                      "exercised_by": [stem for stem, s in statuses.items() if s == "EXERCISED"]}
    return results, rows


def write_corpus(rows, results, fixtures):
    out = ROOT / "artifacts/validation/property_coverage_corpus"
    summary = dict(Counter(r["status"] for r in rows.values()))
    out.with_suffix(".json").write_text(json.dumps({"summary": summary, "fixtures": fixtures, "properties": rows,
                                                    "per_trace_summary": {s: r["summary"] for s, r in results.items()}},
                                                   indent=2, sort_keys=True) + "\n")
    stems = list(results)
    short = {"EXERCISED": "E", "NOT_APPLICABLE": "N/A", "NOT_EXERCISED": "—", "NESTED_NOT_EXERCISED": "nested"}
    lines = ["# DejaVu property coverage across the Table VII traces and simulator fixtures", "",
             "Generated by `tools/run_coverage_fixtures.py`. A property counts as exercised when at least one trace fired its trigger "
             "(and any nested antecedent) and the monitor accepted that trace.", "",
             "| Trace | Terminal | Online / replay | " + " | ".join(("EXERCISED", "NOT_APPLICABLE", "NOT_EXERCISED", "NESTED_NOT_EXERCISED")) + " |",
             "|---|---|---|---:|---:|---:|---:|"]
    by_trace = {Path(f["trace"]).stem: f for f in fixtures}
    for stem, r in results.items():
        fixture = by_trace.get(stem)
        terminal = fixture["terminal_reason"] if fixture else "max_iterations"
        verdicts = f"{fixture['online_status']} / {fixture['replay_status']}" if fixture else "pass / pass (Table VII)"
        lines.append(f"| `{stem}` | {terminal} | {verdicts} | " + " | ".join(str(r["summary"].get(s, 0)) for s in ("EXERCISED", "NOT_APPLICABLE", "NOT_EXERCISED", "NESTED_NOT_EXERCISED")) + " |")
    lines += ["", "Corpus: " + ", ".join(f"{k} {v}" for k, v in sorted(summary.items())) + ".", "",
              "Properties not exercised by both Table VII traces:", "",
              "| Property | " + " | ".join(f"`{s}`" for s in stems) + " | Corpus |", "|---|" + "---|" * (len(stems) + 1)]
    for name, row in sorted(rows.items()):
        if all(row["per_trace"][s] == "EXERCISED" for s in TABLE_VII):
            continue
        lines.append(f"| {name} | " + " | ".join(short[row["per_trace"][s]] for s in stems) + f" | {row['status']} |")
    out.with_suffix(".md").write_text("\n".join(lines) + "\n")
    return summary


def main():
    fixtures = [run_fixture(name, spec) for name, spec in FIXTURES.items()]
    properties = property_coverage.parse_spec()
    traces = [ROOT / f"artifacts/traces/{stem}.jsonl" for stem in TABLE_VII] + [ROOT / f["trace"] for f in fixtures]
    results, rows = corpus(properties, traces)
    for stem, r in results.items():
        stem_path = ROOT / f"artifacts/validation/property_coverage_{stem}"
        stem_path.with_suffix(".json").write_text(json.dumps(r, indent=2, sort_keys=True) + "\n")
        stem_path.with_suffix(".md").write_text(property_coverage.markdown(r))
    summary = write_corpus(rows, results, fixtures)
    for f in fixtures:
        print(f"{f['fixture']}: terminal={f['terminal_reason']} online={f['online_status']} replay={f['replay_status']} "
              f"levels={f['online_levels']} injected={f['injected_exception'] is not None}")
    print("corpus:", summary)


if __name__ == "__main__":
    main()
