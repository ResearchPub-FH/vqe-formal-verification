# Design rationale and assurance model

## 1. Why two cooperating checkers are necessary

DejaVu is well suited to past-time first-order temporal relationships: whether
binding preceded submission, whether all declared terms were observed before a
seal, whether an energy certificate preceded release, and whether the next
iteration refers to the last checkpoint. It is not the right place to perform
floating-point vector arithmetic or parse backend result schemas.

Python therefore validates the value domain and produces certificates; DejaVu
validates their temporal use. This is the runtime analogue of the manuscript's
Dafny/Python assume-guarantee bridge:

```text
raw observed values
   -> Python executable contract
   -> identity-bound certificate
   -> DejaVu causal contract
   -> guarded side effect
```

The split prevents two common overclaims:

1. A temporal monitor does not make an unverified numeric claim true.
2. A correct numeric record does not prove it was fresh or used in the right
   phase of the loop.

## 2. Reference lifecycle

The instrumentation uses landmark witnesses for mode entry/completion; it does
not literally emit paired entry/exit events for every shared mode. It refines
the manuscript's shared execution model as follows:

```text
INIT
  runStarted(run_id, config_hash)  # manifest is in the hash-bound payload
  optimizerAskTellConfigured | optimizerOpaqueConfigured
PREPARE
  firstIterationStarted | nextIterationStarted
  parametersBound(theta_hash)
MEASURE
  termExpected*
  jobSubmitIntent
  jobSubmitted(external_job_id)
  termObserved*
  measurementsSealed
AGGREGATE
  numericValid(energy_hash, theta_hash)
CHECK
  firstConvergenceChecked | nextConvergenceChecked
  convergenceTrue | convergenceFalse
  iterationPass
  objectiveReleaseIntent
OPTIMIZE
  optimizerUpdateIntent
  optimizerUpdated
  iterationClosed
DONE / ABORT
  runConverged | runMaxIterations | runOptimizerStopped | runAborted
  runClosed
```

`runClosed` is an evidence-stream meta-event, not a transition out of the
absorbing `DONE`/`ABORT` model state.

This implementation defines one monitored iteration as one complete objective
evaluation. That is exact for the instrumented demo loop. For SciPy/COBYLA it
is a stated abstraction: an objective evaluation is not necessarily one
accepted optimizer step. The schema preserves `evaluation_id`, but does not
claim access to a hidden optimizer-iteration identifier.

Every normal domain event is preceded by an `activity` event. This gives the
past-time monitor a compact absorbing-state guard. The Scala bridge additionally
enforces an event allowlist, exact arity, consecutive sequence watermarks, and
no event after `runClosed`.
The Python contract engine pairs every `activity(kind)` with the immediately
following event of that exact kind and rejects unsupported or dangling kinds.

## 3. Intra-iteration contracts

The intra level checks one evaluation in isolation:

- exactly one parameter binding and backend submission;
- complete, unique ordered Hamiltonian term identity;
- exact submission and external backend-job continuity;
- term observations tied to the submitted theta and job;
- finite expectation values in `[-1, 1]`;
- observed shot count and optional counts-to-expectation reconstruction;
- explicit `INCONCLUSIVE` rather than an assumed executed-sample count when a
  shot-based backend omits both shot and count metadata;
- no missing/duplicate term at measurement seal;
- independently reconstructed `sum(c_i * expectation_i)`;
- coefficient-induced energy bound;
- convergence check only after valid aggregation;
- iteration pass and objective release only after the check;
- close only after release; abort only after a critical failure.

The configured Hamiltonian, not the trace itself, defines completeness. A
self-consistent trace that silently drops a Hamiltonian term therefore fails.
The one-submission rule intentionally excludes split/grouped multi-job
measurement, retries, and adaptive resampling; those need a submission-group
schema rather than weakening identity checks in this one-job profile.

## 4. Inter-iteration contracts

The inter level intentionally does **not** require monotonically decreasing
energy. Optimizers such as COBYLA legitimately evaluate worse candidates.
Coherence means evidence/history continuity:

