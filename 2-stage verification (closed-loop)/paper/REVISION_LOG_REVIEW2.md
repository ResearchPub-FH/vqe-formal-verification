# Requested figure follow-up (review round 2)

The author requested different, more saturated line colors for the probability
comparison and Storm scalability figures, and conversion of any remaining table
that would communicate better as a figure. This is the explicitly requested
follow-up to completed review round 1, rather than an automatic revision round.

Reference: `manuscript_review1.tex` and its PDF, both preserved unchanged.
Revised integration: `manuscript_review2.tex`. The initial byte-identical copy
compiled before editing. Only Section V-D's content changes in the new main source.
The bibliography column break is adjusted for the resulting float placement.
Bibliography, figures, scripts, tables, and experimental artifacts remain shared.

## Request 1 — distinct, more saturated line colors

Status: **ADDRESSED**

Files: `scripts/figures/probability_comparison.py`,
`scripts/figures/storm_scalability.py`, and their existing figure PDFs.

Change: The probability figure uses green (`#009B63`) for the Gaussian model and
Storm checkpoints, and magenta (`#D60078`) for empirical finite-shot executions.
The scalability figure uses vivid blue (`#005BFF`) and orange (`#F26700`).
Line widths increase to 1.35 pt for legibility at single-column size. Solid and
dashed lines, distinct markers, neutral confidence shading, axes, and legend
meanings are preserved. Neither point data nor statistical transformations change.
The other existing figures retain their colors.

## Request 2 — reassess the remaining tables

Status: **ADDRESSED**

Files: `scripts/figures/fault_discrepancies.py`,
`figures/fault-discrepancies.pdf`, `manuscript_review2.tex` Section V-D,
figure/result manifests, and common build/validation scripts.

Change: Converted the fault-results table to Figure 5, a double-column categorical
matrix. Grouped logical and numeric columns expose the patterns of complementary
detection, assumption mismatch, and unavailable checks. Every original verdict
letter and both detection-count columns remain visible. Nominal colors accompany
letters, so the matrix is interpretable in grayscale and does not imply a numeric
scale. The caption preserves the missing-count L1 classification limitation.

The script reads individual audited fault records, verifies result and trace
hashes, and requires all repetitions within a scenario to have the same full
vector before showing one row. It computes counts from individual records and
exports every plotted cell/count to `data/fault_figure_points.csv`. The numerical
validator checks this export against the independent reconstruction. The original
`tables/faults.tex` is preserved under its existing filename for exact reuse.

### Disposition of the other six tables

| Retained table | Reason |
|---|---|
| Specification mapping | Exact obligations, assumptions, and prospective/runtime scopes require aligned textual comparison. The architecture already supplies the workflow figure. |
| Configuration | Exact reproducibility parameters are clearer in a compact table. |
| Hardware results | Two observed runs have identical totals and statuses. A chart adds no trend or scientifically useful contrast. |
| Logical/numeric agreement | Every baseline count agrees. The meaningful differences are the stated prospective scopes, which need text. A success-rate chart would obscure those qualifications. |
| P1 checkpoints | The probability trend already has a figure. Exact counts, Wilson bounds, deviations, and Holm values complement that curve. |
| P2/P3 resources | The quantities use different units and are deterministically linked by fixed shots per iteration. Exact intervals and the statistical interpretation are best retained together. |

The revised main paper has five figures and six tables. No other table is
converted solely to reduce the count.

## Reproducibility and preservation

- Existing figure filenames are regenerated in place. No bibliography, figure,
  script, configuration, or separate table has a review-numbered duplicate.
- Common build and validation scripts include the new matrix. Revision validation
  supports the existing sequence of main sources and protects preceding versions.
- Adjusted the IEEE bibliography column break to balance the final page after
  the table-to-figure conversion. Citation content and ordering are unchanged.
- The source/PDF of review 1, the original source/PDF, bibliography, scientific
  reconstruction, numeric macros, existing point CSVs, and fault-table input are
  checked against the before-follow-up hashes in `data/revision_baseline.json`.
- All experiment inputs remain checked through the original source manifest.
  No experiment, statistical analysis, configuration, or contract semantics change.
- Human-readable and raw manuscript differences are in
  `MANUSCRIPT_DIFF_REVIEW2.md` and `manuscript_review2.patch`.
- Final numerical/compilation and visual checks are recorded in
  `data/paper_validation.json`, `data/revision_validation.json`, and
  `LAYOUT_REVIEW.md`.

The runtime artifact directory has been relocated from the recorded
`VQE Runtime Verification - DejaVu copy` path to `VQE Runtime Verification - DejaVu`.
All relocated files match their original source-manifest checksums. A narrowly
defined path resolver lets the common reconstruction, plotting, and validation
scripts read that location while preserving the original manifest and raw files.
`data/source_location_resolution.json` records each verified relocation. This
changes path handling only, not experiment selection or scientific results.

There are no partially addressed requests or outstanding author decisions.
