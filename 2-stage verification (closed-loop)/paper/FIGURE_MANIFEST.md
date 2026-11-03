# Figure manifest

All paths below are relative to `paper/` unless they start with `../../`.
Measured plotting values are read by each script from the artifact paths. The
scripts export every plotted estimate and interval endpoint as CSV in `data/`.
The full input SHA-256 list is `data/source_manifest.json`; the paper validation
script checks plotted points against independent reconstruction.

## Figure 1 — `figures/architecture.pdf`

- Editable vector source: `figures/architecture.tex` (standalone TikZ).
- Generation: a LaTeX engine with TikZ; build instructions in `README.md`.
- Inputs: `../config/contracts.json`, `../closed_loop/{pre_execution,execution,checker,comparison,temporal}.py`,
  `../formal/runtime.qtl`, `../artifacts/approved-experiment/stage1/pre_execution.json`.
- Configuration/run: `approved-experiment` (identifiers below).
- Quantities: architectural relationships and actual verdict categories; no
  measured quantitative points and no statistical transformation.
- Width: double column (94% of text width in the manuscript).
- Caveat: the contract mappings are implementation links, not formal equivalences.

## Figure 2 — `figures/storm-scalability.pdf`

- Script: `scripts/figures/storm_scalability.py`; typography: `style.py`.
- Processed input: `../../Probabilistic verification - 2 methods comparision/artifacts/h2_vqe/additional_experiments/model_checking_scalability/scalability_results.csv`.
- Raw detail/configuration: adjacent `metadata.json` (active states at each depth,
  per-invocation checking times, grid, shots, bounds, tool version).
- Model source: `../../Probabilistic verification - 2 methods comparision/model_checking_scalability.py`,
  with kernel/circuit configuration in `h2_prism_fakebackend_workflow.py`.
- Run: retained `h2_vqe/additional_experiments/model_checking_scalability` study.
- Quantities: reachable state/transition counts, one construction time, and the
  median of three recorded Storm checking times against the iteration bound.
- Transformation: logarithmic count axis in the top panel, linear time axis
  in the bottom panel. Actual integer counts are used as ticks.
- Intervals: none. Model sizes are deterministic; construction has one
  measurement and checking shows the archived median of three tool timings.
- Exported plotted values: `data/scalability_figure_points.csv`.
- Width: single column, 3.5 in; two vertically aligned panels.
- Limitation: explicit scalability model files were not retained. State counts are
  checked against depth metadata including success/timeout absorbing states;
  transitions are sourced from the archived CSV. This is not the fixed-size
  homogeneous final DTMC, and it does not imply growth with quantum-state dimension.

## Figure 3 — `figures/runtime-overhead.pdf`

- Script: `scripts/figures/runtime_overhead.py`; typography: `style.py`.
- Processed index: `../../VQE Runtime Verification - DejaVu copy/artifacts/sampler_verification_scaling_restart02_20260930/runs.csv`.
- Raw measurements: the same directory's `runs/{measured,warmup}/{baseline,verified}/n*/r*/run_summary.json`.
- Configuration: adjacent `summary.json` (configuration, timing boundary,
  repetitions, schedule seed) and `completion_audit.json`.
- Run: completed `sampler_verification_scaling_restart02_20260930`; excluded
  restart01 and interrupted study directories are never pooled.
- Quantities: median total runtime, by condition and evaluation count; difference
  of verified and baseline medians.
- Transformation: independent condition summaries, not a paired estimator.
- Intervals: 95% percentile bootstrap, 10,000 resamples, analysis seed 20261006.
  Independently resample the 30 measured times in each condition/count; subtract
  bootstrap medians for the added-time interval. Five warm-ups per cell excluded.
- Statistical unit: repeated timing observations for a fixed seeded workload,
  not independent optimization trajectories.
- Exported plotted values: `data/runtime_figure_points.csv`.
- Width: single column, 3.5 in; two vertically aligned panels.
- Limitation: this earlier ask/tell runtime implementation is separately configured.
  It does not measure overhead of the final matched experiment. Timing includes
  setup, synchronous checking and verified evidence persistence, and finalization.
  Baseline post-run serialization, fidelity analysis, and offline replay are excluded.

## Figure 4 — `figures/probability-comparison.pdf`

- Script: `scripts/figures/probability_comparison.py`; typography: `style.py`.
- Processed model: `../artifacts/approved-experiment/stage1/quantitative.json`.
- Raw prospective evidence: `stage1/gaussian-kernels.npz`, `gaussian.tra`,
  `gaussian.lab`, `gaussian.props`, and `storm.log` in the same final run.
- Raw empirical evidence: `stage2/baseline/baseline-*.jsonl.gz`; first-success
  iteration derived from each raw terminal. Trace hashes from `stage2/baseline/results.json`.
