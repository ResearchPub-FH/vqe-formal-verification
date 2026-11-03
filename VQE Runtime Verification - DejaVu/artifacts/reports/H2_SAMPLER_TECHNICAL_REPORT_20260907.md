# Verified H2 VQE execution with IBM Runtime SamplerV2

## Executive summary

The primary H2 experiment completed on `ibm_marrakesh` with the authorized
maximum of 50 monitored evaluations. Each evaluation used four independent
1,024-shot SamplerV2 PUBs for `YZ`, `ZI`, `ZZ`, and `XX`. The final campaign
therefore contains 50 IBM jobs, 200 PUBs, and exactly 204,800 physical shots.

Online verification and independent replay both returned **PASS** at the
intra-iteration, inter-iteration, and run levels with zero findings. The raw
sidecar contains every count dictionary, ordered bitstring, packed `BitArray`,
parity count, expectation, circuit and parameter identity, physical layout,
timestamp, and returned IBM metadata. Its sealed manifest commits to all 200
records and the 204,800-shot total.

The hardware run started at energy `0.1916484375`, reached its best observed
energy `-0.418932421875` at zero-based evaluation 28, and ended at
`-0.3775728515625`. It did not satisfy the declared convergence policy, so the
verifier accepted the truthful `max_iterations` terminal reason. The comparable
shot-based statevector run also used 50 evaluations and 204,800 samples; it
reached a best observed energy of `-0.4398875` at evaluation 40. These values
describe two sampled optimizer trajectories and do not constitute a general
hardware-accuracy estimate.

## Research question and assurance boundary

The experiment asks whether a concrete hybrid VQE execution conforms to a
declared lifecycle and data contract while it runs, and whether an independent
replay reaches the same verdict from durable evidence.

The accepted result supports this statement:

> Given faithful instrumentation and the archived observations, the execution
> obeyed the declared parameter-binding, backend-submission, measurement,
> arithmetic, optimizer-transition, budget, convergence, and termination
> contracts.

The result does not prove backend honesty, ideal state preparation, absence of
device noise, global optimization, chemical accuracy, or general behavior over
repeated hardware campaigns. The Hamiltonian is the representative reduced
four-term H2 operator used across the paper layers, not necessarily a complete
total molecular energy with every constant included.

## Fixed protocol

The Hamiltonian manifest defines:

```text
H = 0.3980 YZ - 0.3980 ZI - 0.0113 ZZ + 0.1810 XX
```

| Field | Declared value | Observed value |
|---|---:|---:|
| System | two-qubit H2 | two-qubit H2 |
| Backend | `ibm_marrakesh` | `ibm_marrakesh` |
| Primitive | Runtime `SamplerV2` | Runtime `SamplerV2` |
| Evaluations | at most 50 | 50 |
| PUBs per evaluation | 4 | 4 |
| Shots per term | 1,024 | 1,024 for all 200 PUBs |
| Maximum PUBs | 200 | 200 |
| Full-run shot ceiling | 204,800 | 204,800 |
| Terms in order | `YZ`, `ZI`, `ZZ`, `XX` | exact match |
| Parameter count | 4 | 4 |
| Optimizer | ask/tell pattern search | exact match |
| Convergence | tolerance 0.005, min 10, patience 3 | not reached |
| Terminal reason | verified convergence or cap | `max_iterations` |
| Physical layout | one fixed layout per run | logical `[0,1]` to physical `[6,7]` |

No terms were grouped. Four PUBs with 1,024 shots each make “shots per term” a
physical count rather than an effective count derived from shared data.

## Measurement and reconstruction

Qiskit bitstrings use the order `q1q0`. For a Pauli term, a shot has negative
eigenvalue when the parity over non-identity positions is odd. The verifier uses:

```text
expectation(P) = 1 - 2 * N_negative(P) / 1024
energy = sum(coefficient(P) * expectation(P))
```

As a concrete example, the best hardware checkpoint at evaluation 28 came from
IBM job `dafoahbdd5gc73da3qf0`:

| Term | Counts (`00`,`01`,`10`,`11`) | Negative count | Expectation |
|---|---|---:|---:|
| `YZ` | 158, 387, 162, 317 | 549 | -0.072265625 |
| `ZI` | 350, 660, 5, 9 | 14 | 0.972656250 |
| `ZZ` | 314, 688, 6, 16 | 694 | -0.355468750 |
| `XX` | 479, 32, 500, 13 | 532 | -0.039062500 |

