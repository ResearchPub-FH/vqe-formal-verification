#!/usr/bin/env python3
"""Two simulator runs of the reference configuration for the companion page's opening view.

Both runs use the frozen configuration of the reference run
(2-stage verification (closed-loop)/artifacts/experiment) and the seed of its run
baseline-0000. The declared run is baseline-0000 itself, as recorded: it aggregates
energies with the declared Hamiltonian coefficients. The swapped run is executed here
with the same seed and exchanges the YZ and XX coefficients at every evaluation, so
its optimizer minimizes the wrong operator. It is not gated by the runtime monitor
and continues to its own stop (success by the ideal-energy oracle of the declared
operator, or the iteration budget).

The run loop repeats closed_loop.execution.execute_run event for event (same
random-number stream, same trace schema) without stopping at a detected violation,
and uses the experiment's own physics and energy functions. Before the swapped run,
the loop's declared run is checked against execute_run itself on this machine.
Both traces are replayed through the experiment's runtime checker.

Exact counts depend on the platform's floating-point rounding where two outcome
probabilities tie (e.g. 0.25 and 0.25): NumPy's binomial sampler then takes
different branches. The swapped run is reproducible bit for bit on the platform
recorded in results.json.

Writes swapped.jsonl.gz and results.json into --out-dir, which must not exist yet.
Python >= 3.11 and NumPy 2.5.3.
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
from pathlib import Path
import platform
import sys
import tempfile

import numpy as np

HERE = Path(__file__).resolve().parent
CLOSED = HERE.parents[1] / "2-stage verification (closed-loop)"
REFERENCE = CLOSED / "artifacts" / "experiment"
sys.path.insert(0, str(CLOSED))

from closed_loop.common import canonical, digest, file_hash  # noqa: E402
from closed_loop.execution import execute_run, execution_values, replay  # noqa: E402
from closed_loop.physics import GROUP_VALUES, candidate_indices, ideal_success, point  # noqa: E402

SEED_RUN = "baseline-0000"


def run(c, run_id, seed_words, pre_digest, path, swap):
    """execute_run without monitor gating; swap exchanges YZ and XX at every evaluation."""
    rng = np.random.default_rng(np.random.SeedSequence(seed_words))
    index, seq, shots_total, updates, reason = list(c["initial_index"]), 0, 0, 0, None
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        def emit(kind, **data):
            nonlocal seq
            seq += 1
            stream.write(canonical({"seq": seq, "type": kind, "run_id": run_id, "configuration_digest": digest(c), **data}) + "\n")

        emit("run_start", pre_execution_digest=pre_digest, index=index, seed_words=seed_words,
             injected_fault="coefficient_swap_every_evaluation" if swap else None)
        if ideal_success(index, c):
            reason = "success"
        for u in range(1, c["maximum_updates"] + 1):
            if reason:
                break
            coordinate = c["coordinate_schedule"][(u - 1) % 4]
            candidates = candidate_indices(index, coordinate, c["grid_size"])
            emit("update_start", update=u, index=index, coordinate=coordinate, candidates=candidates)
            values = []
            for candidate, params in enumerate(candidates):
                context = {"update": u, "candidate": candidate, "index": params,
                           "theta": [2 * math.pi * z / c["grid_size"] for z in params],
                           "evaluation_id": f"{run_id}:u{u}:c{candidate}"}
                _, probabilities = point(tuple(params), c["grid_size"])
                groups = []
                for group in range(3):
                    counts = rng.multinomial(c["shots_per_group"], probabilities[group]).tolist()
                    shots_total += c["shots_per_group"]
                    groups.append(counts)
                    emit("measurement", **context, group=group, counts=counts, shots=c["shots_per_group"])
                value = execution_values(groups, c, swap=swap)
                emit("evaluation", **context, **value)
                emit("numeric_valid", **context)
                values.append(value)
            scores = [v["score"] for v in values]
            choice = min(range(3), key=lambda j: scores[j])
            emit("optimizer_commit", update=u, choice=choice, index_after=candidates[choice],
                 energies_used=[v["energy"] for v in values], scores_used=scores,
                 evaluation_ids=[f"{run_id}:u{u}:c{j}" for j in range(3)], physical_shots=shots_total)
            index, updates = candidates[choice], u
            if ideal_success(index, c):
                reason = "success"
        reason = reason or "budget"
        emit("terminal", reason=reason, updates=updates, index=index, physical_shots=shots_total)


def read_trace(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def summary(events, c):
    """Per iteration: reported energy of the chosen candidate, the choice, the choice the
    declared coefficients would make on the same counts, and the ideal energy after."""
    groups, rows = {}, []
    for e in events:
        if e["type"] == "measurement":
            groups.setdefault((e["update"], e["candidate"]), [None] * 3)[e["group"]] = e["counts"]
        elif e["type"] == "optimizer_commit":
            u = e["update"]
            declared = [sum(int(np.dot(groups[(u, j)][g], GROUP_VALUES[g])) for g in range(3)) for j in range(3)]
            rows.append({"update": u, "choice": e["choice"],
                         "declared_choice": min(range(3), key=lambda j: declared[j]),
                         "reported_energy": e["energies_used"][e["choice"]],
                         "energies_used": e["energies_used"],
                         "declared_energies": [s / (c["shots_per_group"] * 10000) for s in declared],
                         "ideal_after": point(tuple(e["index_after"]), c["grid_size"])[0]})
    terminal = events[-1]
    return {"iterations": terminal["updates"], "terminal_reason": terminal["reason"],
            "final_index": terminal["index"], "physical_shots": terminal["physical_shots"],
            "ideal_start": point(tuple(events[0]["index"]), c["grid_size"])[0], "updates": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", type=Path, default=HERE / "runs")
    args = parser.parse_args()
    if args.out_dir.exists():
        raise SystemExit(f"refusing to overwrite {args.out_dir}")
    args.out_dir.mkdir(parents=True)

    pre = json.loads((REFERENCE / "stage1" / "pre_execution.json").read_text())
    c = pre["configuration"]
    recorded = json.loads((REFERENCE / "stage2" / "baseline" / "results.json").read_text())
    pre_digest = recorded["pre_execution_digest"]
    seed_words = next(r for r in recorded["results"] if r["run_id"] == SEED_RUN)["seed_words"]

    out = {"configuration_digest": digest(c), "pre_execution_digest": pre_digest,
           "seed_words": seed_words, "seed_run": SEED_RUN,
           "platform": {"machine": platform.machine(), "system": platform.system(),
                        "python": platform.python_version(), "numpy": np.__version__},
           "runs": {}}

    # The run loop must equal the experiment's own execute_run on this machine.
    with tempfile.TemporaryDirectory() as tmp:
        execute_run(c, "loop-check", seed_words, pre_digest, Path(tmp) / "execute_run.jsonl.gz")
        run(c, "loop-check", seed_words, pre_digest, Path(tmp) / "loop.jsonl.gz", swap=False)
        if read_trace(Path(tmp) / "execute_run.jsonl.gz") != read_trace(Path(tmp) / "loop.jsonl.gz"):
            raise SystemExit("the run loop differs from closed_loop.execution.execute_run")
    out["loop_matches_execute_run"] = True
    out["note"] = "violations_listed: the runtime checker lists at most 100 violations per contract."

    traces = {"declared": REFERENCE / "stage2" / "baseline" / f"{SEED_RUN}.jsonl.gz",
              "swapped": args.out_dir / "swapped.jsonl.gz"}
    run(c, "opening-swapped", seed_words, pre_digest, traces["swapped"], swap=True)
    for name, path in traces.items():
        verdicts = replay(c, pre_digest, path)["contracts"]
        out["runs"][name] = {"run_id": read_trace(path)[0]["run_id"], "swap_yz_xx": name == "swapped",
                             "trace": str(path.relative_to(HERE.parents[1])), "trace_sha256": file_hash(path),
                             **summary(read_trace(path), c),
                             "runtime_verdicts": {cid: {"verdict": v["runtime_verdict"], "checks": v["checks"],
                                                        "violations_listed": len(v["violations"])}
                                                  for cid, v in verdicts.items()}}

    (args.out_dir / "results.json").write_text(json.dumps(out, indent=1) + "\n")
    for name, r in out["runs"].items():
        flips = sum(1 for row in r["updates"] if row["choice"] != row["declared_choice"])
        bad = {cid: v["verdict"] for cid, v in r["runtime_verdicts"].items() if v["verdict"] != "AGREEMENT"}
        print(f"{name}: {r['iterations']} iterations, stop {r['terminal_reason']}, final ideal "
              f"{r['updates'][-1]['ideal_after']:.4f}, choices differing from the declared coefficients: "
              f"{flips}, runtime verdicts other than AGREEMENT: {bad or 'none'}")


if __name__ == "__main__":
    main()
