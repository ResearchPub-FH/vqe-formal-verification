# Three-level DejaVu runtime verification for VQE

This project implements the manuscript's missing runtime-verification layer for
a sequential hybrid VQE loop. Guarded `RuntimeSession` boundaries are
synchronous and fail closed; offline replay is retrospective. The component
combines executable Python data contracts with an actual generated DejaVu
past-time monitor and produces separate verdicts for three scopes.

The assurance claim is deliberately conditional: for a complete, faithfully
instrumented observed execution, the component checks conformance to the
declared VQE lifecycle and data contracts. Opaque optimizer internals and
physical/backend truth remain outside that claim.

| Scope | Question answered | Main evidence |
|---|---|---|
| Intra-iteration | Was this monitored iteration (one evaluation) executed correctly? | binding, backend job identity, complete term set, shots/counts, expectations, reconstructed energy, convergence check, guarded release |
| Inter-iteration | Did optimization evolve coherently? | contiguous and globally fresh IDs, immutable config, certified optimizer protocol, previous checkpoint/energy, patience counter, optimizer output to next binding, cumulative budget |
| Run level | Did the finite run obey lifecycle and termination? | one start, closed iterations, truthful terminal reason, absorbing terminal state, explicit `runClosed` |

A complete, valid run receives `PASS`. A detected contract violation receives
`FAIL`. Missing evidence, a truncated trace, monitor failure, or a guarantee
that the chosen integration cannot observe receives `INCONCLUSIVE`. A run-level
pass is impossible before the explicit finite-trace `runClosed` event.
Inter-iteration `PASS` additionally requires at least two verified checkpoints;
a one-evaluation run has no adjacent transition and is `INCONCLUSIVE` at that
scope rather than vacuously passing.

A `PASS` does not say which properties a trace actually exercised: most are
`trigger -> history` and hold trivially when the trigger never occurs.
`tools/property_coverage.py <trace.jsonl>...` classifies each of the 68
properties per trace as `EXERCISED`, `NOT_APPLICABLE` (ruled out by the
recorded optimizer protocol or stop setting), `NOT_EXERCISED`, or
`NESTED_NOT_EXERCISED`, and writes JSON/Markdown to `artifacts/validation/`.
For both 50-evaluation Sampler traces (simulator and `ibm_marrakesh`) the
split is 55 / 7 / 5 / 1: convergence and abort properties are applicable but
were not exercised by these budget-terminated, failure-free runs.

`tools/run_coverage_fixtures.py` exercises those six with two local
StatevectorSampler fixtures through the unmodified runner, then replays each
from trace and raw evidence:

- `configs/h2_statevector_converging.toml` differs from `h2_statevector.toml`
  only in its 100-evaluation budget; with the unchanged convergence policy and
  seed 7 it converges at evaluation 58 (`runConverged`).
- The injected-failure fixture uses `h2_statevector.toml` with a sampler whose
  job result is unavailable at evaluation 12; the runner's exception path emits
  `criticalFail`, `iterationAborted`, `runAborted` and `runClosed`.

Both pass online and replay at all three levels. Across the two Table VII
traces and the two fixtures, 61 properties are exercised by a trace the
monitor accepted and 7 are not applicable to the ask/tell, no-optimizer-stop
configuration; none is left unexercised
(`artifacts/validation/property_coverage_corpus.md`).

## Pipeline

```text
resolved TOML config + Hamiltonian manifest
                    |
                    v
VQE instrumentation at side-effect boundaries
                    |
          +---------+---------+
          |                   |
          v                   v
Python data contracts   synchronous DejaVu
schema + arithmetic     past-time causality
identity + budgets      relational freshness
          |                   |
          +---------+---------+
                    |
                    v
    release / optimizer-update gate
                    |
                    v
JSONL evidence journal + three-level JSON report
```

Python does not send unverified numeric claims to DejaVu. It independently
checks raw observations and emits monitor-visible certificates whose run,
configuration, iteration, evaluation, submission, backend job, theta, energy,
and checkpoint identities are stable hashes or IDs. DejaVu verifies when those
certificates may be used.

The report records the exact SHA-256 identities of the QTL specification,
Scala bridge, DejaVu runtime, and generated monitor. Startup refuses a monitor
whose external manifest, embedded build metadata, or source/runtime hashes do
not agree.

## Quick start

Requirements are Python 3.11+ and Java. The core has no third-party Python
dependency. The pinned DejaVu runtime and generated monitor are bundled.

```bash
PYTHONPATH=src python3 -m vqe_runtime demo \
  --config configs/h2_demo.toml \
  --output artifacts/traces/h2_demo.jsonl \
  --report artifacts/reports/h2_demo.json

PYTHONPATH=src python3 -m vqe_runtime check \
  artifacts/traces/h2_demo.jsonl \
  --config configs/h2_demo.toml \
  --report artifacts/reports/h2_demo_replay.json

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  python3 -m unittest discover -s tests -v
```

