# DejaVu property coverage: `h2_ibm_marrakesh_sampler_20260907.jsonl`

Configuration: optimizer_protocol = ask-tell, allow_optimizer_stopped = False, max_iterations = 50.

| Status | Properties |
|---|---:|
| EXERCISED | 55 |
| NOT_APPLICABLE | 7 |
| NOT_EXERCISED | 5 |
| NESTED_NOT_EXERCISED | 1 |

A PASS on a NOT_EXERCISED or NESTED_NOT_EXERCISED property is vacuous for this trace; NOT_APPLICABLE properties cannot fire under the recorded configuration.

| Property | Status | Trigger events | Detail |
|---|---|---|---|
| intra_abortAfterFailure | NOT_EXERCISED | iterationAborted: 0 |  |
| run_abortAfterFailure | NOT_EXERCISED | runAborted: 0 |  |
| run_abortIsFirstTerminal | NOT_EXERCISED | runAborted: 0 |  |
| run_convergedAfterTrueClose | NOT_EXERCISED | runConverged: 0 |  |
| run_convergedIsFirstTerminal | NOT_EXERCISED | runConverged: 0 |  |
| run_failureRequiresAbortAtClose | NESTED_NOT_EXERCISED | runClosed: 1 | nested antecedent criticalFail: 0 |
| inter_opaqueAdvanceAfterClose | NOT_APPLICABLE | opaqueOptimizerAdvanced: 0 | not applicable: opaqueOptimizerAdvanced |
| inter_opaqueAdvanceBeforeLimit | NOT_APPLICABLE | opaqueOptimizerAdvanced: 0 | not applicable: opaqueOptimizerAdvanced |
| inter_opaqueAdvanceOnce | NOT_APPLICABLE | opaqueOptimizerAdvanced: 0 | not applicable: opaqueOptimizerAdvanced |
| inter_opaqueAdvanceUsesConfiguredProtocol | NOT_APPLICABLE | opaqueOptimizerAdvanced: 0 | not applicable: opaqueOptimizerAdvanced |
| inter_opaqueProtocolConfiguredOnce | NOT_APPLICABLE | optimizerOpaqueConfigured: 0 | not applicable: optimizerOpaqueConfigured |
| run_optimizerStopAfterFalseClose | NOT_APPLICABLE | runOptimizerStopped: 0 | not applicable: runOptimizerStopped |
| run_optimizerStopIsFirstTerminal | NOT_APPLICABLE | runOptimizerStopped: 0 | not applicable: runOptimizerStopped |
| inter_askTellIntentUsesConfiguredProtocol | EXERCISED | optimizerUpdateIntent: 49 |  |
| inter_askTellProtocolConfiguredOnce | EXERCISED | optimizerAskTellConfigured: 1 |  |
| inter_askTellUpdateUsesConfiguredProtocol | EXERCISED | optimizerUpdated: 49 |  |
| inter_backendJobIdentityUnique | EXERCISED | jobSubmitted: 50 |  |
| inter_closeAfterCommittedUpdate | EXERCISED | iterationClosed: 50 | nested antecedent optimizerUpdateIntent: 49 |
| inter_firstEvaluationIdentityUnique | EXERCISED | firstIterationStarted: 1 |  |
| inter_firstIterationAfterConfiguredProtocol | EXERCISED | firstIterationStarted: 1 |  |
| inter_iterationClosedOnce | EXERCISED | iterationClosed: 50 |  |
| inter_nextAfterOptimizerUpdate | EXERCISED | nextIterationStarted: 49 |  |
| inter_nextAfterPreviousClose | EXERCISED | nextIterationStarted: 49 |  |
| inter_nextEvaluationIdentityUnique | EXERCISED | nextIterationStarted: 49 |  |
| inter_nextIterationAfterConfiguredProtocol | EXERCISED | nextIterationStarted: 49 |  |
| inter_previousEnergyIsLastCheckpoint | EXERCISED | nextConvergenceChecked: 49 |  |
| inter_submissionIdentityUnique | EXERCISED | jobSubmitIntent: 50 |  |
| inter_updateAppliedOnce | EXERCISED | optimizerUpdated: 49 |  |
| inter_updateIntentAfterRelease | EXERCISED | optimizerUpdateIntent: 49 |  |
| inter_updateIntentOnce | EXERCISED | optimizerUpdateIntent: 49 |  |
| inter_updateOnlyWhenNotConverged | EXERCISED | optimizerUpdateIntent: 49 |  |
| inter_updatedAfterIntent | EXERCISED | optimizerUpdated: 49 |  |
| intra_allDeclaredTermsObserved | EXERCISED | measurementsSealed: 50 | nested antecedent termExpected: 200 |
| intra_bindingAfterStart | EXERCISED | parametersBound: 50 |  |
| intra_bindingOnce | EXERCISED | parametersBound: 50 |  |
| intra_closeAfterRelease | EXERCISED | iterationClosed: 50 |  |
| intra_energyAfterSeal | EXERCISED | numericValid: 50 |  |
| intra_energyOnce | EXERCISED | numericValid: 50 |  |
| intra_firstCheckAfterEnergy | EXERCISED | firstConvergenceChecked: 1 |  |
| intra_firstCheckOnce | EXERCISED | firstConvergenceChecked: 1 |  |
| intra_nextCheckAfterEnergy | EXERCISED | nextConvergenceChecked: 49 |  |
| intra_nextCheckOnce | EXERCISED | nextConvergenceChecked: 49 |  |
| intra_oneSubmissionPerIteration | EXERCISED | jobSubmitIntent: 50 |  |
| intra_passAfterCheck | EXERCISED | iterationPass: 50 |  |
| intra_passOnce | EXERCISED | iterationPass: 50 |  |
| intra_releaseAfterPass | EXERCISED | objectiveReleaseIntent: 50 |  |
| intra_releaseOnce | EXERCISED | objectiveReleaseIntent: 50 |  |
| intra_sealAfterSubmission | EXERCISED | measurementsSealed: 50 |  |
| intra_sealOnce | EXERCISED | measurementsSealed: 50 |  |
| intra_submitAfterBinding | EXERCISED | jobSubmitIntent: 50 |  |
| intra_submittedAfterIntent | EXERCISED | jobSubmitted: 50 |  |
| intra_submittedOnce | EXERCISED | jobSubmitted: 50 |  |
| intra_termAfterSubmission | EXERCISED | termObserved: 200 |  |
| intra_termDeclaredOnce | EXERCISED | termExpected: 200 |  |
| intra_termExpectedAfterBinding | EXERCISED | termExpected: 200 |  |
| intra_termObservedOnce | EXERCISED | termObserved: 200 |  |
| intra_termWasDeclared | EXERCISED | termObserved: 200 |  |
| run_activityAfterMatchingStart | EXERCISED | activity: 1050 |  |
| run_closeAfterOptimizerProtocol | EXERCISED | runClosed: 1 |  |
| run_closeAfterTerminal | EXERCISED | runClosed: 1 |  |
| run_closeOnce | EXERCISED | runClosed: 1 |  |
| run_iterationLimitOnce | EXERCISED | iterationLimitReached: 1 |  |
| run_maxAfterLimitAndFalseClose | EXERCISED | runMaxIterations: 1 |  |
| run_maxIsFirstTerminal | EXERCISED | runMaxIterations: 1 |  |
| run_noActivityAfterClose | EXERCISED | activity: 1050 |  |
| run_noActivityAfterTerminal | EXERCISED | activity: 1050 |  |
| run_normalTerminalWithoutFailure | EXERCISED | runConverged: 0, runMaxIterations: 1, runOptimizerStopped: 0 | not applicable: runOptimizerStopped; disjuncts never fired: runConverged |
| run_startOnce | EXERCISED | runStarted: 1 |  |
