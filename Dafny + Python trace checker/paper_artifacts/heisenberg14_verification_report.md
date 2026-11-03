# Qiskit Runtime VQE Verification Report

## Execution Summary

| Item | Value |
|---|---:|
| Trace | `traces/myTests/heisenberg14_statevector.jsonl` |
| Run id | `heisenberg14-qiskit-statevector` |
| System | `heisenberg14` |
| Records / optimizer evaluations | 60 |
| Hamiltonian Pauli terms | 287 |
| Parameters | 28 |
| Estimator kind | `exact` |
| Shots used | 0 |
| Initial energy | -0.41107007 Ha |
| Final energy | -0.9331586478 Ha |
| Best observed energy | -0.940597976 Ha at iter 55 |
| Reference ground energy | -1.907692308 Ha |
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
| 0 | -0.41107007 | 0 | 0/3 | False | PASS |
| 1 | 1.054675706 | 1.46575 | 0/3 | False | PASS |
| 2 | 0.7830457564 | 0.27163 | 0/3 | False | PASS |
| 3 | 0.4751241793 | 0.307922 | 0/3 | False | PASS |
| 4 | 0.1640143792 | 0.31111 | 0/3 | False | PASS |
| 5 | -0.1188814183 | 0.282896 | 0/3 | False | PASS |
| 6 | -0.3472552744 | 0.228374 | 0/3 | False | PASS |
| 7 | -0.5045437887 | 0.157289 | 0/3 | False | PASS |
| 8 | -0.5337589833 | 0.0292152 | 0/3 | False | PASS |
| 9 | -0.5478831147 | 0.0141241 | 0/3 | False | PASS |
| 10 | -0.5638581061 | 0.015975 | 0/3 | False | PASS |
| 11 | -0.5874153712 | 0.0235573 | 0/3 | False | PASS |
| 12 | -0.6169187931 | 0.0295034 | 0/3 | False | PASS |
| 13 | -0.6415813788 | 0.0246626 | 0/3 | False | PASS |
| 14 | -0.6476237687 | 0.00604239 | 0/3 | False | PASS |
| 15 | -0.5048336937 | 0.14279 | 0/3 | False | PASS |
| 16 | -0.513364979 | 0.00853129 | 0/3 | False | PASS |
| 17 | -0.5386299752 | 0.025265 | 0/3 | False | PASS |
| 18 | -0.5824677234 | 0.0438377 | 0/3 | False | PASS |
| 19 | -0.6412961681 | 0.0588284 | 0/3 | False | PASS |
| 20 | -0.6981896753 | 0.0568935 | 0/3 | False | PASS |
| 21 | -0.704426292 | 0.00623662 | 0/3 | False | PASS |
| 22 | -0.6738286914 | 0.0305976 | 0/3 | False | PASS |
| 23 | -0.6644278647 | 0.00940083 | 0/3 | False | PASS |
| 24 | -0.6904638793 | 0.026036 | 0/3 | False | PASS |
| 25 | -0.6915223216 | 0.00105844 | 0/3 | False | PASS |
| 26 | -0.707830876 | 0.0163086 | 0/3 | False | PASS |
| 27 | -0.7236909872 | 0.0158601 | 0/3 | False | PASS |
| 28 | -0.6948002791 | 0.0288907 | 0/3 | False | PASS |
| 29 | -0.4471123572 | 0.247688 | 0/3 | False | PASS |
| 30 | -0.5430376036 | 0.0959252 | 0/3 | False | PASS |
| 31 | -0.1605233727 | 0.382514 | 0/3 | False | PASS |
| 32 | -0.5896457345 | 0.429122 | 0/3 | False | PASS |
| 33 | -0.3906241136 | 0.199022 | 0/3 | False | PASS |
| 34 | -0.6426261636 | 0.252002 | 0/3 | False | PASS |
| 35 | -0.6286559756 | 0.0139702 | 0/3 | False | PASS |
| 36 | -0.7238455181 | 0.0951895 | 0/3 | False | PASS |
| 37 | -0.5036798688 | 0.220166 | 0/3 | False | PASS |
| 38 | -0.6959059338 | 0.192226 | 0/3 | False | PASS |
| 39 | -0.5842430476 | 0.111663 | 0/3 | False | PASS |
| 40 | -0.697541754 | 0.113299 | 0/3 | False | PASS |
| 41 | -0.7305920444 | 0.0330503 | 0/3 | False | PASS |
| 42 | -0.5886643312 | 0.141928 | 0/3 | False | PASS |
| 43 | -0.7182841893 | 0.12962 | 0/3 | False | PASS |
| 44 | -0.3027019487 | 0.415582 | 0/3 | False | PASS |
| 45 | -0.7439555514 | 0.441254 | 0/3 | False | PASS |
| 46 | -0.7246808535 | 0.0192747 | 0/3 | False | PASS |
| 47 | -0.8085355419 | 0.0838547 | 0/3 | False | PASS |
| 48 | -0.7970269648 | 0.0115086 | 0/3 | False | PASS |
| 49 | -0.8593067369 | 0.0622798 | 0/3 | False | PASS |
| 50 | -0.6060973344 | 0.253209 | 0/3 | False | PASS |
| 51 | -0.8725815822 | 0.266484 | 0/3 | False | PASS |
| 52 | -0.8400931281 | 0.0324885 | 0/3 | False | PASS |
| 53 | -0.8937676081 | 0.0536745 | 0/3 | False | PASS |
| 54 | -0.7047161156 | 0.189051 | 0/3 | False | PASS |
| 55 | -0.940597976 | 0.235882 | 0/3 | False | PASS |
| 56 | -0.6178970558 | 0.322701 | 0/3 | False | PASS |
| 57 | -0.9377498437 | 0.319853 | 0/3 | False | PASS |
| 58 | -0.7084077068 | 0.229342 | 0/3 | False | PASS |
| 59 | -0.9331586478 | 0.224751 | 0/3 | False | PASS |

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
