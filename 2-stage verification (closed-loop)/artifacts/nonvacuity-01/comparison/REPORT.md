# Two-stage verification: results

Configuration: `03b387a2e7fede7a78b71b5a25065f673af10bbb9193103dd9895866d10706be`. Stage 1 record: `034f7081b3741d577f38dad670fe8fa37e336f1b7c196d8c6de148ccc9afee31`.

Executed 400 baseline runs; 373 reached the declared ideal-energy target by 50 updates.
Physical shots: 124,416,000. Online/replay agreement: True.
Independent DejaVu temporal replay: 400/400 passed.

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
| L1: Complete measurements precede candidate energy aggregation | PROVED | AGREEMENT: 400 | 324000 | groups_before_energy: 40,500 | AGREEMENT |
| L2: All three candidate validations precede optimizer commitment | PROVED | AGREEMENT: 400 | 135000 | validation_certified: 40,500<br>validations_before_commit: 13,500 | AGREEMENT |
| L3: Evaluation identity and parameter provenance remain current | PROVED | AGREEMENT: 400 | 1353600 | commit_identity_current: 13,500<br>evaluation_identity_current: 202,500 | AGREEMENT |
| L4: Termination is final and has the declared reason | PROVED | AGREEMENT: 400 | 244200 | terminal_reason: 400 | AGREEMENT |
| N1: Raw counts normalize to the reported expectations | PROVED | AGREEMENT: 400 | 445500 | expectation_reconstructed: 162,000 | AGREEMENT |
| N2: Declared coefficients and measurements produce the actual energy | PROVED | AGREEMENT: 400 | 351000 | energy_reconstructed: 40,500 | AGREEMENT |
| N3: Unique measurement groups determine physical shot consumption | PROVED | AGREEMENT: 400 | 256900 | allocation_checked: 121,500<br>cumulative_total_checked: 13,900 | AGREEMENT |
| N4: Candidate generation and selection preserve the parameter grid | PROVED | AGREEMENT: 400 | 459400 | candidates_generated: 13,500<br>selection_checked: 13,500 | AGREEMENT |

| DejaVu property | Runs exercised | Antecedent events |
|---|---:|---:|
| L1_groupsBeforeEnergy | 400/400 | 40,500 |
| L2_validationsBeforeCommit | 400/400 | 13,500 |
| L3_energyAfterBegin | 400/400 | 40,500 |
| L3_validationAfterEnergy | 400/400 | 40,500 |
| L4_noActivityAfterStop | 400/400 | 400 |

Maximum energy reconstruction error: 5.54223e-17 (allowed 1e-12).
Maximum expectation reconstruction error: 0.

## Probabilistic contract matching

| Update bound | Gaussian/Storm probability | Runtime successes | Runtime probability | 95% Wilson interval | Verdict agreement |
|---:|---:|---:|---:|---|---|
| 10 | 0.000000 | 0/400 | 0.000000 | [0.000000, 0.009512] | AGREEMENT |
| 20 | 0.000000 | 0/400 | 0.000000 | [0.000000, 0.009512] | AGREEMENT |
| 30 | 0.383940 | 168/400 | 0.420000 | [0.372618, 0.468904] | AGREEMENT |
| 40 | 0.756253 | 307/400 | 0.767500 | [0.723677, 0.806234] | AGREEMENT |
| 50 (primary) | 0.928027 | 373/400 | 0.932500 | [0.903573, 0.953199] | AGREEMENT |

| Contract | Model conditional mean | Runtime conditional mean | 95% bootstrap interval | Verdict agreement |
|---|---:|---:|---|---|
| P2 | 33.11118709897007 | 32.57372654155496 | [31.85254691689008, 33.27620643431635] | AGREEMENT |
| P3 | 305152.70030410815 | 300199.4638069705 | [293553.072386059, 306673.5184986595] | AGREEMENT |

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

- Logical model abstracts measurements and arithmetic into counters/readiness and nondeterministic outcomes; L3's epoch abstraction is strengthened by concrete runtime identity checks.
- Logical non-vacuity is checked on the same bounded abstraction: every antecedent disjunct is reachable, no consequent is invariant on its own, the defensive default branch is unreachable, and each seeded control mutant is detected by its contract.
- Dafny verifies real/integer kernels, not the entire Python program or a floating-point compiler refinement. Runtime checks actual observed outputs against exact rational reconstruction within frozen tolerances.
- Circuit generation, measurement-basis interpretation, event instrumentation, proof tools, and the independent checker are in the trusted base.
- Measurements follow ideal Born probabilities, independent across groups/candidates and executions; within-group correlations are retained.
- Gaussian selection is approximate; finite-shot ties use current/minus/plus priority, while the continuous Gaussian model has zero tie probability.
- Ideal-energy success is a simulator benchmark oracle, not a hardware-observed stopping certificate.
- The 50-update probability is the primary comparison. Other checkpoints and conditional means are supporting marginal comparisons, not a simultaneous-confidence claim.

The run records and compressed traces remain under `stage2/`. Verifier output, generated models, Gaussian kernels, and the sealed assurance record remain under `stage1/`. Corrections require a new Stage 1 output directory; old evidence is retained.
