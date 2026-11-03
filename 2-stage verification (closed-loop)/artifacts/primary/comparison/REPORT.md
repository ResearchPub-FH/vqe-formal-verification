# Two-stage verification: results

Configuration: `03b387a2e7fede7a78b71b5a25065f673af10bbb9193103dd9895866d10706be`. Stage 1 record: `9dac5c0876e2b0a06e79bb17c2b7c3086419b176cdefa6225fd7821b656d8c36`.

Executed 400 baseline runs; 366 reached the declared ideal-energy target by 50 updates.
Physical shots: 124,581,888. Online/replay agreement: True.
Independent DejaVu temporal replay: 400/400 passed.

## Logical and numeric contract matching

| Contract | Stage 1 | Runtime verdict counts | Checks | Verdict agreement |
|---|---|---|---:|---|
| L1: Complete measurements precede candidate energy aggregation | PROVED | AGREEMENT: 400 | 324432 | AGREEMENT |
| L2: All three candidate validations precede optimizer commitment | PROVED | AGREEMENT: 400 | 81108 | AGREEMENT |
| L3: Evaluation identity and parameter provenance remain current | PROVED | AGREEMENT: 400 | 1355400 | AGREEMENT |
| L4: Termination is final and has the declared reason | PROVED | AGREEMENT: 400 | 244524 | AGREEMENT |
| N1: Raw counts normalize to the reported expectations | PROVED | AGREEMENT: 400 | 446094 | AGREEMENT |
| N2: Declared coefficients and measurements produce the actual energy | PROVED | AGREEMENT: 400 | 337950 | AGREEMENT |
| N3: Unique measurement groups determine physical shot consumption | PROVED | AGREEMENT: 400 | 257242 | AGREEMENT |
| N4: Candidate generation and selection preserve the parameter grid | PROVED | AGREEMENT: 400 | 446494 | AGREEMENT |

Maximum energy reconstruction error: 0 (allowed 1e-12).
Maximum expectation reconstruction error: 0.

## Probabilistic contract matching

| Update bound | Gaussian/Storm probability | Runtime successes | Runtime probability | 95% Wilson interval | Verdict agreement |
|---:|---:|---:|---:|---|---|
| 10 | 0.000000 | 0/400 | 0.000000 | [0.000000, 0.009512] | AGREEMENT |
| 20 | 0.000000 | 0/400 | 0.000000 | [0.000000, 0.009512] | AGREEMENT |
| 30 | 0.383940 | 169/400 | 0.422500 | [0.375055, 0.471419] | AGREEMENT |
| 40 | 0.756253 | 307/400 | 0.767500 | [0.723677, 0.806234] | AGREEMENT |
| 50 (primary) | 0.928027 | 366/400 | 0.915000 | [0.883568, 0.938537] | AGREEMENT |

| Contract | Model conditional mean | Runtime conditional mean | 95% bootstrap interval | Verdict agreement |
|---|---:|---:|---|---|
| P2 | 33.111187098970056 | 32.2896174863388 | [31.579234972677597, 32.994535519125684] | DISAGREEMENT |
| P3 | 305152.70030410803 | 297581.11475409835 | [291034.2295081967, 304077.6393442623] | DISAGREEMENT |

Probabilistic AGREEMENT means statistical compatibility, not equality of distributions. Supporting intervals are marginal; no joint confidence claim. P3 scales P2 by the fixed shots per update.

Conditional means come from Python propagation of the same Gaussian DTMC; Storm independently checks the listed bounded reachability probabilities. No reward-query result is claimed.

## Controlled faults

| Fault | Contract | Expected verdict | Detected/tested | Scope |
|---|---|---|---:|---|
| coefficient_swap | N2 | DISAGREEMENT | 10/10 | controlled execution |
| corrupt_energy | N2 | DISAGREEMENT | 10/10 | controlled execution |
| missing_evidence | N1 | INCONCLUSIVE | 10/10 | saved-trace mutation; no execution mutation |
| premature_update | L2 | DISAGREEMENT | 10/10 | controlled execution |
| shot_mismatch | N3 | ASSUMPTION_MISMATCH | 10/10 | controlled execution |

## Assumptions and boundaries

- Logical model abstracts measurements and arithmetic into counters/readiness and nondeterministic outcomes; L3's epoch abstraction is strengthened by concrete runtime identity checks.
- Dafny verifies real/integer kernels, not the entire Python program or a floating-point compiler refinement. Runtime checks actual observed outputs against exact rational reconstruction within frozen tolerances.
- Circuit generation, measurement-basis interpretation, event instrumentation, proof tools, and the independent checker are in the trusted base.
- Measurements follow ideal Born probabilities, independent across groups/candidates and executions; within-group correlations are retained.
- Gaussian selection is approximate; finite-shot ties use current/minus/plus priority, while the continuous Gaussian model has zero tie probability.
- Ideal-energy success is a simulator benchmark oracle, not a hardware-observed stopping certificate.
- The 50-update probability is the primary comparison. Other checkpoints and conditional means are supporting marginal comparisons, not a simultaneous-confidence claim.

The run records and compressed traces remain under `stage2/`. Verifier output, generated models, Gaussian kernels, and the sealed assurance record remain under `stage1/`. Corrections require a new Stage 1 output directory; old evidence is retained.
