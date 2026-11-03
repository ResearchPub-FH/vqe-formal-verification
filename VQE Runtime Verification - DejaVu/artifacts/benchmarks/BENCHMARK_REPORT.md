# Executable monitor overhead and scaling report

## Outcome

The required benchmark harness is `tools/benchmark_overhead.py`. The primary
run used five warm-ups and 30 measured repetitions for each condition, followed
by one measured scaling run at each declared size. All individual runs, gate
round trips, and memory samples are retained as CSV rather than only as summary
statistics.

Primary raw evidence:

- `h2_monitor_baseline_20260906/runs.csv`
- `h2_monitor_baseline_20260906/gate_latencies.csv`
- `h2_monitor_baseline_20260906/memory_samples.csv`
- `h2_monitor_baseline_20260906/summary.json`
- `h2_monitor_baseline_20260906/environment.json`

An independent pilot with repeated energy identities is retained under
`h2_monitor_pilot_repeated_energy_20260906/`. It shows the same qualitative
late-run growth and prevents the scaling claim from resting on one energy
sequence.

## Primary three-evaluation results

| Condition | End-to-end p50 | End-to-end p95 | Peak combined RSS p50 |
|---|---:|---:|---:|
| Generated DejaVu monitor | 358.260 ms | 375.798 ms | 239.69 MiB |
| Python shadow monitor | 7.185 ms | 7.505 ms | 38.02 MiB |
| Uninstrumented synthetic loop | 0.040 ms | 0.050 ms | 38.01 MiB |

For the generated monitor, startup p50 was 228.539 ms. Across 3,810
acknowledged events, synchronous gate latency was 0.505 ms p50 and 1.722 ms
p95. The relative percentages in `summary.json` are arithmetically correct but
should not be generalized to a hardware VQE: the uninstrumented comparator is
an intentionally tiny in-memory loop, so fixed JVM startup dominates it.
Hardware queue and execution time were deliberately excluded.

## Scaling results and the 50-evaluation bound

| Evaluations | Events | End-to-end | All-gate p95 | `nextConvergenceChecked` p95 | JVM peak RSS |
|---:|---:|---:|---:|---:|---:|
| 10 | 423 | 0.537 s | 1.214 ms | 1.332 ms | 219.03 MiB |
| 25 | 1,053 | 0.819 s | 1.063 ms | 1.237 ms | 273.66 MiB |
| 50 | 2,103 | 1.210 s | 0.984 ms | 1.305 ms | 439.80 MiB |
| 60 | 2,523 | 1.350 s | 0.929 ms | 1.669 ms | 481.05 MiB |
| 100 | 4,203 | 2.081 s | 0.970 ms | 1.532 ms | 635.36 MiB |
| 125 | 5,253 | 2.929 s | 1.438 ms | 2.307 ms | 718.81 MiB |
| 150 | 6,303 | 6.436 s | 3.722 ms | 4.373 ms | 839.92 MiB |
| 175 | 7,353 | 12.486 s | 7.742 ms | 7.606 ms | 847.94 MiB |
| 200 | 8,403 | 29.971 s | 16.362 ms | 16.222 ms | 941.80 MiB |

The monitor is not constant-cost over unbounded histories. Latency growth is
visible beyond roughly 125 evaluations and memory grows throughout the sweep.
At the primary experiment's hard ceiling of 50 evaluations, however, the
observed all-gate p95 remained below 1 ms and the convergence-event p95 was
1.305 ms. This is several orders of magnitude below the hardware profile's
30-second acknowledgement timeout.

## Decision on `nextConvergenceChecked`

The current relation is retained for this submission. It binds the current
evaluation, energy and parameter identities to the immediately previous
evaluation and energy identity. Projecting fields out only to reduce BDD state
would weaken a useful continuity claim, while the fixed 50-evaluation campaign
stays below the measured latency knee. The defensible engineering response is
therefore to enforce and disclose the bound, not to claim unbounded scaling.

Before any profile is raised materially above 100 evaluations, the planned fix
is:

1. Replace the wide temporal tuple with a compact, hash-bound checkpoint
   certificate issued by the Python numeric verifier.
2. Keep exact energy-delta, patience, theta, and predecessor validation in the
   Python checker; let QTL relate only the checkpoint identity and causal
   ordering.
3. Add differential mutation tests proving the redesigned split rejects every
   stale-predecessor, stale-energy, false-convergence, and reordered-check
   mutant rejected today.
4. Rebuild the generated monitor and rerun the five-warm-up/30-repetition
   benchmark plus scaling sweeps through at least 400 evaluations.
5. Accept the redesign only if assurance is unchanged and both p95 latency and
   resident memory remain bounded enough for the newly declared profile.

This plan treats a higher bound as a new verification design, not as an
unreviewed performance patch to the experiment reported here.
