"""Mutation probes of the runtime checker using scratch copies of a saved trace.

Uses the experiment's own replay() (read-only import); never writes into artifacts/.
"""
import copy, gzip, json, sys
from fractions import Fraction
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from closed_loop.execution import replay
from closed_loop.common import load_json

OUT = Path(__file__).resolve().parent / "_out" / "checker_mut"; OUT.mkdir(parents=True, exist_ok=True)
APP = ROOT / "artifacts/approved-experiment"
pre = load_json(APP / "stage1/pre_execution.json"); c = pre["configuration"]
seal = load_json(APP / "stage1/pre_execution.seal.json")["sha256"]
src = APP / "stage2/baseline/baseline-0000.jsonl.gz"
base = [json.loads(l) for l in gzip.open(src, "rt")]
coef = c["hamiltonian"]["terms"]; GV = [[-4093, -3867, 4093, 3867], [3980, -3980, -3980, 3980], [1810, -1810, -1810, 1810]]
EIG = {"ZI": [1, 1, -1, -1], "ZZ": [1, -1, -1, 1], "YZ": [1, -1, -1, 1], "XX": [1, -1, -1, 1]}

def run(name, events, renumber=True):
    ev = copy.deepcopy(events)
    if renumber:
        for i, e in enumerate(ev, 1): e["seq"] = i
    p = OUT / f"{name}.jsonl.gz"
    with gzip.open(p, "wt") as f:
        for e in ev: f.write(json.dumps(e, sort_keys=True) + "\n")
    r = replay(c, seal, p)
    verdicts = {k: v["runtime_verdict"] for k, v in r["contracts"].items()}
    bad = {k: v for k, v in verdicts.items() if v != "AGREEMENT"}
    first = {k: (r["contracts"][k]["violations"] or r["contracts"][k]["assumption_mismatches"] or r["contracts"][k]["inconclusive"])[:1] for k in bad}
    print(f"{name:42s} -> {bad if bad else 'ALL AGREEMENT'}  {first if bad else ''}")
    return r

def values_from(groups):
    shots = sum(groups[0]); exps = {}
    for g, terms in enumerate(c["measurement_groups"]):
        for t in terms: exps[t] = sum(n * s for n, s in zip(groups[g], EIG[t])) / shots
    contr = {t: coef[t] * v / 10000 for t, v in exps.items()}
    score = sum(sum(n * v for n, v in zip(groups[g], GV[g])) for g in range(3))
    return {"expectations": exps, "contributions": contr, "score": score, "energy": score / (shots * 10000)}

run("control_unmodified", base, renumber=False)

# (a) stale optimizer input: commit of update 2 uses update-1 energies/scores
ev = copy.deepcopy(base)
commits = [e for e in ev if e["type"] == "optimizer_commit"]
commits[1]["energies_used"] = list(commits[0]["energies_used"]); commits[1]["scores_used"] = list(commits[0]["scores_used"])
run("a_stale_optimizer_inputs_u2", ev, renumber=False)

# (b) consistent relabeling: swap group-0 counts between candidate 0 and 1 of update 1, recompute derived values
ev = copy.deepcopy(base)
m = {(e["update"], e["candidate"], e["group"]): e for e in ev if e["type"] == "measurement"}
a, b = m[(1, 0, 0)], m[(1, 1, 0)]
a["counts"], b["counts"] = b["counts"], a["counts"]
for cand in (0, 1):
    groups = [m[(1, cand, g)]["counts"] for g in range(3)]
    evl = next(e for e in ev if e["type"] == "evaluation" and e["update"] == 1 and e["candidate"] == cand)
    evl.update(values_from(groups))
cm = next(e for e in ev if e["type"] == "optimizer_commit" and e["update"] == 1)
evals = [next(e for e in ev if e["type"] == "evaluation" and e["update"] == 1 and e["candidate"] == j) for j in range(3)]
cm["energies_used"] = [x["energy"] for x in evals]; cm["scores_used"] = [x["score"] for x in evals]
newchoice = min(range(3), key=lambda j: cm["scores_used"][j])
print("   (b) original choice", next(e for e in base if e["type"] == "optimizer_commit")["choice"], "-> after swap", newchoice)
if newchoice == cm["choice"]:
    run("b_consistent_evidence_relabeling", ev, renumber=False)
else:
    print("   (b) swap changed the optimizer decision; trajectory would diverge - skipped")

