"""Independent re-derivation of every saved baseline trace.

Own JSON parser, own Pauli-parity tables, exact Fractions, own candidate generation
and argmin, success table from indep_physics.py. Does not import experiment code.
Run after indep_physics.py (needs _out/indep_physics.npz). Python >= 3.8 + NumPy.
"""
import gzip, hashlib, json
from fractions import Fraction
from pathlib import Path
import numpy as np

EXP = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "_out"
RUN = EXP / "artifacts/approved-experiment"
res = {r["run_id"]: r for r in json.load(open(RUN / "stage2/baseline/results.json"))["results"]}
succ = np.load(OUT / "indep_physics.npz")["succ"]
G = 16; mult = np.array([G**3, G**2, G, 1])
coef = {"YZ": Fraction(3980, 10000), "ZI": Fraction(-3980, 10000), "ZZ": Fraction(-113, 10000), "XX": Fraction(1810, 10000)}
par = lambda o: (-1) ** (((o >> 1) & 1) ^ (o & 1))   # outcome index o = 2*b1 + b0
z1 = lambda o: (-1) ** ((o >> 1) & 1)
term_eig = {"ZI": z1, "ZZ": par, "YZ": par, "XX": par}
groups = [["ZI", "ZZ"], ["YZ"], ["XX"]]
s = dict(runs=0, evaluations=0, max_energy_err=Fraction(0), max_expectation_err=Fraction(0), choice_mismatch=0,
         successor_or_candidate_mismatch=0, success_step_mismatch=0, shots_mismatch=0, terminal_mismatch=0,
         trace_hash_mismatch=0, optimizer_input_mismatch=0, score_mismatch=0, expectation_out_of_range=0)
for rid, r in res.items():
    path = RUN / r["trace"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != r["trace_sha256"]:
        s["trace_hash_mismatch"] += 1
    ev = [json.loads(l) for l in gzip.open(path, "rt")]
    s["runs"] += 1
    counts, exact = {}, {}
    idx = list(ev[0]["index"]); first_success = None; shots = 0; updates = 0
    for e in ev:
        t = e["type"]
        if t == "measurement":
            counts[(e["update"], e["candidate"], e["group"])] = e["counts"]; shots += sum(e["counts"])
        elif t == "evaluation":
            u, c = e["update"], e["candidate"]
            gc = [counts[(u, c, g)] for g in range(3)]
            E = Fraction(0)
            for g, terms in enumerate(groups):
                tot = sum(gc[g])
                for term in terms:
                    ex = Fraction(sum(n * term_eig[term](o) for o, n in enumerate(gc[g])), tot)
                    if not (-1 <= ex <= 1):
                        s["expectation_out_of_range"] += 1
                    s["max_expectation_err"] = max(s["max_expectation_err"], abs(Fraction(e["expectations"][term]) - ex))
                    E += coef[term] * ex
            exact[(u, c)] = E
            s["max_energy_err"] = max(s["max_energy_err"], abs(Fraction(e["energy"]) - E))
            if Fraction(e["score"]) != E * 10000 * sum(gc[0]):
                s["score_mismatch"] += 1
            s["evaluations"] += 1
        elif t == "optimizer_commit":
            u = e["update"]; Es = [exact[(u, j)] for j in range(3)]
            best = min(range(3), key=lambda j: Es[j])
            if best != e["choice"]:
                s["choice_mismatch"] += 1
            if any(abs(Fraction(x) - y) > Fraction(1, 10**12) for x, y in zip(e["energies_used"], Es)):
                s["optimizer_input_mismatch"] += 1
            us = next(x for x in ev if x["type"] == "update_start" and x["update"] == u)
            coord = (u - 1) % 4
            exp_c = [list(idx), list(idx), list(idx)]
            exp_c[1][coord] = (idx[coord] - 1) % G; exp_c[2][coord] = (idx[coord] + 1) % G
            if us["candidates"] != exp_c or e["index_after"] != exp_c[best]:
                s["successor_or_candidate_mismatch"] += 1
            idx = list(exp_c[best]); updates = u
            if first_success is None and succ[int(np.dot(idx, mult))]:
                first_success = u
        elif t == "terminal":
            reason = "success" if first_success is not None else "budget"
            if e["reason"] != reason or (reason == "budget" and updates != 50) or (first_success is not None and first_success != updates):
                s["terminal_mismatch"] += 1
            if e["physical_shots"] != shots:
                s["shots_mismatch"] += 1
    if first_success != r["success_step"]:
        s["success_step_mismatch"] += 1
    if shots != r["physical_shots"]:
        s["shots_mismatch"] += 1
s["max_energy_err"] = float(s["max_energy_err"]); s["max_expectation_err"] = float(s["max_expectation_err"])
print(json.dumps(s, indent=1))
tot = sum(r["physical_shots"] for r in res.values())
print("total physical shots", tot, "=", tot // 9216, "updates x 9216")
