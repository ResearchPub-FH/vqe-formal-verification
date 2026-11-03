# Reproducing the H2 SamplerV2 verification experiment

This guide explains the experiment from first principles and gives exact steps
for reproducing it. It covers the local statevector comparator, the IBM Quantum
hardware run, independent replay, raw-evidence inspection, and the monitor
overhead benchmark.

The archived reference campaign ran on September 7–8, 2026. Hardware sampling
is inherently random, so a new run should reproduce the protocol and
verification verdicts, not the exact bitstrings or energy sequence.

## 1. What this experiment demonstrates

The experiment tests whether a two-qubit variational quantum eigensolver (VQE)
execution obeys declared runtime contracts. It checks three scopes:

1. **Within each evaluation:** the bound parameters, submitted job, four
   measurement results, shot totals, parity-derived expectations, energy, and
   convergence decision are internally consistent.
2. **Across evaluations:** identifiers are fresh, the shot budget is cumulative,
   the optimizer proposes the next vector without mutation, the verifier
   approves that exact vector, and only then does the optimizer commit it.
3. **For the whole run:** startup, terminal reason, and closure occur exactly
   once in a valid order.

The accepted claim is conditional: the recorded execution conforms to these
contracts if the instrumentation and archived observations faithfully represent
what occurred. The experiment does not prove that IBM hardware is honest, that
the ansatz reaches the global ground state, or that one stochastic run estimates
physical accuracy.

## 2. Vocabulary for new readers

- **H2:** molecular hydrogen, represented here by a reduced two-qubit model.
- **Hamiltonian:** the weighted sum of quantum observables whose expectation is
  reported as the objective energy.
- **Pauli term:** one observable such as `YZ` or `XX`. Each character names the
  measurement axis for one qubit.
- **Shot:** one circuit execution that returns a classical bitstring.
- **PUB:** Qiskit's primitive unified block. In this experiment one PUB is one
  fully measured circuit for one Hamiltonian term at one parameter vector.
- **SamplerV2:** the IBM Runtime primitive that returns sampled measurement data.
- **Evaluation:** four independent PUBs, one for each Hamiltonian term, combined
  into one energy value.
- **Ask/tell optimizer:** the optimizer first previews a candidate and a token
  without changing state. The verifier authorizes the exact candidate. A commit
  using that token then changes optimizer state.
- **Trace:** compact JSONL lifecycle events consumed by the online and replay
  verifiers.
- **Evidence sidecar:** full counts, ordered bitstrings, packed `BitArray` bytes,
  hashes, circuit/layout identity, parameters, timestamps, and IBM metadata.

## 3. Fixed experiment identity

The model is:

```text
H = 0.3980 YZ - 0.3980 ZI - 0.0113 ZZ + 0.1810 XX
```

The authoritative manifest is `data/h2_hamiltonian.json`. This is the same
representative two-qubit H2 circuit family used for the other paper layers. The
reported objective is the energy of this reduced four-term operator; do not
silently compare it with a total molecular energy that includes different
constants or mappings.

| Setting | Value |
|---|---:|
| Backend | `ibm_marrakesh` |
| Primitive | IBM Runtime `SamplerV2` |
| Maximum evaluations | 50 |
| PUBs per evaluation | 4 |
| Shots per PUB/term | 1,024 |
| Maximum PUBs | 200 |
| Physical shots per evaluation | 4,096 |
| Full-run physical-shot ceiling | 204,800 |
| Parameter count | 4 |
| Initial/transpiler/local-sampler seed | 7 |
| Convergence tolerance | 0.005 |
| Minimum evaluations | 10 |
| Patience | 3 |
| Transpiler optimization level | 3 |
| Hardware physical layout in the reference run | `[6, 7]` |

The preflight uses one evaluation and 4,096 additional shots. Therefore the
largest campaign total, including preflight, is 208,896 shots. The 204,800
ceiling applies to the primary 50-evaluation run itself.

Each evaluation submits four independent measurement circuits in this order:

| PUB | Term | Basis change before Z measurement | Negative eigenvalue rule |
|---:|---|---|---|
| 0 | `YZ` | `Sdg` then `H` on Y; Z unchanged | odd parity across both bits |
| 1 | `ZI` | Z on logical qubit 1; ignore qubit 0 | bit for qubit 1 is `1` |
| 2 | `ZZ` | no basis rotation | odd parity across both bits |
| 3 | `XX` | `H` on both qubits | odd parity across both bits |

Qiskit writes two-bit count keys as `q1q0`. The left character is logical qubit
1 and the right character is logical qubit 0. This convention is why `ZI`
classifies `10` and `11` as negative.

For every term, the verifier recomputes:

