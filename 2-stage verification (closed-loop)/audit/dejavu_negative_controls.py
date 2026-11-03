"""DejaVu monitor negative controls: crafted projected traces, one per QTL property, plus a compliant trace.

Uses the frozen Stage 1 monitor jar and the pinned DejaVu runtime. Needs Java on PATH.
"""
import subprocess
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "_out"; OUT.mkdir(exist_ok=True)
JAR = EXP / "artifacts/approved-experiment/stage1/runtime-monitor.jar"
DJ = EXP.parent / "VQE Runtime Verification - DejaVu/src/vqe_runtime/vendor/dejavu/dejavu.jar"
T = "\t"

def ev(seq, name, *args):
    return T.join(["EVENT", str(seq), name] + [str(a) for a in args])

def good_update(r, u, start):
    lines = [ev(start, "activity", r), ev(start, "begin", r, u)]
    s = start
    for c in range(3):
        for gn in ("groupZero", "groupOne", "groupTwo"):
            s += 1; lines += [ev(s, "activity", r), ev(s, gn, r, u, c)]
        s += 1; lines += [ev(s, "activity", r), ev(s, "energy", r, u, c)]
        s += 1; lines += [ev(s, "activity", r), ev(s, "validated", r, u, c), ev(s, ("validZero", "validOne", "validTwo")[c], r, u)]
    s += 1; lines += [ev(s, "activity", r), ev(s, "commit", r, u)]
    return lines, s

cases = {}
l, s = good_update("ok", 1, 2); l2, s = good_update("ok", 2, s + 1)
cases["compliant"] = l + l2 + [ev(s + 1, "activity", "ok"), ev(s + 1, "stopped", "ok")]
l, _ = good_update("v", 1, 2); cases["L2_commit_missing_validTwo"] = [x for x in l if "\tvalidTwo\t" not in x]
l, _ = good_update("v", 1, 2); cases["L1_energy_missing_groupTwo_c0"] = [x for x in l if not (x.split(T)[2] == "groupTwo" and x.endswith(T + "0"))]
l, _ = good_update("v", 1, 2); cases["L3_energy_without_begin"] = [x for x in l if "\tbegin\t" not in x]
l, _ = good_update("v", 1, 2); cases["L3_validated_without_energy_c1"] = [x for x in l if not (x.split(T)[2] == "energy" and x.endswith(T + "1"))]
l, _ = good_update("v", 1, 2); cases["L4_activity_after_stop"] = l[:3] + [ev(4, "activity", "v"), ev(4, "stopped", "v"), ev(5, "activity", "v")]
l, _ = good_update("v", 1, 2); conf = []
for x in l:
    p = x.split(T)
    if p[2] in ("energy", "validated"):
        p[4] = "2"   # energy/validation claimed for update 2, groups recorded for update 1
    conf.append(T.join(p))
cases["L1_cross_update_identity"] = [ev(2, "activity", "v"), ev(2, "begin", "v", 2)] + conf
tsv = OUT / "dejavu_negative_controls.tsv"
tsv.write_text("".join(f"RESET\t{name}\n" + "\n".join(lines) + "\nEND\n" for name, lines in cases.items()))
p = subprocess.run(["java", "-cp", f"{JAR}:{DJ}", "ClosedLoopBridge"], stdin=tsv.open(), capture_output=True, text=True)
print("\n".join(line for line in p.stdout.splitlines() if line.startswith("RESULT")))
