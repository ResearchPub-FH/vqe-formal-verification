include "VQEContracts.dfy"

module VQETraceContracts {
  import opened VQETypes
  import opened VQEContracts

  predicate ValidIterationRecord(record: IterationRecord) {
    CompleteTermRecord(
      record.expectedTermCount,
      record.termIds,
      record.coefficients,
      record.expectations,
      record.perTermEnergies,
      record.termsDone
    ) &&
    ValidExpectations(record.expectations) &&
    ValidParameterState(record) &&
    ValidShotConsistency(record) &&
    ValidEnergyComputation(record) &&
    ValidConvergenceCheck(record) &&
    SameLayout(record) &&
    FreshOptimizerInput(record) &&
    WithinShotBudget(record)
  }

  predicate FirstRecord(record: IterationRecord) {
    record.iteration == 0 &&
    record.budgetUsed == record.totalShotsThisIteration &&
    !record.previousEnergyAvailable &&
    record.energyDelta == 0.0
  }

  predicate ValidTraceStep(previous: IterationRecord, current: IterationRecord) {
    ValidIterationRecord(previous) &&
    ValidIterationRecord(current) &&
    current.iteration == previous.iteration + 1 &&
    current.expectedTermCount == previous.expectedTermCount &&
    current.shotBudget == previous.shotBudget &&
    current.maxIterations == previous.maxIterations &&
    current.convergenceTolerance == previous.convergenceTolerance &&
    current.previousEnergyAvailable &&
    current.previousEnergy == previous.reportedEnergy &&
    current.energyDelta == Abs(current.reportedEnergy - previous.reportedEnergy) &&
    current.budgetUsed ==
      previous.budgetUsed + current.totalShotsThisIteration
  }

  method RequireValidIteration(record: IterationRecord)
    requires ValidIterationRecord(record)
    ensures SameLayout(record)
    ensures FreshOptimizerInput(record)
    ensures record.reportedEnergy ==
      SumProd(record.coefficients, record.expectations, |record.coefficients|)
    ensures record.reportedEnergy ==
      SumReal(record.perTermEnergies, |record.perTermEnergies|)
    ensures WithinEnergyBound(record.coefficients, record.reportedEnergy)
    ensures WithinShotBudget(record)
    ensures ValidShotConsistency(record)
    ensures ValidParameterState(record)
    ensures ValidConvergenceCheck(record)
  {
  }

  method RequireValidTraceStep(
    previous: IterationRecord,
    current: IterationRecord
  )
    requires ValidTraceStep(previous, current)
    ensures current.iteration == previous.iteration + 1
    ensures current.budgetUsed ==
      previous.budgetUsed + current.totalShotsThisIteration
    ensures current.previousEnergy == previous.reportedEnergy
    ensures current.energyDelta ==
      Abs(current.reportedEnergy - previous.reportedEnergy)
  {
  }
}
