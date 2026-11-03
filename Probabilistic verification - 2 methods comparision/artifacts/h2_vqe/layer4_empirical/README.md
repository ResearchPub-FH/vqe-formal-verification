# Layer 4 — Direct noisy FakeBackend statistics

These are 400 direct adaptive VQE executions on Qiskit's noisy
`FakeJakarta` snapshot. No empirical transition matrix or empirical
DTMC is inferred.

The fixed protocol uses 1024 shots for each of three commuting
groups and independently measures current, minus, and plus. FakeBackend gate,
relaxation, and readout noise affect the measured candidate scores. There is no
injected reliability event or artificial early termination.

Observed terminal counts:

- success: 347
- not converged by 50: 53

`fakebackend_runs.jsonl` is the direct trace record. `empirical_properties.csv`
contains direct estimates and confidence intervals. `comparison.csv` compares
them with Layer 1 and has an empty PRISM column until `summarize-prism` is run.
