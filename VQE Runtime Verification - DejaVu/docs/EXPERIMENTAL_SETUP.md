# Reproducible experimental setup

This protocol separates three questions that should not be collapsed into one
experiment:

1. **Conformance:** does a valid, fully observed VQE execution pass all three
   verification levels?
2. **Fault detection:** do controlled lifecycle, identity, arithmetic, and
   termination mutants receive `FAIL` or the deliberately expected
   `INCONCLUSIVE` verdict?
3. **Cost:** what latency, runtime, memory, and evidence-storage overhead does
   synchronous monitoring add relative to the same uninstrumented loop?

The deterministic H2 profile remains the normative lifecycle regression. The
primary scientific integration is now the count-backed Sampler experiment:
statevector and IBM hardware use the same ansatz, initialization, four
independent 1,024-shot term PUBs, explicit ask/tell optimizer, convergence
policy, and 50-evaluation cap. Both paths archive full raw shot evidence.

## 1. Reference environment

Core requirements:

- Python 3.11 or newer;
- Java 17 or another compatible Java runtime;
- no third-party Python packages for the deterministic demo and replay;
- the bundled, hash-pinned DejaVu runtime and generated monitor.

The primary Sampler campaign on 2026-09-07 and 2026-09-08 used macOS 26.6.2 on
arm64, Python 3.12.14, OpenJDK 17.0.4.1, Qiskit 2.5.2, and Qiskit IBM Runtime
0.49.0. This describes the validating host; it is not a requirement to
reproduce the core experiment.

Qiskit profiles use the dependency ranges in `pyproject.toml`: Qiskit 2.3 up
to but excluding 3, Qiskit IBM Runtime 0.48 up to but excluding 1, and SciPy
1.11 up to but excluding 2. A published hardware or statevector experiment
must additionally archive exact resolved versions, backend name, UTC execution
time, external job IDs, raw evidence, layout, and available backend metadata.

## 2. System and Hamiltonian

All supplied profiles use the two-qubit H2 Hamiltonian in
`data/h2_hamiltonian.json`:

```text
H = 0.3980 YZ - 0.3980 ZI - 0.0113 ZZ + 0.1810 XX
```

The ordered four-term manifest and coefficient scale of 10,000 are included in
the canonical configuration hash. Parameters are constrained to `[-pi, pi]`.
Changing the manifest, term order, policy, or execution configuration creates a
different experiment identity.

## 3. Configuration matrix

| Setting | Deterministic regression | Statevector Sampler comparator | IBM SamplerV2 primary |
|---|---:|---:|---:|
| Config | `configs/h2_demo.toml` | `configs/h2_statevector.toml` | `configs/h2_ibm_sampler_50.toml` |
| Backend | deterministic counts | `StatevectorSampler` | `ibm_marrakesh` |
| Parameter count | 2 | 4 | 4 |
| Maximum monitored evaluations | 3 | 50 | 50 |
| Physical shots per term | 1,000 | 1,024 | 1,024 |
| PUBs per evaluation | N/A | 4 independent | 4 independent |
| Total sample/shot budget | 12,000 | 204,800 | 204,800 |
| Seed | 7 | 7 | 7 |
| Optimizer protocol | ask/tell | explicit ask/tell | explicit ask/tell |
| Convergence tolerance | 0.001 | 0.005 | 0.005 |
| Minimum evaluations | 3 | 10 | 10 |
| Patience | 2 | 3 | 3 |
| Raw counts required | yes | yes | yes |
| Monitor timeout | 10 s | 10 s | 30 s |
| DejaVu bits per variable | 24 | 24 | 24 |

For the primary Sampler path, the requested value is not accepted as execution
evidence. Every returned `BitArray.num_shots` and full count dictionary must
show exactly 1,024 outcomes. Missing or mismatched shot evidence blocks the
objective from reaching the optimizer.

## 4. Normative regression procedure

Run from the repository root:

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

Acceptance criteria:

