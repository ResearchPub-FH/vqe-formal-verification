**VQE nuXmv non-vacuity checks — 25 October 2026**

Most properties in the two standalone models are implications (`G (p -> q)`,
`AG (p -> …)`, `INVARSPEC p -> q`). Such a property is satisfied vacuously when
`p` can never occur, or when `q` holds everywhere regardless of `p`. This folder
checks both conditions for every property, and checks every `case` branch of
`next(state)` and `next(term_reason)` for reachability. The models are not
edited.

| Model | Source | Original properties | Non-vacuity queries | Unreachable findings |
| --- | --- | --- | --- | --- |
| Refined ABORT | `VQE_NuXmv_Refinement/vqe_refined_abort.smv` | 41/41 true | 94 | 5 (2 redundant disjuncts, 3 dead guards) |
| Canonical | `claude/vqe_canonical.smv` | 32/32 true | 66 | 1 (dead default) |

Every consequent is falsifiable on its own (no consequent probe is invariant),
and every other antecedent disjunct and branch is reachable.

**Method**

- *Antecedent witness*: for each disjunct `p_i` of a property's antecedent,
  `G !(p_i)` must be **false**. nuXmv's counterexample is then a concrete
  trace reaching `p_i`. A disjunct written as `(a | b)` gets one witness per
  disjunct, so a property can be partly vacuous.
- *Consequent probe*: `G (q)` must be **false**; otherwise the property holds
  for a reason unrelated to its antecedent.
- *Branch coverage*: branch `i` is reachable when
  `G !(guard_i & !guard_1 & … & !guard_{i-1})` is false (nuXmv takes the first
  matching guard). Guards are parsed from the snapshot, not retyped.
- Existential and liveness properties (`EF`, `AF`, `F`) and unconditional
  invariants (`F1`–`F3`, `T4` in the canonical model) have no antecedent to
  witness and are listed as `n/a`.
- Queries are LTL so that the canonical model's `IVAR` inputs are allowed;
  nuXmv rejects input variables in CTL.

**Findings and triage**

Vacuity is triaged, never resolved by deleting a property:

| Model | Item | Unreachable condition | Class | Why |
| --- | --- | --- | --- | --- |
| Refined | B3, disjunct 2 | `state = BIND & !params_ready` | redundant disjunct | A1 already proves `params_ready` in BIND |
| Refined | B7, disjunct 2 | `state = COMPUTE_ENERGY & !all_terms_done` | redundant disjunct | A3 already proves `all_terms_done` in COMPUTE_ENERGY |
| Refined | `next(state)` branch 13 | `OPTIMIZER_STEP & !optimizer_error & iter = MAX_ITERS : ABORT` | intended dead guard | A5 proves OPTIMIZER_STEP only occurs below the bound; CHECK_STOP enforces it |
| Refined | `next(term_reason)` branch 6 | the same guard `: ABORT_MAX_ITERS` | intended dead guard | mirror of the branch above |
| Refined | `next(state)` branch 16 | `TRUE : ABORT` | intended dead guard | defensive default; earlier guards cover every state |
| Canonical | `next(state)` branch 15 | `TRUE : state` | intended dead guard | defensive default; earlier guards cover every state |

B3 and B7 hold, but half of each antecedent is never exercised, so they do not
verify a "missing parameters" bind abort or a "missing terms" energy abort.
Those paths are dead in the model. The positive statements that make them dead
already exist as invariants A1, A3 and A5, so no extra `AG !(…)` property is
needed for them.

**Proposed rewrite (not applied; changes the 41-property results)**

```smv
-- B3: binding failure aborts immediately (dead !params_ready disjunct removed; A1 covers it)
LTLSPEC G ((state = BIND & bind_error) -> X (state = ABORT & term_reason = ABORT_BIND_ERROR));
-- B7: energy computation failure aborts immediately (dead !all_terms_done disjunct removed; A3 covers it)
LTLSPEC G ((state = COMPUTE_ENERGY & energy_error) -> X (state = ABORT & term_reason = ABORT_ENERGY_ERROR));
```

The model's guards can keep their defensive disjuncts; with this rewrite each
property's antecedent is fully reachable, and the dead branches are recorded
here as intended.

**Evidence and reproducibility**

- `results/witnesses.csv`: every query with its result, class and rationale.
- `results/summary.json`: per-model counts and findings.
- `results/<model>_properties.log`, `results/<model>_nonvacuity.log`: raw
  nuXmv output, including the witness traces.
- `results/integrity.json`: SHA-256 of all 2,262 files in `NuXmv Files`
  outside this folder before and after the run; none changed.
- `snapshots/`: byte-identical copies of the two models (hash-checked).

From `NuXmv Files/`:

```sh
python3 VQE_NonVacuity/run_checks.py
```

It exits non-zero if a model's specification count changes, a snapshot differs
from its source, an original file changes, or a finding appears that is not in
the triage table (`needs_investigation`).