The reconstructed energy is:

```text
0.3980*(-0.072265625)
- 0.3980*( 0.972656250)
- 0.0113*(-0.355468750)
+ 0.1810*(-0.039062500)
= -0.418932421875
```

The offline analyzer repeated this calculation for every one of the 50
evaluations and found exact agreement within the configured absolute tolerance
of `1e-12`.

## Explicit ask/tell enforcement

The optimizer integration uses a two-phase mutation protocol:

1. `preview_update(theta, energy)` returns a candidate vector and opaque token
   without mutating optimizer state.
2. The runtime verifier authorizes the exact candidate vector and records its
   hash.
3. `commit_update(token, authorized_theta=candidate)` is the only mutation
   boundary.
4. The verifier records the commit.
5. The next evaluation must bind that exact vector and hash.

The actual evaluation-0 sequence demonstrates the boundary:

| Stage | Evidence |
|---|---|
| Bound input | theta hash `1d0b2ef6…609` |
| Verified energy | `0.1916484375` |
| Previewed/authorized next vector | `[-0.7068913836, -2.1937793404, 0.9483492634, -2.6864620415]` |
| Authorized next hash | `a2a5a327…844` |
| Commit | same vector and hash, after authorization |
| Evaluation 1 binding | same vector and hash |

Across the complete hardware trace, the offline analyzer found 49 proposal
intents, 49 commits, and 49 exact successor bindings in strict order. Altered,
foreign, stale, or reused tokens are rejected by executable tests.

## Result-processing policy

The primary verification run records explicit raw-sampling options:

- 1,024 default and run-level shots;
- classified measurement output;
- gate twirling disabled;
- measurement twirling disabled;
- dynamical decoupling disabled;
- measurement mitigation, ZNE, and PEC marked not applicable to this direct raw
  SamplerV2 path.

This preserves the chain:

```text
IBM bitstrings -> complete counts -> parity -> term expectation
-> four-term H2 energy -> verified objective release -> optimizer
```

The policy favors auditability. It does not correct measurement or gate error,
so differences from the statevector comparator include device noise and may
also change later optimizer proposals.

## Validation before the primary run

Local validation completed 36 checks with zero failures. It included a
1,024-shot Hadamard circuit, all four H2 measurement circuits with
`StatevectorSampler`, count-derived comparisons with `StatevectorEstimator`,
the `q1q0` convention, and negative tests for missing, swapped, mismatched, and
corrupted results.

The full automated suite passed 129 tests in 14.787 seconds immediately before
hardware submission. Coverage includes optimizer mutation boundaries, raw
evidence, replay correlation, lifecycle ordering, budget accounting, monitor
identity, property-level attribution, and a real DejaVu rejection on the online
path.

## Hardware preflight and provenance correction

The one-evaluation preflight used IBM job `dafnocu42tqs73b06mb0` and 4,096
shots. All hardware-specific schema, count, parity, and metadata checks passed.
Independent replay correctly rejected one circuit-provenance hash.

Investigation showed that the code serialized a parameterized QPY circuit once
for the evidence record and a second time for run provenance. QPY byte output
was not stable across those separate serializations, although the circuit had
not changed. The fix captures each QPY digest once and reuses the captured
digest everywhere. A new test enforces this single-capture rule. The preflight
artifacts remain unchanged and the preflight was not repeated. The complete
50-evaluation run used the corrected implementation and passed replay.

This incident demonstrates why circuit provenance belongs in the verified
path: the system rejected inconsistent identity evidence even though the
hardware counts themselves were valid.

## Primary hardware results

| Metric | Result |
|---|---:|
| IBM jobs | 50 unique IDs |
| PUB records | 200 |
| Physical shots | 204,800 |
| Trace events | 2,103 |
| Monitored wall duration | 1,918.285 s |
| QPU charge time | 150 s |
| Estimated quantum time | 137.703 s |
| Online verdict | PASS |
| Replay verdict | PASS |
| Intra-iteration level | PASS |
| Inter-iteration level | PASS |
| Run level | PASS |
| Initial energy | 0.1916484375 |
| Best energy | -0.4189324219 at evaluation 28 |
| Final energy | -0.3775728516 |
| Terminal reason | max iterations |

