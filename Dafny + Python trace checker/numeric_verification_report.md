# VQE Numeric Verification Report

Dafny static verification status: **verified**.

The runtime checker validates the concrete assumptions consumed by the Dafny numeric and trace contracts.

## Trace Summary

| Trace | Records | Result | Violations |
|---|---:|---|---:|
| traces/bug_seeded_bad_energy.jsonl | 1 | FAIL | 2 |
| traces/bug_seeded_convergence.jsonl | 2 | FAIL | 1 |
| traces/bug_seeded_missing_term.jsonl | 1 | FAIL | 10 |
| traces/bug_seeded_parameter_bounds.jsonl | 1 | FAIL | 1 |
| traces/bug_seeded_shot_inconsistency.jsonl | 1 | FAIL | 1 |
| traces/bug_seeded_stale_energy.jsonl | 2 | FAIL | 2 |
| traces/h2_run.jsonl | 3 | PASS | 0 |
| traces/lih_run.jsonl | 3 | PASS | 0 |

## Contract Matrix

| Trace | Contract | Result |
|---|---|---|
| traces/bug_seeded_bad_energy.jsonl | Trace schema and finite-value validity | PASS |
| traces/bug_seeded_bad_energy.jsonl | All Hamiltonian terms occur exactly once | PASS |
| traces/bug_seeded_bad_energy.jsonl | Pauli expectations remain in [-1, 1] | PASS |
| traces/bug_seeded_bad_energy.jsonl | Shot counts, count normalization, and shot budget are consistent | PASS |
| traces/bug_seeded_bad_energy.jsonl | Per-term energies, aggregation, hashes, and bounds are correct | FAIL |
| traces/bug_seeded_bad_energy.jsonl | Optimizer parameters remain inside declared bounds | PASS |
| traces/bug_seeded_bad_energy.jsonl | Energy deltas and convergence flags are internally consistent | PASS |
| traces/bug_seeded_bad_energy.jsonl | Ansatz and Hamiltonian use the same layout | PASS |
| traces/bug_seeded_bad_energy.jsonl | Optimizer consumes current theta and energy | PASS |
| traces/bug_seeded_bad_energy.jsonl | Iterations and cumulative state progress consistently | PASS |
| traces/bug_seeded_convergence.jsonl | Trace schema and finite-value validity | PASS |
| traces/bug_seeded_convergence.jsonl | All Hamiltonian terms occur exactly once | PASS |
| traces/bug_seeded_convergence.jsonl | Pauli expectations remain in [-1, 1] | PASS |
| traces/bug_seeded_convergence.jsonl | Shot counts, count normalization, and shot budget are consistent | PASS |
| traces/bug_seeded_convergence.jsonl | Per-term energies, aggregation, hashes, and bounds are correct | PASS |
| traces/bug_seeded_convergence.jsonl | Optimizer parameters remain inside declared bounds | PASS |
| traces/bug_seeded_convergence.jsonl | Energy deltas and convergence flags are internally consistent | FAIL |
| traces/bug_seeded_convergence.jsonl | Ansatz and Hamiltonian use the same layout | PASS |
| traces/bug_seeded_convergence.jsonl | Optimizer consumes current theta and energy | PASS |
| traces/bug_seeded_convergence.jsonl | Iterations and cumulative state progress consistently | PASS |
| traces/bug_seeded_missing_term.jsonl | Trace schema and finite-value validity | PASS |
| traces/bug_seeded_missing_term.jsonl | All Hamiltonian terms occur exactly once | FAIL |
| traces/bug_seeded_missing_term.jsonl | Pauli expectations remain in [-1, 1] | PASS |
| traces/bug_seeded_missing_term.jsonl | Shot counts, count normalization, and shot budget are consistent | PASS |
| traces/bug_seeded_missing_term.jsonl | Per-term energies, aggregation, hashes, and bounds are correct | PASS |
| traces/bug_seeded_missing_term.jsonl | Optimizer parameters remain inside declared bounds | PASS |
| traces/bug_seeded_missing_term.jsonl | Energy deltas and convergence flags are internally consistent | PASS |
| traces/bug_seeded_missing_term.jsonl | Ansatz and Hamiltonian use the same layout | PASS |
| traces/bug_seeded_missing_term.jsonl | Optimizer consumes current theta and energy | PASS |
| traces/bug_seeded_missing_term.jsonl | Iterations and cumulative state progress consistently | PASS |
| traces/bug_seeded_parameter_bounds.jsonl | Trace schema and finite-value validity | PASS |
| traces/bug_seeded_parameter_bounds.jsonl | All Hamiltonian terms occur exactly once | PASS |
| traces/bug_seeded_parameter_bounds.jsonl | Pauli expectations remain in [-1, 1] | PASS |
| traces/bug_seeded_parameter_bounds.jsonl | Shot counts, count normalization, and shot budget are consistent | PASS |
| traces/bug_seeded_parameter_bounds.jsonl | Per-term energies, aggregation, hashes, and bounds are correct | PASS |
| traces/bug_seeded_parameter_bounds.jsonl | Optimizer parameters remain inside declared bounds | FAIL |
| traces/bug_seeded_parameter_bounds.jsonl | Energy deltas and convergence flags are internally consistent | PASS |
| traces/bug_seeded_parameter_bounds.jsonl | Ansatz and Hamiltonian use the same layout | PASS |
| traces/bug_seeded_parameter_bounds.jsonl | Optimizer consumes current theta and energy | PASS |
| traces/bug_seeded_parameter_bounds.jsonl | Iterations and cumulative state progress consistently | PASS |
| traces/bug_seeded_shot_inconsistency.jsonl | Trace schema and finite-value validity | PASS |
| traces/bug_seeded_shot_inconsistency.jsonl | All Hamiltonian terms occur exactly once | PASS |
| traces/bug_seeded_shot_inconsistency.jsonl | Pauli expectations remain in [-1, 1] | PASS |
| traces/bug_seeded_shot_inconsistency.jsonl | Shot counts, count normalization, and shot budget are consistent | FAIL |
| traces/bug_seeded_shot_inconsistency.jsonl | Per-term energies, aggregation, hashes, and bounds are correct | PASS |
| traces/bug_seeded_shot_inconsistency.jsonl | Optimizer parameters remain inside declared bounds | PASS |
| traces/bug_seeded_shot_inconsistency.jsonl | Energy deltas and convergence flags are internally consistent | PASS |
| traces/bug_seeded_shot_inconsistency.jsonl | Ansatz and Hamiltonian use the same layout | PASS |
| traces/bug_seeded_shot_inconsistency.jsonl | Optimizer consumes current theta and energy | PASS |
| traces/bug_seeded_shot_inconsistency.jsonl | Iterations and cumulative state progress consistently | PASS |
| traces/bug_seeded_stale_energy.jsonl | Trace schema and finite-value validity | PASS |
| traces/bug_seeded_stale_energy.jsonl | All Hamiltonian terms occur exactly once | PASS |
| traces/bug_seeded_stale_energy.jsonl | Pauli expectations remain in [-1, 1] | PASS |
| traces/bug_seeded_stale_energy.jsonl | Shot counts, count normalization, and shot budget are consistent | PASS |
| traces/bug_seeded_stale_energy.jsonl | Per-term energies, aggregation, hashes, and bounds are correct | PASS |
| traces/bug_seeded_stale_energy.jsonl | Optimizer parameters remain inside declared bounds | PASS |
| traces/bug_seeded_stale_energy.jsonl | Energy deltas and convergence flags are internally consistent | PASS |
| traces/bug_seeded_stale_energy.jsonl | Ansatz and Hamiltonian use the same layout | PASS |
| traces/bug_seeded_stale_energy.jsonl | Optimizer consumes current theta and energy | FAIL |
| traces/bug_seeded_stale_energy.jsonl | Iterations and cumulative state progress consistently | PASS |
| traces/h2_run.jsonl | Trace schema and finite-value validity | PASS |
| traces/h2_run.jsonl | All Hamiltonian terms occur exactly once | PASS |
| traces/h2_run.jsonl | Pauli expectations remain in [-1, 1] | PASS |
| traces/h2_run.jsonl | Shot counts, count normalization, and shot budget are consistent | PASS |
| traces/h2_run.jsonl | Per-term energies, aggregation, hashes, and bounds are correct | PASS |
| traces/h2_run.jsonl | Optimizer parameters remain inside declared bounds | PASS |
| traces/h2_run.jsonl | Energy deltas and convergence flags are internally consistent | PASS |
| traces/h2_run.jsonl | Ansatz and Hamiltonian use the same layout | PASS |
| traces/h2_run.jsonl | Optimizer consumes current theta and energy | PASS |
| traces/h2_run.jsonl | Iterations and cumulative state progress consistently | PASS |
| traces/lih_run.jsonl | Trace schema and finite-value validity | PASS |
| traces/lih_run.jsonl | All Hamiltonian terms occur exactly once | PASS |
| traces/lih_run.jsonl | Pauli expectations remain in [-1, 1] | PASS |
| traces/lih_run.jsonl | Shot counts, count normalization, and shot budget are consistent | PASS |
| traces/lih_run.jsonl | Per-term energies, aggregation, hashes, and bounds are correct | PASS |
| traces/lih_run.jsonl | Optimizer parameters remain inside declared bounds | PASS |
| traces/lih_run.jsonl | Energy deltas and convergence flags are internally consistent | PASS |
| traces/lih_run.jsonl | Ansatz and Hamiltonian use the same layout | PASS |
| traces/lih_run.jsonl | Optimizer consumes current theta and energy | PASS |
| traces/lih_run.jsonl | Iterations and cumulative state progress consistently | PASS |

