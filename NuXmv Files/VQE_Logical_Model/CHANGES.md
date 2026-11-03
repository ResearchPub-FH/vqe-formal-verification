# Merged logical model: changes and manuscript edits (2026-10-27)

Reference manuscript: "Coordinated Formal Verification of Hybrid
Quantum-Classical Workflows: From Pre-Execution Guarantees to Runtime Evidence"
(18 pp.). Before this change, its logical layer cited four nuXmv models:

- the 41-property refined-ABORT model (Section VI-B, Table VI)
- the 32-property canonical model (Table XI)
- the 7-property controller and the revised 10-property controller (Table I/IX, Fig. 11, Section VII-F, Table XI)

These are now one model, with 24 properties (see `README.md`).

## 1. What the merged model takes from each source

| Source | Kept |
| --- | --- |
| Paper, Table III | The eight states and their names; `DONE`/`ABORT` as the only terminals |
| Paper, Eq. 22 and Table VI | `iter`, `terms_done`, `params_ready`, `energy_ready`, `converged`, `error`, `bound_version`, `energy_version`; P1-P12 (revised where noted in section 2) |
| Two-stage controller | Candidate structure (three candidates per iteration, three groups per candidate), validation counter (L2), per-iteration reset (L3), separate success and budget stops, "abort only on error", the Stage 1 gate (witnesses, probes, branch coverage, mutants) |
| Refined-ABORT model | Per-phase errors with an immediate ABORT and a recorded cause, `term_reason`, terminal-reason invariants, `circ_ready`/`params_ready` readiness, its counterexamples ce1-ce3 (now M9, M4, M1) |
| Canonical model | Version numbers for freshness (now keyed to `iter`, plus a candidate index), update accounting (`iter` changes only at a commit, by one) |
| Executor (`closed_loop/execution.py`) | Order of phases: the stop rule is applied to the initial point and to each committed point |

## 2. Conflicts and how each was resolved

| # | Conflict | Decision | Why |
| --- | --- | --- | --- |
| C1 | Exhausted budget: the paper says DONE (Sections V-A and VI-B, P8); the refined and canonical models sent it to `ABORT_MAX_ITERS` | **Paper.** DONE with `term_reason = DONE_MAX_ITERS`; ABORT only for errors | Table III defines ABORT as "after an error condition". The executor reports `budget` as a normal stop, and the Storm model and Section VII treat budget exhaustion as a normal outcome. The reason field keeps success and budget distinct (L4). |
| C2 | Order of CHECK and OPTIMIZE: Figs. 2 and 4 show COMPUTE_ENERGY -> CHECK_STOP -> OPTIMIZER_STEP | **Section IV-C and the executor.** OPTIMIZER_STEP -> CHECK_STOP, and CHECK_STOP also runs once after INIT | Section IV-C applies the stop rule to the selected point. The executor checks the initial point, then each committed point. The old order would shift every iteration count by one relative to Storm and the runtime traces. |
| C3 | One energy per iteration (refined, canonical, Fig. 4) vs three candidates of three groups each (Section IV-C, Table I L2) | **Section IV-C.** NCANDS = 3 evaluations per iteration, each with its own BIND | Table I's L2 ("all candidate energies are ready before selection") cannot be stated without candidates. Each candidate has its own parameters, so it must be bound again; the old controller went straight from validation to measurement. |
| C4 | P2 `AG(s = CHECK_STOP -> energy_ready)` | **Revised:** `(CHECK_STOP & iter > 0) -> energy_ready` | The initial point is checked by the ideal-energy oracle before any energy is measured, so P2 as written fails on the executor's control flow. |
| C5 | P8 `AG(s = DONE -> (converged \| iter = MAX_ITERS))` | **Revised:** `DONE -> (term_reason = DONE_CONVERGED \| (term_reason = DONE_MAX_ITERS & iter = MAX_ITERS))` | `converged` is an unconstrained input, so its value in DONE is arbitrary and P8 as written is false in any model where the oracle is nondeterministic. The reason field is the recorded fact. |
| C6 | P11 `AG(error -> AF(s = ABORT))` | **Strengthened:** E1-E4 `G(<phase>_fails -> X(ABORT & reason = cause))`, plus E5 "ABORT only after an error"; `error` is derived from the phase | With `error` as a free input, P11 is false (an error can be raised in DONE). AF also allows an error to be ignored for several steps; L4 needs the correct cause. |
| C7 | P12 `AG(iter <= MAX_ITERS)` | **Replaced:** E6 `OPTIMIZER_STEP -> iter < MAX_ITERS`, plus T9 update accounting | `iter` is declared `0..MAX_ITERS` and nuXmv rejects out-of-range assignments, so P12 holds by typing alone (vacuous). E6 and T9 state the actual budget requirement. |
| C8 | P3-P4 `bound_version = iter` | **Strengthened:** F1 adds `bound_cand = cands_done` and also covers aggregation; R3 requires `circ_ready & params_ready` | An iteration-level version cannot detect measuring candidate 1 on candidate 0's circuit (mutants M5, M7). Table I's L3 is about the correct *evaluation*. |
| C9 | Eq. 22 lists `error` as a state variable | **Model:** four per-phase error inputs; `error` is a derived definition | Needed for C6 and for a recorded cause per phase. |
| C10 | Number of property classes: Section V-A says three, Section VI-B says four | **Four:** readiness, freshness, termination, failure handling (R, F, T, E) | Matches Table VI. |

