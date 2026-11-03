"""End-to-end probe of the probabilistic eligibility gate (comparison.py).

Copies approved-experiment into _out/gate-copy, substitutes baseline-0000 by the
shot-allocation-mismatch fault execution (relabelled to the same run id), and runs
the experiment's own compare(). Expected: every P verdict becomes ASSUMPTION_MISMATCH.
Also demonstrates that Stage 2 results.json is not sealed (the edited copy audits cleanly).
Run with the experiment interpreter (Python >= 3.11, tested 3.14.6).
"""
import gzip, json, shutil, sys
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXP))
from closed_loop.common import canonical, file_hash, load_json, save_json
from closed_loop.comparison import compare
from closed_loop.execution import replay

out = Path(__file__).resolve().parent / "_out" / "gate-copy"
if out.exists():
    shutil.rmtree(out)
shutil.copytree(EXP / "artifacts/approved-experiment", out)
c = load_json(out / "stage1/pre_execution.json")["configuration"]
seal = load_json(out / "stage1/pre_execution.seal.json")["sha256"]
src = out / "stage2/faults/shot_mismatch-000.jsonl.gz"; dst = out / "stage2/baseline/baseline-0000.jsonl.gz"
lines = []
for line in gzip.open(src, "rt"):
    e = json.loads(line); e["run_id"] = "baseline-0000"
    if "evaluation_id" in e:
        e["evaluation_id"] = e["evaluation_id"].replace("shot_mismatch-000", "baseline-0000")
    lines.append(canonical(e))
with gzip.open(dst, "wt", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
r = replay(c, seal, dst)
res = load_json(out / "stage2/baseline/results.json"); old = res["results"][0]
r.update({"seed_words": old["seed_words"], "injected_fault": "shot_mismatch(substituted)", "trace_sha256": file_hash(dst),
          "online_replay_agreement": True, "trace": old["trace"], "dejavu": {"passed": True, "violations": {}}})
res["results"][0] = r
save_json(out / "stage2/baseline/results.json", res)
rep = compare(out, full_replay=True)
print("N3 row:", next(x for x in rep["logical_numeric"] if x["contract"] == "N3"))
print("probabilistic eligibility:", rep["probabilistic_eligibility"])
print("P1 verdicts:", [(p["update_bound"], p["verdict_agreement"]) for p in rep["probability_comparison"]])
print("P2/P3 verdicts:", [(m["contract"], m["verdict_agreement"]) for m in rep["conditional_means"]])
