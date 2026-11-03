# DejaVu property coverage: `h2_statevector_sampler_injected_failure_20261025.jsonl`

Configuration: optimizer_protocol = ask-tell, allow_optimizer_stopped = False, max_iterations = 50.

| Status | Properties |
|---|---:|
| EXERCISED | 55 |
| NOT_APPLICABLE | 7 |
| NOT_EXERCISED | 6 |
| NESTED_NOT_EXERCISED | 0 |

A PASS on a NOT_EXERCISED or NESTED_NOT_EXERCISED property is vacuous for this trace; NOT_APPLICABLE properties cannot fire under the recorded configuration.

| Property | Status | Trigger events | Detail |
|---|---|---|---|
| run_convergedAfterTrueClose | NOT_EXERCISED | runConverged: 0 |  |
| run_convergedIsFirstTerminal | NOT_EXERCISED | runConverged: 0 |  |
| run_iterationLimitOnce | NOT_EXERCISED | iterationLimitReached: 0 |  |
| run_maxAfterLimitAndFalseClose | NOT_EXERCISED | runMaxIterations: 0 |  |
| run_maxIsFirstTerminal | NOT_EXERCISED | runMaxIterations: 0 |  |
| run_normalTerminalWithoutFailure | NOT_EXERCISED | runConverged: 0, runMaxIterations: 0, runOptimizerStopped: 0 | not applicable: runOptimizerStopped |
| inter_opaqueAdvanceAfterClose | NOT_APPLICABLE | opaqueOptimizerAdvanced: 0 | not applicable: opaqueOptimizerAdvanced |
| inter_opaqueAdvanceBeforeLimit | NOT_APPLICABLE | opaqueOptimizerAdvanced: 0 | not applicable: opaqueOptimizerAdvanced |
| inter_opaqueAdvanceOnce | NOT_APPLICABLE | opaqueOptimizerAdvanced: 0 | not applicable: opaqueOptimizerAdvanced |
| inter_opaqueAdvanceUsesConfiguredProtocol | NOT_APPLICABLE | opaqueOptimizerAdvanced: 0 | not applicable: opaqueOptimizerAdvanced |
| inter_opaqueProtocolConfiguredOnce | NOT_APPLICABLE | optimizerOpaqueConfigured: 0 | not applicable: optimizerOpaqueConfigured |
| run_optimizerStopAfterFalseClose | NOT_APPLICABLE | runOptimizerStopped: 0 | not applicable: runOptimizerStopped |
| run_optimizerStopIsFirstTerminal | NOT_APPLICABLE | runOptimizerStopped: 0 | not applicable: runOptimizerStopped |
| inter_askTellIntentUsesConfiguredProtocol | EXERCISED | optimizerUpdateIntent: 11 |  |
| inter_askTellProtocolConfiguredOnce | EXERCISED | optimizerAskTellConfigured: 1 |  |
| inter_askTellUpdateUsesConfiguredProtocol | EXERCISED | optimizerUpdated: 11 |  |
| inter_backendJobIdentityUnique | EXERCISED | jobSubmitted: 12 |  |
| inter_closeAfterCommittedUpdate | EXERCISED | iterationClosed: 11 | nested antecedent optimizerUpdateIntent: 11 |
| inter_firstEvaluationIdentityUnique | EXERCISED | firstIterationStarted: 1 |  |
| inter_firstIterationAfterConfiguredProtocol | EXERCISED | firstIterationStarted: 1 |  |
| inter_iterationClosedOnce | EXERCISED | iterationClosed: 11 |  |
| inter_nextAfterOptimizerUpdate | EXERCISED | nextIterationStarted: 11 |  |
| inter_nextAfterPreviousClose | EXERCISED | nextIterationStarted: 11 |  |
| inter_nextEvaluationIdentityUnique | EXERCISED | nextIterationStarted: 11 |  |
| inter_nextIterationAfterConfiguredProtocol | EXERCISED | nextIterationStarted: 11 |  |
| inter_previousEnergyIsLastCheckpoint | EXERCISED | nextConvergenceChecked: 10 |  |
| inter_submissionIdentityUnique | EXERCISED | jobSubmitIntent: 12 |  |
| inter_updateAppliedOnce | EXERCISED | optimizerUpdated: 11 |  |
| inter_updateIntentAfterRelease | EXERCISED | optimizerUpdateIntent: 11 |  |
| inter_updateIntentOnce | EXERCISED | optimizerUpdateIntent: 11 |  |
| inter_updateOnlyWhenNotConverged | EXERCISED | optimizerUpdateIntent: 11 |  |
| inter_updatedAfterIntent | EXERCISED | optimizerUpdated: 11 |  |
| intra_abortAfterFailure | EXERCISED | iterationAborted: 1 |  |
| intra_allDeclaredTermsObserved | EXERCISED | measurementsSealed: 11 | nested antecedent termExpected: 48 |
| intra_bindingAfterStart | EXERCISED | parametersBound: 12 |  |
| intra_bindingOnce | EXERCISED | parametersBound: 12 |  |
| intra_closeAfterRelease | EXERCISED | iterationClosed: 11 |  |
| intra_energyAfterSeal | EXERCISED | numericValid: 11 |  |
| intra_energyOnce | EXERCISED | numericValid: 11 |  |
| intra_firstCheckAfterEnergy | EXERCISED | firstConvergenceChecked: 1 |  |
| intra_firstCheckOnce | EXERCISED | firstConvergenceChecked: 1 |  |
| intra_nextCheckAfterEnergy | EXERCISED | nextConvergenceChecked: 10 |  |
| intra_nextCheckOnce | EXERCISED | nextConvergenceChecked: 10 |  |
| intra_oneSubmissionPerIteration | EXERCISED | jobSubmitIntent: 12 |  |
| intra_passAfterCheck | EXERCISED | iterationPass: 11 |  |
| intra_passOnce | EXERCISED | iterationPass: 11 |  |
| intra_releaseAfterPass | EXERCISED | objectiveReleaseIntent: 11 |  |
| intra_releaseOnce | EXERCISED | objectiveReleaseIntent: 11 |  |
| intra_sealAfterSubmission | EXERCISED | measurementsSealed: 11 |  |
| intra_sealOnce | EXERCISED | measurementsSealed: 11 |  |
| intra_submitAfterBinding | EXERCISED | jobSubmitIntent: 12 |  |
| intra_submittedAfterIntent | EXERCISED | jobSubmitted: 12 |  |
| intra_submittedOnce | EXERCISED | jobSubmitted: 12 |  |
| intra_termAfterSubmission | EXERCISED | termObserved: 44 |  |
| intra_termDeclaredOnce | EXERCISED | termExpected: 48 |  |
| intra_termExpectedAfterBinding | EXERCISED | termExpected: 48 |  |
| intra_termObservedOnce | EXERCISED | termObserved: 44 |  |
| intra_termWasDeclared | EXERCISED | termObserved: 44 |  |
| run_abortAfterFailure | EXERCISED | runAborted: 1 |  |
| run_abortIsFirstTerminal | EXERCISED | runAborted: 1 |  |
| run_activityAfterMatchingStart | EXERCISED | activity: 242 |  |
| run_closeAfterOptimizerProtocol | EXERCISED | runClosed: 1 |  |
| run_closeAfterTerminal | EXERCISED | runClosed: 1 |  |
| run_closeOnce | EXERCISED | runClosed: 1 |  |
| run_failureRequiresAbortAtClose | EXERCISED | runClosed: 1 | nested antecedent criticalFail: 1 |
| run_noActivityAfterClose | EXERCISED | activity: 242 |  |
| run_noActivityAfterTerminal | EXERCISED | activity: 242 |  |
| run_startOnce | EXERCISED | runStarted: 1 |  |
