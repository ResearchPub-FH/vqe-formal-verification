# Review round 3 revision log

Review source: `/Users/rome/Desktop/Review2.docx`. Baseline: `../manuscript_review2.tex`. Revised main: `manuscript_review3.tex`.

Eight substantive items were identified: one general comment, five Contents comments, and two Terms comments. The blank final Terms line carries no request. All eight are addressed; there are no partial items or pending author decisions.

The review header names an earlier paper title. It supplies context rather than an explicit title-change request, so the current title is preserved.

## Review General comment

Status: **ADDRESSED**

Files: `manuscript_review3.tex`

Location: Sections II-A and III-C

Change: Introduced verdicts with their meaning and purpose; explained the requirements selected for evaluation and the Gaussian approximation/DTMC choice before their technical use. Existing introductions for the other verification layers were reviewed and retained.

## Review Contents 1

Status: **ADDRESSED**

Files: `manuscript_review3.tex`

Location: Section II-A, paragraph introducing Table I; Table I caption/header

Change: Described Table I as the selected requirements evaluated in this study, justified selection at measurement/calculation/optimizer interfaces, and stated the additional specifications needed for broader VQE questions.

## Review Contents 2

Status: **ADDRESSED**

Files: `manuscript_review3.tex`

Location: Section III-C opening paragraph

Change: Explained the central-limit motivation for sample-mean energy estimates, the computational benefit of selection probabilities, and the finite Markov state from the grid/phase and fresh independent measurements. Retained empirical validation and absence of a certified approximation-error bound. Cited the existing McClean et al. primary reference.

## Review Contents 3

Status: **ADDRESSED**

Files: `tables/contracts.tex`, `scripts/generate_tables.py`, `manuscript_review3.tex`

Location: Table IV, L4 row; Section V-B

Change: Selected Agreement under mapping, consistent with the other rows and the recorded AGREEMENT verdict. Preserved terminal absorption/budget scope and the separate runtime support for termination reasons.

## Review Contents 4

Status: **ADDRESSED**

Files: `manuscript_review3.tex`

Location: Captions of all five figures and five revised tables; Sections II-B, IV-C, IV-D, V-C and V-D

Change: Shortened every retained caption. Kept curve/panel meanings, sample counts and interval methods needed to read the graphics. Moved iteration/group counts, timing exclusions and resolution, and statistical/fault qualifications into surrounding prose. The combined probabilistic caption replaces the two previous captions.

## Review Contents 5

Status: **ADDRESSED**

Files: `manuscript_review3.tex`, `tables/probabilistic_results.tex`, `scripts/generate_tables.py`

Location: Section V-C; new Table V

Change: Merged old Tables V and VI into one four-column table containing predictions, empirical estimates/counts and original intervals. Removed deviation and Holm columns. Retained primary deviation and P2 multiplicity analysis in prose to preserve the scientific interpretation. Generated all cells from shared audited results.

## Review Terms 1

Status: **ADDRESSED**

Files: `manuscript_review3.tex`

Location: Section II-A before Figure 1; Section V-A and V-D

Change: Defined ASSUMPTION_MISMATCH before first diagram use, explained why assumption-dependent prospective results need an applicability verdict, and illustrated shot-allocation changes. Distinguished violation, inapplicability and insufficient observations. Retained the implementation-specific fault classification qualification.

## Review Terms 2

Status: **ADDRESSED**

Files: `manuscript_review3.tex`, `tables/contracts.tex`, `../figures/architecture.tex`, `figures/architecture.pdf`

Location: Abstract, Sections I-V and VIII, Tables I/IV, architecture library label

Change: Used requirement for system expectations and routine per-run comparisons. Retained obligation only in the agreed methodological quotation, its precise contract definition, and the mathematical kernel discussion. Defined the technical meaning and aligned the diagram label.

## Editorial and scientific decisions

- The single merged probabilistic table retains exact counts and intervals that complement the probability plot. Its compact form is more useful than deleting both original tables. Statistical analysis belongs in Section V-C, including the original P2 interval and the family-level interpretation.
- L4 is agreement under the stated mapping. The label change aligns presentation with the raw verdict; it does not enlarge the prospective property.
- The central methodological quotation remains verbatim. Technically meaningful uses of obligation are retained and defined rather than mechanically replaced.
- Gaussian justification uses McClean et al., *New Journal of Physics* 18, 023023 (2016), existing key `mcclean2016`. Sections III-A and V of the [primary manuscript](https://arxiv.org/pdf/1509.04279) discuss finite-variance estimators, the central limit theorem, and independent measurement statistics. The finite grid/phase construction is explained from this implementation. No bibliography entry was added or changed.

## Additional changes

- Adapted relative asset paths because the new main is located in the requested subfolder. Compiled the copied main successfully before editorial edits; `data/initial_compile.json` records this check.
- Replaced the unexplained hardware-table header PUBs with Submissions, consistent with the setup description. Counts and timing boundaries are unchanged.
- Updated the existing shared TikZ source label to requirements and generated the revised PDF only in this folder. The previous shared PDF remains unchanged.
- Updated the shared consistency validator to accept a main in a revision subfolder and write its generated reports alongside that main. The numerical checks are unchanged.
- Added revision-local table-generation, build and validation scripts. They share the parent results, bibliography and unchanged plots.

## Verification and preservation

- Baseline hashes were captured before edits for all 71 existing paper files. Only the shared architecture source and validator are permitted ancillary edits. The current and original main sources/PDFs, bibliography, numerical data, tables, and existing figure PDFs remain byte-for-byte unchanged.
- The common audit verifies all 881 recorded experimental input hashes, the numerical macros, all plotted points, original intervals, references and vector PDFs. The local audit independently parses the merged table cells and checks L4 scope, captions, item coverage and preservation.
- The new main compiles independently with the shared project inputs. The final validation reports record reference, citation and box checks. All pages and the architecture diagram were visually inspected. See `LAYOUT_REVIEW.md`.
- A second pass reread all review comments, checked every response, and reviewed remaining technical uses of obligation. Experimental implementation, formal outputs, statistical data and configurations were not changed.
