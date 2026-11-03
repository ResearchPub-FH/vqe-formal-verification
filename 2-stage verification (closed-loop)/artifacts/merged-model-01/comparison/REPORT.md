# Two-stage verification: results

Configuration: `03b387a2e7fede7a78b71b5a25065f673af10bbb9193103dd9895866d10706be`. Stage 1 record: `ad0f09cfc34b36e61bfd0657f93f8f493c2afd7c630085fda26cf2345ab67613`.

Executed 400 baseline runs; 366 reached the declared ideal-energy target by 50 updates.
Physical shots: 124,581,888. Online/replay agreement: True.
Independent DejaVu temporal replay: 400/400 passed.

## Logical non-vacuity (Stage 1)

NuXmv status PROVED: 24/24 properties hold; 62/62 antecedent-witness, consequent-probe and branch queries have their expected result.
Defensive branches confirmed unreachable: `TRUE : ABORT`.

| Seeded mutant | Target contract | Killed | Detected by |
|---|---|---|---|
| M1_early_aggregation | L1 | True | L1 |
| M2_skipped_candidate | L2 | True | L2, L4 |
| M3_no_candidate_reset | L3 | True | L3, L4 |
| M4_stale_energy_ready | L3 | True | L3 |
| M5_skipped_rebind | L3 | True | L3 |
| M6_stale_binding | L3 | True | L3, L4 |
| M7_wrong_candidate | L3 | True | L3 |
| M8_stale_energy_epoch | L3 | True | L3, L4 |
| M9_measurement_error_ignored | L4 | True | L1, L4 |
| M10_budget_as_abort | L4 | True | L4 |
| M11_success_as_abort | L4 | True | L4 |
| M12_budget_overrun | L4 | True | L3, L4 |

## Logical and numeric contract matching

Each obligation counts the runtime events at which its antecedent was evaluated. A contract with an unexercised obligation is INCONCLUSIVE, never a vacuous AGREEMENT. Coverage: every completed baseline run matches the update-count equations.

| Contract | Stage 1 | Runtime verdict counts | Checks | Triggered obligations | Verdict agreement |
|---|---|---|---:|---|---|
| L1: Complete measurements precede candidate energy aggregation | PROVED | AGREEMENT: 400 | 324432 | groups_before_energy: 40,554 | AGREEMENT |
| L2: All three candidate validations precede optimizer commitment | PROVED | AGREEMENT: 400 | 135180 | validation_certified: 40,554<br>validations_before_commit: 13,518 | AGREEMENT |
| L3: Evaluation identity and parameter provenance remain current | PROVED | AGREEMENT: 400 | 1355400 | commit_identity_current: 13,518<br>evaluation_identity_current: 202,770 | AGREEMENT |
| L4: Termination is final and has the declared reason | PROVED | AGREEMENT: 400 | 244524 | terminal_reason: 400 | AGREEMENT |
| N1: Raw counts normalize to the reported expectations | PROVED | AGREEMENT: 400 | 446094 | expectation_reconstructed: 162,216 | AGREEMENT |
| N2: Declared coefficients and measurements produce the actual energy | PROVED | AGREEMENT: 400 | 351468 | energy_reconstructed: 40,554 | AGREEMENT |
| N3: Unique measurement groups determine physical shot consumption | PROVED | AGREEMENT: 400 | 257242 | allocation_checked: 121,662<br>cumulative_total_checked: 13,918 | AGREEMENT |
| N4: Candidate generation and selection preserve the parameter grid | PROVED | AGREEMENT: 400 | 460012 | candidates_generated: 13,518<br>selection_checked: 13,518 | AGREEMENT |

| DejaVu property | Runs exercised | Antecedent events |
|---|---:|---:|
| L1_groupsBeforeEnergy | 400/400 | 40,554 |
| L2_validationsBeforeCommit | 400/400 | 13,518 |
| L3_energyAfterBegin | 400/400 | 40,554 |
| L3_validationAfterEnergy | 400/400 | 40,554 |
| L4_noActivityAfterStop | 400/400 | 400 |

Maximum energy reconstruction error: 5.54223e-17 (allowed 1e-12).
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

Full verdict vector (A agreement, D disagreement, M assumption mismatch, I inconclusive, including unexercised obligations):

| Fault | L1 | L2 | L3 | L4 | N1 | N2 | N3 | N4 |
|---|---|---|---|---|---|---|---|---|
| coefficient_swap | A | I | I | A | A | D | A | I |
| corrupt_energy | A | I | I | A | A | D | A | I |
| missing_evidence | D | I | A | A | I | I | I | I |
| premature_update | I | D | I | A | I | I | I | I |
| shot_mismatch | I | I | I | A | I | I | M | I |

## Assumptions and boundaries

- Logical model abstracts measurements and arithmetic into counters, readiness flags and nondeterministic outcomes; L3's (iteration, candidate) version abstraction is strengthened by concrete runtime identity checks.
- Logical non-vacuity is checked on the same bounded abstraction: every antecedent disjunct is reachable, no consequent is invariant on its own, the defensive default branch is unreachable, and each seeded control mutant is detected by its contract.
- Dafny verifies real/integer kernels, not the entire Python program or a floating-point compiler refinement. Runtime checks actual observed outputs against exact rational reconstruction within frozen tolerances.
- Circuit generation, measurement-basis interpretation, event instrumentation, proof tools, and the independent checker are in the trusted base.
- Measurements follow ideal Born probabilities, independent across groups/candidates and executions; within-group correlations are retained.
- Gaussian selection is approximate; finite-shot ties use current/minus/plus priority, while the continuous Gaussian model has zero tie probability.
- Ideal-energy success is a simulator benchmark oracle, not a hardware-observed stopping certificate.
- The 50-update probability is the primary comparison. Other checkpoints and conditional means are supporting marginal comparisons, not a simultaneous-confidence claim.

The run records and compressed traces remain under `stage2/`. Verifier output, generated models, Gaussian kernels, and the sealed assurance record remain under `stage1/`. Corrections require a new Stage 1 output directory; old evidence is retained.
