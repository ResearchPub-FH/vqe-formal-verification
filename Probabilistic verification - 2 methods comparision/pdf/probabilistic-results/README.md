# Expanded probabilistic-results figure

This review package contains a 3.5 x 3.82 inch, four-panel figure for a single IEEE column: (a) over (b) in the left column, (c) over (d) in the right. It is based exclusively on the original approved 400-run experiment and its retained Gaussian model. The manuscript, Table X, and existing figures are unchanged.

The current export uses bright sky blue (`#1AA7FF`) and orange (`#FF9826`)
consistently across all panels, and empirical bars use the full orange color.
Typography is sized for the single column: 7.5 pt panel titles and 7 pt axis
labels, legend, ticks and numerical annotations. One legend above both columns
pairs each series' line glyph (a, b) with its bar glyph (c). Hatching, line
styles, and marker shapes preserve distinctions in grayscale.

**Single-column revision (2026-11-02).** The earlier 7.1 x 5.95 inch
double-column version was redrawn at 3.5 inches. Panel (b) is titled
"Discrepancy comparison", and the legend reads "Empirical runs (n = 400)". The
two local legends in (a) and (c) became the shared legend. The no-success
category label in (c) wraps onto three lines and sits slightly apart from
"41-50", and each count label sits above the taller bar of its pair. All plotted
data are unchanged: the four derived data files are byte-identical. The supplied
paper PDF, hashed for provenance only, is now read from `~/Downloads`, so
`data/source_manifest.json` records that path and the newer file's hash.

## Files

- `probabilistic-results-four-panel.pdf`: vector figure with embedded fonts and an exact 3.5-inch page width.
- `probabilistic-results-four-panel.svg`: vector figure with editable text.
- `probabilistic-results-four-panel.png`: 600 dpi preview (2100 x 2292 pixels).
- `plot_probabilistic_results.py`: complete extraction, validation, statistics, and plotting code.
- `caption.tex`: proposed IEEE caption, for later integration.
- `data/iteration_results.csv`: all 51 original integer-indexed model/empirical CDF points, first-passage masses, Wilson intervals, and signed discrepancies.
- `data/run_first_success.csv`: first-success iteration, termination, seed words, and physical consumption extracted from each of the 400 traces.
- `data/grouped_first_success.csv`: exact first-success masses aggregated into the displayed disjoint windows.
- `data/verified_statistics.json`: full-precision statistics, configuration, p-values, and interpretation.
- `data/source_manifest.json`: SHA-256 hashes and roles of every input, including the 400 compressed traces.
- `validation/checks.json`: numerical, provenance, dimension, and vector-output verification.
- `validation/print-size-100dpi.png` and `validation/inspection-150dpi.png`: previews for print-size layout review.
- `validation/annotated-reference.pdf`: unchanged copy of the supplied annotated PDF (review of the earlier double-column version).
- `validation/annotation-checklist.json`: all seven extracted comments and their revision status (earlier double-column version).

## What each panel adds

**(a) Success probability comparison.** Gaussian-kernel propagation, 400 empirical finite-shot executions, and the five independently recorded Storm reachability checkpoints share the same initial point, success set, measurement allocation, optimizer rule, and iteration bound. Integer iterations are displayed as post-step curves. The two-series legend sits above the panels and is shared with (c). Hollow diamonds and shading remain in the plot and are explained in the caption. Shading is the empirical pointwise 95% Wilson interval; it is neither a simultaneous band nor an uncertainty interval for the Gaussian abstraction. The primary endpoint is retained in the caption: 92.80% modeled versus 91.50% observed (366/400), with Wilson interval [88.36%, 93.85%].

**(b) Signed discrepancy.** The curve is 100 times the empirical CDF minus the Gaussian CDF. The shaded limits are 100 times each empirical Wilson endpoint minus the fixed model prediction. This preserves the pointwise coverage interpretation and makes departures of either sign visible. The endpoint is -1.30 percentage points, reported in the caption. Both trend panels omit the former endpoint text blocks. The early interval around an observed zero is retained. A localized pointwise exclusion at an intermediate iteration is not a newly performed hypothesis test or a simultaneous family-level rejection. No smoothing or interpolation is applied.

