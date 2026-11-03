include "VQEContracts.dfy"

module VQELemmas {
  import opened VQEContracts

  lemma AbsNonNegative(x: real)
    ensures 0.0 <= Abs(x)
  {
  }

  lemma MulNonnegative(left: real, right: real)
    requires 0.0 <= left
    requires 0.0 <= right
    ensures 0.0 <= left * right
  {
  }

  lemma ProductWithinAbs(coefficient: real, expectation: real)
    requires -1.0 <= expectation <= 1.0
    ensures -Abs(coefficient) <= coefficient * expectation
    ensures coefficient * expectation <= Abs(coefficient)
  {
    if coefficient < 0.0 {
      var magnitude := -coefficient;
      assert Abs(coefficient) == -coefficient;
      MulNonnegative(magnitude, 1.0 - expectation);
      MulNonnegative(magnitude, 1.0 + expectation);
      assert coefficient * expectation - coefficient ==
        magnitude * (1.0 - expectation);
      assert -coefficient - coefficient * expectation ==
        magnitude * (1.0 + expectation);
    } else {
      assert Abs(coefficient) == coefficient;
      MulNonnegative(coefficient, 1.0 + expectation);
      MulNonnegative(coefficient, 1.0 - expectation);
      assert coefficient * expectation + coefficient ==
        coefficient * (1.0 + expectation);
      assert coefficient - coefficient * expectation ==
        coefficient * (1.0 - expectation);
    }
  }

  lemma SumProdWithinL1(
    coeffs: seq<real>,
    exps: seq<real>,
    n: nat
  )
    requires n <= |coeffs|
    requires n <= |exps|
    requires ValidExpectations(exps)
    ensures -L1Bound(coeffs, n) <= SumProd(coeffs, exps, n)
    ensures SumProd(coeffs, exps, n) <= L1Bound(coeffs, n)
    decreases n
  {
    if n > 0 {
      SumProdWithinL1(coeffs, exps, n - 1);
      var coefficient := coeffs[n - 1];
      var expectation := exps[n - 1];
      assert -1.0 <= expectation <= 1.0;
      ProductWithinAbs(coefficient, expectation);
      assert -Abs(coefficient) <= coefficient * expectation;
      assert coefficient * expectation <= Abs(coefficient);
      var previousSum := SumProd(coeffs, exps, n - 1);
      var previousBound := L1Bound(coeffs, n - 1);
      var term := coefficient * expectation;
      var termBound := Abs(coefficient);
      assert -previousBound <= previousSum <= previousBound;
      assert -termBound <= term <= termBound;
      assert -previousBound - termBound <= previousSum + term;
      assert previousSum + term <= previousBound + termBound;
      assert SumProd(coeffs, exps, n) == previousSum + term;
      assert L1Bound(coeffs, n) == previousBound + termBound;
    }
  }

  lemma SumContributionsEqualsSumProd(
    coeffs: seq<real>,
    exps: seq<real>,
    terms: seq<real>,
    n: nat
  )
    requires n <= |coeffs|
    requires n <= |exps|
    requires n <= |terms|
    requires forall i :: 0 <= i < n ==> terms[i] == coeffs[i] * exps[i]
    ensures SumReal(terms, n) == SumProd(coeffs, exps, n)
    decreases n
  {
    if n > 0 {
      SumContributionsEqualsSumProd(coeffs, exps, terms, n - 1);
      assert terms[n - 1] == coeffs[n - 1] * exps[n - 1];
    }
  }

  lemma ClampWithin(value: real, lower: real, upper: real)
    requires lower <= upper
    ensures lower <= (if value < lower then lower else if value > upper then upper else value)
    ensures (if value < lower then lower else if value > upper then upper else value) <= upper
  {
  }
}
