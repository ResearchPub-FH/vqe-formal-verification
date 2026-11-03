# H2 Sampler comparison result package

This directory contains derived, human-readable tables for the verified
September 7–8, 2026 H2 experiment. The authoritative raw data remains in the
trace and evidence JSONL files listed in `campaign_summary.json`.

## Files

- `campaign_summary.json`: fixed design, acceptance criteria, run metrics,
  result hashes, and hardware/statevector comparison.
- `hardware_evaluations.csv`: one row per IBM energy evaluation, including
  parameters, four expectations, energy, best energy so far, job timestamps,
  and QPU charge time.
- `hardware_pubs.csv`: one row per IBM PUB with counts, negative-parity count,
  expectation, shot totals, circuit hashes, layout, and raw-evidence hashes.
- `hardware_jobs.json`: one deduplicated metadata record per IBM job. It is
  derived offline from metadata already embedded in the evidence sidecar.
- `statevector_evaluations.csv` and `statevector_pubs.csv`: matching comparator
  tables using the same columns.
- `SHA256SUMS`: checksums for the generated files present when the analyzer ran.

The CSVs retain complete count dictionaries but omit the 1,024 ordered
bitstrings and packed `BitArray` bytes for each PUB to stay compact. Those
lossless fields remain in:

```text
artifacts/evidence/h2_ibm_marrakesh_sampler_20260907.jsonl
artifacts/evidence/h2_statevector_sampler_20260907.jsonl
```

## Regeneration

The analyzer refuses to overwrite this directory. Regenerate into a new path:

```bash
python tools/summarize_sampler_campaign.py \
  --output-dir artifacts/results/h2_sampler_comparison_REGENERATED
```

The command exits unsuccessfully if strict sidecar validation, parity or energy
reconstruction, ask/tell continuity, job uniqueness, fixed-layout checks, shot
accounting, online/replay agreement, or terminal semantics fail.

