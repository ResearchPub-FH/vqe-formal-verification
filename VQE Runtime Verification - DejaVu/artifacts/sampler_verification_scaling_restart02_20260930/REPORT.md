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
| 10 | 0.044279 | 0.630474 | 0.665955 | 0.586194 | 1323.86 |
| 20 | 0.086575 | 0.958633 | 1.043129 | 0.872057 | 1007.28 |
| 30 | 0.129624 | 1.268450 | 1.404294 | 1.138826 | 878.56 |
| 40 | 0.173525 | 1.561667 | 1.724147 | 1.388143 | 799.97 |
| 50 | 0.215147 | 1.875747 | 2.139172 | 1.660600 | 771.84 |

## Convergence and fidelity diagnostics

| Evaluations | Baseline check p50 (ms) | Verified check p50 (ms) | Baseline mean infidelity | Verified mean infidelity | Infidelity impact | Verified cumulative infidelity p50 | First stable evaluation (B/V) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 0.000583 | 3.370250 | 0.00034914337 | 0.00034914337 | 0 | 0.0034914337 | None/None |
| 20 | 0.000500 | 3.170334 | 0.00046618109 | 0.00046618109 | 0 | 0.0093236217 | None/None |
| 30 | 0.000500 | 3.098167 | 0.00044343333 | 0.00044343333 | 0 | 0.013303 | None/None |
| 40 | 0.000541 | 2.962458 | 0.00048306398 | 0.00048306398 | 0 | 0.019322559 | None/None |
| 50 | 0.000500 | 2.868792 | 0.00046643074 | 0.00046643074 | 0 | 0.023321537 | None/None |

The fidelity quantity measures agreement of sampled and exact measurement distributions for the four executed PUBs. It does not reconstruct a density matrix and should not be described as full quantum-state fidelity. The infidelity-impact column is the verified median minus the baseline median at the same evaluation count.

The first stable evaluation is the first one-based evaluation whose tolerance condition has held for the configured patience, evaluated independently of the forced scaling bound. This diagnoses an evaluation-count convergence change while the timing figure reports wall-clock delay.

All per-run traces, raw evidence, timings, distributions, monitor acknowledgements, memory samples, online reports, and replay reports are retained under `runs/`.