The deterministic H2 demo is a lifecycle regression fixture, not an optimizing
VQE result: it deliberately reuses a fixed energy for three evaluations so the
convergence and termination protocol is deterministic. It exercises all three
monitor levels and uses synthetic finite-shot counts.

## Execution profiles

Configuration is an implementation adaptation inspired by the manuscript's
Dafny/Python proof-instrument-check pipeline: the Hamiltonian is a separate
ordered manifest, while execution and verification policy live in a versioned
config file. Explicit CLI values override the file.

- `configs/h2_demo.toml`: deterministic finite-shot regression, 1,000 samples
  per term, three evaluations.
- `configs/h2_statevector.toml`: local Qiskit `StatevectorSampler`, four
  independent 1,024-shot PUBs per evaluation, and at most 50 monitored
  evaluations.
- `configs/h2_ibm_sampler_50.toml`: the comparable IBM Runtime `SamplerV2`
  profile on `ibm_marrakesh`, with the same H2 ansatz, initialization,
  measurement PUBs, ask/tell optimizer, convergence policy, and 204,800-shot
  ceiling.
- `configs/h2_ibm_sampler_preflight.toml`: one four-PUB hardware evaluation
  used only to validate the IBM result schema before the primary run.
- `configs/h2_statevector_estimator_legacy.toml` and the
  `h2_ibm_runtime*.toml` files preserve the earlier opaque-optimizer Estimator
  experiments; they are not the primary comparison.

Install optional Qiskit dependencies and run a profile with:

```bash
python3 -m pip install -e '.[qiskit]'

vqe-dejavu run \
  --config configs/h2_statevector.toml \
  --run-id h2-statevector-001 \
  --output artifacts/traces/h2_statevector.jsonl \
  --report artifacts/reports/h2_statevector-online.json \
  --evidence-output artifacts/evidence/h2_statevector.jsonl

vqe-dejavu check artifacts/traces/h2_statevector.jsonl \
  --config configs/h2_statevector.toml \
  --evidence artifacts/evidence/h2_statevector.jsonl \
  --report artifacts/reports/h2_statevector-replay.json
```

The familiar overrides are available: `--mode`, `--system`, `--backend`,
`--maxiter`, `--shots`, `--shot-budget`, `--convergence-tolerance`,
`--min-iterations`, and `--convergence-patience`. If maximum iterations or
shots are changed, the explicit total shot budget must remain sufficient.

The primary Sampler profiles do not group terms. Every evaluation contains four
independent PUBs (`YZ`, `ZI`, `ZZ`, `XX`), each with 1,024 physical shots, so
the per-evaluation total is exactly 4,096. The full 50-evaluation ceiling is
therefore 200 PUBs and 204,800 physical shots. Each trace observation links by
SHA-256 to a sidecar record containing the complete counts, ordered bitstrings,
packed `BitArray`, negative-parity count, circuit/layout identity, timestamps,
and returned metadata. Replay requires the sidecar path as an independent
command-line input.

The archived September 7–8, 2026 reference campaign completed all 50
evaluations on `ibm_marrakesh`. Online and replay verification both passed all
three levels over 200 PUBs and 204,800 physical shots. The best observed
hardware energy was `-0.418932421875`; the comparable sampled statevector run
reached `-0.4398875`. See `docs/H2_SAMPLER_REPRODUCIBILITY.md` for meticulous
reproduction instructions and
`artifacts/reports/H2_SAMPLER_TECHNICAL_REPORT_20260907.md` for results,
assumptions, limitations, reviewer-response details, and the durable artifact
index. A presentation-ready walkthrough is available at
`artifacts/presentation/H2_SamplerV2_Verified_Experiment_20260908_v2.pptx`.
An Overleaf-ready replacement for the paper's runtime-verification subsection
is provided in `docs/RUNTIME_VERIFICATION_OVERLEAF_SECTION.tex`.

## Integration boundary

`RuntimeSession` exposes gates at the operations that matter:

```python
session.begin_iteration(theta)
session.bind_parameters()

session.authorize_job(submission_id)       # call before backend.run(...)
job = backend.run(...)
session.mark_job_submitted(job.job_id())

session.observe_terms(term_observations)
session.seal_measurements()
session.aggregate_energy(reported_energy)
session.check_convergence(declared_flag)

energy = session.authorize_objective_release()

# Strong ask/tell boundary: preview is pure and the verifier approves the exact
# proposed vector before the helper permits commit_update to mutate state.
next_theta, update_token = optimizer.preview_update(theta, energy)  # pure
session.authorize_and_commit_optimizer_update(
    optimizer, update_token, next_theta
)

session.close_iteration()
session.finish(TerminationReason.CONVERGED)
session.seal_run()
```

The primary count-backed integration supplies the observed shot total and the
explicit `negative_eigenvalue_count`; the legacy `counts_ones` field is an
alias for that parity count, not the number of one bits on one qubit.

No energy should be returned to an optimizer before
`authorize_objective_release`. No ask/tell mutation should occur before
`authorize_optimizer_update`. On a violation, timeout, monitor death, malformed
acknowledgement, or journal failure, `VerificationAbort` stops the guarded path.
The strong path assumes a two-phase optimizer adapter whose `preview_update` is
side-effect free and whose `commit_update` is the atomic mutation.