# (c) consistent fabrication of one candidate's raw counts at the final update (same totals), derived values recomputed
ev = copy.deepcopy(base)
last_u = max(e["update"] for e in ev if e["type"] == "update_start")
meas = {(e["candidate"], e["group"]): e for e in ev if e["type"] == "measurement" and e["update"] == last_u}
target = 2 if next(e for e in ev if e["type"] == "optimizer_commit" and e["update"] == last_u)["choice"] != 2 else 1
x = meas[(target, 2)]["counts"]; x[0] += 5; x[1] -= 5  # move 5 shots, raises that candidate's XX value
evl = next(e for e in ev if e["type"] == "evaluation" and e["update"] == last_u and e["candidate"] == target)
evl.update(values_from([meas[(target, g)]["counts"] for g in range(3)]))
cm = next(e for e in ev if e["type"] == "optimizer_commit" and e["update"] == last_u)
evals = [next(e for e in ev if e["type"] == "evaluation" and e["update"] == last_u and e["candidate"] == j) for j in range(3)]
cm["energies_used"] = [q["energy"] for q in evals]; cm["scores_used"] = [q["score"] for q in evals]
assert min(range(3), key=lambda j: cm["scores_used"][j]) == cm["choice"]
run("c_consistent_count_fabrication_final_update", ev, renumber=False)

# (d) commit moved before the last numeric_valid of update 1
ev = copy.deepcopy(base)
i_nv = max(i for i, e in enumerate(ev) if e["type"] == "numeric_valid" and e["update"] == 1)
i_cm = next(i for i, e in enumerate(ev) if e["type"] == "optimizer_commit" and e["update"] == 1)
nv = ev.pop(i_nv); ev.insert(i_cm, nv)  # now commit precedes candidate-2 validation
run("d_commit_before_last_validation", ev)

# (e) duplicated commit
ev = copy.deepcopy(base)
i_cm = next(i for i, e in enumerate(ev) if e["type"] == "optimizer_commit" and e["update"] == 1)
ev.insert(i_cm + 1, copy.deepcopy(ev[i_cm]))
run("e_duplicate_commit", ev)

# (f) stale measurement replayed from update 1 into update 2 (old evaluation id)
ev = copy.deepcopy(base)
old = copy.deepcopy(next(e for e in ev if e["type"] == "measurement" and e["update"] == 1 and e["candidate"] == 0 and e["group"] == 0))
i = next(i for i, e in enumerate(ev) if e["type"] == "measurement" and e["update"] == 2 and e["candidate"] == 0 and e["group"] == 0)
ev[i] = old
run("f_stale_measurement_from_previous_update", ev)

# (g) choice not argmin but successor consistent with the (wrong) choice
ev = copy.deepcopy(base)
cm = next(e for e in ev if e["type"] == "optimizer_commit" and e["update"] == 1)
us = next(e for e in ev if e["type"] == "update_start" and e["update"] == 1)
wrong = (cm["choice"] + 1) % 3
cm["choice"] = wrong; cm["index_after"] = us["candidates"][wrong]
run("g_non_argmin_choice", ev, renumber=False)

# (h) terminal reason relabelled from success to budget
ev = copy.deepcopy(base); ev[-1]["reason"] = "budget"
run("h_success_relabelled_budget", ev, renumber=False)

# (i) shots metadata changed only
ev = copy.deepcopy(base)
next(e for e in ev if e["type"] == "measurement")["shots"] = 2048
run("i_shot_metadata_only", ev, renumber=False)

# (j) one shot dropped from raw counts, derived values recomputed consistently
ev = copy.deepcopy(base)
m0 = next(e for e in ev if e["type"] == "measurement" and e["update"] == 1 and e["candidate"] == 0 and e["group"] == 1)
k = max(range(4), key=lambda o: m0["counts"][o]); m0["counts"][k] -= 1; m0["shots"] = 1023
run("j_one_shot_dropped", ev, renumber=False)

# (k) energy perturbed below tolerance (5e-13) - should be accepted by design
ev = copy.deepcopy(base)
e1 = next(e for e in ev if e["type"] == "evaluation"); e1["energy"] += 5e-13
cm = next(e for e in ev if e["type"] == "optimizer_commit"); cm["energies_used"][0] = e1["energy"]
run("k_energy_perturbed_5e-13_within_tolerance", ev, renumber=False)

# (l) truncated after the first commit (no terminal)
ev = copy.deepcopy(base)
i_cm = next(i for i, e in enumerate(ev) if e["type"] == "optimizer_commit")
run("l_truncated_after_first_commit", ev[: i_cm + 1], renumber=False)