The first job experienced the largest queue/service delay. Later small jobs
completed rapidly. Queue and service latency are included in the monitored wall
duration but excluded from the local monitor-overhead benchmark.

## Statevector comparison

| Measure | IBM hardware | Statevector sampler |
|---|---:|---:|
| Evaluations | 50 | 50 |
| Samples | 204,800 | 204,800 |
| Initial theta | same seed-7 vector | same seed-7 vector |
| Measurement circuits | four independent term PUBs | same design |
| Optimizer | ask/tell pattern search | same policy |
| Initial energy | 0.1916484375 | 0.2069205078 |
| Best observed energy | -0.4189324219 | -0.4398875000 |
| Best iteration | 28 | 40 |
| Final energy | -0.3775728516 | -0.4398074219 |
| Online/replay verdicts | PASS / PASS | PASS / PASS |
| Terminal reason | max iterations | max iterations |

The best-energy difference is `0.020955078125` in the model's energy units.
Because both objectives are sampled and each result controls the next ask/tell
decision, the optimizer trajectories need not evaluate the same parameter
vectors after they diverge. The difference should therefore be reported as a
descriptive comparison of these runs, not an estimate of backend bias at one
fixed vector.

## Acceptance matrix

| Requirement | Evidence | Result |
|---|---|---|
| Each term has exactly 1,024 outcomes | all 200 sidecar records | PASS |
| Every count dictionary sums to 1,024 | independent offline recomputation | PASS |
| Packed data, ordered shots, counts, and hashes agree | strict sidecar loader and manifest | PASS |
| Expectations reconstruct from negative parity | all 200 PUB records | PASS |
| Energies reconstruct from four expectations | all 50 checkpoints | PASS |
| Shot total does not exceed 204,800 | sealed manifest total 204,800 | PASS |
| Online and replay verdicts agree | both reports pass all three levels | PASS |
| Ask/tell authorizes before mutation | 49 ordered intent/commit/bind chains | PASS |
| Backend job identities are fresh | 50 unique IBM job IDs | PASS |
| Layout is fixed across PUBs | all hardware records use `[6,7]` | PASS |
| Terminal reason is truthful | 50th non-converged checkpoint then cap | PASS |

The separate preflight adds 4,096 shots, making the observed campaign total
208,896. It is not counted against the primary run's declared 204,800 ceiling.

## Monitor overhead and scaling

The executable harness uses five warm-ups and 30 measured repetitions for the
primary comparison, plus a size sweep with raw latency and memory samples.

| Evaluations | Events | End-to-end | All-gate p95 | `nextConvergenceChecked` p95 | JVM peak RSS |
|---:|---:|---:|---:|---:|---:|
| 10 | 423 | 0.537 s | 1.214 ms | 1.332 ms | 219.03 MiB |
| 25 | 1,053 | 0.819 s | 1.063 ms | 1.237 ms | 273.66 MiB |
| 50 | 2,103 | 1.210 s | 0.984 ms | 1.305 ms | 439.80 MiB |
| 100 | 4,203 | 2.081 s | 0.970 ms | 1.532 ms | 635.36 MiB |
| 125 | 5,253 | 2.929 s | 1.438 ms | 2.307 ms | 718.81 MiB |
| 150 | 6,303 | 6.436 s | 3.722 ms | 4.373 ms | 839.92 MiB |
| 175 | 7,353 | 12.486 s | 7.742 ms | 7.606 ms | 847.94 MiB |
| 200 | 8,403 | 29.971 s | 16.362 ms | 16.222 ms | 941.80 MiB |

The monitor does not have constant cost over unbounded history. Growth becomes
material beyond roughly 125 evaluations. At the fixed 50-evaluation campaign
bound, however, p95 acknowledgement latency remained about 1 ms and far below
the 30-second hardware monitor timeout.

The implementation therefore retains `nextConvergenceChecked` for this
submission. Removing or projecting fields out of that relation would weaken a
useful predecessor and energy-continuity check without helping the bounded
campaign. A future profile above roughly 100 evaluations should replace the
wide temporal tuple with a compact hash-bound checkpoint certificate, retain
exact numeric and patience validation in Python, rerun differential mutants,
rebuild the monitor, and benchmark through at least 400 evaluations before the
new bound is accepted.

