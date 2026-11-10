# Two-stage verification (closed-loop)

This experiment connects pre-execution logical, numeric, and probabilistic
verification to runtime evidence through explicit contract matching and verdict
agreement. Each pre-execution layer owns its contract family. Runtime
verification checks the corresponding obligations and assumptions.

`config/contracts.json` is the shared contract library: it records each family's
Stage 1 obligation, Stage 2 evidence, assumptions, and comparison rule. The
library is included in the frozen source hashes and assurance record.

The reference run of this implementation, and the source of every result in
the paper, is `artifacts/experiment/`; its report is
[`artifacts/experiment/comparison/REPORT.md`](artifacts/experiment/comparison/REPORT.md).
The other folders in `artifacts/` are earlier development snapshots kept for
provenance; see the artifact index there. They must not be combined with it as
additional independent runs.

## Run the experiment

Use Python 3.11 or later with NumPy. The implementation locates the existing
workspace NuXmv and Dafny executables and finds Storm on `PATH` (Storm 1.13.0 and 2.0.0 output formats are both parsed). Java and `jar`
must also be on `PATH`. The existing pinned DejaVu runtime is reused read-only.

From this folder, prepare the hash-checked DejaVu compiler dependencies once:

```sh
python3 '../VQE Runtime Verification - DejaVu/tools/fetch_monitor_build_deps.py' --out-dir '.cache/scala-2.12.21'
```

Then run:

```sh
python3 -m unittest discover -s tests -v
python3 experiment.py all --output artifacts/new-run
```

The command runs Stage 1, freezes its results, executes 400 independent baseline
runs, performs 10 tests for each of five controlled faults, and produces the
verdict-agreement report. Existing Stage 1 and runtime result directories are
never overwritten. To repeat the experiment, choose a new output directory.

Individual commands are available:

```sh
python3 experiment.py pre --output artifacts/repeat-01
python3 experiment.py execute --output artifacts/repeat-01
python3 experiment.py faults --output artifacts/repeat-01
python3 experiment.py compare --output artifacts/repeat-01
python3 experiment.py audit --output artifacts/repeat-01
```

`audit` checks the frozen source/evidence hashes and replays all baseline and
fault traces before regenerating the report. Python performs online checks and
saved-trace replay. The separately generated DejaVu monitor independently
checks temporal projections during Stage 2 replay. Its results are retained.

To audit the reference run, use a copy, because `audit` regenerates
`comparison/` in the folder it checks:

```sh
cp -r artifacts/experiment /tmp/experiment-audit
python3 experiment.py audit --output /tmp/experiment-audit
```

The audit needs no verification tool. It reports 366/400 successes and
online/replay agreement, and the regenerated `verdict_agreement.json` matches
the stored one apart from its timestamp and floating-point rounding in the last
digit.

For a small end-to-end test, use `--config config/smoke.json` with a new output
directory. Smoke results use a smaller grid, horizon, and repetition count;
they are not results for the primary configuration.

## Configuration and units

`config/h2.json` fixes the existing benchmark's two-qubit circuit and Hamiltonian
`0.398 YZ - 0.398 ZI - 0.0113 ZZ + 0.181 XX`. Qubit and outcome order is q1,q0.
The four parameter indices each range from 0 through 15, with angle `2*pi*z/16`.
Initial indices are `[3,11,6,14]`. Coordinates cycle through 0,1,2,3.

Each update evaluates three candidates: current, minus one grid step, plus one
grid step. Indices wrap modulo 16. All candidates are freshly sampled. Selection
uses the minimum exact integer measurement score, with current/minus/plus tie
priority. The three groups are `{ZI,ZZ}`, `{YZ}`, and `{XX}`. Every group uses
1,024 shots per candidate. Thus an update costs **9,216 physical shots**; at
most 50 updates cost **460,800 shots per execution**. The two terms sharing a
group do not double physical shot consumption. One update is three candidate
evaluations, not one evaluation.