## 3. Removed as redundant or unnecessary

- **Per-transition restatements** (refined B1, B2, B5, B6, B8, B11, B13). Each
  repeated one `case` line of the model. Phase reachability is now covered by
  branch coverage in the gate.
- **Duplicate LTL/CTL pairs** (refined D1/D2, B14/D9-D10, canonical T2a/T2b vs
  E7). Each fact is kept once.
- **`EF` reachability "properties"** (refined D3-D8, canonical T5 and E8).
  These are non-vacuity witnesses, not requirements, and now live in the gate
  (25 witnesses).
- **`theta_version`** (canonical). It equals `iter` (canonical F1), so `iter` is
  the version.
- **Version ordering** (canonical F2/F3), "ABORT clears readiness" (refined A9)
  and "parameters consumed before aggregation" (refined A3/C5) as properties.
  They are implied by, or weaker than, F1-F5 and T4, and no mutant
  distinguishes them.
- **Dead guards** in the refined model (`BIND & !params_ready`,
  `COMPUTE_ENERGY & !all_terms_done`, and `OPTIMIZER_STEP` at the bound). They
  could never fire, which made B3/B7 partly vacuous.
- **The boolean epoch** of the two-stage controller. It is replaced by version
  numbers, because parity cannot tell iteration k from k-2.

## 4. Manuscript edits needed

The PDF's LaTeX source is not in this folder, so the manuscript was not
edited. Each item below names what to change.

1. **Section V-A, "Termination" paragraph:** "successful completion occurs
   through DONE after convergence or the maximum iteration bound" -> "normal
   completion occurs through DONE, by convergence (DONE_CONVERGED) or by the
   exhausted iteration budget (DONE_MAX_ITERS); ABORT records the error that
   caused it". Also, "three classes" -> four classes (C10).
2. **Eq. 9:** all four formulas still hold, as consequences of R1, R4, R3 and
   T1. T1 checks the stronger `AG(!terminal -> AF terminal)`.
3. **Table III:** the states are unchanged. Add that NTERMS counts measurement
   groups (3, Table II) and that each iteration evaluates NCANDS = 3
   candidates. `prev_energy` in the INIT row has no role in this instance's
   stop rule.
4. **Eq. 22:** add `cands_done in {0..NCANDS}`, `circ_ready`,
   `bound_cand in {0..NCANDS}`, `term_reason`, and replace `error` with
   `bind_error, qpu_error, energy_error, optimizer_error`, with `error` derived
   (C9).