## Response to the external review

| Review concern | Resolution |
|---|---|
| No executable overhead harness or raw results | `tools/benchmark_overhead.py` plus raw run, gate, and memory CSVs and `BENCHMARK_REPORT.md` |
| No statevector or hardware evidence | complete count-backed statevector and IBM SamplerV2 traces, sidecars, and reports |
| Monitor cannot be rebuilt practically | pinned Scala 2.12.21 dependencies, verified fetcher, deterministic builder, and byte-identical rebuild test |
| Stock old Python fails unclearly | explicit Python 3.11+ import guard |
| Online tests use only a shadow monitor | real DejaVu rejection test proves the online session aborts on a monitor violation |
| Level attribution relies on string prefixes | explicit audited property-level registry and coverage tests |
| Demo appears to demonstrate convergence | README labels it a deterministic lifecycle fixture rather than an optimizing VQE result |
| `nextConvergenceChecked` scales poorly | measured bound disclosed; retained for 50; checkpoint redesign planned for larger profiles |

The reviewer also observed that Python and DejaVu kill different mutants. That
two-way asymmetry remains central: Python checks numeric/raw-data facts that the
monitor represents by certificates, while DejaVu checks temporal uniqueness
and causal ordering that the Python arithmetic engine alone can miss.

## Remaining limitations and potential failure modes

1. **Single hardware campaign.** Statistical conclusions require repeated runs
   and a declared analysis plan.
2. **Raw, unmitigated data.** Auditability is strong, while physical accuracy is
   limited by device and readout error.
3. **Hardware trust boundary.** The archive proves consistency of returned data,
   not the truth of IBM's physical execution.
4. **Ansatz and optimizer limits.** A four-parameter `EfficientSU2` circuit and
   bounded pattern search do not guarantee the model ground state.
5. **Dynamic backend state.** Calibration and queue conditions change; a new
   run may choose a different physical layout and produce different counts.
6. **QPY byte identity.** The runner now hashes each captured serialization once.
   A future Qiskit upgrade should rerun the provenance tests.
7. **Bounded temporal monitor.** The 50-evaluation result does not justify an
   unbounded scaling claim.
8. **Credential hygiene.** IBM tokens must stay outside artifacts and logs and
   should be rotated if ever exposed.

## Durable artifact index

| Artifact | Path |
|---|---|
| Hardware trace | `artifacts/traces/h2_ibm_marrakesh_sampler_20260907.jsonl` |
| Hardware raw evidence | `artifacts/evidence/h2_ibm_marrakesh_sampler_20260907.jsonl` |
| Hardware online report | `artifacts/reports/h2_ibm_marrakesh_sampler_20260907_online.json` |
| Hardware replay report | `artifacts/reports/h2_ibm_marrakesh_sampler_20260907_replay.json` |
| Statevector trace | `artifacts/traces/h2_statevector_sampler_20260907.jsonl` |
| Statevector raw evidence | `artifacts/evidence/h2_statevector_sampler_20260907.jsonl` |
| Comparison summary | `artifacts/results/h2_sampler_comparison_20260907/campaign_summary.json` |
| Evaluation CSVs | `artifacts/results/h2_sampler_comparison_20260907/*_evaluations.csv` |
| Per-PUB CSVs | `artifacts/results/h2_sampler_comparison_20260907/*_pubs.csv` |
| IBM job metadata | `artifacts/results/h2_sampler_comparison_20260907/hardware_jobs.json` |
| Exact environment and hashes | `artifacts/environments/h2_sampler_campaign_20260907.json` |
| Local validation | `artifacts/validation/h2_sampler_local_validation_20260907.json` |
| Scaling report | `artifacts/benchmarks/BENCHMARK_REPORT.md` |
| Full reproduction guide | `docs/H2_SAMPLER_REPRODUCIBILITY.md` |
| Presentation deck | `artifacts/presentation/H2_SamplerV2_Verified_Experiment_20260908_v2.pptx` |
| Overleaf runtime-verification section | `docs/RUNTIME_VERIFICATION_OVERLEAF_SECTION.tex` |
