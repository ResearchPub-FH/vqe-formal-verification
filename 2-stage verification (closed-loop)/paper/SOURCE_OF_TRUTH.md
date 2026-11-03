# Reconstructed source of truth

Final run: `approved-experiment`; audit: `AUDIT_REPORT.md` dated 2026-10-06.

Configuration digest: `03b387a2e7fede7a78b71b5a25065f673af10bbb9193103dd9895866d10706be`. Stage 1 seal: `b3de315ae48c909ca80e275fafde44deb567ec68cad3b0de366e93a93c53c3ca`.

The complete machine-readable result list is `data/derived_results.json`; every quantitative prose value is generated in `data/claim_values.json` and `data/numbers.tex`. All input hashes are in `data/source_manifest.json`.

## Reporting decisions

- Primary: final sealed run only. Earlier same-seed directories are excluded.
- P2/P3: retain the original marginal intervals; report compatibility after the audit-recommended Holm correction. This is a post-audit reporting correction, not a rerun, reseeding, or a preregistered equivalence test.
- L4: agreement is restricted to prospectively checked terminal absorption and budget bounds; termination reasons have runtime evidence only.
- N1/N3: parity mapping and unique physical group identity remain assumptions; Dafny does not establish them.
- Baseline online/replay uses the same Python class. DejaVu independently checks only its five temporal projections.
- All five fault rows retain their full vectors, including the L1 missing-evidence reporting artifact.
- The benchmark is described by its actual two-qubit operator; legacy H2 filenames remain unchanged.
- Archived time-unrolled scalability and September runtime costs are separate layer-specific evaluations; no pooling or cost claim for the final closed-loop run.
- Independent audit Monte Carlo arrays are missing; no numerical re-use or plotted supplement.
- No joint theorem, physical-backend correctness, Gaussian approximation-error certificate, automatic repair loop, or general scalability law is claimed.
