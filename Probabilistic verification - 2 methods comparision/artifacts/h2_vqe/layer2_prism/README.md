# Layer 2 — PRISM explicit Gaussian DTMC

The transition matrix contains only the Born-derived Gaussian optimizer kernel.
No empirical FakeBackend transition frequency is used.

One DTMC transition is one complete optimizer update: 9 circuits are measured
(three candidates times three groups), the selected parameter point is entered,
and the coordinate phase advances.

## Run the approved PRISM properties

Install the command-line PRISM distribution from
https://www.prismmodelchecker.org/download.php and either add its `bin`
directory to `PATH` or replace `prism` below with the full path to that
executable.

From this directory:

```bash
prism -importmodel h2_gaussian.tra,sta,lab -dtmc -ex \
  h2_gaussian.props -prop P_success_by_H -const H=0:1:50 \
  -exportresults ../layer3_prism_results/prism_success_curve.csv:csv
```

The fixed-horizon convergence properties can also be checked together:

```bash
prism -importmodel h2_gaussian.tra,sta,lab -dtmc -ex \
  h2_gaussian.props -const H=50 \
  -prop P_success_10,P_success_20,P_success_30,P_success_40,P_success_50
```

## Conditional update and shot expectations

The requested expectation excludes runs that do not converge by iteration 50,
so it is derived from the PRISM bounded-success curve:

`P(T=t) = P(T<=t) - P(T<=t-1)`

`E[T | T<=50] = sum(t * P(T=t)) / P(T<=50)`

Run the workflow's `summarize-prism` command after exporting the CSV file.
The shot expectation is exactly `9216` times the update
expectation. The `.trew` files are supplied for auditing the resource mapping;
each non-terminal optimizer transition costs one update and
`9216` shots.