**(c) Timing of first success and budget exhaustion.** Paired bars compare Gaussian and empirical unconditional outcome masses for first success in iterations 1-20, 21-30, 31-40, and 41-50, followed by a separate no-success-by-50 outcome. Empirical bar labels are run counts: 0, 169, 138, 59, and 34. Every denominator is 400. The initial point has zero success probability, so these categories partition the configured outcomes exactly. Each model category is the sum of exact integer-level first-passage masses from propagation of the saved kernel; empirical categories use exact first-hit records recovered from the traces. Both partitions sum to 100%. No within-window timing is inferred from checkpoint aggregates, and budget exhaustion does not imply permanent failure. These bars are descriptive; no additional grouped-outcome tests or confidence intervals were introduced.

**(d) Success-conditioned resources.** Two vertically aligned point-and-interval plots compare conditional mean iterations and conditional mean physical shots. Both use the same Gaussian/Empirical labels, square/circle markers, and model/empirical colors. The upper plot compares the model's conditional mean iteration count (33.111) with the empirical mean (32.290) and the original 95% percentile-bootstrap interval [31.579, 32.995]. Only the 366 successful paths enter the empirical mean or bootstrap. The blue reference makes the model's position beyond the marginal interval visible. Exactly 9,216 physical shots are used per iteration (three candidates x three groups x 1,024 shots), so the lower plot's shot means and interval are scaled versions of the same statistic, not additional independent evidence. All plotted values and intervals are read from the reconstructed statistics. The p-values remain in the caption and data: raw p=0.024 and Holm-adjusted p=0.094 under the existing post-audit normal-approximation mean comparison. The four-member family is P1 at k=30,40,50 and P2; P3 and structural-zero checkpoints are not additional tests. Neither bootstrap interval was widened after adjustment.

The first-success panel (c) uses the bar glyphs of the shared legend in place of the former explanatory note. Its bar labels remain empirical counts out of 400, as specified in the caption. All corresponding series labels in the graphic use "Empirical."

## Source-to-figure mapping

All paths below are relative to the original workspace. The code verifies source hashes and extracts observations without invoking VQE execution, building a new Gaussian kernel, or rerunning Storm.

| Figure content | Authoritative input | Extraction and cross-check |
|---|---|---|
| Common experiment and success predicate | `2-stage verification (closed-loop)/artifacts/approved-experiment/stage1/configuration.json`; sealed `pre_execution.json`; `closed_loop/physics.py` and `closed_loop/execution.py` | K=50; ideal energy gap <=0.02; grid size 16; initial index (3,11,6,14); cyclic coordinates; grouped ideal-Born finite-shot measurements; 1,024 shots/group/candidate. Configuration digest and seal are verified. |
| Gaussian CDF in (a), fixed model in (b) | `.../stage1/gaussian-kernels.npz`; `.../stage1/quantitative.json` | Repropagate the retained transition kernel for 50 iterations, with absorbing first hits. All 51 CDF points match the saved quantitative output and original figure CSV. Probability mass is checked at every iteration. |
| Storm markers in (a) | `.../stage1/storm.log`; `.../stage1/gaussian.props` | Parse the five actual Storm results, check query ordering and values against the saved model; maximum difference from forward propagation is about 1.11e-16. This is numerical consistency within the Gaussian model, not an empirical approximation-error bound. |
| Empirical CDF and residuals in (a,b) | `.../stage2/baseline/results.json`; all 400 indexed `baseline-*.jsonl.gz` files | Verify every trace hash and unique original seed stream. Recover each first hit from actual optimizer successors and the retained success mask, then confirm the terminal record and result index. Recompute Wilson intervals using the original method. |
| Exact first-success aggregation in (c) | Same 400 traces and saved Gaussian kernel | Group the observed first-hit iterations and model PMF into four disjoint iteration windows plus the complement at K. Validate both complete partitions. |
| Conditional model resources in (d) | `.../stage1/quantitative.json`; saved-kernel first-passage distribution | Compute sum(k * first-passage mass) / P(T<=50); verify the saved conditional iteration mean and the 9,216-shot scaling. |
| Empirical resource means/intervals in (d) | Same successful trace paths; `.../comparison/verdict_agreement.json`; `closed_loop/comparison.py` | Exactly reproduce the original 5,000 percentile-bootstrap means with `SeedSequence([20260721,99])`; confirm the original endpoints, including scaled shot endpoints. |
| Raw and adjusted P2 p-values in (d) | `paper/data/derived_results.json`; `paper/scripts/extract_results.py`; `audit/stats_recompute.py` | Reproduce the already adopted four-comparison post-audit procedure, not a new choice of tests. The broader audit script, which also contains unrelated Monte Carlo analyses, is inspected but never executed. |
| Manuscript/Table X consistency | `Formal_Verification_in_Hybrid_Quantum_Classical_Computing_Systems.pdf`; `paper/manuscript_review3/tables/probabilistic_results.tex`; original `paper/data/probability_figure_points.csv` | Verify all five reported checkpoint pairs, original Wilson intervals, P2/P3 values and intervals, p-value rounding, and all 51 original plot points. |

