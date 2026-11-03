# DejaVu property coverage: `h2_statevector_sampler_converging_20261025.jsonl`

Configuration: optimizer_protocol = ask-tell, allow_optimizer_stopped = False, max_iterations = 100.

| Status | Properties |
|---|---:|
| EXERCISED | 54 |
| NOT_APPLICABLE | 7 |
| NOT_EXERCISED | 6 |
| NESTED_NOT_EXERCISED | 1 |

A PASS on a NOT_EXERCISED or NESTED_NOT_EXERCISED property is vacuous for this trace; NOT_APPLICABLE properties cannot fire under the recorded configuration.

| Property | Status | Trigger events | Detail |
|---|---|---|---|
| intra_abortAfterFailure | NOT_EXERCISED | iterationAborted: 0 |  |
| run_abortAfterFailure | NOT_EXERCISED | runAborted: 0 |  |
| run_abortIsFirstTerminal | NOT_EXERCISED | runAborted: 0 |  |
| run_iterationLimitOnce | NOT_EXERCISED | iterationLimitReached: 0 |  |
| run_maxAfterLimitAndFalseClose | NOT_EXERCISED | runMaxIterations: 0 |  |
| run_maxIsFirstTerminal | NOT_EXERCISED | runMaxIterations: 0 |  |
| run_failureRequiresAbortAtClose | NESTED_NOT_EXERCISED | runClosed: 1 | nested antecedent criticalFail: 0 |
| inter_opaqueAdvanceAfterClose | NOT_APPLICABLE | opaqueOptimizerAdvanced: 0 | not applicable: opaqueOptimizerAdvanced |
| inter_opaqueAdvanceBeforeLimit | NOT_APPLICABLE | opaqueOptimizerAdvanced: 0 | not applicable: opaqueOptimizerAdvanced |
| inter_opaqueAdvanceOnce | NOT_APPLICABLE | opaqueOptimizerAdvanced: 0 | not applicable: opaqueOptimizerAdvanced |
| inter_opaqueAdvanceUsesConfiguredProtocol | NOT_APPLICABLE | opaqueOptimizerAdvanced: 0 | not applicable: opaqueOptimizerAdvanced |
| inter_opaqueProtocolConfiguredOnce | NOT_APPLICABLE | optimizerOpaqueConfigured: 0 | not applicable: optimizerOpaqueConfigured |
| run_optimizerStopAfterFalseClose | NOT_APPLICABLE | runOptimizerStopped: 0 | not applicable: runOptimizerStopped |
| run_optimizerStopIsFirstTerminal | NOT_APPLICABLE | runOptimizerStopped: 0 | not applicable: runOptimizerStopped |
| inter_askTellIntentUsesConfiguredProtocol | EXERCISED | optimizerUpdateIntent: 57 |  |
| inter_askTellProtocolConfiguredOnce | EXERCISED | optimizerAskTellConfigured: 1 |  |
| inter_askTellUpdateUsesConfiguredProtocol | EXERCISED | optimizerUpdated: 57 |  |
| inter_backendJobIdentityUnique | EXERCISED | jobSubmitted: 58 |  |
| inter_closeAfterCommittedUpdate | EXERCISED | iterationClosed: 58 | nested antecedent optimizerUpdateIntent: 57 |
| inter_firstEvaluationIdentityUnique | EXERCISED | firstIterationStarted: 1 |  |
| inter_firstIterationAfterConfiguredProtocol | EXERCISED | firstIterationStarted: 1 |  |
| inter_iterationClosedOnce | EXERCISED | iterationClosed: 58 |  |
| inter_nextAfterOptimizerUpdate | EXERCISED | nextIterationStarted: 57 |  |
| inter_nextAfterPreviousClose | EXERCISED | nextIterationStarted: 57 |  |
| inter_nextEvaluationIdentityUnique | EXERCISED | nextIterationStarted: 57 |  |
| inter_nextIterationAfterConfiguredProtocol | EXERCISED | nextIterationStarted: 57 |  |
| inter_previousEnergyIsLastCheckpoint | EXERCISED | nextConvergenceChecked: 57 |  |
| inter_submissionIdentityUnique | EXERCISED | jobSubmitIntent: 58 |  |
| inter_updateAppliedOnce | EXERCISED | optimizerUpdated: 57 |  |
| inter_updateIntentAfterRelease | EXERCISED | optimizerUpdateIntent: 57 |  |
| inter_updateIntentOnce | EXERCISED | optimizerUpdateIntent: 57 |  |
| inter_updateOnlyWhenNotConverged | EXERCISED | optimizerUpdateIntent: 57 |  |
| inter_updatedAfterIntent | EXERCISED | optimizerUpdated: 57 |  |
| intra_allDeclaredTermsObserved | EXERCISED | measurementsSealed: 58 | nested antecedent termExpected: 232 |
| intra_bindingAfterStart | EXERCISED | parametersBound: 58 |  |
| intra_bindingOnce | EXERCISED | parametersBound: 58 |  |
| intra_closeAfterRelease | EXERCISED | iterationClosed: 58 |  |
| intra_energyAfterSeal | EXERCISED | numericValid: 58 |  |
| intra_energyOnce | EXERCISED | numericValid: 58 |  |
| intra_firstCheckAfterEnergy | EXERCISED | firstConvergenceChecked: 1 |  |
| intra_firstCheckOnce | EXERCISED | firstConvergenceChecked: 1 |  |
| intra_nextCheckAfterEnergy | EXERCISED | nextConvergenceChecked: 57 |  |
| intra_nextCheckOnce | EXERCISED | nextConvergenceChecked: 57 |  |
| intra_oneSubmissionPerIteration | EXERCISED | jobSubmitIntent: 58 |  |
| intra_passAfterCheck | EXERCISED | iterationPass: 58 |  |
| intra_passOnce | EXERCISED | iterationPass: 58 |  |
| intra_releaseAfterPass | EXERCISED | objectiveReleaseIntent: 58 |  |
| intra_releaseOnce | EXERCISED | objectiveReleaseIntent: 58 |  |
| intra_sealAfterSubmission | EXERCISED | measurementsSealed: 58 |  |
| intra_sealOnce | EXERCISED | measurementsSealed: 58 |  |
| intra_submitAfterBinding | EXERCISED | jobSubmitIntent: 58 |  |
| intra_submittedAfterIntent | EXERCISED | jobSubmitted: 58 |  |
| intra_submittedOnce | EXERCISED | jobSubmitted: 58 |  |
| intra_termAfterSubmission | EXERCISED | termObserved: 232 |  |
| intra_termDeclaredOnce | EXERCISED | termExpected: 232 |  |
| intra_termExpectedAfterBinding | EXERCISED | termExpected: 232 |  |
| intra_termObservedOnce | EXERCISED | termObserved: 232 |  |
| intra_termWasDeclared | EXERCISED | termObserved: 232 |  |
| run_activityAfterMatchingStart | EXERCISED | activity: 1217 |  |
| run_closeAfterOptimizerProtocol | EXERCISED | runClosed: 1 |  |
| run_closeAfterTerminal | EXERCISED | runClosed: 1 |  |
| run_closeOnce | EXERCISED | runClosed: 1 |  |
| run_convergedAfterTrueClose | EXERCISED | runConverged: 1 |  |
| run_convergedIsFirstTerminal | EXERCISED | runConverged: 1 |  |
| run_noActivityAfterClose | EXERCISED | activity: 1217 |  |
| run_noActivityAfterTerminal | EXERCISED | activity: 1217 |  |
| run_normalTerminalWithoutFailure | EXERCISED | runConverged: 1, runMaxIterations: 0, runOptimizerStopped: 0 | not applicable: runOptimizerStopped; disjuncts never fired: runMaxIterations |
| run_startOnce | EXERCISED | runStarted: 1 |  |