5. **Fig. 2 and Fig. 4:** redraw the order as INIT -> CHECK ->
   [PREPARE -> MEASURE x NTERMS -> AGGREGATE] x NCANDS -> OPTIMIZE -> CHECK
   (C2, C3). The Fig. 4 trace should show three candidates and the CHECK_STOP
   after OPTIMIZER_STEP.
6. **Section VI-B:** "The model checks 41 properties in total: 10 CTL, 22 LTL,
   and 9 invariants" -> "24 properties: 12 invariants, 9 LTL and 3 CTL". The
   sentence "DONE is reachable only through convergence or the iteration bound,
   whereas ABORT is reachable through ... failures" is now correct as written.
   Add the bound sweep from `README.md`, including the paper instance
   (50, 3): 24/24 in 0.45 s. The superseded reference-model sweep stopped at
   MAX_ITERS = 20; only the 7/10-property controller had been checked at
   K = 50.
7. **Table VI:** use the formulas of P2, P3-P4, P8, P11 and P12 from section 2
   (C4-C8). Use the nuXmv state names: `COMPUTE_ENERGY` rather than
   `AGGREGATE`, `EXECUTE_MEASURE` rather than `MEASURE`, and `OPTIMIZER_STEP`
   rather than `OPTIMIZE`.
8. **Table I, pre-execution column:** L3 -> "NuXmv checks (iteration,
   candidate) versions of the binding and the energy and resets readiness for
   each evaluation and iteration". L4 -> "NuXmv checks termination, absorbing
   terminals, the update budget, and the recorded reason for every success,
   budget and error stop".
9. **Section VII-B:** "The stronger termination-reason requirement is assessed
   at runtime" is out of date. The model now proves the termination reasons
   before execution (T2, T5-T8, E1-E5). See item 11 for what this does and
   does not change for the approved sample.
10. **Section VII-F and Table XI:** replace the four logical rows with one:
    "Merged model (24 properties): 24/24 hold; 62/62 non-vacuity queries as
    expected (25 witnesses, 24 probes, 13 branches); default branch
    unreachable; 12/12 mutants killed: PROVED at every bound". Replace "six
    seeded control mutants ... extending the controller from 7 to 10
    properties" with the twelve mutants in `README.md`.
11. **Provenance (keep one sentence):** the approved 400-run sample was gated by
    the earlier 7-property controller. The runtime verdicts do not depend on
    the nuXmv model, so Table IX and Fig. 11 are unchanged. However, the sealed
    Stage 1 record of that sample is the old controller's. To make the
    two-stage claim refer to the merged model, Stage 1 and Stage 2 must be run
    again (bitwise reproduction of the approved sample needs NumPy 2.5.3; see
    AUDIT_REPORT F10).

## 5. Files

- `2-stage verification (closed-loop)/closed_loop/logical.py`: rewritten. It
  is the merged model, properties, witnesses and mutants.
- `.../closed_loop/pre_execution.py`: also reads `-- invariant` results;
  assumption text updated.
- `.../config/contracts.json`: L1-L4 Stage 1 and non-vacuity descriptions
  updated.
- `.../tests/test_experiment.py`: the weak-specification test uses the new
  property names.
- `.../README.md`: Stage 1 description updated.
- `.../audit/legacy_controller.py` (new) and `.../audit/nonvacuity_audit.py`:
  the audit of the approved experiment re-checks the frozen 7-property
  controller with its own obligations. It reproduces the earlier result
  (7/7, 33/33, WEAK_SPECIFICATION).
- `NuXmv Files/VQE_Logical_Model/` (new): `vqe_logical.smv`, `evaluate.py`,
  `results/`, `README.md`, this file.
- `NuXmv Files/_superseded/` (moved, not deleted): the baseline, canonical and
  refined-ABORT models and the non-vacuity and phase-reachability studies.