Success means the selected parameter state's ideal energy is at most 0.02 above
the Hamiltonian's smallest eigenvalue. The execution stops on this success or
the update bound. Success and budget exhaustion have distinct terminal reasons.
The ideal-energy oracle is available for this small simulator benchmark; it
does not certify hardware-measured ground-state quality. The older runtime
energy-stability stopping rule is not used by this experiment.

The runtime uses an exact NumPy statevector of the declared gate sequence and
multinomial draws from its measurement-group Born laws. It does not sample the
Gaussian DTMC. Measurements are independent across groups and candidates; the
two terms in a group share their bitstrings. No device/gate/readout noise is
included in the primary configuration.

## Stage 1: pre-execution verification

- NuXmv checks the logical model generated by `closed_loop/logical.py`, the
  single model of the logical layer (also used by the layer-wise evaluation in
  `NuXmv Files/VQE_Logical_Model`). It has 24 properties (12 invariants, 9
  LTL, 3 CTL) covering the four logical contracts. DONE is a normal stop,
  either by convergence or by the exhausted budget, and ABORT is an error stop;
  `term_reason` records the cause, and L4 properties check every cause.
- Non-vacuity is part of the Stage 1 gate. Every antecedent disjunct has an
  `EF` witness that must hold, every consequent has a probe showing it is not
  invariant on its own, every `next(state)` branch is reachable except the
  defensive default (which must be unreachable), and twelve seeded control
  mutants must each be detected by their target contract. A failed witness
  gives `VACUOUS`, a surviving mutant `WEAK_SPECIFICATION`; both block Stage 2.
  The earlier development snapshot `artifacts/approved-experiment/` was gated
  by a 7-property version of the model, which `audit/legacy_controller.py`
  preserves for auditing that snapshot.
- Dafny checks arithmetic kernels, supporting lemmas, physical group summation,
  modular candidate generation, and integer candidate selection. The imported
  energy kernels are copied from the existing numeric artifact; see
  `PROVENANCE.md`.
- Storm checks bounded reachability at 10,20,30,40,50 updates in an explicit
  Gaussian DTMC with parameter-grid and coordinate-phase states. Independent
  forward propagation computes the complete first-success distribution and
  conditional means, and is compared against every Storm checkpoint.
- The DejaVu runtime specification is compiled and its provenance is recorded.
  Building the monitor is preparation for Stage 2, not an extra proof claim.

`stage1/pre_execution.json` records configuration, source hashes, assumptions,
tool invocations, results, and evidence hashes. A seal detects later edits.
Stage 2 refuses changed sources/configuration/evidence or incomplete Stage 1.
The seal supplies local reproducibility checks, not cryptographic authenticity
against an actor who can replace both a record and its seal.

## Numeric contract matching

The Stage 1 numeric statement is `A(x) => Q(x, f_Dafny(x))`. Stage 2 checks
`A(x_observed)` and `Q_tolerance(x_observed, y_actually_used)`. Checking input
assumptions alone does not prove separately implemented Python code correct.

The runtime checker reconstructs term expectations from the parity of raw group
bitstrings, associates terms with coefficients from the frozen manifest, and
uses `Fraction` for an exact reference energy. It compares reported term
contributions, candidate energies, exact selection scores, and optimizer energy
inputs against that reference. Numeric tolerance is 1e-12; counts, grid indices,
identities and physical shot totals use exact comparisons. Quantum sampling
variation is not classified as an arithmetic error.

Floating-point values are converted to their exact rational representations for
the error comparison, so the report includes their actual rounding error. The
optimizer's integer scores are recorded and checked as well as its displayed
energies. The optimizer input is compared directly with the rational reference,
so intermediate tolerances do not accumulate into a looser final check.