- Configuration: final `stage1/configuration.json` and sealed `pre_execution.json`.
- Run/configuration identifier: `approved-experiment`;
  configuration SHA-256 `03b387a2e7fede7a78b71b5a25065f673af10bbb9193103dd9895866d10706be`;
  pre-execution record SHA-256 `b3de315ae48c909ca80e275fafde44deb567ec68cad3b0de366e93a93c53c3ca`.
- Quantities: discrete-iteration cumulative success probability for the identical
  ideal-energy predicate in Gaussian and finite-shot processes.
- Transformation: cumulative first-success frequencies over all 400 executions,
  including budget stops in the denominator; exact retained CDF, no interpolation.
- Intervals: pointwise 95% Wilson score intervals using the normal 0.975 quantile.
  The shaded region is not a simultaneous confidence band.
- Exported plotted values: `data/probability_figure_points.csv`.
- Width: single column, 3.5 in.
- Distinction: the full curve is Python propagation of the Gaussian kernel,
  independently checked by Storm at declared checkpoints. No noisy execution
  curve and no absent audit Monte Carlo arrays are used.

## Figure 5 — `figures/fault-discrepancies.pdf`

- Script: `scripts/figures/fault_discrepancies.py`; typography: `style.py`.
- Direct input: `../artifacts/merged-model-01/stage2/faults/results.json`, the
  delivered run (fault vectors use obligation counting, so unexercised
  obligations are INCONCLUSIVE).
- Raw sources: the same run's linked `stage2/faults/*.jsonl.gz` traces;
  `comparison/verdict_agreement.json` (`result_files.faults`) supplies the
  fault-result checksum, since this run has no `completion_audit.json`. Trace
  checksums are read from the individual records and verified before plotting.
- Configuration: `../config/contracts.json` supplies the logical/numeric IDs
  and families. `stage1/pre_execution.json` supplies the configuration digest,
  checked against the fault results. The configuration digest equals Figure 4's;
  the run is `merged-model-01`, not `approved-experiment`.
- Quantities: complete verdict vectors for each fault class, number of records
  with the expected target-obligation result, and DejaVu acceptance counts.
- Transformation: group individual records by fault. Every repetition must
  have the same complete vector to be represented by one categorical row.
  Counts are sums of individual Boolean outcomes. No estimates or interpolation.
- Categories: agreement, disagreement, assumption mismatch, and inconclusive.
  Color is nominal. Each cell also contains its verdict letter for grayscale.
- Intervals: none. These are categorical results and exact counts in a fixed
  fault-injection suite, rather than estimates of population detection rates.
- Exported cells/counts: `data/fault_figure_points.csv`. Validation checks all
  cells and counts against fault results reconstructed independently from
  `merged-model-01`'s raw fault records.
- Width: single column, 3.5 in; fault names wrap onto two lines and the legend
  uses two rows. Replaces the main-paper fault table.
- Scope: the saved-trace missing-count scenario retains the existing L1
  classification limitation. The figure is not a pre-execution detection matrix
  or a claim of detection for untested faults. The ancillary fault table remains.

## Numeric text and figure consistency

`scripts/extract_results.py` reconstructs the full model CDF from the raw kernel,
every baseline estimator from group counts, all used optimizer values, final
successes and resources, proof-log counts, and timing summaries. It writes
`data/derived_results.json`, `data/claim_values.json`, `data/numbers.tex`, and
`tables/*.tex`. `scripts/validate_paper.py` checks the figure CSVs, every generated
table, macros, references, captions' declared configurations, and source hashes.
The correction of P2/P3 is an analysis-layer reporting correction; final raw
artifacts and original marginal intervals remain unchanged.

## Review round 1

The revised main source is `manuscript_review1.tex`, using this same set of
figures. No numerical prediction, estimate, interval, or recorded timing is changed.
The scalability CSV now additionally exports `construction_seconds` and
`checking_median_seconds` from the same source CSV, and validation checks those
points against the reconstructed results. Architecture labels and iteration
axes are revised in place. The source inputs remain hash-checked, and all four
PDFs retain vector text.

## Figure-style follow-up

The new integration source is `manuscript_review2.tex`. Review 1's main source
and PDF remain unchanged. Existing figure filenames are preserved. Figure 4's
model/empirical curves use green `#009B63` and magenta `#D60078`; Figure 2 uses
blue `#005BFF` and orange `#F26700`. The line widths are 1.35 pt. Styles, markers,
neutral Wilson shading, all plotted values, and statistical calculations are
unchanged. Figure 5 adds the fault matrix described above. Its cells retain
letter labels and exact counts, with colors representing unordered categories.

Runtime-source location note: the historical `../../VQE Runtime Verification -
DejaVu copy/` paths above now resolve to `../../VQE Runtime Verification - DejaVu/`.
Every relocated file is checked against its original manifest checksum. The
manifest is unchanged, and `data/source_location_resolution.json` records the
verified physical locations. This alias does not select a different timing study.
