include "VQELemmas.dfy"

module VQENumericKernels {
  import opened VQEContracts
  import opened VQELemmas

  method NormalizeExpectation(countsOnes: nat, shots: nat)
      returns (expectation: real)
    requires 0 < shots
    requires countsOnes <= shots
    ensures expectation ==
      1.0 - 2.0 * (countsOnes as real) / (shots as real)
    ensures -1.0 <= expectation <= 1.0
  {
    expectation :=
      1.0 - 2.0 * (countsOnes as real) / (shots as real);
    assert 0.0 <= (countsOnes as real) / (shots as real) <= 1.0;
  }

  method TermEnergyContribution(coefficient: real, expectation: real)
      returns (contribution: real)
    requires -1.0 <= expectation <= 1.0
    ensures contribution == coefficient * expectation
    ensures -Abs(coefficient) <= contribution <= Abs(coefficient)
  {
    contribution := coefficient * expectation;
    ProductWithinAbs(coefficient, expectation);
  }

  method ComputeTermEnergies(coeffs: seq<real>, exps: seq<real>)
      returns (perTermEnergies: seq<real>)
    requires |coeffs| == |exps|
    requires ValidExpectations(exps)
    ensures ValidEnergyContributions(coeffs, exps, perTermEnergies)
  {
    perTermEnergies := [];
    var i := 0;
    while i < |coeffs|
      invariant 0 <= i <= |coeffs|
      invariant |coeffs| == |exps|
      invariant |perTermEnergies| == i
      invariant forall j :: 0 <= j < |perTermEnergies| ==>
        perTermEnergies[j] == coeffs[j] * exps[j]
    {
      var contribution := TermEnergyContribution(coeffs[i], exps[i]);
      perTermEnergies := perTermEnergies + [contribution];
      i := i + 1;
    }
  }

  method AggregateEnergy(
    expectedCount: nat,
    termIds: seq<nat>,
    coeffs: seq<real>,
    exps: seq<real>,
    perTermEnergies: seq<real>,
    done: seq<bool>
  ) returns (energy: real)
    requires CompleteTermRecord(
      expectedCount,
      termIds,
      coeffs,
      exps,
      perTermEnergies,
      done
    )
    requires ValidExpectations(exps)
    requires ValidEnergyContributions(coeffs, exps, perTermEnergies)
    ensures energy == SumProd(coeffs, exps, |coeffs|)
    ensures energy == SumReal(perTermEnergies, |perTermEnergies|)
    ensures WithinEnergyBound(coeffs, energy)
  {
    var i := 0;
    energy := 0.0;
    while i < |coeffs|
      invariant 0 <= i <= |coeffs|
      invariant i <= |exps|
      invariant i <= |perTermEnergies|
      invariant energy == SumProd(coeffs, exps, i)
      invariant energy == SumReal(perTermEnergies, i)
    {
      assert perTermEnergies[i] == coeffs[i] * exps[i];
      energy := energy + perTermEnergies[i];
      i := i + 1;
    }
    SumProdWithinL1(coeffs, exps, |coeffs|);
    SumContributionsEqualsSumProd(
      coeffs,
      exps,
      perTermEnergies,
      |perTermEnergies|
    );
  }

  method SumShotUsage(shots: seq<nat>) returns (used: nat)
    ensures used == SumNat(shots, |shots|)
  {
    var i := 0;
    used := 0;
    while i < |shots|
      invariant 0 <= i <= |shots|
      invariant used == SumNat(shots, i)
    {
      used := used + shots[i];
      i := i + 1;
    }
  }

  method EnergyDelta(currentEnergy: real, previousEnergy: real)
      returns (delta: real)
    ensures delta == Abs(currentEnergy - previousEnergy)
    ensures 0.0 <= delta
  {
    delta := Abs(currentEnergy - previousEnergy);
    AbsNonNegative(currentEnergy - previousEnergy);
  }

  method CheckConverged(delta: real, tolerance: real)
      returns (converged: bool)
    requires 0.0 <= delta
    requires 0.0 <= tolerance
    ensures converged == (delta <= tolerance)
  {
    converged := delta <= tolerance;
  }

  function Clamp(value: real, lower: real, upper: real): real
    requires lower <= upper
  {
    if value < lower then lower else if value > upper then upper else value
  }

  method ClampParameters(theta: seq<real>, lower: real, upper: real)
      returns (bounded: seq<real>)
    requires lower <= upper
    ensures |bounded| == |theta|
    ensures ValidParameterDomain(bounded, lower, upper)
  {
    bounded := [];
    var i := 0;
    while i < |theta|
      invariant 0 <= i <= |theta|
      invariant |bounded| == i
      invariant forall j :: 0 <= j < |bounded| ==>
        lower <= bounded[j] <= upper
    {
      ClampWithin(theta[i], lower, upper);
      bounded := bounded + [Clamp(theta[i], lower, upper)];
      i := i + 1;
    }
  }
}
