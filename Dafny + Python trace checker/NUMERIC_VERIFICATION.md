# Numeric Verification Design for VQE

This artifact implements a two-stage numeric verification layer for VQE.

```text
Dafny static verification
  proves contracts and deterministic numeric kernels
        |
        v
Python trace checker
  checks concrete VQE JSONL traces against those contracts
```

The goal is not to prove that VQE always finds the physical ground state. The
goal is narrower and machine-checkable: the classical numeric part of the VQE
loop must not violate its own energy, shot, parameter, or convergence contract.

## 1. Energy Computation

Energy computation is the central property.

For a Hamiltonian decomposition:

```text
H = sum_i c_i P_i
```

the trace must provide one aligned coefficient, expectation, and per-term energy
contribution for every term:

```text
per_term_energies[i] = coefficients[i] * expectations[i]
reported_energy      = sum_i per_term_energies[i]
```

Dafny models this with:

- `ValidEnergyContributions`
- `ValidEnergyComputation`
- `TermEnergyContribution`
- `ComputeTermEnergies`
- `AggregateEnergy`

The Python checker recomputes every contribution, recomputes the aggregate
energy, checks the `energy_terms_hash`, checks the `energy_hash`, and checks the
Hamiltonian L1 energy bound.

Focused mutant:

```text
traces/bug_seeded_bad_energy.jsonl
```

## 2. Shot Consistency

Shot consistency connects raw measurement counts to expectation values and to
the cumulative shot budget.

The trace must satisfy:

```text
total_shots_this_iter = sum(shots)
counts_ones[i] <= shots[i]
expectations[i] = 1 - 2 * counts_ones[i] / shots[i]
budget_used = previous_budget_used + total_shots_this_iter
budget_used <= shot_budget
```

Dafny models this with:

- `ValidShotConsistency`
- `NormalizeExpectation`
- `SumShotUsage`
- `WithinShotBudget`

Focused mutant:

```text
traces/bug_seeded_shot_inconsistency.jsonl
```

## 3. Parameter Bounds

Every optimizer parameter must stay inside the declared domain.

The trace must satisfy:

```text
parameter_count = len(theta)
parameter_lower <= theta[i] <= parameter_upper
theta_hash = hash(theta)
```

Dafny models this with:

- `ValidParameterState`
- `ValidParameterDomain`
- `ClampParameters`

Focused mutant:

```text
traces/bug_seeded_parameter_bounds.jsonl
```

## 4. Convergence Check

The convergence check is a trace-level numeric consistency condition. It does
not prove global VQE convergence. It proves that the recorded convergence flag
matches the recorded energy delta and tolerance.

The trace must satisfy:

```text
energy_delta = abs(reported_energy - previous_energy)
converged = previous_energy_available and energy_delta <= convergence_tolerance
final_iteration implies converged or max_iterations reached
```

Dafny models this with:

- `ValidConvergenceCheck`
- `EnergyDelta`
- `CheckConverged`
- `ValidTraceStep`

Focused mutant:

```text
traces/bug_seeded_convergence.jsonl
```

## Run the Artifact

Static verification:

```bash
./dafny/dafny verify vqe_dafny/VQENumericKernels.dfy
./dafny/dafny verify vqe_dafny/VQETraceContracts.dfy
```

Generate traces:

```bash
python3 python/instrumented_vqe.py --generate-fixtures traces
```

Check valid traces:

```bash
python3 python/trace_checker.py traces/h2_run.jsonl traces/lih_run.jsonl
```

Check all seeded failures:

```bash
python3 python/trace_checker.py traces/bug_seeded_*.jsonl
```

Generate the Markdown report:

```bash
python3 python/trace_to_report.py traces/*.jsonl \
  --dafny-status verified \
  --output numeric_verification_report.md
```

### state vector execution

Run Statevector VQE

```bash
python python/instrumented_vqe.py \
  --mode qiskit-statevector \
  --system h2 \
  --maxiter 12 \
  --output traces/myTests/h2_statevector.jsonl
```

Run Trace Checker for Results
```bash
python python/trace_checker.py traces/myTests/h2_statevector.jsonl
```

### IBM Quantum Execution
Run On IBM Quantum Hardware

```bash
python python/instrumented_vqe.py \
  --mode qiskit-runtime \
  --system h2 \
  --maxiter 3 \
  --shots 1024 \
  --output traces/myTests/h2_ibm_runtime.jsonl
```