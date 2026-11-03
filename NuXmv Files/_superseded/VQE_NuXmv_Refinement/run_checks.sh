#!/usr/bin/env zsh
set -e

ROOT="${0:A:h}"
NUXMV="$ROOT/../nuXmv/bin/nuXmv"

echo "== Refined VQE model =="
"$NUXMV" "$ROOT/vqe_refined_abort.smv"

echo
echo "== Counterexample 1: ignored QPU error =="
"$NUXMV" "$ROOT/counterexamples/ce1_qpu_error_ignored.smv"

echo
echo "== Counterexample 2: stale energy reused =="
"$NUXMV" "$ROOT/counterexamples/ce2_stale_energy_reused.smv"

echo
echo "== Counterexample 3: partial energy computation =="
"$NUXMV" "$ROOT/counterexamples/ce3_partial_energy_compute.smv"