```text
N_negative = sum of counts with odd active-qubit parity
expectation = 1 - 2 * N_negative / 1024
```

The energy is then reconstructed from the four expectations and the exact
integer-scaled coefficients in the Hamiltonian manifest.

## 4. Repository map

| Purpose | Path |
|---|---|
| Hardware configuration | `configs/h2_ibm_sampler_50.toml` |
| One-evaluation hardware preflight | `configs/h2_ibm_sampler_preflight.toml` |
| Comparable statevector configuration | `configs/h2_statevector.toml` |
| Hamiltonian manifest | `data/h2_hamiltonian.json` |
| Sampler runner | `src/vqe_runtime/sampler_runner.py` |
| Ask/tell optimizer | `src/vqe_runtime/optimizer.py` |
| Shot/parity encoding | `src/vqe_runtime/sampling.py` |
| Raw-evidence journal | `src/vqe_runtime/evidence.py` |
| Independent evidence replay | `src/vqe_runtime/evidence_replay.py` |
| QTL specification | `specs/vqe_runtime.qtl` |
| Local preflight validator | `tools/validate_sampler_experiment.py` |
| Offline campaign summarizer | `tools/summarize_sampler_campaign.py` |
| Monitor benchmark | `tools/benchmark_overhead.py` |

## 5. Software environment

Use Python 3.11 or newer and Java 17 or a compatible Java runtime. The archived
reference environment was:

```text
macOS 26.6.2, arm64
CPython 3.12.14
OpenJDK 17.0.4.1
Qiskit 2.5.2
qiskit-ibm-runtime 0.49.0
NumPy 2.5.3
SciPy 1.18.1
```

Create an isolated environment from the repository root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[qiskit]'
python -m pip freeze > artifacts/environments/reproduction-pip-freeze.txt
java -version
```

`artifacts/environments/h2_sampler_campaign_20260907.json` records exact
reference versions, commands, and SHA-256 digests. The package enforces Python
3.11+ at import time and reports a clear version error on older Python.

## 6. Tests and local validation

Run the complete suite before any paid or quota-consuming hardware work:

```bash
python -m unittest discover -s tests -v
```

The archived implementation passes 129 tests. The suite includes malformed raw
data, corrupted counts, wrong term/PUB assignments, missing PUBs, shot mismatch,
stale or reused optimizer tokens, altered authorized vectors, duplicate job IDs,
configuration drift, false convergence, and a real DejaVu online rejection.

Run the executable local validation:

```bash
python tools/validate_sampler_experiment.py \
  --config configs/h2_statevector.toml \
  --out artifacts/validation/h2_sampler_local_validation_REPRODUCTION.json
```

Expected checks include:

- a one-qubit Hadamard circuit with exactly 1,024 outcomes;
- all four H2 measurement circuits through `StatevectorSampler`;
- count-derived expectations compared with `StatevectorEstimator`;
- explicit confirmation of Qiskit's Pauli-label/qubit ordering;
- rejected missing PUB, swapped term, shot mismatch, and corrupted count cases.

The archived validation report records 36 passed checks and zero failures.

## 7. Reproduce the statevector comparator

Choose a fresh run ID and fresh output paths. The runner may overwrite local
statevector outputs, but unique paths make provenance easier to audit.

```bash
python -m vqe_runtime.cli run \
  --config configs/h2_statevector.toml \
  --output artifacts/traces/h2_statevector_sampler_REPRODUCTION.jsonl \
  --report artifacts/reports/h2_statevector_sampler_REPRODUCTION_online.json \
  --evidence-output artifacts/evidence/h2_statevector_sampler_REPRODUCTION.jsonl \
  --run-id h2-statevector-sampler-REPRODUCTION

python -m vqe_runtime.cli check \
  artifacts/traces/h2_statevector_sampler_REPRODUCTION.jsonl \
  --config configs/h2_statevector.toml \
  --evidence artifacts/evidence/h2_statevector_sampler_REPRODUCTION.jsonl \
  --report artifacts/reports/h2_statevector_sampler_REPRODUCTION_replay.json
```

This comparator intentionally uses 1,024 sampled shots for each of the same
four independent measurement circuits. It does not use an exact, shot-free
statevector objective. That choice makes its measurement and accounting design
directly comparable with hardware. Seed 7 makes the archived local run
repeatable under the same Qiskit implementation.

## 8. Configure IBM Quantum safely

Configure an IBM Quantum account using Qiskit Runtime's normal account setup.
Never place an API token in this repository, a command transcript, or a report.
Confirm read-only access before submission:

```python
from qiskit_ibm_runtime import QiskitRuntimeService