- online and replay reports are complete and `PASS` overall;
- intra-iteration, inter-iteration, and run-level verdicts are all `PASS`;
- replay uses the same canonical configuration hash as the online run;
- all automated mutation/adversarial tests pass;
- monitor provenance hashes match `monitor-manifest.json`;
- the trace has an explicit terminal event followed by `runClosed`.

The supplied replay evidence contains 127 events across three evaluations,
12,000 verified effective term samples, and 29 recorded Python contracts.

## 5. Count-backed Sampler integration runs

Install the optional packages in an isolated environment and record the exact
resolved versions:

```bash
python3 -m pip install -e '.[qiskit]'
python3 -m pip freeze > artifacts/qiskit-environment.txt
```

Then run the local statevector profile with explicit trace, report, and raw
evidence outputs:

```bash
vqe-dejavu run \
  --config configs/h2_statevector.toml \
  --run-id h2-statevector-001 \
  --output artifacts/traces/h2_statevector.jsonl \
  --report artifacts/reports/h2_statevector.json \
  --evidence-output artifacts/evidence/h2_statevector.jsonl

vqe-dejavu check artifacts/traces/h2_statevector.jsonl \
  --config configs/h2_statevector.toml \
  --evidence artifacts/evidence/h2_statevector.jsonl \
  --report artifacts/reports/h2_statevector-replay.json
```

The IBM profile uses the same command shape with
`configs/h2_ibm_sampler_50.toml`, authenticated IBM Runtime credentials, unique
paths, and a unique run ID. The hardware runner refuses existing destination
paths to prevent duplicate submissions. Both primary profiles use the explicit
two-phase ask/tell optimizer, so the verifier approves the proposed vector
before commit and enforces exact candidate-to-next-binding continuity.

For the complete novice-oriented hardware lifecycle, preflight protocol,
recovery rules, archived outcomes, and commands, use
`docs/H2_SAMPLER_REPRODUCIBILITY.md`.

## 6. Fault-detection experiment

Use the existing test suite as the executable mutation catalogue. It covers
unknown and wrong-arity events, duplicate starts, truncated traces,
post-terminal activity, configuration drift, protocol substitution,
parameter-dimension drift, skipped iterations, stale or reused job identities,
missing terms, unverifiable shots, wrong energy, false convergence, stale next
parameters, monitor outage, and misleading termination reasons.

For manuscript reporting, classify each injected mutant by scope and expected
verdict, then report:

- mutants killed by `FAIL`;
- mutants safely withheld as `INCONCLUSIVE` because evidence is unavailable;
- false accepts, which must be zero for the declared threat model;
- the first event at which an online violation is blocked.

## 7. Overhead experiment

Measure an instrumented and an otherwise identical uninstrumented loop on the
same host. Use five warm-up runs followed by 30 measured repetitions per
condition. Keep the Hamiltonian, parameter sequence, seed, backend observations,
and process launch policy fixed. Do not mix hardware queue time into local
monitor overhead.

Report median and p95 for:

- end-to-end runtime;
- synchronous gate acknowledgement latency;
- per-evaluation monitoring overhead;
- peak resident memory;
- events and JSONL bytes per evaluation;
- close/replay time for complete and truncated traces.

Compute relative overhead as
`(instrumented - baseline) / baseline * 100%`. Repeat a separate robustness
sweep over declared seeds only if stochastic sensitivity is part of the
research question; do not combine that sweep with the fixed-seed overhead
comparison.

## 8. Reproducibility package

Archive together:

- resolved TOML configuration and ordered Hamiltonian manifest;
- raw JSONL trace and online/replay JSON reports;
- QTL, Scala bridge, DejaVu, and monitor SHA-256 identities;
- exact command line, UTC timestamp, host OS/architecture, Python and Java
  versions;
- exact optional dependency lock for Qiskit runs;
- mutation outcome table and raw benchmark samples;
- backend/job/circuit/layout provenance for external executions.

The defensible conclusion is conditional: a complete, faithfully instrumented
observed execution conforms to the declared VQE lifecycle and data contracts.
The experiment does not establish physical backend honesty, correct state
preparation, global-optimum attainment, or probabilistic reliability from one
run.
