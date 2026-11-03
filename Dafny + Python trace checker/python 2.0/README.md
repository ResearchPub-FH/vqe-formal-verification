# Python 2.0 VQE Trace Checker

This folder is a separate implementation copy. It keeps the JSONL trace schema
from `../python`, but changes the Qiskit execution paths so each optimizer
evaluation submits one Estimator PUB containing all Hamiltonian term
observables.

The Estimator result is a vector of term expectations. `instrumented_vqe.py`
unpacks that vector into the per-term trace fields required by
`trace_checker.py`.

## Run Statevector

```bash
/opt/miniconda3/envs/qiskit200/bin/python "python 2.0/instrumented_vqe.py" \
  --mode qiskit-statevector \
  --system h2 \
  --stop-on-convergence \
  --output traces/myTests/h2_statevector_python20.jsonl

/opt/miniconda3/envs/qiskit200/bin/python "python 2.0/trace_checker.py" \
  traces/myTests/h2_statevector_python20.jsonl
```

## Run Large Hamiltonian Stress Case

`heisenberg14` is a 14-qubit all-to-all Heisenberg Hamiltonian with a
longitudinal field. It has 287 Pauli terms and computes an exact sparse
eigensolver reference energy at run time. In the current fixture parameters,
that reference is approximately `-1.90769230769`. It is non-molecular by
design: the verification target is the numeric Hamiltonian structure, not
chemistry-specific tooling.

```bash
/opt/miniconda3/envs/qiskit200/bin/python "python 2.0/instrumented_vqe.py" \
  --mode qiskit-statevector \
  --system heisenberg14 \
  --maxiter 60 \
  --output traces/myTests/heisenberg14_statevector_python20.jsonl

/opt/miniconda3/envs/qiskit200/bin/python "python 2.0/trace_checker.py" \
  traces/myTests/heisenberg14_statevector_python20.jsonl
```

The local `qiskit200` environment does not currently include `qiskit-nature` or
`pyscf`, so full-basis LiH, BeH2, or H2O generation would require adding those
chemistry dependencies.

## Run IBM Runtime Job Mode

```bash
/opt/miniconda3/envs/qiskit200/bin/python "python 2.0/instrumented_vqe.py" \
  --mode qiskit-runtime \
  --system h2 \
  --backend ibm_marrakesh \
  --maxiter 30 \
  --shots 1024 \
  --output traces/myTests/h2_ibm_runtime_python20.jsonl

/opt/miniconda3/envs/qiskit200/bin/python "python 2.0/trace_checker.py" \
  traces/myTests/h2_ibm_runtime_python20.jsonl
```

## Convergence Policy

For Qiskit runs, convergence is not a single small energy jump. By default, the
runner requires:

- absolute energy-delta tolerance from the system fixture (`1e-5` for H2),
- at least `min(30, maxiter)` optimizer evaluations,
- `5` consecutive stable energy deltas.

Statevector mode defaults to `--maxiter 80`; IBM Runtime mode defaults to
`--maxiter 30` for H2 and `--maxiter 10` for the larger Heisenberg runtime case
to avoid accidental hardware overuse. Use `--stop-on-convergence` to stop once
the convergence policy is satisfied.
