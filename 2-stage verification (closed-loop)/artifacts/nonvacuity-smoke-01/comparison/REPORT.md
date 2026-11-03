# Two-stage verification: results

Configuration: `0988fc089b0bbec6c0095dd1b4a7d94d35e54c6962f005c1f1d64bde8cfa0c15`. Stage 1 record: `224d6047bd4339b646d374aa239ef59c4a0ea6053d1c0bdf2c1ff069039774f9`.

Executed 3 baseline runs; 0 reached the declared ideal-energy target by 3 updates.
Physical shots: 82,944. Online/replay agreement: True.
Independent DejaVu temporal replay: 3/3 passed.

## Logical non-vacuity (Stage 1)

NuXmv status PROVED: 10/10 properties hold; 39/39 antecedent-witness, consequent-probe and branch queries have their expected result.
Defensive branches confirmed unreachable: `TRUE : aborted`.

| Seeded mutant | Target contract | Killed | Detected by |
|---|---|---|---|
| M1_early_aggregate | L1 | True | L1 |
| M2_skip_candidate | L2 | True | L2 |
| M3_no_ready_reset | L3 | True | L3, L4 |
| M4_budget_as_abort | L4 | True | L4 |
| M5_stale_energy | L3 | True | L3 |
| M6_success_as_abort | L4 | True | L4 |

## Logical and numeric contract matching

Each obligation counts the runtime events at which its antecedent was evaluated. A contract with an unexercised obligation is INCONCLUSIVE, never a vacuous AGREEMENT. Coverage: every completed baseline run matches the update-count equations.

| Contract | Stage 1 | Runtime verdict counts | Checks | Triggered obligations | Verdict agreement |
|---|---|---|---:|---|---|
| L1: Complete measurements precede candidate energy aggregation | PROVED | AGREEMENT: 3 | 216 | groups_before_energy: 27 | AGREEMENT |
| L2: All three candidate validations precede optimizer commitment | PROVED | AGREEMENT: 3 | 90 | validation_certified: 27<br>validations_before_commit: 9 | AGREEMENT |
| L3: Evaluation identity and parameter provenance remain current | PROVED | AGREEMENT: 3 | 927 | commit_identity_current: 9<br>evaluation_identity_current: 135 | AGREEMENT |
| L4: Termination is final and has the declared reason | PROVED | AGREEMENT: 3 | 171 | terminal_reason: 3 | AGREEMENT |
| N1: Raw counts normalize to the reported expectations | PROVED | AGREEMENT: 3 | 297 | expectation_reconstructed: 108 | AGREEMENT |
| N2: Declared coefficients and measurements produce the actual energy | PROVED | AGREEMENT: 3 | 234 | energy_reconstructed: 27 | AGREEMENT |
| N3: Unique measurement groups determine physical shot consumption | PROVED | AGREEMENT: 3 | 174 | allocation_checked: 81<br>cumulative_total_checked: 12 | AGREEMENT |
| N4: Candidate generation and selection preserve the parameter grid | PROVED | AGREEMENT: 3 | 309 | candidates_generated: 9<br>selection_checked: 9 | AGREEMENT |

| DejaVu property | Runs exercised | Antecedent events |
|---|---:|---:|
| L1_groupsBeforeEnergy | 3/3 | 27 |
| L2_validationsBeforeCommit | 3/3 | 9 |
| L3_energyAfterBegin | 3/3 | 27 |
| L3_validationAfterEnergy | 3/3 | 27 |
| L4_noActivityAfterStop | 3/3 | 3 |

Maximum energy reconstruction error: 2.06946e-17 (allowed 1e-12).
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

Full verdict vector (A agreement, D disagreement, M assumption mismatch, I inconclusive, including unexercised obligations):

| Fault | L1 | L2 | L3 | L4 | N1 | N2 | N3 | N4 |
|---|---|---|---|---|---|---|---|---|
| coefficient_swap | A | I | I | A | A | D | A | I |
| corrupt_energy | A | I | I | A | A | D | A | I |
| missing_evidence | D | I | A | A | I | I | I | I |
| premature_update | I | D | I | A | I | I | I | I |
| shot_mismatch | I | I | I | A | I | I | M | I |

## Assumptions and boundaries

- Logical model abstracts measurements and arithmetic into counters/readiness and nondeterministic outcomes; L3's epoch abstraction is strengthened by concrete runtime identity checks.
- Logical non-vacuity is checked on the same bounded abstraction: every antecedent disjunct is reachable, no consequent is invariant on its own, the defensive default branch is unreachable, and each seeded control mutant is detected by its contract.
- Dafny verifies real/integer kernels, not the entire Python program or a floating-point compiler refinement. Runtime checks actual observed outputs against exact rational reconstruction within frozen tolerances.
- Circuit generation, measurement-basis interpretation, event instrumentation, proof tools, and the independent checker are in the trusted base.
- Measurements follow ideal Born probabilities, independent across groups/candidates and executions; within-group correlations are retained.
- Gaussian selection is approximate; finite-shot ties use current/minus/plus priority, while the continuous Gaussian model has zero tie probability.
- Ideal-energy success is a simulator benchmark oracle, not a hardware-observed stopping certificate.
- The 50-update probability is the primary comparison. Other checkpoints and conditional means are supporting marginal comparisons, not a simultaneous-confidence claim.

The run records and compressed traces remain under `stage2/`. Verifier output, generated models, Gaussian kernels, and the sealed assurance record remain under `stage1/`. Corrections require a new Stage 1 output directory; old evidence is retained.
