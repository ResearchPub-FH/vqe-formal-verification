# DejaVu property verdicts for the verified run

- Events checked: 2103 online, 2103 in replay.
- Events rejected: 0 online, 0 in replay.
- Properties obeyed: 68/68 online, 68/68 in replay.
- Properties violated: 0 online, 0 in replay.
- Overall status: pass online, pass in replay.
- Coverage: 55 EXERCISED, 7 NOT_APPLICABLE, 5 NOT_EXERCISED, 1 NESTED_NOT_EXERCISED.

`OBEYED` on a property that is not `EXERCISED` is vacuous: its trigger never occurred or cannot occur under this configuration.

| Level | Status online | Status replay | Findings online | Findings replay |
|---|---|---|---:|---:|
| intra_iteration | pass | pass | 0 | 0 |
| inter_iteration | pass | pass | 0 | 0 |
| run_level | pass | pass | 0 | 0 |

| Property | Online | Replay | Coverage | Trigger events | Violated at (online) |
|---|---|---|---|---:|---|
| `inter_askTellIntentUsesConfiguredProtocol` | OBEYED | OBEYED | EXERCISED | 49 |  |
| `inter_askTellProtocolConfiguredOnce` | OBEYED | OBEYED | EXERCISED | 1 |  |
| `inter_askTellUpdateUsesConfiguredProtocol` | OBEYED | OBEYED | EXERCISED | 49 |  |
| `inter_backendJobIdentityUnique` | OBEYED | OBEYED | EXERCISED | 50 |  |
| `inter_closeAfterCommittedUpdate` | OBEYED | OBEYED | EXERCISED | 50 |  |
| `inter_firstEvaluationIdentityUnique` | OBEYED | OBEYED | EXERCISED | 1 |  |
| `inter_firstIterationAfterConfiguredProtocol` | OBEYED | OBEYED | EXERCISED | 1 |  |
| `inter_iterationClosedOnce` | OBEYED | OBEYED | EXERCISED | 50 |  |
| `inter_nextAfterOptimizerUpdate` | OBEYED | OBEYED | EXERCISED | 49 |  |
| `inter_nextAfterPreviousClose` | OBEYED | OBEYED | EXERCISED | 49 |  |
| `inter_nextEvaluationIdentityUnique` | OBEYED | OBEYED | EXERCISED | 49 |  |
| `inter_nextIterationAfterConfiguredProtocol` | OBEYED | OBEYED | EXERCISED | 49 |  |
| `inter_opaqueAdvanceAfterClose` | OBEYED | OBEYED | NOT_APPLICABLE | 0 |  |
| `inter_opaqueAdvanceBeforeLimit` | OBEYED | OBEYED | NOT_APPLICABLE | 0 |  |
| `inter_opaqueAdvanceOnce` | OBEYED | OBEYED | NOT_APPLICABLE | 0 |  |
| `inter_opaqueAdvanceUsesConfiguredProtocol` | OBEYED | OBEYED | NOT_APPLICABLE | 0 |  |
| `inter_opaqueProtocolConfiguredOnce` | OBEYED | OBEYED | NOT_APPLICABLE | 0 |  |
| `inter_previousEnergyIsLastCheckpoint` | OBEYED | OBEYED | EXERCISED | 49 |  |
| `inter_submissionIdentityUnique` | OBEYED | OBEYED | EXERCISED | 50 |  |
| `inter_updateAppliedOnce` | OBEYED | OBEYED | EXERCISED | 49 |  |
| `inter_updateIntentAfterRelease` | OBEYED | OBEYED | EXERCISED | 49 |  |
| `inter_updateIntentOnce` | OBEYED | OBEYED | EXERCISED | 49 |  |
| `inter_updateOnlyWhenNotConverged` | OBEYED | OBEYED | EXERCISED | 49 |  |
| `inter_updatedAfterIntent` | OBEYED | OBEYED | EXERCISED | 49 |  |
| `intra_abortAfterFailure` | OBEYED | OBEYED | NOT_EXERCISED | 0 |  |
| `intra_allDeclaredTermsObserved` | OBEYED | OBEYED | EXERCISED | 50 |  |
| `intra_bindingAfterStart` | OBEYED | OBEYED | EXERCISED | 50 |  |
| `intra_bindingOnce` | OBEYED | OBEYED | EXERCISED | 50 |  |
| `intra_closeAfterRelease` | OBEYED | OBEYED | EXERCISED | 50 |  |
| `intra_energyAfterSeal` | OBEYED | OBEYED | EXERCISED | 50 |  |
| `intra_energyOnce` | OBEYED | OBEYED | EXERCISED | 50 |  |
| `intra_firstCheckAfterEnergy` | OBEYED | OBEYED | EXERCISED | 1 |  |
| `intra_firstCheckOnce` | OBEYED | OBEYED | EXERCISED | 1 |  |
| `intra_nextCheckAfterEnergy` | OBEYED | OBEYED | EXERCISED | 49 |  |
| `intra_nextCheckOnce` | OBEYED | OBEYED | EXERCISED | 49 |  |
| `intra_oneSubmissionPerIteration` | OBEYED | OBEYED | EXERCISED | 50 |  |
| `intra_passAfterCheck` | OBEYED | OBEYED | EXERCISED | 50 |  |
| `intra_passOnce` | OBEYED | OBEYED | EXERCISED | 50 |  |
| `intra_releaseAfterPass` | OBEYED | OBEYED | EXERCISED | 50 |  |
| `intra_releaseOnce` | OBEYED | OBEYED | EXERCISED | 50 |  |
| `intra_sealAfterSubmission` | OBEYED | OBEYED | EXERCISED | 50 |  |
| `intra_sealOnce` | OBEYED | OBEYED | EXERCISED | 50 |  |
| `intra_submitAfterBinding` | OBEYED | OBEYED | EXERCISED | 50 |  |
| `intra_submittedAfterIntent` | OBEYED | OBEYED | EXERCISED | 50 |  |
| `intra_submittedOnce` | OBEYED | OBEYED | EXERCISED | 50 |  |
| `intra_termAfterSubmission` | OBEYED | OBEYED | EXERCISED | 200 |  |
| `intra_termDeclaredOnce` | OBEYED | OBEYED | EXERCISED | 200 |  |
| `intra_termExpectedAfterBinding` | OBEYED | OBEYED | EXERCISED | 200 |  |
| `intra_termObservedOnce` | OBEYED | OBEYED | EXERCISED | 200 |  |
| `intra_termWasDeclared` | OBEYED | OBEYED | EXERCISED | 200 |  |
| `run_abortAfterFailure` | OBEYED | OBEYED | NOT_EXERCISED | 0 |  |
| `run_abortIsFirstTerminal` | OBEYED | OBEYED | NOT_EXERCISED | 0 |  |
| `run_activityAfterMatchingStart` | OBEYED | OBEYED | EXERCISED | 1050 |  |
| `run_closeAfterOptimizerProtocol` | OBEYED | OBEYED | EXERCISED | 1 |  |
| `run_closeAfterTerminal` | OBEYED | OBEYED | EXERCISED | 1 |  |
| `run_closeOnce` | OBEYED | OBEYED | EXERCISED | 1 |  |
| `run_convergedAfterTrueClose` | OBEYED | OBEYED | NOT_EXERCISED | 0 |  |
| `run_convergedIsFirstTerminal` | OBEYED | OBEYED | NOT_EXERCISED | 0 |  |
| `run_failureRequiresAbortAtClose` | OBEYED | OBEYED | NESTED_NOT_EXERCISED | 1 |  |
| `run_iterationLimitOnce` | OBEYED | OBEYED | EXERCISED | 1 |  |
| `run_maxAfterLimitAndFalseClose` | OBEYED | OBEYED | EXERCISED | 1 |  |
| `run_maxIsFirstTerminal` | OBEYED | OBEYED | EXERCISED | 1 |  |
| `run_noActivityAfterClose` | OBEYED | OBEYED | EXERCISED | 1050 |  |
| `run_noActivityAfterTerminal` | OBEYED | OBEYED | EXERCISED | 1050 |  |
| `run_normalTerminalWithoutFailure` | OBEYED | OBEYED | EXERCISED | 1 |  |
| `run_optimizerStopAfterFalseClose` | OBEYED | OBEYED | NOT_APPLICABLE | 0 |  |
| `run_optimizerStopIsFirstTerminal` | OBEYED | OBEYED | NOT_APPLICABLE | 0 |  |
| `run_startOnce` | OBEYED | OBEYED | EXERCISED | 1 |  |