service = QiskitRuntimeService(instance="test")
backend = service.backend("ibm_marrakesh")
print(backend.name, backend.num_qubits, backend.status().operational)
```

If the account uses a different instance, record that instance in the new
environment manifest. Backend availability, queue time, calibration, and
layout may differ from the archived run.

## 9. Hardware preflight

The reference preflight already consumed 4,096 shots and must not be repeated
when analyzing the archived campaign. For a genuinely new campaign, submit one
fresh preflight with unique paths:

```bash
python -m vqe_runtime.cli run \
  --config configs/h2_ibm_sampler_preflight.toml \
  --output artifacts/traces/h2_ibm_preflight_REPRODUCTION.jsonl \
  --report artifacts/reports/h2_ibm_preflight_REPRODUCTION_online.json \
  --evidence-output artifacts/evidence/h2_ibm_preflight_REPRODUCTION.jsonl \
  --run-id h2-ibm-preflight-REPRODUCTION
```

Verify the job ID exists in the trace before doing anything else. If the client
disconnects, retrieve that existing job and reconstruct state from the durable
trace; do not launch the command again. Inspect all four sidecar records for
1,024 observed shots, count totals of 1,024, expected result fields, and a
single physical layout.

The archived preflight job was `dafnocu42tqs73b06mb0`. Its hardware data passed,
but replay rejected a parameterized-circuit provenance hash because the runner
serialized the same QPY circuit twice and QPY bytes were not stable across those
serializations. The runner now captures each QPY digest once and reuses it. The
preflight remains immutable evidence of both the successful schema check and the
detected provenance defect; it was not resubmitted.

## 10. Full IBM hardware run

Hardware execution consumes quota or credits. Review the 204,800-shot maximum
and obtain authorization before submission. Use a new run ID and four paths
that do not already exist:

```bash
python -m vqe_runtime.cli run \
  --config configs/h2_ibm_sampler_50.toml \
  --output artifacts/traces/h2_ibm_marrakesh_sampler_REPRODUCTION.jsonl \
  --report artifacts/reports/h2_ibm_marrakesh_sampler_REPRODUCTION_online.json \
  --evidence-output artifacts/evidence/h2_ibm_marrakesh_sampler_REPRODUCTION.jsonl \
  --run-id h2-ibm-marrakesh-sampler-REPRODUCTION
```

The hardware runner refuses to start if any destination already exists. This
guard prevents a resume attempt from becoming a duplicate hardware campaign.
For each evaluation it performs this sequence:

1. bind the exact recorded four-parameter vector;
2. emit the four-term expected manifest;
3. authorize one submission for four PUBs;
4. submit one IBM job and durably record its job ID;
5. wait for that job and archive four raw `BitArray` results;
6. verify counts, parity, expectations, hashes, layout, and total shots;
7. reconstruct and verify the four-term energy;
8. release that verified energy to the optimizer;
9. preview the next optimizer proposal without mutation;
10. authorize that exact proposal and then commit it;
11. bind the committed vector only in the next evaluation.

The explicit Sampler options are recorded in both trace and evidence:

```text
default_shots = 1024
run shots = 1024
measurement type = classified
gate twirling = false
measurement twirling = false
dynamical decoupling = false
measurement mitigation = not applicable to raw SamplerV2
ZNE = not applicable to raw SamplerV2
PEC = not applicable to raw SamplerV2
```

These settings preserve the direct chain from IBM bitstrings to optimizer
energy. They also mean the reported hardware objective includes device and
readout noise; it is not an error-mitigated chemistry estimate.

## 11. Independent replay

Supply the evidence path explicitly. The trace cannot choose its own evidence:

```bash
python -m vqe_runtime.cli check \
  artifacts/traces/h2_ibm_marrakesh_sampler_REPRODUCTION.jsonl \
  --config configs/h2_ibm_sampler_50.toml \
  --evidence artifacts/evidence/h2_ibm_marrakesh_sampler_REPRODUCTION.jsonl \
  --report artifacts/reports/h2_ibm_marrakesh_sampler_REPRODUCTION_replay.json
```

Acceptance requires `status: "pass"` in both reports, `pass` for all three
levels, matching configuration identity, and the same terminal reason. Replay
strictly reloads packed shots, ordered bitstrings, counts, record hashes, record
order, and the final manifest.

## 12. Generate raw result tables

For the archived campaign, run:

```bash
python tools/summarize_sampler_campaign.py \
  --output-dir artifacts/results/h2_sampler_comparison_NEW
