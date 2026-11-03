include "VQETypes.dfy"

module VQEContracts {
  import opened VQETypes

  function Abs(x: real): real {
    if x < 0.0 then -x else x
  }

  function SumProd(coeffs: seq<real>, exps: seq<real>, n: nat): real
    requires n <= |coeffs|
    requires n <= |exps|
    decreases n
  {
    if n == 0 then
      0.0
    else
      SumProd(coeffs, exps, n - 1) + coeffs[n - 1] * exps[n - 1]
  }

  function L1Bound(coeffs: seq<real>, n: nat): real
    requires n <= |coeffs|
    decreases n
  {
    if n == 0 then
      0.0
    else
      L1Bound(coeffs, n - 1) + Abs(coeffs[n - 1])
  }

  function SumNat(values: seq<nat>, n: nat): nat
    requires n <= |values|
    decreases n
  {
    if n == 0 then
      0
    else
      SumNat(values, n - 1) + values[n - 1]
  }

  function SumReal(values: seq<real>, n: nat): real
    requires n <= |values|
    decreases n
  {
    if n == 0 then
      0.0
    else
      SumReal(values, n - 1) + values[n - 1]
  }

  predicate ValidExpectations(exps: seq<real>) {
    forall i :: 0 <= i < |exps| ==> -1.0 <= exps[i] <= 1.0
  }

  predicate AllTermsMeasured(done: seq<bool>) {
    forall i :: 0 <= i < |done| ==> done[i]
  }

  predicate DistinctTermIds(ids: seq<nat>) {
    forall i, j :: 0 <= i < j < |ids| ==> ids[i] != ids[j]
  }

  predicate CompleteTermRecord(
    expectedCount: nat,
    ids: seq<nat>,
    coeffs: seq<real>,
    exps: seq<real>,
    perTermEnergies: seq<real>,
    done: seq<bool>
  ) {
    expectedCount > 0 &&
    |ids| == expectedCount &&
    |coeffs| == expectedCount &&
    |exps| == expectedCount &&
    |perTermEnergies| == expectedCount &&
    |done| == expectedCount &&
    DistinctTermIds(ids) &&
    (forall i :: 0 <= i < |ids| ==> ids[i] < expectedCount) &&
    AllTermsMeasured(done)
  }

  predicate ValidParameterDomain(
    theta: seq<real>,
    lower: real,
    upper: real
  ) {
    lower <= upper &&
    (forall i :: 0 <= i < |theta| ==> lower <= theta[i] <= upper)
  }

  predicate SameLayout(record: IterationRecord) {
    record.ansatzLayoutId == record.hamiltonianLayoutId
  }

  predicate FreshOptimizerInput(record: IterationRecord) {
    record.energyReady &&
    record.paramsReady &&
    record.thetaId == record.boundThetaId &&
    record.thetaId == record.energyThetaId &&
    record.thetaId == record.optimizerThetaId &&
    record.energyId == record.optimizerEnergyId
  }

  predicate AlignedCountVectors(record: IterationRecord) {
    |record.shots| == record.expectedTermCount &&
    |record.countsOnes| == record.expectedTermCount &&
    |record.countsAvailable| == record.expectedTermCount &&
    |record.expectations| == record.expectedTermCount
  }

  predicate ValidShotConsistency(record: IterationRecord) {
    AlignedCountVectors(record) &&
    record.totalShotsThisIteration == SumNat(record.shots, |record.shots|) &&
    record.totalShotsThisIteration <= record.budgetUsed <= record.shotBudget &&
    (forall i :: 0 <= i < record.expectedTermCount ==>
      if record.countsAvailable[i] then
        0 < record.shots[i] &&
        record.countsOnes[i] <= record.shots[i] &&
        record.expectations[i] ==
          1.0 - 2.0 * (record.countsOnes[i] as real) /
            (record.shots[i] as real)
      else
        record.countsOnes[i] == 0)
  }

  predicate ValidCountData(record: IterationRecord) {
    ValidShotConsistency(record)
  }

  predicate ValidEnergyContributions(
    coeffs: seq<real>,
    exps: seq<real>,
    perTermEnergies: seq<real>
  ) {
    |coeffs| == |exps| &&
    |perTermEnergies| == |coeffs| &&
    (forall i :: 0 <= i < |perTermEnergies| ==>
      perTermEnergies[i] == coeffs[i] * exps[i])
  }

  predicate ValidEnergyComputation(record: IterationRecord) {
    ValidEnergyContributions(
      record.coefficients,
      record.expectations,
      record.perTermEnergies
    ) &&
    record.reportedEnergy ==
      SumReal(record.perTermEnergies, |record.perTermEnergies|) &&
    record.reportedEnergy ==
      SumProd(record.coefficients, record.expectations, |record.coefficients|) &&
    WithinEnergyBound(record.coefficients, record.reportedEnergy)
  }

  predicate ValidParameterState(record: IterationRecord) {
    record.parameterCount == |record.theta| &&
    ValidParameterDomain(
      record.theta,
      record.parameterLower,
      record.parameterUpper
    )
  }

  predicate ValidConvergenceCheck(record: IterationRecord) {
    record.maxIterations > 0 &&
    record.iteration < record.maxIterations &&
    0.0 <= record.convergenceTolerance &&
    0.0 <= record.energyDelta &&
    (record.iteration == 0 ==>
      !record.previousEnergyAvailable &&
      record.energyDelta == 0.0) &&
    (record.iteration > 0 ==>
      record.previousEnergyAvailable &&
      record.energyDelta == Abs(record.reportedEnergy - record.previousEnergy)) &&
    record.converged ==
      (record.previousEnergyAvailable &&
        record.energyDelta <= record.convergenceTolerance) &&
    (record.finalIteration ==>
      record.converged || record.iteration + 1 == record.maxIterations)
  }

  predicate WithinEnergyBound(coeffs: seq<real>, energy: real) {
    -L1Bound(coeffs, |coeffs|) <= energy <= L1Bound(coeffs, |coeffs|)
  }

  predicate WithinShotBudget(record: IterationRecord) {
    record.totalShotsThisIteration == SumNat(record.shots, |record.shots|) &&
    record.totalShotsThisIteration <= record.budgetUsed <= record.shotBudget
  }
}
