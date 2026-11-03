# Review3 claim traceability

All scientific results remain those of the shared audited experiment. See the parent `../PAPER_RESULT_TRACEABILITY.md` and `../data/source_manifest.json` for complete provenance.

| Claim or clarification | Revised manuscript location | Source |
|---|---|---|
| Requirements selected at measurement/calculation/optimizer interfaces | II-A, Table I | `../../config/contracts.json`; prospective models/kernels and runtime checks indexed by the shared manifest |
| Gaussian mean/variance, candidate selection and grid/phase Markov construction | III-C, Eqs. 6–8 | `../../closed_loop/physics.py`, probabilistic model-generation source, Stage 1 configuration/kernel/model artifacts; existing `mcclean2016` citation for the central-limit motivation |
| Applicability verdict for changed shot allocation | II-A, V-D, Fig. 5 | Contract assumptions; `../../closed_loop/checker.py` and `comparison.py`; raw fault results and traces |
| L4 agreement under the stated mapping | III-A, V-B, Table IV | `../data/derived_results.json` L4 record; original NuXmv outputs and runtime results, with audit qualification retained |
| Bounded-success predictions, empirical counts and Wilson intervals | V-C, Fig. 4, Table V | `../data/derived_results.json` probability comparison; raw kernel/Storm outputs and baseline terminal records |
| Conditional iterations/shots, original bootstrap intervals and corrected interpretation | V-C, Table V | Shared P2/P3 results and original `comparison/verdict_agreement.json`; original intervals unchanged, existing Holm analysis preserved |
| Model size/cost, runtime cost and fault outcomes | IV-C/D and V-D, Figs. 2/3/5 | Unchanged shared plot PDFs, point CSVs and source manifest; captions reorganized only |

`data/table_traceability.json` maps the merged table to each processed result row and the original source manifest. `data/paper_validation.json` checks the 65 numerical macros and all plotted points. `data/revision_validation.json` independently checks printed merged-table cells, unchanged equations, retained result scope and preservation of the existing manuscript/data assets.

No quantitative result, confidence interval, formal-verification output, configuration or contract meaning has been altered in this round.
