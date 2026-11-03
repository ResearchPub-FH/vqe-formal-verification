# Major claim-to-artifact mapping

The final matched run is `../artifacts/approved-experiment/` (R). Retained
probabilistic artifacts are `../../Probabilistic verification - 2 methods comparision/artifacts/h2_vqe/` (P).
The completed timing study is `../../VQE Runtime Verification - DejaVu copy/artifacts/sampler_verification_scaling_restart02_20260930/` (T).
All exact values and transformations are in `data/derived_results.json`; prose
values in `data/claim_values.json` are generated rather than manually transcribed.

| Major paper claim | Contract / result | Paper location | Authoritative source |
|---|---|---|---|
| One specified configuration recorded before execution | Verification record; Stage 2 reference digests/timestamps | Figure 1; setup | R/stage1/pre_execution.json, seal; R/stage2/baseline/results.json; source hashes |
| Families keep heterogeneous semantics | Contract library and model/proof/evidence mappings | Table I; methodology | ../config/contracts.json; frozen sources; AUDIT_REPORT.md §§3,5–9 |
| The implemented operator and ansatz match the published IBM VQE benchmark | Actual coefficient/Pauli manifest | Hamiltonian equation; setup table | R/stage1/configuration.json; physics.py; ../../vqe_qiskit.py; data/benchmark_provenance.json; IBM VQE example Section 3 (references.bib key ibmvqe); audit F1 |
| Iteration, shots, grid and ideal-energy target | Frozen configuration and actual executor | Setup table; Figure 4 caption | R/stage1/pre_execution.json; raw measurements/commit/terminal events |
| All logical/numeric baseline rows have observed agreement, under their mappings | L1–L4, N1–N4 | Contract-wise table | R/stage1/nuxmv.log; dafny-*.log; R/stage2/baseline/results.json and all raw traces; full replay |
| L4 prospective scope is narrower than runtime termination checking | Absorption/budget properties; audit negative controls | Tables I and contract-wise results; logical method | R/stage1/controller.smv; nuxmv.log; ../audit/nuxmv_negative_controls.sh; audit F2 |
| Numeric match checks actual outputs, not just assumed valid inputs | N1–N4; rational parity/energy/score reconstruction | Numeric method; matched results | Raw baseline counts/evaluation/optimizer_commit events; formal kernels; checker.py; data/derived_results.json.resource |
| Maximum energy error, total updates, evaluations, groups and shots | Independent paper reconstruction of all baseline counts | Matched logical/numeric results | All R/stage2/baseline/*.jsonl.gz; original results; data/derived_results.json.resource |
| Python replay agrees; DejaVu checks ordering separately | Same-class replay; five temporal projections | Runtime method; matched results | Results/log/input hashes; R/stage2/baseline/dejavu.log; ../formal/runtime.qtl |
| Bounded modeled probability and empirical success estimates are compatible | P1 at declared checkpoints | Figure 4; probability table | R/stage1/quantitative.json; raw kernel; storm.log; raw trace terminals; Wilson reconstruction |
| P2/P3 support agreement under the stated post-audit Holm analysis | P2 normal-approximation test; Holm family; P3 derived | Conditional-resource table and discussion | All first-success terminals; R/comparison/verdict_agreement.json for original marginal intervals; ../audit/stats_recompute.py; new recomputation in scripts/extract_results.py |
| Conditional means do not include failed-path expense | P2/P3 versus mean total expenditure | Conditional-resource and probability results | Full raw first-success/budget stops; modeled CDF; data/derived_results.json.resource |
| Sample size limits statistical resolution | Approximate 80%-power local score-test calculation | Statistical discussion | Final model probability and n; scripts/extract_results.py resolution calculation; audit F3 |
| Faults have distinct full verdict vectors and limited scenario diversity | L1–L4/N1–N4 vector; target detection; DejaVu | Figure 5 (fault matrix); original fault table remains ancillary | R/stage2/faults/results.json, raw/control traces and dejavu.log; audit F5–F8; scripts/figures/fault_discrepancies.py |
| Missing-evidence L1 is an evidence-classification artifact | Deleted counts; L1 D alongside numeric I | Figure 5 caption and text | Saved mutated/control traces; current checker; audit F5 |
| Reachable time-unrolled model size grows with the bound | Archived deterministic states/transitions | Figure 2 | P/additional_experiments/model_checking_scalability CSV/metadata; generator source |
| Final homogeneous DTMC has a fixed grid/phase size | Different representation from time unrolling | Model-cost explanation | R/stage1/gaussian.tra, gaussian.lab, quantitative.json |
| Model construction and checking costs have different boundaries | One construction timing; median checker timings | Figure 2 cost panel | Archived scalability metadata and CSV; explicit exports missing |
| Verification adds measured time in the separate simulator cost study | Independent condition medians and difference; bootstrap CI | Figure 3; runtime cost prose (exact ancillary table preserved) | T/runs.csv; all per-run run_summary.json; T/summary.json and completion_audit.json |
| No final matched-run overhead estimate is available | Missing uninstrumented timing baseline | Cost/limitations | Final run has no equivalent repeated baseline timing condition |
| Earlier logical model has its own property and timing counts | Distinct legacy controller/reachability study | Section IV-B generated prose; logical_scaling.tex ancillary data | ../../NuXmv Files/VQE_NuXmv_Refinement/results/*.txt; phase reachability CSV |
| Larger numeric and Estimator traces pass their recorded checker | Separate traces; later checker; no raw Estimator counts | Section IV-B generated prose; numeric_traces.tex ancillary data | Original JSONL traces; freshly saved data/numeric_trace_replay.json; checker source |
| Separate simulator/hardware runs pass online/replay at their budget | Runtime conformance, not matched Gaussian validation | Hardware table | Runtime campaign_summary.json; linked hashes, raw trace/evidence, reports |
| Noisy robustness differs from the ideal matched process | FakeJakarta success count, with different noise assumptions | Section IV-C noise-robustness prose | P/layer4_empirical/fakebackend_runs.jsonl and fakebackend_metadata.json |

## Corrections and unavailable evidence

- Original P2/P3 marginal bootstrap intervals and numerical estimates are retained;
  corrected compatibility is explicitly post-audit and multiplicity-adjusted.
- No claim of equality, equivalence, global PASS, or a combined proof theorem.
- The independent audit's 100,000-run and 20,000-run arrays are absent; no figure
  or newly verified numerical claim uses their narrative values.
- Archived time-unrolled explicit exports are absent. This limits retrospective
  raw-model verification of transition counts; recorded metadata/CSV are retained.
- No final matched-run overhead series or general numeric-verifier scaling study.
- The narrowed L4 and missing-evidence interpretations do not imply a source fix.

Full input hashes: `data/source_manifest.json`. Automated numerical and reference
checks: `data/paper_validation.json`; manual PDF inspection: `LAYOUT_REVIEW.md`.

## Review round 1 preservation

`manuscript.tex` and `manuscript.pdf` are unchanged references. The paper revision
is `manuscript_review1.tex`/PDF. `derived_results.json` and `source_manifest.json`
retain their initial hashes, preserving all measured and statistical results.
Eight additional prose macros are generated for the two small-table conversions.
All original macro values and the underlying experiment are unchanged. The
review log lists each removed-table disposition and the three new primary-source
citations. Preservation checks are in `data/revision_validation.json`.

## Requested figure follow-up

`manuscript_review2.tex` integrates the requested line-color changes and replaces
the main fault table with Figure 5. The matrix is generated directly from the
individual audited fault records. All forty categorical cells and the two
count columns are checked against the reconstructed results. The probability
and scalability point CSVs, all scientific results, the bibliography, and
review 1's source/PDF retain their before-follow-up hashes. No other paper
claims, configuration parameters, intervals, or verdicts are changed.
