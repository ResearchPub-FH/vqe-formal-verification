# Layout and consistency reviews

## Requested figure follow-up — completed 2026-10-06

Reviewed the three new/regenerated standalone vector figures at 150 dpi and
all eleven pages of `manuscript_review2.pdf` at 125 dpi. After the final
bibliography adjustment, page 11 was re-rendered and reviewed. Pages 1–10
have byte-identical drawing content to their inspected pre-adjustment pages.

- Saturated green/magenta probability lines and vivid blue/orange scalability
  lines remain distinct at single-column size. Solid/dashed styles and circle/
  square markers retain meaning in grayscale. The neutral pointwise Wilson
  shading is unchanged.
- The double-column fault matrix is readable at final paper size. Logical and
  numeric columns are grouped. All forty verdict letters and both exact count
  columns are visible. Category colors accompany letters, without a numeric
  color scale. The caption retains the scope of the missing-count result.
- Figure 5 is introduced and discussed in Section V-D. The original fault-table
  input is preserved. The paper now contains five figures and six tables.
- All equations, table cells, captions, figure labels, citations, and final-page
  references remain readable, without clipping or overlap. Final bibliography
  columns are balanced after adapting the IEEE reference break.
- Compilation reports zero overfull boxes and zero undefined references or
  citations. The eleven ordinary underfull horizontal-spacing notes cause no
  visible defects. All labels are unique and all figures/tables are referenced.
- Probability/scalability point CSVs, all existing numeric macros, statistical
  results, scientific reconstruction, bibliography, and the preserved fault
  table match their before-follow-up hashes. Every new matrix cell/count matches
  the independent fault-result reconstruction.
- All 881 original source inputs match their recorded checksums. Of these, 362
  runtime-source files resolve through the documented directory relocation.
  The source manifest and raw files remain unchanged. Actual locations are
  recorded in `data/source_location_resolution.json`.
- Both `manuscript.tex`/PDF and `manuscript_review1.tex`/PDF remain unchanged.
  The only content change in the new main source is Section V-D's figure
  integration. Other main-source differences concern the bibliography break.

Numerical/compilation audit: `data/paper_validation.json` (PASS).
Preservation/scope audit: `data/revision_validation.json` (PASS).
Figure generation and source traceability: `FIGURE_MANIFEST.md`.

Revised PDF SHA-256:
`40bc17631dead0cf83d6b2bcc6f77cf6d652309ee5b159a0d7346ba274547991`.

## Review round 1 — completed 2026-10-06

Reviewed `manuscript_review1.pdf` after its independent successful IEEE
two-column compilation. The reference source and PDF remain unchanged.

- Inspected all eleven revised manuscript pages individually at 125 dpi and
  all four standalone figures at 150 dpi. Checked the figures at their final
  single-column or double-column placement in the manuscript.
- Confirmed readable equations, table cells, axes, legends, captions, and
  references. No clipped text, overlapping content, or connector collisions
  remain. The bibliography columns are balanced using the IEEE reference break.
- The architecture clearly distinguishes pre-execution verification from
  execution and runtime verification. Each verification family retains its
  formalism. Diagram labels follow the revised terminology and actual verdicts.
- The scalability figure includes the recorded construction time and median
  Storm checking time alongside state and transition counts. Its logarithmic
  model-size axis and linear timing axis are separate panels. The caption states
  the timing repetition count and model scope.
- Probability and scalability axes count optimizer iterations. Runtime cost
  counts energy evaluations. Pointwise Wilson intervals and percentile-bootstrap
  timing intervals retain their original data and stated statistical meanings.
- All four figures retain vector text and contain no raster image XObjects.
  Figure numbers and captions appear only in the manuscript.
- The revised manuscript has seven tables. Exact configuration, specification
  mappings, agreement counts, conditional resources, and full fault verdicts
  remain tabulated. Removed main-paper tables retain their common ancillary
  files and artifact-generated values.
- Checked captions, surrounding prose, fixed parameters, numerical macros,
  and table values against the validation report and reconstructed artifacts.
  The P2 marginal interval is unchanged. Its original exclusion of the model
  mean and the family-level statistical interpretation remain explicit.
- Reread all 27 substantive review comments and checked every remaining
  specification/property/contract occurrence in context. Necessary qualifications
  concern scientific scope, unavailable molecular derivation and measurement
  records, statistical interpretation, and fault-classification limitations.
  The sole remaining flagged prose term is the technically appropriate
  expression "statistical evidence" in Discussion.
- Compilation has zero overfull boxes, zero undefined references or citations,
  and eleven ordinary underfull horizontal-spacing notes. Visual inspection
  confirms that these notes cause no clipping or overlap. All four figures and
  seven tables are referenced in the text, and all labels are unique.

Automated records: `data/paper_validation.json` and
`data/revision_validation.json` (both PASS). They verify all 881 experiment
inputs, the unchanged scientific results and original numeric macros, the
plotted points, generated tables, references, vector outputs, one serialized
main source, and the unchanged original manuscript and PDF.

Revised PDF SHA-256:
`45dffacd7712d1ba910a89d66a6717e54261edc65ad8f1387f420793c802bad8`.

## Preserved baseline layout review

Reviewed 2026-10-06 after the final successful IEEE two-column compilation.

- Inspected all ten rendered manuscript pages, individually, at 125 dpi, plus
  a page contact sheet for flow and float placement.
- Inspected all four standalone vector figures and their final paper placement.
- Architecture: readable double-column labels, clear stage boundary, correct
  family-owned branches, actual verdict vocabulary, no overlapping connectors.
- Quantitative figures: readable single-column axes/legends, percentages for
  probability, distinct line/marker styles, preserved vector text, no raster
  image XObjects, no figure number or manuscript caption inside the graphics.
- Probability intervals are explicitly pointwise Wilson intervals. Storm points
  are distinguished from the forward-propagated model curve and empirical runs.
- Timing intervals describe repeated measurements of a fixed seeded workload;
  the different implementation/configuration and timing boundary are explicit.
- State-space plot is labeled time-unrolled; the text distinguishes the final
  fixed-size grid/phase model and discloses the missing archived model exports.
- Tables have readable cells, exact units, consistent contract identifiers,
  full fault verdict vectors, and documented scopes. The P2 interval remains
  unchanged and visibly excludes the model mean; the adjusted interpretation
  is explained, avoiding an implied change of data or marginal interval.
- Checked captions and nearby prose against actual figure data and configuration.
- Reviewed literal numerals in `data/literal_numeric_lines.json`: these are
  fixed experimental/methodological settings, mathematical notation, contract
  identifiers, or reference keys. Measured prose values use generated macros.
- All figure/table labels are discussed; all citations resolve. LaTeX reports
  zero overfull boxes and zero undefined references. Remaining underfull notes
  concern ordinary float/paragraph spacing and do not cause clipping or overlap.
- Bibliography and final columns are balanced. No author identities were invented.

Automated check: `data/paper_validation.json` (PASS). It verifies source-input
preservation, every quantitative plotted point, every generated numerical table,
all generated prose macros, the P2/P3 correction, references, compilation, and
vector outputs. The full trace reconstruction and independent kernel propagation
are recorded by `scripts/extract_results.py` and `data/derived_results.json`.

The scientific qualifications remain intentional: incomplete prospective L4
scope; trusted numeric/evidence mappings; post-audit statistical correction;
limited fault diversity; absent independent-audit arrays; unretained historical
scalability exports; no final matched-run overhead condition. This review does
not certify a formal composition theorem or repair the frozen implementation.
