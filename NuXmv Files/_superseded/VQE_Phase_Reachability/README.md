**VQE phase reachability verification — 10 September 2026**

All six requested phases are reachable in each of the three runnable project
models: **18 of 18 EF properties are TRUE**. nuXmv 2.1.0 performed BDD-based CTL
model checking on exact source snapshots, with the existing `MAX_ITERS = 5` and
`NTERMS = 3`. These are complete reachability checks for those finite models;
the search was not restricted to a chosen trace depth.

The repeated formulas in the request were treated as six distinct checks.
The actual control variable is `state`, corresponding to the requested `s`.
Phase names map as follows; the results and minimum distances are identical
across all three runnable models.

| Requested phase | Exact query | Result in all three models | Minimum transitions from initialization |
| --- | --- | --- | --- |
| BIND | `EF (state = BIND)` | TRUE | 1 |
| MEASURE | `EF (state = EXECUTE_MEASURE)` | TRUE | 2 |
| AGGREGATE | `EF (state = COMPUTE_ENERGY)` | TRUE | 6 |
| CHECK_STOP | `EF (state = CHECK_STOP)` | TRUE | 7 |
| OPTIMIZE | `EF (state = OPTIMIZER_STEP)` | TRUE | 8 |
| DONE | `EF (state = DONE)` | TRUE | 8 |

Minimum distances were computed by nuXmv using
`check_compute -p "MIN [state = S_INIT, state = ...]"`.
The initial state is at distance zero. Measurement enters with `terms_done = 0`,
then takes three measurement self-loops to reach `terms_done = 3`, followed by
the transition to aggregation. OPTIMIZE and DONE are alternate successors of
the first CHECK_STOP, which explains their equal minimum distance.

**Models and raw evidence**

| Model | Original source | Requested checks | Raw result log |
| --- | --- | --- | --- |
| Baseline | `nuXmv/vqe_rename.smv` | 6/6 TRUE | [baseline_reachability.log](results/baseline_reachability.log) |
| Refined ABORT | `VQE_NuXmv_Refinement/vqe_refined_abort.smv` | 6/6 TRUE | [refined_abort_reachability.log](results/refined_abort_reachability.log) |
| Canonical | `claude/vqe_canonical.smv` | 6/6 TRUE | [canonical_reachability.log](results/canonical_reachability.log) |

The older `nuXmv/vqe.smv` cannot be checked as supplied: nuXmv reports
`line 25: at token "INIT": syntax error`. Its exact copy and
[parser diagnostic](results/legacy_parse.log) are retained. No pass result is
claimed for that file. The baseline above is the project's already-existing
`vqe_rename.smv`, which has other differences from `vqe.smv` as well as the
initial-state rename; it was not created or modified by this verification.

**Witnesses and additional checks**

Each runnable model has seven saved witness traces: one for every requested
phase and one reaching DONE after an optimizer step. To obtain these traces,
the harness checks the negated reachability claims `AG !(state = PHASE)` and
`AG !(state = DONE & iter > 0)`. Their expected FALSE results produce
counterexamples demonstrating that the target states are reachable; these
are evidence of successful reachability, not defects.

| Model | All raw witnesses | Readable execution through all six phases |
| --- | --- | --- |
| Baseline | [baseline_witnesses.log](results/baseline_witnesses.log) | [Example trace](results/baseline_example_trace.md) |
| Refined ABORT | [refined_abort_witnesses.log](results/refined_abort_witnesses.log) | [Example trace](results/refined_abort_example_trace.md) |
| Canonical | [canonical_witnesses.log](results/canonical_witnesses.log) | [Example trace](results/canonical_example_trace.md) |

The extracted executions reach DONE at step 16 after visiting OPTIMIZER_STEP
at step 8. The harness also verifies this stronger ordered reachability query
as TRUE in each model:

```smv
EF (state = BIND &
    EF (state = EXECUTE_MEASURE &
        EF (state = COMPUTE_ENERGY &
            EF (state = CHECK_STOP &
                EF (state = OPTIMIZER_STEP & EF (state = DONE))))))
```

All three transition relations are total: nuXmv found no deadlock state.
The additional `EF (state = ABORT)` check is TRUE in both refined models.
Those models contain ABORT; the baseline does not. Supplemental results are
in the corresponding `results/*_supplemental.log` files.

An EF property establishes that an execution can reach the phase. It does
not establish that every execution visits it. This is the standard
[CTL existential-eventual interpretation](https://nusmv.fbk.eu/userman/v21/nusmv_2.html).
For example, early convergence can skip OPTIMIZE, and faults can lead to ABORT.
These results concern the symbolic control models at their existing bounds
and nondeterministic convergence/fault abstractions. They do not establish
numerical VQE convergence or reachability in a concrete quantum backend.
The pre-existing full safety/LTL property suites, scaling fixtures, and
intentional mutant models were not rerun for this focused reachability task.

**Isolation and reproducibility**

All additions are inside `VQE_Phase_Reachability/`. No original file was
edited. The four files in `snapshots/` are byte-identical copies, including
the legacy file with its original syntax error. New queries are supplied
through nuXmv command files; no transition, initial condition, fairness
assumption, or model constant was changed. No additional fairness or
fault-free restriction was imposed.

SHA-256 verification confirmed **2,225 pre-existing files unchanged**, with
no added files outside the isolated folder. `.DS_Store` metadata was excluded.
The before/after manifests are `original_files_before.json` and
`original_files_after.json`; the [integrity result](results/integrity.json)
records the comparison.

From the original project directory, rerun with:

```sh
python3 VQE_Phase_Reachability/run_checks.py
```

The runner only reads the original project and writes verification artifacts
inside this folder. It checks snapshot hashes, verifies expected tool output,
and checks original-file integrity. nuXmv sometimes returns exit code 0 after
a command or parser error, so the runner also inspects diagnostics and result
counts. It preserves the expected legacy parser failure separately.

To rerun just the baseline's six checks and distance calculations, from this
verification folder:

```sh
../nuXmv/bin/nuXmv -s -source commands/baseline_reachability.cmd
```

The [property fragment](reachability_properties.smv) contains the six named
CTLSPEC declarations for reference. It is not a standalone model.
[CSV results](results/reachability.csv) and the
[JSON summary](results/summary.json) include the full query results;
the JSON also records the model and executable hashes and the run timestamp.
