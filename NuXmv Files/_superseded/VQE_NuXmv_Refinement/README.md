# VQE nuXmv Refinement: ABORT Mode and Property Suite

This folder is a separate refinement of the existing VQE model-checking work.
The original project files under `nuXmv/` are unchanged.

## Files

- `vqe_refined_abort.smv`: refined VQE outer-loop model with `ABORT`, terminal causes, and the expanded CTL/LTL/invariant property suite.
- `property_suite.md`: paper-facing explanation of the property groups and why each group is needed.
- `counterexamples/`: small mutant models that intentionally contain logical errors.
- `counterexamples/counterexample_traces.md`: concrete counterexample traces and interpretation.
- `run_checks.sh`: convenience script for running the refined model and the three counterexample harnesses.

## Implementation Rationale

1. I used `nuXmv/vqe_rename.smv` as the runnable baseline. The older `nuXmv/vqe.smv` uses `INIT`, which this nuXmv build treats as a reserved token, so it does not parse.
2. I kept the same abstraction level as the workshop paper target: real-valued parameters, gradients, and energies are represented by finite readiness flags and bounded counters.
3. I split termination into two meanings:
   - `DONE`: successful convergence only.
   - `ABORT`: safety/error termination caused by binding failure, QPU/measurement failure, energy aggregation failure, optimizer failure, or non-convergence at `MAX_ITERS`.
4. I added `term_reason` so the model can prove not only that ABORT is reachable, but also that each abort cause is reachable and preserved in the terminal state.
5. I refined data freshness semantics:
   - initial `theta_0` is available at startup,
   - `BIND` clears stale energy and starts with `terms_done = 0`,
   - `EXECUTE_MEASURE` requires fresh parameters and a bound circuit,
   - `COMPUTE_ENERGY` consumes parameters only after all Pauli terms are complete,
   - `OPTIMIZER_STEP` consumes the current energy and produces fresh parameters for the next iteration.

## How To Run

From `/Users/rome/Desktop/NuXmv Files`:

```sh
./nuXmv/bin/nuXmv VQE_NuXmv_Refinement/vqe_refined_abort.smv
```

Or run everything:

```sh
zsh VQE_NuXmv_Refinement/run_checks.sh
```

## Verified Result

The refined model passes all included CTL, LTL, and invariant properties with
nuXmv 2.1.0. The checked properties include:

- all paths eventually reach `DONE` or `ABORT`,
- `DONE` is reachable only as convergence,
- every abort cause is reachable,
- terminal states are absorbing,
- no energy computation occurs before all Pauli terms are measured,
- no optimizer step occurs before current energy is ready,
- stale energy is cleared before a new iteration,
- measurement uses fresh parameters and a bound circuit,
- max-iteration non-convergence goes to `ABORT`, not `DONE`.

## Paper-Ready Framing

The key technical contribution is the move from a happy-path state machine to a
safety-aware hybrid-control model. The property suite now covers control-flow
conformance, data readiness, stale-data rejection, liveness/termination, and
explicit error handling. The counterexample harnesses show why these categories
are necessary: each intentionally broken model violates one property with a short,
explainable trace.