- iteration index is exactly `previous + 1`;
- run and configuration hash never change;
- evaluation, submission, and external backend-job IDs are never reused;
- exactly one optimizer protocol is certified at startup, and ask/tell and
  opaque events cannot be substituted for one another;
- no overlapping iteration;
- a successor identifies the last closed evaluation;
- the prior accepted energy is the convergence check's previous energy;
- energy delta and stable-delta patience counter are recomputed;
- convergence respects tolerance, minimum iterations, and patience;
- optimizer output hash equals the next bound theta hash;
- vector length always equals the hash-bound `parameter_count`;
- a converged checkpoint has no successor;
- effective term-sample accounting is cumulative and bounded.

For ask/tell, update intent is an enforceable pre-mutation gate. For an opaque
SciPy objective, only post-hoc candidate linkage is observable, and the report
states that limitation as one `INCONCLUSIVE` inter-level property.

Minimum iterations, consecutive-delta patience, and the inclusive comparator
`delta <= tolerance + energy_abs_tolerance` are declared project policies, not
rules supplied by the manuscript. The first evaluation is never converged and
starts with stable count zero.

## 5. Run-level contracts and finite-trace semantics

Past-time safety properties can reject bad prefixes online. Eventual
termination cannot be proven while a trace may still grow. The explicit
`runClosed` event changes the question to finite-trace conformance.

At `runClosed`, the implementation requires:

- one matching `runStarted` and immutable resolved config;
- no open iteration;
- exactly one terminal path;
- final checkpoint identity matching the terminal event;
- `CONVERGED` supported by a true convergence certificate;
- `MAX_ITERATIONS` supported by exact limit exhaustion and nonconvergence;
- `OPTIMIZER_STOPPED` supported by a closed nonconverged checkpoint;
- `OPTIMIZER_STOPPED` occurs strictly before the configured iteration limit;
- `ABORTED` supported by a recorded critical failure;
- any critical failure forces abort rather than normal completion;
- no activity after a terminal event or close.

A truncated trace is `INCONCLUSIVE`, not `FAIL`, because it may be a prefix of a
still-running valid execution. Operationally, the guarded online controller
still fails closed when its monitor or journal becomes unavailable.

`OPTIMIZER_STOPPED` is a declared extension to the manuscript's baseline
`CONVERGED | MAX_ITERATIONS | ABORTED` outcomes. Python accepts it only when the
hash-bound config explicitly enables `allow_optimizer_stopped`; otherwise it is
an untruthful terminal reason.

## 6. Verdict composition

For each scope:

```text
FAIL         if any required property in the scope is violated
INCONCLUSIVE if none fail but required evidence/observability is missing
PASS         otherwise, with run level additionally requiring runClosed
```

The inter-iteration scope also requires at least one adjacent checkpoint pair.
A run with exactly one verified evaluation is `INCONCLUSIVE` for inter-iteration
coherence, while its intra-iteration and run-lifecycle scopes may still pass.

Overall composition is fail-dominant:

```text
overall FAIL         if any scope FAILs
overall INCONCLUSIVE if none FAIL and any scope is INCONCLUSIVE
overall PASS         only if all three scopes PASS
```

Lifecycle compliance and algorithm outcome remain distinct. A correctly
executed abort path can satisfy the run protocol, while the injected property
violation still makes the overall report `FAIL`.

## 7. Stable identities and provenance

All monitor relations are keyed by `run_id` and the canonical resolved config
hash. The config snapshot includes execution policy, numeric/convergence
tolerances, observability policy, monitor parameters, and the entire ordered
Hamiltonian manifest. Later events carry the same hash.

Parameter and energy values use canonical SHA-256 identities. Backend submission
and result events carry both the internal submission ID and external job ID.
Term observations bind those IDs, the term ID, and theta hash. These hashes are
integrity/linkage devices, not signatures; journal authenticity is outside the
current threat model.

`runStarted` also commits a canonical execution-provenance object. Every profile
records mode, system, backend, and seed. The Qiskit runner additionally records
QPY hashes for the logical ansatz and executable circuit, a layout fingerprint,
requested shots, optimizer, transpiler level, and transpiler seed. These fields
support reproducibility and diagnose environment drift; they do not prove that
an external backend honestly executed the fingerprinted circuit.

