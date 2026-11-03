# Meaningful manuscript differences: review2 to review3

Baseline: `../manuscript_review2.tex`. Revised main: `manuscript_review3.tex`.

## Title

Preserved the current title and section structure.

## Abstract

Normalized routine references to logical/numeric requirements. The architecture, benchmark result and future direction are unchanged.

## Introduction

Used requirement for routine cross-stage comparisons and the contribution list. Retained the agreed methodological principle verbatim.

## Background and shared execution model

Defined requirement and the precise contract meaning of obligation. Introduced all verdict categories, explained assumption-dependent applicability and illustrated a changed shot allocation before the architecture. Justified the selection and boundary of Table I. Moved the three-candidate/nine-group iteration definition into prose.

## Methodology

Added the Gaussian approximation rationale with an existing primary citation. Explained finite variance, independent sampling, tractable selection probabilities, and the finite grid/phase Markov construction. Preserved the original variance/selection equations, tie distinction, and approximation-error limits.

## Evaluation

Shortened model-size and runtime captions while retaining panel and interval meanings. Moved construction/checking exclusions and tool timing resolution into prose. Replaced PUBs with Submissions in the hardware table header without changing counts.

## Results

Normalized L4 to Agreement under mapping, preserving its limited prospective scope. Combined the two probabilistic tables into one compact Table V with the original estimates, success counts and intervals. Removed deviation and Holm columns while retaining the essential analysis in the results prose. Shortened probability and fault captions without changing their plots or findings.

## Discussion

Preserved all scientific limitations, including incomplete termination properties, missing-record classification, the post-audit statistical interpretation, available-sample resolution and absent model exports/audit arrays.

## Conclusion

Normalized requirement terminology. Preserved the conclusions and future-work scope.

## Assets and build structure

Placed the new main and newly generated artifacts in this folder. Reused the parent bibliography, macros, data and unchanged plots. Updated only the shared architecture source terminology and validator's support for revision subfolders. Added a data-driven local table generator and revision-specific consistency checks.
