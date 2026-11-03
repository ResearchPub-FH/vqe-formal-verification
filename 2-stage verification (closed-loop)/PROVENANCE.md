# Provenance

The implementation follows the experiment approved in this chat. It does not
modify the earlier experiments.

- `formal/VQETypes.dfy`, `VQEContracts.dfy`, `VQELemmas.dfy`, and
  `VQENumericKernels.dfy` are copied from the sibling `Dafny + Python trace
  checker/vqe_dafny` directory. `GroupGrid.dfy` adds the contracts needed by
  shared measurement groups and the finite-grid optimizer.
- The Hamiltonian, gate sequence, finite grid, initial indices, measurement
  decomposition, Gaussian construction and tie priority follow the sibling
  `Probabilistic verification - 2 methods comparision/h2_prism_fakebackend_workflow.py`.
  The statevector evaluation is vectorized here. Finite-shot execution is a
  direct ideal Born sampler and retains raw counts.
- The DejaVu runtime and pinned Scala compiler dependency manifest come from
  the sibling `VQE Runtime Verification - DejaVu copy` project. The compact QTL
  contract projections and batch replay bridge are new for this experiment.
- `closed_loop/checker.py` reconstructs numeric values independently from raw
  group counts and frozen coefficients; it does not call the execution scorer.

Source and evidence hashes in each Stage 1 report identify the precise versions
used. Existing artifacts and their reported numerical outcomes are not imported
as new results.
