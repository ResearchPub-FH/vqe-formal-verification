# Additional experiments

These experiments extend the baseline H2 VQE artifact without changing its
Hamiltonian, ansatz, parameter grid, initial index, convergence tolerance, or
coordinate-search semantics.

## Shot-count sensitivity of P(50)

The Gaussian model and noisy FakeJakarta executions both improve as shots per
commuting group increase.  The empirical estimate is below the ideal Gaussian
prediction at every point.  The gap is largest at 512 shots (0.1532) and
smallest at 2048 shots (0.0122), where both series are near saturation.

| Shots/group | Gaussian P(50) | Empirical P(50) | 95% Wilson CI |
|---:|---:|---:|---:|
| 256 | 0.540106 | 0.447500 (179/400) | [0.399500, 0.496499] |
| 512 | 0.760711 | 0.607500 (243/400) | [0.558840, 0.654114] |
| 1024 | 0.928027 | 0.867500 (347/400) | [0.830753, 0.897255] |
| 2048 | 0.989743 | 0.977500 (391/400) | [0.957797, 0.988119] |

The source CSV, compact direct-execution traces, configuration, detailed
method note, and PNG/SVG chart are in `shot_sensitivity/`.

## Model-checking scalability versus K

`K` is the optimizer-update bound.  Counts are for separately constructed,
reachable, time-unrolled DTMCs; construction time excludes the shared,
K-independent Gaussian-kernel calculation.

| K | Reachable states | Transitions | DTMC construction | Storm checking time |
|---:|---:|---:|---:|---:|
| 10 | 3,582 | 7,900 | 0.008 s | <0.001 s |
| 20 | 70,849 | 178,378 | 0.161 s | 0.002 s |
| 30 | 435,618 | 1,143,927 | 1.067 s | 0.020 s |
| 40 | 1,086,396 | 3,014,507 | 2.821 s | 0.072 s |
| 50 | 1,741,676 | 4,889,851 | 4.663 s | 0.206 s |

Storm 1.13.0 checked each truncated DTMC three times.  The table reports the
median tool-reported checking time.  Storm probabilities agree with independent
NumPy propagation to a maximum absolute difference of `4.41e-11`.  The source
CSV and complete timing/count metadata are in `model_checking_scalability/`.
