# Evidence-driven figure plan

The main experiment is exclusively `../artifacts/approved-experiment/`, frozen on
2026-10-05 and independently audited on 2026-10-06. Earlier full executions reuse
its seeds and are not additional samples. `manuscript.tex` is the unchanged manuscript baseline for review round 1;
`manuscript_review1.tex` is preserved. The requested figure follow-up is integrated
in `manuscript_review2.tex`. No raw experimental file is edited.

| Figure | Scientific purpose | Data | Source | Width | Section | Supported claim |
|---|---|---|---|---|---|---|
| 1 | Distinguish the three prospective aspects from runtime verification | Frozen assurance record, contract library, implementation | `figures/architecture.tex` (TikZ) | Double column, 7.1 in | Shared execution model and specifications | Contracts link the two stages without equating the formalisms |
| 2 | Show reachable time-unrolled model growth and recorded construction/checking costs | Archived final scalability CSV and metadata, plus final homogeneous DTMC record for the explanatory distinction | `scripts/figures/storm_scalability.py` | Single column, 3.5 in | Individual layer evaluation | Reachable sizes and costs vary with iteration horizon. The homogeneous phase model has fixed size |
| 3 | Report measured monitoring cost without a negligible-overhead claim | Completed restart02 timing study: raw per-run summaries, runs.csv, configuration, completion audit | `scripts/figures/runtime_overhead.py` | Single column, 3.5 in | Individual layer evaluation | Instrumentation adds measurable absolute runtime on the tested simulator |
| 4 | Compare the same bounded first-success predicate | Final Gaussian CDF and Storm log; all 400 raw baseline traces and result records | `scripts/figures/probability_comparison.py` | Single column, 3.5 in | Cross-layer relationships and agreement | Finite-shot execution under the specified assumptions is statistically compatible with Gaussian predictions |
| 5 | Compare fault responses across logical and numeric obligations | Individual audited fault results, linked raw traces, completion hashes, and contract library | `scripts/figures/fault_discrepancies.py` | Double column, 7.1 in | Faults and cross-stage discrepancies | Temporal and numeric checks have complementary responses. Missing observations and changed assumptions have distinct verdicts |

## Tables and rejected candidates

- B: exact contract mapping is Table I. Contract-wise results are a separate table.
- D: a separate prediction-error plot repeats Figure 4; exact checkpoint deviations
  are in the probability table instead.
- G: the figure follow-up replaces the fault table with a nominal-color matrix.
  Its five scenarios span eight obligations, making patterns across components
  visually comparable. Letters and exact counts retain all table information.
  It uses no numerical color scale or categorical bar chart.
- No noisy curve is added to the matched-model plot. The retained FakeJakarta
  study is reported separately as out-of-model robustness, with its own sources.
- No final-experiment overhead plot: the final matched run has no repeated
  uninstrumented baseline timing condition. Figure 3 measures an earlier,
  separately configured runtime implementation.
- The audit's 100,000-run and 20,000-run supplements have scripts and narrative
  results, but their `_out/*.npy` data are absent. They are not plotted or used
  for new numerical claims. P2/P3 correction is recomputed from the available
  primary observations using the audit's multiplicity adjustment.

All quantitative scripts read artifacts directly, emit plotted-point data, and
use vector PDF. Counts, intervals, captions, and text use generated LaTeX macros.

## Review round 1 presentation changes

All figure filenames and numbers are unchanged. Figure 1 uses the revised
specification/verification-record terminology and names runtime verification
explicitly. Figure 2 now has a second panel for recorded construction time and
median checking time; it replaces the redundant Storm timing table. Figure 4
labels optimizer iteration, consistently with the defined three-candidate step.
Figure 3 already shows timing medians and intervals and replaces the redundant
runtime table. The main paper has seven tables. The four removed main-paper
table inputs remain under their existing filenames; the two small trace/controller
tables are expressed through generated prose macros.

## Requested figure follow-up

Figures 2 and 4 use distinct, more saturated palettes, with line styles and
markers preserved. Figure 5 replaces only the fault table. The main paper now
has five figures and six tables. The six retained tables contain the exact
specification mapping, configuration, hardware-run summaries, scoped agreement
counts, probability checkpoints, and conditional resources. The first four
are primarily exact/categorical comparisons. The probability trend is already
plotted, and the resource rows are deterministically linked through fixed shots
per iteration. Further plots would add repetition or obscure the exact scopes
and statistical summaries. The original fault-table input is preserved.
