# Figure manifest for review3

Paths are relative to this folder. The parent `../FIGURE_MANIFEST.md` retains full experimental provenance. This manifest records the assets used by the revised main and the changes in this round.

Only the architecture PDF is regenerated. All four quantitative PDFs retain their previous hashes and data. The common numerical audit validates every plotted point against the recorded experimental sources.

Configuration digest: `03b387a2e7fede7a78b71b5a25065f673af10bbb9193103dd9895866d10706be`.
Pre-execution record digest: `b3de315ae48c909ca80e275fafde44deb567ec68cad3b0de366e93a93c53c3ca`.

## Figure 1 — `fig:architecture`

- PDF: `figures/architecture.pdf`
- Editable source/script: `../figures/architecture.tex`
- Generation: scripts/build_revision.py (Tectonic/TikZ)
- Intended width: double column, 94% of text width; section II-A.
- Scientific purpose: Show the four aspects and two stages with separate per-run checks and empirical probabilistic comparison.
- Transformation: None; vector architecture diagram.
- Intervals: None; diagram, deterministic counts, or categorical outcomes as described.
- Revision: Library label obligations changed to requirements; all other relationships unchanged.
- PDF SHA-256: `11c68784222acb6448f462825470a3f9f5a8c82ab080f3ccf03de7b0786abff0`
- Processed/raw/configuration inputs:
  - `../../config/contracts.json`
  - `../../closed_loop/pre_execution.py`
  - `../../closed_loop/execution.py`
  - `../../closed_loop/checker.py`
  - `../../closed_loop/comparison.py`
  - `../../artifacts/approved-experiment/stage1/pre_execution.json`

## Figure 2 — `fig:storm-scalability`

- PDF: `../figures/storm-scalability.pdf`
- Editable source/script: `../scripts/figures/storm_scalability.py`
- Generation: Shared existing script and PDF; not regenerated in review3.
- Intended width: single column; section IV-C.
- Scientific purpose: Show time-unrolled Gaussian model counts and construction/checking cost.
- Transformation: Deterministic state/transition counts; one construction observation and median of three recorded checking times.
- Intervals: None; diagram, deterministic counts, or categorical outcomes as described.
- Revision: Caption shortened; blue/orange lines and all data unchanged.
- PDF SHA-256: `c6e89c7513dcaf99984644948543c217c97a26decb27a593e535961ec81f0090`
- Processed/raw/configuration inputs:
  - `../data/scalability_figure_points.csv`
  - `../data/derived_results.json`
  - `../../../Probabilistic verification - 2 methods comparision/artifacts/h2_vqe/additional_experiments/model_checking_scalability/scalability_results.csv`
  - `../../../Probabilistic verification - 2 methods comparision/artifacts/h2_vqe/additional_experiments/model_checking_scalability/metadata.json`

## Figure 3 — `fig:runtime-overhead`

- PDF: `../figures/runtime-overhead.pdf`
- Editable source/script: `../scripts/figures/runtime_overhead.py`
- Generation: Shared existing script and PDF; not regenerated in review3.
- Intended width: single column; section IV-D.
- Scientific purpose: Show condition medians and added median time on the fixed sampled workload.
- Transformation: Independent condition medians and their difference. Raw per-run summaries and configuration remain indexed by the common source manifest.
- Intervals: 95% percentile bootstrap, 10,000 independent-condition resamples; 30 measured repetitions after five warm-ups per condition/count.
- Revision: Caption shortened; plot and data unchanged.
- PDF SHA-256: `c5743f0f9db15e4acc92e2231c581ef6ca8071870b8170640278854f8ed525e8`
- Processed/raw/configuration inputs:
  - `../data/runtime_figure_points.csv`
  - `../data/derived_results.json`
  - `../../../VQE Runtime Verification - DejaVu/artifacts/sampler_verification_scaling_restart02_20260930/runs.csv`
  - `../../../VQE Runtime Verification - DejaVu/artifacts/sampler_verification_scaling_restart02_20260930/summary.json`

## Figure 4 — `fig:probability-comparison`

- PDF: `../figures/probability-comparison.pdf`
- Editable source/script: `../scripts/figures/probability_comparison.py`
- Generation: Shared existing script and PDF; not regenerated in review3.
- Intended width: single column; section V-C.
- Scientific purpose: Compare the same ideal-energy bounded-success predicate under the Gaussian model and finite-shot execution.
- Transformation: Gaussian forward-propagation CDF and recorded Storm checkpoints; empirical cumulative first-success frequency across all runs, without interpolation.
- Intervals: Pointwise 95% Wilson intervals; no simultaneous-band claim.
- Revision: Caption shortened; green/magenta lines, configuration and all points unchanged.
- PDF SHA-256: `32395ef6ab5fb0812837bfabb6b21f2f030bcf9e9db6d3527b5668162c75000a`
- Processed/raw/configuration inputs:
  - `../data/probability_figure_points.csv`
  - `../data/derived_results.json`
  - `../../artifacts/approved-experiment/stage1/quantitative.json`
  - `../../artifacts/approved-experiment/stage1/gaussian-kernels.npz`
  - `../../artifacts/approved-experiment/stage1/storm.log`
  - `../../artifacts/approved-experiment/stage1/configuration.json`
  - `../../artifacts/approved-experiment/stage2/baseline/results.json`
  - `../../artifacts/approved-experiment/stage2/baseline/baseline-*.jsonl.gz`

## Figure 5 — `fig:fault-discrepancies`

- PDF: `../figures/fault-discrepancies.pdf`
- Editable source/script: `../scripts/figures/fault_discrepancies.py`
- Generation: Shared existing script and PDF; not regenerated in review3.
- Intended width: double column; section V-D.
- Scientific purpose: Show the complete logical/numeric verdict vector and exact test counts for each fault class.
- Transformation: Identical per-class verdict vectors grouped into categorical rows; exact target-result and DejaVu acceptance counts.
- Intervals: None; diagram, deterministic counts, or categorical outcomes as described.
- Revision: Caption shortened; all classifications, counts and caveats preserved.
- PDF SHA-256: `dd348510a6a1999750ce661915d475a8b68aff18f9a5c10d89f4595a6b766e27`
- Processed/raw/configuration inputs:
  - `../data/fault_figure_points.csv`
  - `../data/derived_results.json`
  - `../../config/contracts.json`
  - `../../artifacts/approved-experiment/stage2/faults/results.json`
  - `../../artifacts/approved-experiment/stage2/faults/*.jsonl.gz`

## Table provenance

The new Table V is generated by `scripts/generate_tables.py` from `../data/derived_results.json`. This file is already reconstructed from the raw Gaussian kernels, Storm results and first-success records. `data/table_traceability.json` preserves each input row, run/configuration identifiers, formatted cells and the source checksum. The script applies formatting only; it does not calculate new estimates or intervals.

Table IV preserves all counts and scope descriptions from the existing table and changes only the L4 display label, checked against the raw AGREEMENT result. The local validator parses both revised tables independently.

The shared raw source manifest and its hashes remain unchanged. The documented runtime-directory relocation is resolved by the existing alias and verified against the same recorded checksums.