```

The script refuses to overwrite an existing directory. Use its path arguments
to point at reproduction artifacts. It writes:

- `campaign_summary.json`: machine-readable acceptance verdicts and headline
  statistics;
- `hardware_evaluations.csv`: one row per hardware energy evaluation;
- `hardware_pubs.csv`: one row per hardware term/PUB, including full counts and
  evidence hashes;
- `hardware_jobs.json`: all 50 deduplicated IBM job metadata records;
- matching statevector CSV files;
- `SHA256SUMS`: digests for every generated summary file.

The archived output is `artifacts/results/h2_sampler_comparison_20260907/`.

## 13. Reproduce the overhead and scaling benchmark

Do not mix hardware queue time with local monitor overhead. The benchmark uses
synthetic observations so instrumented and uninstrumented loops receive the
same data:

```bash
python tools/benchmark_overhead.py \
  --config configs/h2_demo.toml \
  --out-dir artifacts/benchmarks/h2_monitor_REPRODUCTION \
  --warmups 5 \
  --repetitions 30 \
  --scaling-repetitions 1 \
  --scales 10,25,50,60,100,125,150,175,200
```

Archive `runs.csv`, `gate_latencies.csv`, `memory_samples.csv`, `summary.json`,
and `environment.json`. At 50 evaluations the reference run measured 0.984 ms
all-gate p95, 1.305 ms `nextConvergenceChecked` p95, and 439.80 MiB peak JVM
RSS. Growth becomes material after roughly 125 evaluations and reaches 16.362
ms all-gate p95 with 941.80 MiB at 200 evaluations.

The current `nextConvergenceChecked` relation is retained because the declared
experiment stops at 50, below the measured latency knee, and the relation
provides useful predecessor/energy continuity. Raising the bound materially
beyond 100 evaluations requires the checkpoint-certificate redesign described
in `artifacts/benchmarks/BENCHMARK_REPORT.md` and a new scaling validation.

## 14. Verify archived hashes

```bash
cd artifacts/results/h2_sampler_comparison_20260907
shasum -a 256 -c SHA256SUMS
```

The broader environment manifest lists digests for source, configuration,
monitor, trace, evidence, and reports.

## 15. Expected archived outcome

| Measure | IBM hardware | Statevector sampler |
|---|---:|---:|
| Evaluations | 50 | 50 |
| PUBs | 200 | 200 |
| Physical/effective shots | 204,800 | 204,800 |
| Online verdict | PASS | PASS |
| Replay verdict | PASS | PASS |
| Terminal reason | max iterations | max iterations |
| Initial energy | 0.1916484375 | 0.2069205078 |
| Best observed energy | -0.4189324219 | -0.4398875000 |
| Best evaluation, zero-based | 28 | 40 |
| Final energy | -0.3775728516 | -0.4398074219 |

Both runs share the ansatz, initial parameters, term circuits, shots, optimizer,
convergence policy, and evaluation cap. Their parameter paths can diverge after
the first sampled objectives because each ask/tell decision depends on observed
energy. The 0.0209550781 difference between best observed energies is a result
of these two runs, not a general hardware-accuracy estimate.

## 16. Troubleshooting and stop conditions

- **An output file already exists:** do not delete it reflexively. Inspect its
  trace for a recorded IBM job ID and recover that run. Use fresh paths only for
  a genuinely new authorized campaign.
- **IBM job is queued or the client disconnects:** query the recorded job ID.
  Do not repeat the submission command.
- **One PUB has the wrong shot count:** reject the evaluation. Do not release an
  energy to the optimizer.
- **Replay is inconclusive:** check that the trace ends in `runClosed`, the
  evidence path was supplied explicitly, and the sidecar contains its manifest.
- **Replay fails a provenance hash:** preserve the artifacts and diagnose the
  serialization/circuit identity. Never edit evidence to make it pass.
- **Monitor timeout:** the guarded path fails closed. At a much larger evaluation
  bound, rerun the scaling benchmark before increasing timeouts.
- **Different physical layout:** this can be valid for a new transpilation, but
  all four PUB circuits in that run must share the selected layout and the new
  layout must be archived.

## 17. Reproduction checklist

- [ ] Python and Java versions recorded
- [ ] exact package versions archived
- [ ] tests pass
- [ ] 36 local validation checks pass
- [ ] credentials kept outside the repository
- [ ] backend and instance recorded
- [ ] one authorized preflight with a unique job ID
- [ ] no destination path existed before full submission
- [ ] at most 50 full-run job IDs
- [ ] exactly four 1,024-shot PUBs per completed evaluation
- [ ] all raw records and final manifest sealed
- [ ] online and replay reports agree
- [ ] ask/tell proposal, authorization, commit, and next binding match
- [ ] shot total does not exceed 204,800 for the full run
- [ ] terminal reason matches the last verified checkpoint
- [ ] result CSVs, environment manifest, and SHA-256 digests archived
