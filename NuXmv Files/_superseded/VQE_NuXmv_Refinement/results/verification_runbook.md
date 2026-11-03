# nuXmv Verification Runbook and Paper Results

Working directory:

```sh
cd "/Users/rome/Desktop/NuXmv Files"
```

## 1. List the Property Suite

Command:

```sh
./nuXmv/bin/nuXmv -lp VQE_NuXmv_Refinement/vqe_refined_abort.smv \
  > VQE_NuXmv_Refinement/results/property_list.txt 2>&1
```

Purpose: records the full property inventory before checking. The refined model
contains 41 properties:

- 10 CTL properties,
- 22 LTL properties,
- 9 invariant properties.

## 2. Run the Refined Model Verification

Command:

```sh
./nuXmv/bin/nuXmv VQE_NuXmv_Refinement/vqe_refined_abort.smv \
  > VQE_NuXmv_Refinement/results/refined_verification_results.txt 2>&1
```

Observed result:

- 41 checked properties.
- 41 properties true.
- 0 properties false.

Paper wording:

> We checked the refined VQE hybrid-control model with nuXmv 2.1.0. The model
> contains 41 temporal and invariant properties covering control-flow
> conformance, data-readiness safety, stale-data rejection, abort handling,
> terminal-state persistence, and bounded termination. All 41 properties were
> verified successfully.

## 3. Run Counterexample Harnesses

These are intentionally faulty models. They should fail and produce traces.

```sh
./nuXmv/bin/nuXmv VQE_NuXmv_Refinement/counterexamples/ce1_qpu_error_ignored.smv \
  > VQE_NuXmv_Refinement/results/ce1_qpu_error_ignored_result.txt 2>&1

./nuXmv/bin/nuXmv VQE_NuXmv_Refinement/counterexamples/ce2_stale_energy_reused.smv \
  > VQE_NuXmv_Refinement/results/ce2_stale_energy_reused_result.txt 2>&1

./nuXmv/bin/nuXmv VQE_NuXmv_Refinement/counterexamples/ce3_partial_energy_compute.smv \
  > VQE_NuXmv_Refinement/results/ce3_partial_energy_compute_result.txt 2>&1
```

Expected failures:

- CE1: `qpu_error` is ignored in `EXECUTE_MEASURE`, violating immediate abort.
- CE2: stale `energy_ready` is reused when returning to `BIND`.
- CE3: `COMPUTE_ENERGY` is reached before `terms_done = NTERMS`.

Paper wording:

> To illustrate diagnostic value, we also checked three mutant models. Each
> intentionally violates one safety obligation: ignoring a QPU fault, carrying
> stale energy into the next iteration, and computing energy from incomplete
> Pauli-term measurements. nuXmv generated short counterexample traces for all
> three, showing that the proposed property suite detects representative
> hybrid-control errors.

## 4. One-Command Reproduction

Command:

```sh
zsh VQE_NuXmv_Refinement/run_checks.sh
```

This prints the refined verification result followed by the three expected
counterexample traces.