## Findings

### All Hamiltonian terms occur exactly once

- traces/bug_seeded_missing_term.jsonl line 1: term_ids has length 3, expected 4
- traces/bug_seeded_missing_term.jsonl line 1: paulis has length 3, expected 4
- traces/bug_seeded_missing_term.jsonl line 1: coefficients has length 3, expected 4
- traces/bug_seeded_missing_term.jsonl line 1: expectations has length 3, expected 4
- traces/bug_seeded_missing_term.jsonl line 1: per_term_energies has length 3, expected 4
- traces/bug_seeded_missing_term.jsonl line 1: terms_done has length 3, expected 4
- traces/bug_seeded_missing_term.jsonl line 1: shots has length 3, expected 4
- traces/bug_seeded_missing_term.jsonl line 1: counts_ones has length 3, expected 4
- traces/bug_seeded_missing_term.jsonl line 1: counts_available has length 3, expected 4
- traces/bug_seeded_missing_term.jsonl line 1: term_ids must contain each identifier 0..N-1 exactly once

### Shot counts, count normalization, and shot budget are consistent

- traces/bug_seeded_shot_inconsistency.jsonl line 1: total_shots_this_iter 39999 does not equal sum(shots) 40000

### Per-term energies, aggregation, hashes, and bounds are correct

- traces/bug_seeded_bad_energy.jsonl line 1: term 0 energy contribution 0.1648 differs from coefficient*expectation 0.039799999999999995
- traces/bug_seeded_bad_energy.jsonl line 1: reported energy 0.09790999999999997 differs from sum(per_term_energies) 0.22290999999999997

### Optimizer parameters remain inside declared bounds

- traces/bug_seeded_parameter_bounds.jsonl line 1: theta must lie inside the declared parameter domain

### Energy deltas and convergence flags are internally consistent

- traces/bug_seeded_convergence.jsonl line 2: converged flag True does not match energy_delta <= tolerance (False)

### Optimizer consumes current theta and energy

- traces/bug_seeded_stale_energy.jsonl line 2: binding, energy, and optimizer must use the current theta
- traces/bug_seeded_stale_energy.jsonl line 2: optimizer consumed an energy other than the current record's energy

## Assurance Scope

- Dafny proves deterministic kernels over exact real and integer models.
- The runtime checker connects concrete JSONL records to those proof assumptions.
- This artifact focuses on shot consistency, parameter bounds, convergence checks, and energy computation.
- Shot noise, backend correctness, floating-point roundoff, and global VQE convergence require separate probabilistic or numerical analyses.
