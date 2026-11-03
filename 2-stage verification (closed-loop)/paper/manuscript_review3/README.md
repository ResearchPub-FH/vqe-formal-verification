# Manuscript review3

This folder contains the revision responding to `/Users/rome/Desktop/Review2.docx`.

- `manuscript_review3.tex` and `manuscript_review3.pdf`: new main source and compiled paper.
- `REVISION_LOG_REVIEW3.md`: response to every review item and preservation decisions.
- `MANUSCRIPT_DIFF_REVIEW3.md` and `manuscript_review3.patch`: substantive and machine-readable differences.
- `tables/`: revised display tables, generated from the shared audited data.
- `figures/architecture.pdf`: revised diagram. Editable source remains `../figures/architecture.tex`.
- `scripts/`: reproducible table generation, build and audit.
- `data/`: preservation hashes, extracted review text, checklist, table provenance and validation reports.

The current reference remains `../manuscript_review2.tex` and its existing PDF. The original `../manuscript.tex` also remains unchanged. The revision shares `../references.bib`, `../data/numbers.tex`, other parent tables, unchanged plots and experimental artifacts. This is one main-manuscript revision, not a copied project.

## Rebuild

Run the following from this folder with Python, Tectonic, NumPy and pypdf installed:

```sh
python3 scripts/build_revision.py
```

`VQE_TECTONIC` can specify the Tectonic executable. The build script also recognizes the configured local tools used for this revision. It regenerates revised tables and the local architecture PDF, compiles the new main, and runs the common and local audits. It does not rerun experiments or write their data.

The audits require the source experiment artifacts and the parent paper directory. The reports preserve the original recorded source hashes and document the already-established relocation alias.