The primary Sampler profiles use the explicit ask/tell optimizer. The preserved
legacy SciPy profiles remain post-hoc integrations and correctly mark mutation
enforcement `INCONCLUSIVE`.

## Rebuilding the generated monitor

Runtime use needs only Java and the bundled JARs. Rebuilding uses JDK 17+ and
three Scala 2.12.21 artifacts whose Maven Central URLs and SHA-256 digests are
pinned in `tools/monitor_build_dependencies.json`:

```bash
python3 tools/fetch_monitor_build_deps.py
python3 tools/build_monitor.py
PYTHONPATH=src python3 -m unittest \
  tests.test_monitor_build_sync tests.test_monitor_build_dependencies -v
```

The fetcher refuses an unexpected existing file and verifies every download
before installing it. The builder re-verifies all dependency hashes, the
bundled DejaVu runtime hash, QTL hash, and bridge hash, and emits a JAR with a
fixed archive timestamp. Two clean rebuilds are byte-identical.

## Termination semantics

The terminal outcomes are intentionally distinct:

- `CONVERGED`: the last verified checkpoint satisfies tolerance, minimum
  iteration, and patience policy.
- `MAX_ITERATIONS`: the last checkpoint is nonconverged and exactly exhausts
  the configured evaluation limit.
- `OPTIMIZER_STOPPED`: an explicit project extension for an optimizer ending
  before convergence/limit. It is accepted only when
  `execution.allow_optimizer_stopped = true`; the manuscript's baseline does
  not include this normal terminal reason.
- `ABORTED`: a recorded critical failure routed execution through the abort
  protocol.

`DONE`/`ABORT` are absorbing. A critical failure cannot be followed by ordinary
submission, release, update, or successful termination. `runClosed` is the
finite-trace witness that enables run-level completion checking.

## Explicit assumptions and limits

The guarantee is conditional on these assumptions:

- execution is sequential and one run is processed by one monitor;
- one monitored iteration means one verified objective evaluation; the
  ask/tell commit links its approved successor exactly;
- each monitored evaluation uses exactly one backend submission containing all
  declared terms; split/grouped multi-job measurement and retries require an
  extended schema;
- every relevant event passes through the guarded instrumentation exactly once
  and in causal order;
- the resolved configuration and ordered Hamiltonian manifest are trusted and
  immutable;
- Python arithmetic certificates, the journal, Java bridge, and DejaVu monitor
  form the trusted computing base;
- backend job IDs and returned classical data are honestly reported;
- SHA-256 is collision resistant for the identity binding used here;
- an ask/tell callback is atomic and does not secretly submit quantum work.

Configuration is strict: unknown TOML/JSON fields, schema-type coercions, and
monitor-unsafe identifiers are rejected before a run starts. Submission,
external-job, and evaluation IDs must also be globally fresh within the run,
which detects stale-identity reuse under faithful instrumentation. It cannot
detect a deceptive adapter that assigns fresh, self-consistent IDs to stale
data. The hash-bound `parameter_count` prevents dimension drift between the
ansatz, optimizer output, and later bindings.

This layer proves conformance of the observed classical trace. It does not
prove physical state preparation, backend honesty, calibration quality, gate
or readout noise, absence of drift/crosstalk/leakage, optimizer internals,
global-optimum attainment, the true ground-state energy, or a convergence
probability from one run. The manuscript's sequential-model limitation remains:
batched, concurrent, distributed, and multi-backend VQE need a different event
and causality model.

See `docs/DESIGN.md` for the property decomposition, event protocol, verdict
composition, trusted boundary, and manuscript-facing rationale.

## Project map

| Path | Role |
|---|---|
| `src/vqe_runtime/config.py` | versioned config/Hamiltonian loading and canonical hashes |
| `src/vqe_runtime/contracts.py` | shared executable intra/inter/run data contracts |
| `src/vqe_runtime/dejavu.py` | acknowledged long-lived DejaVu adapter |
| `src/vqe_runtime/session.py` | online fail-closed gates and lifecycle API |
| `src/vqe_runtime/checker.py` | offline JSONL replay with the same contracts |
| `src/vqe_runtime/sampler_runner.py` | comparable StatevectorSampler/IBM SamplerV2 experiment |
| `src/vqe_runtime/sampling.py` | basis circuits, parity reconstruction, and packed-shot evidence |
| `src/vqe_runtime/evidence.py` | durable raw-evidence sidecar and manifest |
| `src/vqe_runtime/evidence_replay.py` | strict trace-to-sidecar correlation |
| `src/vqe_runtime/optimizer.py` | explicit preview/authorize/commit pattern search |
| `src/vqe_runtime/qiskit_runner.py` | preserved legacy Estimator instrumentation |
| `specs/vqe_runtime.qtl` | scoped past-time temporal contracts |
| `tools/SynchronousBridge.scala` | closed event schema and monitor ACK protocol |
| `tests/` | valid, mutation, closure, bridge, and build-synchronization tests |
