# Storm reward validation

Status: **PASS**

Executed Storm bounded cumulative-reward queries on the unchanged audited Gaussian DTMC.
Both iteration and shot costs are evaluated by Storm in separate runs.

## Primary comparison

| Quantity | Storm-derived | Saved Python | Absolute difference |
|---|---:|---:|---:|
| Conditional mean iterations | 33.1111870989701 | 33.1111870989701 | 7.10543e-15 |
| Conditional mean shots | 305152.700304108 | 305152.700304108 | 5.82077e-11 |

## Reward and conditioning semantics

Let T be the first-success iteration and K the configured bound. Each non-success state has reward 1 (iterations) or S (shots), and absorbing success states have reward 0.
Storm computes `P=? [ F<=K "success" ]` and `R=? [ C<=K ]`.
The latter is the all-run bounded cost C = E[min(T,K)] (or S times it), including budget-exhausted paths.
The conditional mean is obtained from Storm outputs as `(C - scale*K*(1-p))/p`.
This follows from C = E[T*1(T<=K)] + K*Pr(T>K), with the same scale for shots.
Only scalar arithmetic is performed outside Storm to obtain the resource mean. Python propagation is used separately as the comparison reference.
This is not a claim that a native conditional-reward query was executed. Zero-probability conditional means are reported as undefined.

## Validation

- 12 analytic toy-model/unit checks passed, including initial success, first-step success, success exactly at the bound, mixed first-hit times, budget exhaustion and zero success probability.
- All original configured reachability checkpoints were rechecked; resource means were compared wherever bounded-success probability is nonzero.
- Both reward calculations agree with saved Python values and a fresh propagation of the retained kernel within the declared numerical tolerances.
- Absorbing success states, stochastic transition rows and exported state labels were checked before attaching rewards.
- SHA-256 checks confirm every referenced original input stayed unchanged.

## Scope and provenance

- Current verification tool: `Storm 2.0.0`.
- Original probability log: `Storm 1.13.0`. The newly executed queries are supplementary results, not part of that earlier run.
- This checks agreement of calculations on the same Gaussian abstraction; it does not measure Gaussian approximation error or add empirical VQE runs.
- Manuscript, figures, empirical traces, original implementation and original verifier outputs were not edited.
- Raw logs, commands, reward files and query files are retained beside this report.

## References

- Storm reward semantics: https://www.stormchecker.org/documentation/background/properties.html
- Explicit model/reward input: https://www.stormchecker.org/documentation/usage/running-storm.html
