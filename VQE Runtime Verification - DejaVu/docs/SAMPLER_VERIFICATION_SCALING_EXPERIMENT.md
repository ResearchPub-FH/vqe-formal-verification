# Simulator VQE verification-scaling experiment

## Purpose

This experiment measures the execution-time cost of adding the implemented runtime-verification layer to the sampled H₂ VQE process. It compares direct execution times for the baseline process and the verified process at 10, 20, 30, 40, and 50 completed objective evaluations. It also checks whether adding verification changes sampled measurement fidelity, the energy trajectory, or the evaluation at which the convergence condition first becomes stable.

The experiment is restricted to `StatevectorSampler`. It does not make a hardware-performance or hardware-fidelity claim.

## Conditions and timing boundary

The **baseline** condition includes circuit construction, sampler construction, four independent PUBs per evaluation, parity-based expectation reconstruction, energy aggregation, the convergence calculation, and the same ask/tell optimizer used by the verified condition.

The **verified** condition performs the same work and adds `RuntimeSession`, synchronous DejaVu acknowledgements, numeric contract checks, identity-preserving trace events, raw-evidence persistence, and optimizer authorization. Monitor startup and finalization are included because they are part of using the verification layer for a concrete run.

The primary response variable is wall-clock time from setup through run finalization. Fidelity analysis and offline replay run afterward and are excluded from both timing measurements. Baseline evidence is materialized after its timing boundary so evidence collection does not turn the baseline into a second verification implementation. The verified condition writes evidence during execution because evidence association is part of the layer being measured.

Runs are independently summarized within each condition. The report gives the median and p95 for each condition and the direct difference between condition medians. It does not compute a paired estimator.

## Fixed configuration

| Setting | Value | Reason or interpretation |
|---|---:|---|
| Execution mode | `qiskit-statevector-sampler` | Simulator-only scope |
| Backend | `StatevectorSampler` | Exact state preparation followed by finite-shot sampling |
| System | H₂ | Same Hamiltonian and ansatz as the runtime campaign |
| Evaluation counts | 10, 20, 30, 40, 50 | Declared scaling points |
| PUBs per evaluation | 4 | One independent PUB per Hamiltonian term |
| Shots per PUB | 1,024 | 4,096 observed shots per evaluation |
| Optimizer | ask/tell pattern search | Preserves the monitored mutation boundary |
| Initialization | seeded uniform | Seed 7 |
| Convergence tolerance | 0.005 | Runtime-campaign tolerance |
| Convergence patience | 3 | Consecutive within-tolerance transitions |
| Warm-ups | 5 per condition and count | Executed before all measured runs |
| Measured repetitions | 30 per condition and count | Supports condition-level timing distributions |
| Schedule | randomized within warm-up and measured phases | Reduces ordering drift while keeping warm-ups first |
| Monitor encoding | 24 bits per variable | Existing runtime configuration |
| Monitor timeout | 10 s per acknowledgement | Existing runtime configuration |

For a scaling point of \(N\), `max_iterations` and `min_iterations` are both set to \(N\), and the shot budget is set to \(4\times1024\times N\). This forces an equal amount of sampled VQE work in both conditions. The first stable convergence evaluation is still recorded independently of this forced bound by finding the first evaluation at which the tolerance condition has held for the configured patience.

The same sampler seed and optimizer initialization are used in both conditions. Under the deterministic simulator setup, their sampled outcomes and energy trajectories should agree exactly. This is a controlled test for verification-induced behavior changes; it is not an estimate over independent quantum noise realizations.

## Fidelity definition

For each executed PUB, the bound measurement circuit is stripped of its final measurements and evaluated as an exact statevector. If \(p_e(x)\) is its ideal outcome probability and \(p_s(x)\) is the normalized sampled count distribution, the reported PUB fidelity is

\[
F_{\mathrm{PUB}}=\left(\sum_x\sqrt{p_e(x)p_s(x)}\right)^2.
\]

This is the classical fidelity between the ideal and measured outcome distributions for the circuit that was actually sampled. The four PUB fidelities are averaged to obtain one value per objective evaluation. The experiment reports both the run mean infidelity,