In the table, `...` means `2-stage verification (closed-loop)/artifacts/approved-experiment`. Complete, unambiguous paths and hashes are in `data/source_manifest.json`.

The later `merged-model-01` archive has the same 400 seeds, success times, termination reasons, update totals, and shot totals; this is checked for provenance only. It is not pooled as another independent sample. Other development/rerun datasets are not inputs to the figure.

## Proposed IEEE-style caption

**Probabilistic predictions and empirical finite-shot VQE executions under a matched configuration.** All results use the ideal-Born benchmark, the original grid and cyclic candidate rule, success defined by E_ideal(z)-E_ref <= 0.02, and iteration bound K=50. (a) Success probability comparison between Gaussian-DTMC propagation and cumulative first-success frequencies from 400 independently seeded finite-shot executions. Hollow diamonds denote independently recorded Storm bounded-reachability checkpoints. Shading denotes pointwise 95% Wilson intervals. At K=50, the prediction is 92.80%, compared with 91.50% (366/400; interval [88.36%,93.85%]). (b) Empirical-minus-Gaussian discrepancies in percentage points; the shaded intervals translate the same Wilson limits relative to the fixed model, with an endpoint discrepancy of -1.30 percentage points. These intervals quantify sampling uncertainty, not Gaussian approximation error. (c) Unconditional first-success masses aggregated from exact iteration-level model outputs and per-run records; empirical bar labels are counts out of 400. The separate no-success-by-50 category contains 34 budget-terminated executions, and each complete outcome partition sums to 100%. (d) Model and empirical conditional mean iterations (upper) and physical shots (lower), restricted to success within 50 iterations. Squares denote model means and circles denote empirical means. Error bars show the original 95% percentile-bootstrap intervals over 366 successful paths, with 5,000 resamples. Physical shots equal 9,216 times iterations, so the lower plot is a rescaled view of the same resource comparison. The marginal intervals exclude the modeled means; the previously adopted post-audit comparison gives raw p=0.024 and Holm-adjusted p=0.094 across P1@30, P1@40, P1@50, and P2. Conditional model means are obtained by Gaussian-kernel propagation, while Storm verifies reachability checkpoints. The observations are statistically compatible at the evaluated resolution under this analysis; equivalence is not established.

The ready-to-use LaTeX version is in `caption.tex`. Figure numbering is intentionally left to the manuscript.

## Table X after eventual integration

