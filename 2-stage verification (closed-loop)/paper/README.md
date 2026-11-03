# Academic paper and reproducibility bundle

Read `manuscript_review2.pdf`; edit `manuscript_review2.tex` for the requested
figure-style and table-conversion follow-up. Review 1's source and PDF are preserved.
`manuscript.tex` and its compiled `manuscript.pdf` are unchanged reference files.
Only the main source has a parallel review version. Bibliography, figures, tables,
scripts, and experiment artifacts are shared. This paper is based on
`restructured.tex` and the audited `approved-experiment` artifacts.
It preserves the requested flow: shared execution model/contracts, layer methods,
individual evaluations, then **Cross-Layer Relationships and Agreement**.

## Generate from the preserved artifacts

Python 3.12 was used for paper analysis with the packages in
`requirements-paper.txt`. The final experiment itself used Python 3.14.6 and
NumPy 2.5.3; this paper environment does not modify its frozen requirements or
sources. The extraction script performs read-only source/seal/hash checks and
full saved-trace replay before reconstruction. It never calls the experiment's
`compare` or `audit` command, which would rewrite delivered processed outputs.

```sh
python3 scripts/extract_results.py
python3 scripts/figures/storm_scalability.py
python3 scripts/figures/runtime_overhead.py
python3 scripts/figures/probability_comparison.py
python3 scripts/figures/fault_discrepancies.py
tectonic figures/architecture.tex --outdir figures --keep-logs
tectonic manuscript_review2.tex --keep-logs --keep-intermediates
python3 scripts/validate_paper.py --manuscript manuscript_review2.tex
python3 scripts/validate_revision.py
```

The sources also work with a standard LaTeX installation containing IEEEtran,
TikZ, booktabs, tabularx, and IEEEtran.bst. Compile the standalone architecture
first, then run LaTeX/BibTeX until references resolve. Tectonic 0.17.0 was used
locally; its temporary binary and cache are not part of the research artifacts.

`scripts/build_paper.py --manuscript manuscript_review2.tex` runs these steps
sequentially and checks command status. Both build and paper validation default
to the latest existing review source. They do not create a new review round.
Set `TECTONIC` to your compiler path if it is not on PATH.

## Evidence and editorial decisions

- `SOURCE_OF_TRUTH.md`: final-run selection and reporting boundaries.
- `FIGURE_PLAN.md`: scientific purpose, selected versus rejected figure candidates.
- `FIGURE_MANIFEST.md`: inputs, scripts, configurations and statistical methods.
- `PAPER_RESULT_TRACEABILITY.md`: major claim-to-contract-to-artifact links.
- `data/derived_results.json`: reconstructed exact quantities and corrected statistics.
- `data/numbers.tex`, `tables/*.tex`: generated quantitative prose/table inputs.
- `data/*_figure_points.csv`: every quantitative plotted point and interval endpoint.
- `data/source_manifest.json`: hashes of actual source inputs, traces and retained studies.
- `data/paper_validation.json`: numerical, reference, PDF and preservation checks.
- `LAYOUT_REVIEW.md`: final visual inspection.
- `REVISION_LOG_REVIEW1.md`: all 27 substantive comments from `Review.docx`,
  the terminology policy, title alternatives, table dispositions, and audit.
- `MANUSCRIPT_DIFF_REVIEW1.md`: section-by-section explanation of changes.
- `manuscript_review1.patch`: raw source diff against the untouched baseline.
- `REVISION_LOG_REVIEW2.md`, `MANUSCRIPT_DIFF_REVIEW2.md`, and
  `manuscript_review2.patch`: the requested figure follow-up and its small
  manuscript change against preserved review 1.
- `data/revision_baseline.json`: original source/PDF and project checksums.
- `data/revision_checklist.json`, `data/revision_validation.json`: extracted
  comments and programmatic revision/preservation checks.

The P2/P3 agreement correction uses the available original first-success data
and the audit's Holm method. Original estimates, intervals, and archived verdicts
are unchanged. The benchmark is relabeled scientifically by its actual operator.
L4 prospective claims are narrowed; full fault vectors expose the known missing-
evidence classification artifact. No frozen experimental source was repaired.

The architecture and all plots are vector PDFs. The scalability figure now
includes the recorded construction/checking times. The main paper contains six
tables instead of eleven. All numeric table inputs remain available under their
original filenames. Two small tables become generated prose, and two timing
tables are represented by existing plots. Axis labels distinguish iterations
from energy evaluations. Missing independent-audit Monte Carlo arrays and
unavailable scalability model exports are documented rather than fabricated.

The figure follow-up adds a fifth figure: a categorical fault-verdict matrix
that replaces the fault table in the main paper. It retains every letter and
detection count from the audited results. Colors indicate nominal categories,
not magnitudes. The probability figure uses saturated green/magenta and the
scalability figure uses vivid blue/orange. Dashed lines and markers still
distinguish the curves in grayscale. All numerical points and intervals are
unchanged. No ancillary file has a review-numbered duplicate.

The runtime source folder is currently `VQE Runtime Verification - DejaVu`.
The recorded manifest retains its historical `... - DejaVu copy` paths.
`scripts/artifact_paths.py` resolves only that explicit relocation, and validators
still require every file to match its original checksum. Verified physical paths
are recorded in `data/source_location_resolution.json`.

The operator and four-parameter ansatz are traceable to the published IBM VQE
example and the supplied `../../vqe_qiskit.py`. The manuscript calls this the IBM
two-qubit VQE benchmark. A molecular H2 derivation is not supplied by the project
or by the two-qubit example, so no such physical identification is asserted.
The bibliography adds that primary source, the Kolda--Lewis--Torczon direct-search
review, and the Tilly et al. VQE review. No measurements or statistical results
were changed during review round 1.
