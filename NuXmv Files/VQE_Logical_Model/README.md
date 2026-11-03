# VQE logical model (nuXmv)

This is the only nuXmv model of the logical layer. It replaces the baseline,
canonical (32 properties), refined-ABORT (41 properties) and two-stage
controller (7/10 properties) models, which are archived in `../_superseded/`.
`CHANGES.md` lists what changed and which statements in the manuscript must
follow.

- **Source:** `2-stage verification (closed-loop)/closed_loop/logical.py`.
  Stage 1 of the two-stage experiment checks the model generated there, and
  this folder's files are generated from the same functions, so both stages
  check one model.
- **`vqe_logical.smv`:** the model at the paper's configuration (Table II):
  `MAX_ITERS = 50`, `NTERMS = 3` measurement groups, `NCANDS = 3` candidates.
- **`evaluate.py`:** regenerates the model, checks it at six bounds, and runs the
  Stage 1 gate at each bound (non-vacuity witnesses, consequent probes, branch
  coverage, seeded mutants). Results go to `results/`.

```sh
python3 evaluate.py
```

## Model

One iteration follows the executor and Section IV-C of the paper:

```
S_INIT -> CHECK_STOP -+-> DONE   (converged: DONE_CONVERGED; budget spent: DONE_MAX_ITERS)
                      +-> BIND -> EXECUTE_MEASURE x NTERMS -> COMPUTE_ENERGY -+
                            ^                                               |
                            +------------ next candidate (NCANDS) ----------+
                                                                            v
                      CHECK_STOP <------------------------------------ OPTIMIZER_STEP
any error in BIND / EXECUTE_MEASURE / COMPUTE_ENERGY / OPTIMIZER_STEP -> ABORT (cause recorded)
```

- `CHECK_STOP` tests the initial point and every committed point, as the
  executor does. The stop rule is the ideal-energy oracle `converged` (Eq. 8).
- **DONE is a normal stop**, either by convergence or by an exhausted budget,
  and **ABORT is an error stop**. `term_reason` records the cause.
- Freshness is tracked with version numbers: `iter` is the version of the
  current parameters, and (`bound_version`, `bound_cand`) and `energy_version`
  name the iteration and candidate that the binding and the latest energy
  belong to.
- `converged` and the four per-phase errors (`bind_error`, `qpu_error`,
  `energy_error`, `optimizer_error`) are unconstrained inputs. `error` is
  derived: an error observed in the phase where it matters.

## Property suite (24: 12 invariants, 9 LTL, 3 CTL)

"Paper" is the Table VI ID, and "Contract" is the Table I requirement.

| ID | Paper | Contract | Kind | Formula | Meaning |
| --- | --- | --- | --- | --- | --- |
| R1 | P1 | L1 | INVAR | `state = COMPUTE_ENERGY -> terms_done = NTERMS` | Every measurement group of the evaluation is complete before aggregation. |
| R2 | P2 | L2 | INVAR | `(state = CHECK_STOP & iter > 0) -> energy_ready` | Every stop decision after an update follows validated energies (the initial point is checked by the ideal-energy oracle). |
| R3 | P3 | L3 | INVAR | `state = EXECUTE_MEASURE -> (circ_ready & params_ready)` | Measurement runs only on a bound circuit with available parameters. |
| R4 | — | L2 | INVAR | `state = OPTIMIZER_STEP -> (cands_done = NCANDS & energy_ready)` | All candidate energies are validated before selection and commitment. |
| F1 | P4 | L3 | INVAR | `(state = EXECUTE_MEASURE \| state = COMPUTE_ENERGY) -> (bound_version = iter & bound_cand = cands_done)` | Measurement and aggregation use the circuit bound for the current iteration and candidate. |
| F2 | P5 | L3 | INVAR | `state = OPTIMIZER_STEP -> energy_version = iter` | The optimizer consumes energies of the current iteration. |
| F3 | P6 | L3 | INVAR | `state = BIND -> (terms_done = 0 & !energy_ready)` | Each new evaluation starts with no measured groups and no ready energy. |
| F4 | — | L3 | LTL | `G ((state = CHECK_STOP & !converged & iter < MAX_ITERS) -> X (state = BIND & cands_done = 0))` | A new iteration starts with no validated candidates. |
| F5 | — | L4 | INVAR | `(state = DONE & iter > 0) -> (energy_ready & energy_version + 1 = iter)` | DONE returns the validated energy that selected the returned parameters. |
| T1 | P7 | L4 | CTL | `AG (!terminal -> AF terminal)` | Every execution eventually stops. |
| T2 | P8 | L4 | INVAR | `state = DONE -> (term_reason = DONE_CONVERGED \| (term_reason = DONE_MAX_ITERS & iter = MAX_ITERS))` | DONE means convergence, or an exhausted budget recorded as such. |
| T3 | P9 | L4 | CTL | `AG (state = DONE -> AX state = DONE)` | DONE is absorbing. |
| T4 | P10 | L4 | CTL | `AG (state = ABORT -> AX state = ABORT)` | ABORT is absorbing. |
| T5 | — | L4 | LTL | `G ((state = CHECK_STOP & converged) -> X (state = DONE & term_reason = DONE_CONVERGED))` | Success stops at once with reason DONE_CONVERGED. |
| T6 | — | L4 | LTL | `G ((state = CHECK_STOP & !converged & iter = MAX_ITERS) -> X (state = DONE & term_reason = DONE_MAX_ITERS))` | An exhausted budget is a normal stop with reason DONE_MAX_ITERS, not an error. |
| T7 | — | L4 | INVAR | `state = ABORT -> !(term_reason in {NO_TERM, DONE_CONVERGED, DONE_MAX_ITERS})` | ABORT always carries an error cause. |
| T8 | — | L4 | INVAR | `!terminal -> term_reason = NO_TERM` | No termination reason is recorded before the run stops. |
| T9 | — | L4 | LTL | `G ((next(iter) = iter \| next(iter) = iter + 1) & (next(iter) = iter + 1 <-> (state = OPTIMIZER_STEP & !optimizer_error)))` | The update counter advances by one exactly at each successful commitment. |
| E1 | P11 | L4 | LTL | `G (bind_fails -> X (state = ABORT & term_reason = ABORT_BIND_ERROR))` | A binding error aborts at once with reason ABORT_BIND_ERROR. |
| E2 | P11 | L4 | LTL | `G (measure_fails -> X (state = ABORT & term_reason = ABORT_QPU_ERROR))` | A backend/measurement error aborts at once with reason ABORT_QPU_ERROR. |
| E3 | P11 | L4 | LTL | `G (energy_fails -> X (state = ABORT & term_reason = ABORT_ENERGY_ERROR))` | An aggregation/validation error aborts at once with reason ABORT_ENERGY_ERROR. |
| E4 | P11 | L4 | LTL | `G (optimizer_fails -> X (state = ABORT & term_reason = ABORT_OPTIMIZER_ERROR))` | A selection/commitment error aborts at once with reason ABORT_OPTIMIZER_ERROR. |
| E5 | — | L4 | LTL | `G ((!terminal & X state = ABORT) -> error)` | ABORT is entered only from an observed error. |
| E6 | P12 | L4 | INVAR | `state = OPTIMIZER_STEP -> iter < MAX_ITERS` | No update is committed once the budget is spent. |