## 8. Closed-world bridge

The previous DejaVu prototype was open-world: unknown events and several
duplicate or incomplete lifecycle sequences could pass because they did not
trigger a formula. `SynchronousBridge.scala` now rejects:

- unknown event names;
- incorrect arity;
- duplicate, skipped, or out-of-order sequence watermarks;
- any event after an acknowledged `runClosed`.

The generated JAR embeds hashes of the QTL, bridge, and pinned DejaVu runtime.
An external manifest additionally pins the JAR hash. Startup verifies the JAR,
runtime, embedded metadata, manifest, and—when source is present—the current QTL
and bridge before launching Java. `test_monitor_build_sync.py` independently
prevents a stale compiled monitor from silently shipping with changed source.

## 9. Trusted computing base and threat boundary

Trusted:

- instrumentation coverage and ordering;
- configuration/Hamiltonian manifest source;
- Python contract engine and session gates;
- JSONL journal persistence when durable mode is used;
- Java bridge, generated monitor, and DejaVu runtime;
- collision resistance of canonical hashes.

Observed but not proven physically:

- backend execution and job identity;
- reported expectation values or counts;
- calibration, compilation fidelity, noise, and hardware state;
- optimizer implementation beyond observable candidates/ask-tell mutation.

The checker verifies internal consistency and provenance of the observed
interface. It cannot detect a cooperative-looking backend that fabricates an
entire self-consistent result.

Error handling here means fail-closed **error-state safety** and abort routing.
Recovery/retry is not implemented.

## 10. Manuscript property-category crosswalk

The manuscript's broad Table I checkmarks need the following qualifications:

| Manuscript category | Runtime scope/mechanism | Current status |
|---|---|---|
| Control flow and ordering | DejaVu at all three scopes | Implemented for the declared sequential lifecycle |
| Iteration and state consistency | Python + DejaVu inter/run | Implemented with one evaluation per monitored iteration |
| Parameter binding and optimizer update | Hash linkage; ask/tell gate | Implemented for ask/tell; opaque mutation is `INCONCLUSIVE` |
| Measurement and shot consistency | Python intra | Implemented when result metadata/counts are observable; otherwise `INCONCLUSIVE` |
| Expectation aggregation | Python intra | Implemented against the configured Hamiltonian |
| Numeric-bound and interval safety | Python intra/inter | Implemented for finite recorded values and configured tolerances |
| Convergence and termination | Python + DejaVu inter/run | Implemented for the declared delta/patience and terminal policy |
| Probabilistic reliability | None in a single-run trace | Not implemented; requires multi-run statistics or binding to a Storm certificate |
| Backend, compilation, execution environment | Config/job/circuit provenance | Provenance conformance only; physical/compiler correctness is not proved |
| Runtime trace conformance | Closed schema, watermarks, replay, `runClosed` | Implemented for complete traces |
| Error-state safety | Fail-closed gates and abort path | Implemented; recovery is out of scope |

## 11. Mutation/evaluation plan for the manuscript

The automated suite already covers valid completion, unknown/wrong-arity
events, duplicate start, missing terminal, empty/truncated traces,
post-terminal activity, config drift, malformed/unknown configuration,
protocol substitution, parameter-dimension drift, skipped iteration,
reused/duplicate backend job,
contradictory payloads, missing terms, unverifiable shots, wrong energy,
out-of-bound parameters, false convergence, stale next theta, monitor outage,
startup cleanup, and misleading terminal reasons.

For empirical evaluation, report at least:

- mutants killed per scope and any intentionally inconclusive mutant;
- DejaVu property count and Python property count;
- event count and JSONL bytes per evaluation;
- p50/p95 synchronous gate latency;
- total runtime overhead against an uninstrumented baseline;
- peak monitor memory as terms and iterations scale;
- run-close success versus truncation/monitor-death behavior.

The central claim should be phrased conditionally: for a complete, faithfully
instrumented observed execution, the component conclusively checks conformance
to the declared VQE lifecycle and data contracts. It does not conclude physical
or optimization correctness beyond that boundary.