\[
\overline{\epsilon}=\frac{1}{N}\sum_{i=1}^{N}(1-F_i),
\]

and the cumulative infidelity,

\[
E_N=\sum_{i=1}^{N}(1-F_i).
\]

The first quantity makes runs with different evaluation bounds comparable; the second exposes accumulated finite-shot error. Because the four measurement bases are not informationally complete tomography, this quantity must be described as **measurement-distribution fidelity**, not full density-matrix or quantum-state fidelity.

Verification-induced fidelity impact is the verified-condition median mean infidelity minus the baseline-condition median at the same evaluation count. Final-energy differences and the first stable convergence evaluation provide two additional behavior checks.

## Retained records

Every warm-up and measured run has its own directory. The campaign retains:

- the resolved configuration and environment/package versions;
- the randomized execution schedule;
- the verified event trace, raw PUB evidence, online report, and replay report;
- a baseline process trace and raw PUB evidence generated after timing;
- evaluation identities, parameter vectors and digests, energies, deltas, stability state, and optimizer successors;
- per-PUB ideal probabilities, sampled counts, fidelity, and evidence digest;
- setup, sampling, result-processing, convergence-check, optimizer, finalization, and total times;
- every verified event-acknowledgement latency;
- low-interference Python and DejaVu child-process peak-memory snapshots; and
- aggregate CSV, JSON, Markdown, and SVG outputs.

These records permit later analysis without rerunning the simulator, including per-event monitor cost, trace growth, evidence size, energy trajectories, shot accounting, and alternative summary statistics.

## Outputs

The primary figure is `timing_comparison.svg`, a single panel with median execution time versus evaluation count for baseline and verified executions. The figure is supported by `runs.csv`; it does not include a memory panel.

`REPORT.md` contains the timing table, convergence-check latency, mean and cumulative infidelity, the direct fidelity-impact estimate, and the first stable convergence evaluation. `summary.json` contains the same statistics in machine-readable form. Raw aggregate tables are `evaluations.csv`, `pub_fidelity.csv`, `gate_latencies.csv`, and `memory_samples.csv`.

## Running the campaign

From the repository root, in an environment installed with the `qiskit` optional dependencies:

```bash
python tools/benchmark_sampler_verification_scaling.py \
  --config configs/h2_statevector.toml \
  --out-dir artifacts/sampler_verification_scaling
```

A short validation run may use a separate empty output directory:

```bash
python tools/benchmark_sampler_verification_scaling.py \
  --config configs/h2_statevector.toml \
  --out-dir artifacts/sampler_verification_scaling_smoke \
  --scales 10 \
  --warmups 0 \
  --repetitions 1
```

## Interpretation boundaries

- The result measures this H₂ ansatz, four-term independent-PUB workload, host, Python/JVM runtime, Qiskit version, and DejaVu encoding.
- Simulator sampling time is local and excludes hardware queue, network, calibration, and device execution variability.
- The verified time includes synchronous waiting and archive writes. Offline replay and fidelity computation are separately reported and excluded from the primary time.
- The fidelity result measures finite-shot distribution error. It does not characterize a physical device or reconstruct an arbitrary quantum state.
- Equal behavior across conditions establishes that the instrumentation did not alter this deterministic sampled execution. It does not prove noninterference for every controller or optimizer.
- The convergence diagnostic distinguishes evaluation-count behavior from wall-clock delay. Forcing exactly \(N\) evaluations is necessary for the scaling comparison, so the terminal reason alone is not a convergence-performance measure.
- Sequential controller execution, faithful use of the instrumented interface, a responsive monitor, and sufficient storage remain assumptions.

## Tuning later

The command-line arguments expose evaluation counts, warm-ups, repetitions, and the schedule seed. Other scientific settings remain in the TOML configuration. If shots, PUB grouping, ansatz depth, monitor bit width, or durability policy changes, use a new output directory and treat the run as a distinct experiment. Preserve the environment manifest and raw per-run directories when comparing campaigns.
