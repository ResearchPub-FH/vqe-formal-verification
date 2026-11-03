# Fresh campaign: execution time, fidelity impact, and convergence speed

Only `sampler_verification_scaling_restart02_20260930` is used in this report. The interrupted campaigns remain excluded. All 50 warm-ups and 300 measured runs were completed from zero with the unchanged validated implementation.

## Execution-time difference

| Evaluations | Baseline median (s) | Verified median (s) | Added time (s) | Verified / baseline |
|---:|---:|---:|---:|---:|
| 10 | 0.044279 | 0.630474 | 0.586194 | 14.239 |
| 20 | 0.086575 | 0.958633 | 0.872057 | 11.073 |
| 30 | 0.129624 | 1.268450 | 1.138826 | 9.786 |
| 40 | 0.173525 | 1.561667 | 1.388143 | 9.000 |
| 50 | 0.215147 | 1.875747 | 1.660600 | 8.718 |

The primary figure is [timing_comparison.svg](timing_comparison.svg). Each point summarizes 30 independently timed runs. Monitor startup, synchronous checks, trace/evidence persistence, and finalization are included in verified execution time. Fidelity computation and offline replay are excluded.

## Fidelity impact

| Evaluations | Mean measurement fidelity, both conditions | Mean infidelity | Cumulative infidelity | Verified minus baseline mean infidelity |
|---:|---:|---:|---:|---:|
| 10 | 0.999650857 | 0.000349143 | 0.003491434 | 0 |
| 20 | 0.999533819 | 0.000466181 | 0.009323622 | 0 |
| 30 | 0.999556567 | 0.000443433 | 0.013303000 | 0 |
| 40 | 0.999516936 | 0.000483064 | 0.019322559 | 0 |
| 50 | 0.999533569 | 0.000466431 | 0.023321537 | 0 |

No verification-induced measurement-fidelity change was observed. Every measured run at a given evaluation bound follows the same seeded trajectory, and baseline and verified trajectories agree. These repeated runs quantify timing variability for the fixed simulator seed; they do not estimate fidelity variability over independent noise realizations. Fidelity compares exact and sampled PUB outcome distributions. The cumulative infidelity is a sum of per-evaluation errors, not a final-state error probability.

## Convergence speed

Neither condition reached the tolerance/patience criterion within 50 evaluations. Thus time-to-convergence and evaluations-to-convergence are unobserved within this bound. Verification preserved the parameter, energy, energy-delta, and stability trajectories at every evaluation. Its observed effect was added wall-clock time to execute the same progress.

| Evaluations | Final energy, both conditions | Baseline loop median (s) | Verified loop median (s) | Baseline convergence-check median (ms) | Verified convergence-check median (ms) |
|---:|---:|---:|---:|---:|---:|
| 10 | -0.3248650391 | 0.043746 | 0.382548 | 0.000583 | 3.370250 |
| 20 | -0.3857580078 | 0.086124 | 0.714378 | 0.000500 | 3.170334 |
| 30 | -0.3742666016 | 0.129205 | 1.016029 | 0.000500 | 3.098167 |
| 40 | -0.4060007812 | 0.172972 | 1.303862 | 0.000541 | 2.962458 |
| 50 | -0.4398074219 | 0.214708 | 1.609583 | 0.000500 | 2.868792 |

Loop time excludes setup and finalization. The recorded convergence-check stage includes objective-release authorization in the verified condition; it measures the integrated stage cost. Its pooled evaluation median is a diagnostic, separate from the run-level execution-time comparison. The scaling runs force exactly N evaluations; terminal reasons alone therefore cannot establish convergence speed.

## Completion and reproducibility

- 350 complete runs: 50 warm-ups and 300 measured runs.
- 10,500 objective evaluations, 42,000 PUB records, and 43,008,000 observed shots, including warm-ups.
- All 175 verified runs passed both online checking and offline replay.
- All 26 implementation/configuration/specification hashes remained unchanged.
- Full traces, raw ordered shots, packed evidence, parameter/energy histories, timings, fidelity probabilities/counts, monitor latencies, environment records, and replay reports are retained.

See [REPORT.md](REPORT.md), [summary.json](summary.json), and [completion_audit.json](completion_audit.json) for the generated statistics and completion checks.
