# Refined Property Suite

The properties are embedded directly in `vqe_refined_abort.smv` so a batch
nuXmv run checks the full suite. This document explains the intended coverage.

## A. State Invariants and Terminal Integrity

These properties define what must be true in each control state.

- A1: `BIND` starts with fresh parameters, no stale energy, and `terms_done = 0`.
- A2: `EXECUTE_MEASURE` requires both a bound circuit and fresh parameters.
- A3: `COMPUTE_ENERGY` requires all Pauli terms to have been measured.
- A4: `CHECK_STOP` requires a current energy value.
- A5: `OPTIMIZER_STEP` requires current energy and is never entered at `MAX_ITERS`.
- A6: `DONE` means convergence, not a bounded failure.
- A7: `ABORT` always has a non-success terminal reason.
- A8: nonterminal states cannot carry a stale terminal reason.
- A9: `ABORT` disables readiness for further quantum/classical work.

## B. Control-Flow Conformance

These properties verify the allowed transition skeleton.

- B1: `S_INIT -> BIND`.
- B2: successful `BIND -> EXECUTE_MEASURE`.
- B3: binding failure or missing parameters causes `ABORT_BIND_ERROR`.
- B4: QPU/measurement failure causes `ABORT_QPU_ERROR`.
- B5: measurement continues while terms remain.
- B6: all measured terms lead to `COMPUTE_ENERGY`.
- B7: energy computation failure causes `ABORT_ENERGY_ERROR`.
- B8: successful energy computation leads to `CHECK_STOP`.
- B9: convergence leads to `DONE`.
- B10: non-convergence at `MAX_ITERS` leads to `ABORT_MAX_ITERS`.
- B11: non-convergence below `MAX_ITERS` leads to `OPTIMIZER_STEP`.
- B12: optimizer failure causes `ABORT_OPTIMIZER_ERROR`.
- B13: successful optimizer update returns to `BIND`.
- B14: `DONE` and `ABORT` are absorbing.

## C. Freshness and No-Stale-Data Properties

These properties encode the hybrid quantum/classical data-dependency contract.

- C1: each measurement uses fresh parameters.
- C2: the optimizer cannot run before current energy is ready.
- C3: a new iteration cannot reuse the previous iteration's energy.
- C4: a successful optimizer step produces fresh parameters and clears energy.
- C5: parameters are consumed before energy computation.
- C6: successful `DONE` keeps the final valid energy available for return.

## D. Bounds, Termination, and Reachability

These properties demonstrate that the finite abstraction is complete enough for
the workshop-paper claim.

- D1/D2: every execution reaches either `DONE` or `ABORT`.
- D3: successful convergence is reachable.
- D4-D8: every abort reason is reachable under nondeterministic environment behavior.
- D9-D10: terminal states are absorbing in CTL.
- D11: `ABORT_MAX_ITERS` can only happen at the iteration bound.

## Why `DONE` and `ABORT` Are Separate

The original state table treated convergence and maximum-iteration termination
as the same `DONE` state. That is acceptable for a simple algorithm trace, but it
is weak for formal safety claims. In the refined model:

- `DONE` means the convergence condition was satisfied.
- `ABORT` means the run stopped safely without claiming convergence.

This separation lets the property suite prove that the model never returns a
successful result after a backend fault, stale-data fault, optimizer fault, or
bounded non-convergence.
