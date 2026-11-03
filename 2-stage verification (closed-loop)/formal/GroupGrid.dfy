// Additional kernels for physical group accounting and the finite-grid optimizer.
module GroupGrid {
  function Sum(xs: seq<nat>): nat
    decreases |xs|
  { if |xs| == 0 then 0 else xs[0] + Sum(xs[1..]) }

  method AccumulatePhysicalGroups(groups: seq<nat>) returns (shots: nat)
    ensures shots == Sum(groups)
  {
    shots := 0;
    var i := 0;
    while i < |groups|
      invariant 0 <= i <= |groups|
      invariant shots + Sum(groups[i..]) == Sum(groups)
    {
      shots := shots + groups[i];
      i := i + 1;
    }
  }

  method WrapCandidate(index: int, step: int, grid: int) returns (next: int)
    requires 3 <= grid
    requires 0 <= index < grid
    requires -1 <= step <= 1
    ensures next == (index + step) % grid
    ensures 0 <= next < grid
  { next := (index + step) % grid; }

  method SelectCandidate(current: int, minus: int, plus: int) returns (choice: int)
    ensures 0 <= choice <= 2
    ensures choice == 0 <==> current <= minus && current <= plus
    ensures choice == 1 <==> minus < current && minus <= plus
    ensures choice == 2 <==> plus < current && plus < minus
  {
    if current <= minus && current <= plus { choice := 0; }
    else if minus <= plus { choice := 1; }
    else { choice := 2; }
  }
}
