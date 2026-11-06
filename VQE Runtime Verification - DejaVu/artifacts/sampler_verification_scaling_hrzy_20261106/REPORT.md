# Simulator VQE runtime-verification scaling experiment

The timing comparison reports independent condition summaries; it does not use a paired estimator. Fidelity analysis and verified replay were performed after the execution-time boundary.

## Configuration

- Backend: `StatevectorSampler` (`qiskit-statevector-sampler`)
- Warm-ups per condition/count: 5
- Measured repetitions per condition/count: 30
- Shots per PUB: 1024
- PUBs per evaluation: 4
- Seed: 7
- Convergence tolerance/patience: 0.005 / 3
- Timing-run minimum evaluations: equal to each configured evaluation count
- Measurement fidelity: squared Bhattacharyya fidelity between exact and sampled PUB outcome distributions

## Timing results

| Evaluations | Baseline p50 (s) | Verified p50 (s) | Verified p95 (s) | Direct p50 difference (s) | Direct overhead (%) |
|---:|---:|---:|---:|---:|---:|
| 10 | 0.047435 | 0.618405 | 0.638989 | 0.570970 | 1203.69 |
| 20 | 0.092971 | 0.931021 | 0.952434 | 0.838050 | 901.41 |
| 30 | 0.139039 | 1.230461 | 1.250885 | 1.091422 | 784.97 |
| 40 | 0.183554 | 1.523025 | 1.547996 | 1.339471 | 729.74 |
| 50 | 0.230212 | 1.811715 | 1.841495 | 1.581503 | 686.98 |

## Convergence and fidelity diagnostics

| Evaluations | Baseline check p50 (ms) | Verified check p50 (ms) | Baseline mean infidelity | Verified mean infidelity | Infidelity impact | Verified cumulative infidelity p50 | First stable evaluation (B/V) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 0.000500 | 3.242541 | 0.00033900316 | 0.00033900316 | 0 | 0.0033900316 | None/None |
| 20 | 0.000417 | 3.009250 | 0.00036309591 | 0.00036309591 | 0 | 0.0072619182 | None/None |
| 30 | 0.000416 | 2.941917 | 0.00038934246 | 0.00038934246 | 0 | 0.011680274 | None/None |
| 40 | 0.000375 | 2.848958 | 0.00040290426 | 0.00040290426 | 0 | 0.01611617 | None/None |
| 50 | 0.000375 | 2.685563 | 0.00037985101 | 0.00037985101 | 0 | 0.01899255 | None/None |

The fidelity quantity measures agreement of sampled and exact measurement distributions for the four executed PUBs. It does not reconstruct a density matrix and should not be described as full quantum-state fidelity. The infidelity-impact column is the verified median minus the baseline median at the same evaluation count.

The first stable evaluation is the first one-based evaluation whose tolerance condition has held for the configured patience, evaluated independently of the forced scaling bound. This diagnoses an evaluation-count convergence change while the timing figure reports wall-clock delay.

All per-run traces, raw evidence, timings, distributions, monitor acknowledgements, memory samples, online reports, and replay reports are retained under `runs/`.
