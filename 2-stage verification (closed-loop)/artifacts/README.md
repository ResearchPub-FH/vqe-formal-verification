# Experiment evidence index

Use `merged-model-01/` for the delivered experiment (2026-10-27). Its Stage 1
record is gated by the merged logical model (`closed_loop/logical.py`: 24/24
properties, 62/62 non-vacuity queries, 12/12 mutants, PROVED). It was run with
Python 3.12.15 and NumPy 2.5.3 and reproduces `approved-experiment/` exactly:
366/400 successes and identical probability, resource, contract and fault-detection
results. Only the Stage 1 digests differ, and the fault verdict vectors now show
INCONCLUSIVE for obligations that never fired.

`approved-experiment/` is the earlier delivered run, gated by the 7-property
controller (audited by `../audit/nonvacuity_audit.py`). Its report, 400 baseline
traces, 50 fault tests, and Stage 1 record constitute one experiment with the
approved configuration. Do not pool it with `merged-model-01/`: both use the same seeds.

The following earlier snapshots are retained for provenance:

- `development-smoke-01/`: initial small-grid integration check.
- `smoke-verified/`: intermediate small-grid integration check.
- `primary/`: first full integration run, before exact floating-point error
  reporting and explicit optimizer-score logging were strengthened.
- `primary-v2/`: intermediate full run, before incomplete-evidence propagation
  was refined to prevent cascading false state discrepancies.

These outputs have different frozen source hashes and cannot be audited using
the final implementation. They are not additional independent experimental
samples: the full runs reuse the same frozen seed rule. Do not pool them.
The delivered result is exclusively `approved-experiment/`.

Runs of the current sources (Stage 1 non-vacuity gate, runtime obligation
counting, DejaVu trigger cross-check):

- `nonvacuity-smoke-01/`: small-grid end-to-end check.
- `nonvacuity-01/`: full run with the approved configuration and seed, using
  Storm 2.0.0 and NumPy 2.3.2. Bitwise reproduction of the approved sample
  needs NumPy 2.5.3 (AUDIT_REPORT F10); under 2.3.2, 102 of 400 runs diverge,
  giving 373/400 successes instead of 366/400. It is a separate sample under
  the same seed rule; do not pool it with `approved-experiment/`.

Non-vacuity evidence for the approved traces themselves is
`../audit/_out/nonvacuity/REPORT.md`, produced by `audit/nonvacuity_audit.py`.