The group-aware summation proof assumes its input enumerates unique executed
groups; runtime establishes that premise through unique candidate/group keys.
The general aggregation proof assumes complete, aligned terms; runtime validates
the concrete term identities, manifest coefficients, and measurement records.
Dafny uses mathematical real arithmetic, so this is not a proof that all Python
floating-point behavior refines Dafny.

## Stage 2: runtime verification and verdict agreement

Every compressed JSONL trace retains raw outcome counts, candidate and update
identities, parameter indices, actual coefficients, derived values, optimizer
inputs, physical shot totals, and the final termination reason. Online Python
checks gate progress; replay recomputes the checks from the saved evidence.
DejaVu independently evaluates the temporal projections. Runtime counts are
recorded per contract, never collapsed into one global PASS bit.

Each contract declares the obligations it must exercise (for example L2's
commit-after-three-validations check fires at every commit). Their trigger
counts are recorded per run, every completed run must match the update-count
equations (L1 = 3 per update, L2 = 1 per update, N3 = 9 group executions per
update, and so on), and a contract with an obligation that never fired is
`INCONCLUSIVE`, not a vacuous `AGREEMENT`. The DejaVu bridge reports the
events it was given; for an otherwise clean trace, its energy, commit,
validation, and stop counts must equal Python's, so a projection that drops
events cannot let the temporal properties pass vacuously.

`AGREEMENT`, `DISAGREEMENT`, `ASSUMPTION_MISMATCH`, and `INCONCLUSIVE` are distinct.
Absent numeric evidence cannot become an agreement. A trace with no terminal
event is inconclusive for termination. Unobserved contract families in an
early-aborted execution also remain inconclusive.

When saved measurement evidence is missing, dependent numeric checks become
inconclusive. Replay still follows the recorded controller state, preventing
missing evidence from creating artificial stale-state or termination failures
later in an otherwise unchanged trace.

For probability, compare Storm's result with the observed proportion and 95%
Wilson interval. The 50-update bound is primary; earlier bounds are supporting
marginal comparisons. Agreement means statistical compatibility, not equivalence
of model and execution distributions. Conditional successful update/shot means
use a seeded percentile bootstrap. Zero or one successful execution cannot
produce a usable bootstrap verdict. P3 scales P2 by the fixed shots per update.

The Gaussian approximation, normal-CDF approximation, numerical quadrature and
finite-shot tie effects remain explicit boundaries. Kernel row-normalization
corrections are reported. No certified approximation-error bound is claimed.
Conditional means are Python-derived results, not executed Storm reward queries.

## Controlled faults and feedback

Five fault conditions test premature commitment, corrupted energy, coefficient
misassociation, changed shot allocation, and missing raw evidence. Ten seeded
tests are run for each. The first four are controlled executions; the last is
a saved-trace mutation with an unmodified control trace retained alongside it.
The runtime stops controlled execution at a detected contract problem.

Reports identify the failing contract and event, and give each fault's full
verdict vector. Faults injected at the first boundary abort before any commit,
so the commit-dependent obligations (L2, L3, N4) are reported as unexercised. A correction to implementation,
configuration, or model requires a new Stage 1 record and fresh execution data.
The CLI enforces this version boundary; it does not silently tune the model to
observed outcomes. No automatic repair or unconditional composition theorem is
claimed. A device-noise extension is outside the primary run.

## Outputs

- `stage1/`: verifier logs, generated controller, explicit DTMC, Gaussian
  kernels, runtime-monitor provenance, and sealed pre-execution results.
- `stage2/baseline/`: 400 raw traces, numeric/protocol results, DejaVu input/log,
  seeds, exact shot consumption, and online/replay agreement.
- `stage2/faults/`: fault and control traces with expected/detected verdicts.
- `comparison/REPORT.md`: readable results and guarantee boundaries.
- `comparison/verdict_agreement.json`: machine-readable results.
- `comparison/probabilities.csv`: model and runtime success probabilities with
  confidence intervals and verdict agreement.
