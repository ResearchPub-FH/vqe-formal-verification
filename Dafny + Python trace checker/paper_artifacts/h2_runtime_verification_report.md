# Qiskit Runtime VQE Verification Report

## Execution Summary

| Item | Value |
|---|---:|
| Trace | `traces/myTests/h2_ibm_runtime_paper.jsonl` |
| Run id | `h2-qiskit-runtime-ibm_marrakesh` |
| System | `h2` |
| Records / optimizer evaluations | 25 |
| Hamiltonian Pauli terms | 4 |
| Parameters | 4 |
| Estimator kind | `shot` |
| Shots used | 409600 |
| Initial energy | -0.2927551668 Ha |
| Final energy | -0.5003902888 Ha |
| Best observed energy | -0.5024024473 Ha at iter 22 |
| Reference ground energy | -0.7029 Ha |
| Checker result | PASS |

## Runtime Verification Summary

| Verification level | Scope | Result |
|---|---|---|
| Per iteration | schema, term completeness, expectation domain, shot consistency, energy computation, parameter bounds, convergence, layout, optimizer freshness | PASS |
| Cross iteration | contiguous iteration index, constant run/system/term count, cumulative shots, previous-energy linkage, stable convergence counter | PASS |
| Full trace | all checker properties | PASS |

## Per-Iteration Verification

| Iter | Energy (Ha) | Delta | Stable Count | Converged | Per-Iteration Checks |
|---:|---:|---:|---:|---|---|
| 0 | -0.2927551668 | 0 | 0/3 | False | PASS |
| 1 | -0.154709336 | 0.138046 | 0/3 | False | PASS |
| 2 | 0.09201817786 | 0.246728 | 0/3 | False | PASS |
| 3 | -0.3487302713 | 0.440748 | 0/3 | False | PASS |
| 4 | -0.2870394329 | 0.0616908 | 0/3 | False | PASS |
| 5 | -0.2900054489 | 0.00296602 | 1/3 | False | PASS |
| 6 | -0.4059626181 | 0.115957 | 0/3 | False | PASS |
| 7 | -0.3445987522 | 0.0613639 | 0/3 | False | PASS |
| 8 | -0.4345807915 | 0.089982 | 0/3 | False | PASS |
| 9 | -0.4529026032 | 0.0183218 | 0/3 | False | PASS |
| 10 | -0.4635448577 | 0.0106423 | 0/3 | False | PASS |
| 11 | -0.4702042292 | 0.00665937 | 1/3 | False | PASS |
| 12 | -0.4893945214 | 0.0191903 | 0/3 | False | PASS |
| 13 | -0.4764052289 | 0.0129893 | 0/3 | False | PASS |
| 14 | -0.4635881708 | 0.0128171 | 0/3 | False | PASS |
| 15 | -0.4770393715 | 0.0134512 | 0/3 | False | PASS |
| 16 | -0.4854477324 | 0.00840836 | 1/3 | False | PASS |
| 17 | -0.4909627764 | 0.00551504 | 2/3 | False | PASS |
| 18 | -0.4995317736 | 0.008569 | 3/3 | False | PASS |
| 19 | -0.4711908584 | 0.0283409 | 0/3 | False | PASS |
| 20 | -0.4883636668 | 0.0171728 | 0/3 | False | PASS |
| 21 | -0.5003305336 | 0.0119669 | 0/3 | False | PASS |
| 22 | -0.5024024473 | 0.00207191 | 1/3 | False | PASS |
| 23 | -0.4936122788 | 0.00879017 | 2/3 | False | PASS |
| 24 | -0.5003902888 | 0.00677801 | 3/3 | True | PASS |

## Contract Matrix

| Contract | Result | Violations |
|---|---|---:|
| schema and finite values | PASS | 0 |
| all Pauli terms present exactly once | PASS | 0 |
| expectations remain in [-1, 1] | PASS | 0 |
| shot accounting and budget consistency | PASS | 0 |
| term energies and aggregate energy | PASS | 0 |
| optimizer parameters inside bounds | PASS | 0 |
| energy deltas and convergence flags | PASS | 0 |
| ansatz and Hamiltonian layout match | PASS | 0 |
| current theta and energy consumed | PASS | 0 |
| iteration order and cumulative state | PASS | 0 |

## Reporting Note

Each Qiskit Runtime optimizer evaluation submits one Estimator job containing one PUB with the full Hamiltonian observable list. The verifier checks the returned expectation vector after it is expanded into term-level trace fields. The verification result is trace consistency, not a proof of global VQE convergence or backend physical correctness.

Checker tolerance: `1e-09`.
