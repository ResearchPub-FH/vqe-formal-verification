#!/usr/bin/env bash
# NuXmv audit of the approved Stage 1 controller (read-only: works on copies in _out/nuxmv).
#  1. re-check the 7 frozen properties;
#  2. reachability / vacuity witnesses (each "G !(...)" must be FALSE);
#  3. model mutants: which injected control faults do the 7 properties detect?
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
EXP="$(dirname "$HERE")"
NUXMV="$(dirname "$EXP")/NuXmv Files/nuXmv/bin/nuXmv"
SRC="$EXP/artifacts/approved-experiment/stage1/controller.smv"
OUT="$HERE/_out/nuxmv"; mkdir -p "$OUT"; cp "$SRC" "$OUT/controller_orig.smv"
spec() { "$NUXMV" "$1" 2>&1 | grep -- '-- specification' | sed 's/  */ /g'; }

echo "== 1. frozen controller"; spec "$OUT/controller_orig.smv"

cp "$OUT/controller_orig.smv" "$OUT/vacuity.smv"
cat >> "$OUT/vacuity.smv" <<'EOF'
LTLSPEC NAME R_aggregate := G !(phase = aggregate);
LTLSPEC NAME R_select := G !(phase = select);
LTLSPEC NAME R_commit := G !(phase = commit);
LTLSPEC NAME R_done_success := G !(phase = done_success);
LTLSPEC NAME R_done_budget := G !(phase = done_budget);
LTLSPEC NAME R_aborted := G !(phase = aborted);
LTLSPEC NAME R_commit_last := G !(phase = commit & updates = 49);
LTLSPEC NAME R_start_second := G !(phase = start & updates = 1);
LTLSPEC NAME Term := F terminal;
LTLSPEC NAME AbortOnlyByError := G ((!terminal & X (phase = aborted)) -> environment_error);
LTLSPEC NAME BudgetOnlyWithoutSuccess := G ((phase = check & X (phase = done_budget)) -> !success);
EOF
echo "== 2. reachability witnesses (each G !(...) expected false) and extra properties (expected true)"; spec "$OUT/vacuity.smv"

mutant() {  # name, then (old, new) pairs applied to the frozen controller
  local name="$1"; shift
  python3 - "$OUT/controller_orig.smv" "$OUT/$name.smv" "$@" <<'EOF'
import sys
src, dst, *pairs = sys.argv[1:]
t = open(src).read()
for old, new in zip(pairs[::2], pairs[1::2]):
    assert t.count(old) == 1, (old, t.count(old))
    t = t.replace(old, new)
open(dst, "w").write(t)
EOF
  echo "== 3. mutant $name"; spec "$OUT/$name.smv"
}
mutant M1_early_aggregate "phase = measure & groups < 3 : measure;" "phase = measure & groups < 1 : measure;" "phase = measure & groups = 3 : aggregate;" "phase = measure & groups >= 1 : aggregate;"
mutant M2_skip_candidate "phase = validate & ready < 2 : measure;" "phase = validate & ready < 1 : measure;" "phase = validate & ready = 2 : select;" "phase = validate & ready >= 1 : select;"
mutant M3_no_ready_reset "phase = start : 0;
    phase = validate & !environment_error & ready < 3 : ready + 1;" "phase = start : ready;
    phase = validate & !environment_error & ready < 3 : ready + 1;"
mutant M4_budget_as_abort "phase = check & !success & updates = 50 : done_budget;" "phase = check & !success & updates = 50 : aborted;" "LTLSPEC NAME L4_bound" "LTLSPEC NAME W_done_budget_unreachable := G !(phase = done_budget);
LTLSPEC NAME L4_bound"
mutant M5_stale_energy "next(energy_epoch) := case phase = validate : epoch; TRUE : energy_epoch; esac;" "next(energy_epoch) := case TRUE : energy_epoch; esac;"
mutant M6_success_as_abort "phase = check & success : done_success;" "phase = check & success & updates = 50 : done_success;"
