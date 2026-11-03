# Manual Counterexamples for Logical Errors

These counterexamples are not failures of the refined model. They are small
mutant harnesses showing what the refined properties are designed to catch.

## CE1: Ignored QPU Error

File: `ce1_qpu_error_ignored.smv`

Failing property:

```smv
LTLSPEC G ((state = EXECUTE_MEASURE & qpu_error) -> X (state = ABORT))
```

Observed counterexample:

| Step | Key state |
| --- | --- |
| 1.1 | `state = S_INIT`, `terms_done = 0`, `qpu_error = FALSE` |
| 1.2 | `state = BIND` |
| 1.3 | `state = EXECUTE_MEASURE`, `qpu_error = TRUE` |
| 1.4 | `state = EXECUTE_MEASURE`, `terms_done = 1` |
| 1.5 | `state = EXECUTE_MEASURE`, `terms_done = 2` |
| 1.6 | `state = COMPUTE_ENERGY` |
| 1.7 | `state = DONE` |

Interpretation: the model observes a QPU/measurement fault in `EXECUTE_MEASURE`
but continues measuring and eventually returns `DONE`. The refined model fixes
this by routing `state = EXECUTE_MEASURE & qpu_error` to `ABORT_QPU_ERROR`.

## CE2: Stale Energy Reused

File: `ce2_stale_energy_reused.smv`

Failing property:

```smv
LTLSPEC G ((state = BIND & iter > 0) -> !energy_ready)
```

Observed counterexample:

| Step | Key state |
| --- | --- |
| 1.1 | `state = S_INIT`, `iter = 0`, `energy_ready = FALSE` |
| 1.2 | `state = BIND` |
| 1.3 | `state = COMPUTE_ENERGY` |
| 1.4 | `state = CHECK_STOP`, `energy_ready = TRUE` |
| 1.5 | `state = OPTIMIZER_STEP` |
| 1.6 | `state = BIND`, `iter = 1`, `energy_ready = TRUE` |

Interpretation: after one optimizer step, the next iteration begins while the
previous iteration's energy is still marked valid. The refined model fixes this
by clearing `energy_ready` on a successful optimizer transition back to `BIND`.

## CE3: Partial Energy Computation

File: `ce3_partial_energy_compute.smv`

Failing property:

```smv
LTLSPEC G (state = COMPUTE_ENERGY -> terms_done = NTERMS)
```

Observed counterexample:

| Step | Key state |
| --- | --- |
| 1.1 | `state = S_INIT`, `terms_done = 0`, `NTERMS = 3` |
| 1.2 | `state = BIND` |
| 1.3 | `state = EXECUTE_MEASURE` |
| 1.4 | `state = EXECUTE_MEASURE`, `terms_done = 1` |
| 1.5 | `state = EXECUTE_MEASURE`, `terms_done = 2` |
| 1.6 | `state = COMPUTE_ENERGY`, `terms_done = 2` |

Interpretation: energy is computed after only `NTERMS - 1` Pauli terms. The
refined model prevents this with both an invariant on `COMPUTE_ENERGY` and a
control-flow property requiring all terms before the transition.
