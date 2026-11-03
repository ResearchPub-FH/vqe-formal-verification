# Manuscript differences: review 1 to the requested figure follow-up

Reference: `manuscript_review1.tex` (unchanged).
Revised main: `manuscript_review2.tex`.

## Title, abstract, introduction, background, and methodology

Unchanged. The agreed four verification aspects and two-stage architecture,
terminology, operator provenance, optimizer rationale, and citations are preserved.

## Individual-layer evaluation

The main source is unchanged. Its shared Storm scalability PDF uses more saturated
blue/orange lines. All counts, timings, labels, and caption statements are unchanged.

## Cross-layer results

The shared probability PDF uses green/magenta lines. Its source data, confidence
intervals, plotted values, axes, and manuscript caption are unchanged.

In Section V-D, the fault table becomes Figure 5. The opening paragraph identifies
the matrix and explains its visual comparison across obligations. The figure
caption states that every repetition in each row has the displayed vector and
explains the two exact count columns. It preserves all verdict definitions and
the missing-count classification qualification. The original ancillary fault
table remains available.

## Discussion and conclusion

Unchanged. No interpretation, limitation, numerical claim, or scientific result
is revised. Bibliography entries are unchanged in this follow-up.
The final bibliography column break is adjusted to suit the new float placement.

## Shared sources and validation

Updated the existing plotting, build, and validation scripts and the common
figure plan/manifest, claim traceability, README, and layout record. Added a
reproducible fault-matrix plotting script and its exact cell/count CSV. Main-paper
totals change from four figures/seven tables to five figures/six tables.

`manuscript_review2.patch` contains the exact main-source diff against review 1.
Preservation checks cover both earlier main sources and PDFs, all existing
quantitative outputs, and the experiment inputs.