## Results (nuXmv 2.1.0)

Every bound passes every property and the full gate. Time is the median of five
complete property checks. Reachable states include the five unconstrained
inputs (a factor of 32). The only unreachable `next(state)` branch at every
bound is the defensive default `TRUE : ABORT`, as intended.

| (MAX_ITERS, NTERMS) | True | Check (s) | Reachable states | Encoded states | Gate | Non-vacuity | Mutants killed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| (3, 2) | 24/24 | 0.047 | 2,816 | 4.40e+07 | PROVED | 62/62 | 12/12 |
| (5, 3) | 24/24 | 0.056 | 5,568 | 1.98e+08 | PROVED | 62/62 | 12/12 |
| (10, 5) | 24/24 | 0.115 | 14,848 | 1.83e+09 | PROVED | 62/62 | 12/12 |
| (20, 10) | 24/24 | 0.347 | 48,768 | 2.34e+10 | PROVED | 62/62 | 12/12 |
| (50, 3) | 24/24 | 0.454 | 54,528 | 1.22e+11 | PROVED | 62/62 | 12/12 |
| (50, 10) | 24/24 | 0.931 | 121,728 | 3.35e+11 | PROVED | 62/62 | 12/12 |

(50, 3) is the paper instance. The 62 non-vacuity queries are 25 antecedent
witnesses, 24 consequent probes and 13 branch-reachability queries.

## Seeded mutants (paper instance)

Each mutant must be detected by its target contract, or the gate reports
`WEAK_SPECIFICATION`.

| Mutant | Fault | Target | Detected by | Failing properties |
| --- | --- | --- | --- | --- |
| M1_early_aggregation | measurement exits after the first group | L1 | L1 | R1_groups_before_aggregation |
| M2_skipped_candidate | optimizer runs after the first candidate | L2 | L2 L4 | R2_energy_before_check, R4_candidates_before_commit, F5_returned_energy |
| M3_no_candidate_reset | candidate counter not reset at a new iteration | L3 | L3 L4 | F4_iteration_reset, T7_abort_reason, E5_abort_only_on_error |
| M4_stale_energy_ready | energy readiness not cleared at a new iteration | L3 | L3 | F3_evaluation_reset |
| M5_skipped_rebind | next candidate measured without rebinding | L3 | L3 | R3_bound_before_measure, F1_current_evaluation |
| M6_stale_binding | BIND keeps iteration 0's parameters | L3 | L3 L4 | F1_current_evaluation, F2_current_energy, F5_returned_energy |
| M7_wrong_candidate | BIND always binds candidate 0 | L3 | L3 | F1_current_evaluation |
| M8_stale_energy_epoch | aggregation keeps iteration 0's energy | L3 | L3 L4 | F2_current_energy, F5_returned_energy |
| M9_measurement_error_ignored | a backend error does not abort | L4 | L1 L4 | R1_groups_before_aggregation, T1_termination, T8_no_early_reason, E2_measure_fails |
| M10_budget_as_abort | exhausted budget reported as ABORT | L4 | L4 | T6_budget_reason, T7_abort_reason, E5_abort_only_on_error |
| M11_success_as_abort | success recognized only at the budget | L4 | L4 | T5_success_reason, T7_abort_reason, E5_abort_only_on_error |
| M12_budget_overrun | loop continues past the budget | L4 | L3 L4 | F3_evaluation_reset, F5_returned_energy, T1_termination, T6_budget_reason, T8_no_early_reason, T9_update_accounting, E6_update_bound |

These are the six mutants from Section VII-F (M1, M2, M4, M8, M10, M11), plus
the refined-ABORT counterexamples (ce1 = M9, ce2 = M4, ce3 = M1), plus stale
binding, skipped rebind, wrong candidate and budget overrun. They show that
each property class detects realistic faults. They are not a mutation-coverage
score.