- **Move the P2/P3 rows into the figure/caption:** panel (d) plots both resource means and both original intervals. The caption supplies conditioning, sample size, the fixed shot multiplier, and the marginal/adjusted interpretation. Exact interval endpoints remain in the derived data files.
- **Move the primary P1@50 row into the caption:** both probabilities, 366/400, and its original Wilson endpoints are printed there. Panel (a) presents the probability trends.
- **Retain an optional compact checkpoint table or place it in the supplement:** exact k=10,20,30,40 model/empirical values, successes/400, and Wilson endpoints are useful when numerical lookup matters. The curves encode them, but small-point numerical values are not printed beside every curve position. All five exact rows are supplied below and in the CSV/JSON.
- **Keep statistical method and applicability in the main text:** the post-audit origin of Holm adjustment, the four correlated comparisons, the marginal nature of all displayed intervals, lack of an equivalence margin, and ideal-Born/model assumptions remain material. Neither an adjusted non-rejection nor the plot replaces those qualifications.
- No table or manuscript content has been removed by this task.

| k | Gaussian (%) | Empirical successes | Empirical (%) | Original pointwise 95% Wilson interval (%) |
|---:|---:|---:|---:|---:|
| 10 | 0.00 | 0/400 | 0.00 | [0.00, 0.95] |
| 20 | 0.00 | 0/400 | 0.00 | [0.00, 0.95] |
| 30 | 38.39 | 169/400 | 42.25 | [37.51, 47.14] |
| 40 | 75.63 | 307/400 | 76.75 | [72.37, 80.62] |
| 50 | 92.80 | 366/400 | 91.50 | [88.36, 93.85] |

## Limitations and provenance qualifications

No first-success or uncertainty inputs were missing: both the original traces and complete integer-level Gaussian outputs are retained. Panel (c) therefore does not use checkpoint-only reconstruction. Its grouping is a display choice, not a limitation of the available first-hit data. Raw per-run values are delivered separately.

The Gaussian transition kernel is an approximation to finite-shot candidate selection. Its quadrature and row normalization have no certified finite-shot approximation-error bound. Numerical agreement with Storm confirms computation of the specified abstraction; it does not validate the abstraction against every underlying finite-shot process. Empirical sampling uncertainty and approximation discrepancy are not separated by these data.

The original P2 interval excludes the model mean. The retained post-audit Holm adjustment gives no rejection at alpha=0.05 for the four adopted comparisons. It supplies neither an equivalence test nor a guarantee of model accuracy. The confidence band remains pointwise, and successive checkpoints use the same runs. No new tests at intermediate iterations or grouped intervals were added.

**Resource attribution:** the manuscript's individual-layer discussion describes Storm reward analysis, but the preserved Storm output explicitly reports `Reward Models: none` and the query file contains five reachability properties only. The saved quantitative file explicitly attributes conditional means to Python forward propagation. The figure/caption use that verifiable attribution. The requested numerical values are unchanged.

Success is determined by the configured ideal-energy simulator oracle. These 400 ideal-Born finite-shot runs do not establish the same statistical comparison for noisy hardware. Budget paths are included in probabilities/outcome masses but excluded from the success-conditioned resource means and bootstrap.

## Reproduction

From this directory, with the dependencies in `requirements.txt` installed:

```bash
python3 plot_probabilistic_results.py
```

The code locates the original workspace by walking its parent directories. If copied elsewhere:

```bash
python3 plot_probabilistic_results.py --workspace "/absolute/path/to/original/workspace" --output "/absolute/path/to/new/output"
```

All writes are confined to the selected output directory and temporary Matplotlib caches. The script refuses an output inside the original experiment tree. It produces complete derived datasets and source hashes, rechecks every input hash after plotting, verifies PDF dimensions and absence of raster images in PDF/SVG, and records versions in `validation/checks.json`. Rendering/export uses no TeX installation. Original datasets need not be copied into this review package.

## Annotated revision

The supplied PDF annotations are preserved in `validation/annotated-reference.pdf`.
All seven comments are tracked in `validation/annotation-checklist.json`. Corresponding
changes apply throughout the graphic: local legends in (a,c), consistent Empirical
labels, removal of endpoint text from both trend panels, and matching iteration/shot
resource plots in (d). Checkpoint markers, pointwise Wilson bands, bar counts, and
bootstrap intervals retain their original data and statistical meaning. Detailed
interpretation remains in the caption. No manuscript or experiment is revised.
These annotations were addressed in the earlier double-column version; the
single-column revision replaces the local legends in (a,c) with one shared legend.
