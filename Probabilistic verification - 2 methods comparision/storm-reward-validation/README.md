# Storm reward validation for the VQE Gaussian model

This supplement executes actual Storm reward queries and compares their results
with the saved Python resource estimates from `artifacts/approved-experiment`.
The experiment's transition matrix, labels, configuration and original results
are read in place. All new files are confined to this directory.

## Result

The completed run is in [run/REPORT.md](run/REPORT.md). The conditional iteration
and shot means agree with the saved Python calculations to floating-point
precision. Machine-readable values are in [run/results.json](run/results.json)
and [run/comparison.csv](run/comparison.csv).

## What Storm actually computes

The existing Gaussian DTMC has absorbing success states. Attach a reward of
one to each non-success state and zero to each success state. Each transition
before success represents one optimizer iteration. With first-success time T
and iteration bound K, Storm evaluates:

```text
P=? [ F<=K "success" ]
R=? [ C<=K ]
```

The reward query gives C = E[min(T,K)], including K iterations for paths that
have not succeeded by K. Its relation to the desired conditional mean is:

```text
C = E[T * 1(T<=K)] + K * (1-p)
E[T | T<=K] = (C - K*(1-p)) / p
```

Here p is the success probability returned by Storm. The same calculation
is performed with an independently queried shot reward of 9,216 per
non-success state, derived from the configuration as three candidates times
three measurement groups times 1,024 shots. For reward scale S, subtract
`S*K*(1-p)` before dividing by p.

This avoids adding a time counter to the transition graph. Conditional resource
estimates use only the probability and bounded cumulative-reward outputs from
Storm plus the displayed scalar normalization. The separate Python kernel
propagation is the validation reference. This is not native conditional-reward
query syntax, and plain reachability reward until success was not substituted
for the bounded conditional quantity.

The explicit input format permits one unnamed reward structure, so iteration
and shot rewards are loaded in separate Storm invocations. Both raw logs report
`Reward Models: (default)` and contain executed `R=? [C<=k]` results.

## Validation and reproducibility

- Five configured bounds are checked: 10, 20, 30, 40 and 50.
- Conditional quantities at zero-success-probability bounds are undefined.
- Six analytic toy models, each checked with both reward units, validate
  initial success, first-iteration success, success exactly at K, a 90%-success
  example, mixed first-success times, and no success. These test reward counting
  and the conditioning formula independently of the VQE reference calculation.
- The saved kernel is propagated again without rebuilding or fitting it.
- Success labels, absorbing self-loops, transition row sums and original state
  and transition counts are checked before querying rewards.
- Absolute numerical tolerances are 1e-12 for probabilities, 1e-10 iterations,
  and 9.216e-7 shots. Actual differences, rather than only pass/fail outcomes,
  are retained in the comparison files.
- Input hashes before and after execution are saved. The manifest verifies
  all files produced in the completed run.

Requirements: Python 3.10+, NumPy, and the `storm` CLI. The completed run uses
Storm 2.0.0 and NumPy 2.3.5; the original reachability log used Storm 1.13.0.
These are new supplementary verifier results, not a revision of the old log.

From the workspace root, use a Python interpreter with NumPy installed:

```bash
python3 output/storm-reward-validation/verify_rewards.py \
  --output output/storm-reward-validation/reproduction
```

The output directory must not already exist. Use `--storm /path/to/storm` or
`--workspace /path/to/workspace` when necessary. The script does not rerun
empirical VQE executions or modify the manuscript or figures.

## Method references

- [Storm reward properties](https://www.stormchecker.org/documentation/background/properties.html)
- [Storm explicit input and reward files](https://www.stormchecker.org/documentation/usage/running-storm.html)
