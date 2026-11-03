# Two-stage verification: results

Configuration: `0988fc089b0bbec6c0095dd1b4a7d94d35e54c6962f005c1f1d64bde8cfa0c15`. Stage 1 record: `245821aeed61225fb8bf4d57b8052c32f9c1058acb4d24a2fb5199e7d0e77f06`.

Executed 3 baseline runs; 0 reached the declared ideal-energy target by 3 updates.
Physical shots: 82,944. Online/replay agreement: True.
Independent DejaVu temporal replay: 3/3 passed.

## Logical and numeric contract matching

| Contract | Stage 1 | Runtime verdict counts | Checks | Verdict agreement |
|---|---|---|---:|---|
| L1: Complete measurements precede candidate energy aggregation | PROVED | AGREEMENT: 3 | 216 | AGREEMENT |
| L2: All three candidate validations precede optimizer commitment | PROVED | AGREEMENT: 3 | 54 | AGREEMENT |
| L3: Evaluation identity and parameter provenance remain current | PROVED | AGREEMENT: 3 | 927 | AGREEMENT |
| L4: Termination is final and has the declared reason | PROVED | AGREEMENT: 3 | 171 | AGREEMENT |
| N1: Raw counts normalize to the reported expectations | PROVED | AGREEMENT: 3 | 297 | AGREEMENT |
| N2: Declared coefficients and measurements produce the actual energy | PROVED | AGREEMENT: 3 | 225 | AGREEMENT |
| N3: Unique measurement groups determine physical shot consumption | PROVED | AGREEMENT: 3 | 174 | AGREEMENT |
| N4: Candidate generation and selection preserve the parameter grid | PROVED | AGREEMENT: 3 | 165 | AGREEMENT |

Maximum energy reconstruction error: 0 (allowed 1e-12).
Maximum expectation reconstruction error: 0.

## Probabilistic contract matching

| Update bound | Gaussian/Storm probability | Runtime successes | Runtime probability | 95% Wilson interval | Verdict agreement |
|---:|---:|---:|---:|---|---|
| 1 | 0.000000 | 0/3 | 0.000000 | [0.000000, 0.561497] | AGREEMENT |
| 3 (primary) | 0.000000 | 0/3 | 0.000000 | [0.000000, 0.561497] | AGREEMENT |

| Contract | Model conditional mean | Runtime conditional mean | 95% bootstrap interval | Verdict agreement |
|---|---:|---:|---|---|
| P2 | None | None | None | INCONCLUSIVE |
| P3 | None | None | None | INCONCLUSIVE |

Probabilistic AGREEMENT means statistical compatibility, not equality of distributions. Supporting intervals are marginal; no joint confidence claim. P3 scales P2 by the fixed shots per update.

Conditional means come from Python propagation of the same Gaussian DTMC; Storm independently checks the listed bounded reachability probabilities. No reward-query result is claimed.

## Controlled faults

| Fault | Contract | Expected verdict | Detected/tested | Scope |
|---|---|---|---:|---|
| coefficient_swap | N2 | DISAGREEMENT | 1/1 | controlled execution |
| corrupt_energy | N2 | DISAGREEMENT | 1/1 | controlled execution |
| missing_evidence | N1 | INCONCLUSIVE | 1/1 | saved-trace mutation; no execution mutation |
| premature_update | L2 | DISAGREEMENT | 1/1 | controlled execution |
| shot_mismatch | N3 | ASSUMPTION_MISMATCH | 1/1 | controlled execution |

## Assumptions and boundaries

- Logical model abstracts measurements and arithmetic into counters/readiness and nondeterministic outcomes; L3's epoch abstraction is strengthened by concrete runtime identity checks.
- Dafny verifies real/integer kernels, not the entire Python program or a floating-point compiler refinement. Runtime checks actual observed outputs against exact rational reconstruction within frozen tolerances.
- Circuit generation, measurement-basis interpretation, event instrumentation, proof tools, and the independent checker are in the trusted base.
- Measurements follow ideal Born probabilities, independent across groups/candidates and executions; within-group correlations are retained.
- Gaussian selection is approximate; finite-shot ties use current/minus/plus priority, while the continuous Gaussian model has zero tie probability.
- Ideal-energy success is a simulator benchmark oracle, not a hardware-observed stopping certificate.
- The 50-update probability is the primary comparison. Other checkpoints and conditional means are supporting marginal comparisons, not a simultaneous-confidence claim.

The run records and compressed traces remain under `stage2/`. Verifier output, generated models, Gaussian kernels, and the sealed assurance record remain under `stage1/`. Corrections require a new Stage 1 output directory; old evidence is retained.
