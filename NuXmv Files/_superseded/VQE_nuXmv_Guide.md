# VQE Control-Flow Verification with nuXmv — Guide

## How the Model Maps to Your Slides

### Slide 12 (State Definitions) → VAR state

Your seven states become a nuXmv enumeration:

```
state : {INIT, BIND, EXECUTE_MEASURE, COMPUTE_ENERGY,
         CHECK_STOP, OPTIMIZER_STEP, DONE};
```

Each state's entry/exit conditions from Slide 12 are encoded as
transition guards in the `next(state)` CASE block.

---

### Slide 13 (Transition Definitions) → ASSIGN next(state)

Each row of your transition table becomes one line in the CASE:

| Your Transition Table Row               | nuXmv CASE Line                                              |
|------------------------------------------|---------------------------------------------------------------|
| INIT → BIND                              | `state = INIT : BIND;`                                        |
| BIND → EXECUTE_MEASURE                   | `state = BIND : EXECUTE_MEASURE;`                              |
| EXECUTE_MEASURE (term < n) → self        | `state = EXECUTE_MEASURE & terms_done < NTERMS : EXECUTE_MEASURE;` |
| EXECUTE_MEASURE (term == n) → COMPUTE    | `state = EXECUTE_MEASURE & terms_done = NTERMS : COMPUTE_ENERGY;`  |
| CHECK_STOP (converged) → DONE            | `state = CHECK_STOP & converged : DONE;`                       |
| CHECK_STOP (max iters) → DONE            | `state = CHECK_STOP & !converged & iter = MAX_ITERS : DONE;`   |
| CHECK_STOP (otherwise) → OPTIMIZER_STEP  | `state = CHECK_STOP & !converged & iter < MAX_ITERS : OPTIMIZER_STEP;` |
| OPTIMIZER_STEP → BIND                    | `state = OPTIMIZER_STEP : BIND;`                               |

---

### Slide 14 (State Invariants) → INV Properties

Each invariant from Slide 14 becomes a verifiable LTLSPEC:

| Slide 14 Invariant                      | nuXmv Property                                                  |
|------------------------------------------|------------------------------------------------------------------|
| INIT: iter=0, terms_done=0              | `G (state = INIT -> iter = 0 & terms_done = 0)`                  |
| BIND: params_ready = TRUE               | `G (state = BIND -> params_ready = TRUE)`                         |
| EXECUTE_MEASURE: terms_done <= NTERMS   | `G (state = EXECUTE_MEASURE -> terms_done <= NTERMS)`             |
| COMPUTE_ENERGY: terms_done = NTERMS     | `G (state = COMPUTE_ENERGY -> terms_done = NTERMS)`               |
| CHECK_STOP: energy_ready = TRUE         | `G (state = CHECK_STOP -> energy_ready = TRUE)`                   |
| OPTIMIZER_STEP: iter < MAX_ITERS        | `G (state = OPTIMIZER_STEP -> iter < MAX_ITERS)`                  |

---

### Slide 11 (Property Classes) → Grouped LTLSPEC/SPEC

The four property classes from Slide 11 map to property groups in the model:

**Control-Flow Conformance** (CF1–CF5):
Verify hybrid event ordering — e.g., COMPUTE_ENERGY must always
follow EXECUTE_MEASURE, OPTIMIZER_STEP must always lead to BIND.

**Safety** (S1–S7):
Verify nothing bad happens — e.g., no energy computation before
measurements complete, no optimizer step before energy is ready,
DONE is absorbing.

**Liveness** (L1–L5):
Verify progress — e.g., from BIND we eventually reach CHECK_STOP,
from EXECUTE_MEASURE we eventually reach COMPUTE_ENERGY.

**Freshness** (F1–F3):
Verify no stale data — e.g., EXECUTE_MEASURE always uses fresh
parameters, energy_ready resets when entering a new iteration.

---

## Key Abstraction Decisions

### Why is `converged` nondeterministic?

nuXmv cannot compute real-valued expressions like `abs(energy - prev_energy) < tol`.
Instead, we model convergence as a nondeterministic boolean that the model checker
explores exhaustively. At each CHECK_STOP, nuXmv verifies properties under BOTH
outcomes (converged and not converged). This is sound: if a property holds for all
nondeterministic choices, it holds for any real convergence behavior.

### Why is MAX_ITERS set to 5?

For tractability. The state space grows with MAX_ITERS. Setting it to 5 is sufficient
to verify all structural properties (the control flow pattern is the same regardless
of whether max_iters is 5 or 100). You can increase it after confirming properties
pass at small scale.

### Why are shots not modeled?

Shots are internal to EXECUTE_MEASURE. The state machine treats each EXECUTE_MEASURE
invocation as atomic — it runs all shots internally and produces one expectation value.
This matches the real hardware model where you submit a circuit with a shot count and
receive a histogram.

---

## How to Run

### Interactive mode (recommended for first run):

```bash
nuXmv -int vqe_control_flow.smv
```

Then in the nuXmv interactive shell:

```
go                    -- build the model
check_ctlspec         -- verify CTL properties (reachability: R1)
check_ltlspec         -- verify all LTL properties (safety, liveness, etc.)
quit
```

### Batch mode (verify everything at once):

```bash
nuXmv vqe_control_flow.smv
```

### If a property FAILS:

nuXmv produces a counterexample trace — a concrete sequence of state
transitions that violates the property. For example, if S3 fails:

```
-> State 1: state = INIT, iter = 0, energy_ready = FALSE
-> State 2: state = BIND, iter = 0, energy_ready = FALSE    -- ok
...
-> State N: state = BIND, iter = 1, energy_ready = TRUE      -- VIOLATION
```

This tells you exactly which transition allowed stale energy to persist.

### Checking specific properties:

```
# In interactive mode:
go
check_ltlspec -p "G (state = COMPUTE_ENERGY -> terms_done = NTERMS)"
```

---

## Expected Results

All properties should PASS if the state machine is correctly designed.
If any fail, the counterexample trace will point to either:

1. A bug in the state machine design (fix the transition table), or
2. A property that is too strong for the model (refine the property).

Common issues to watch for:
- terms_done not being reset at the right point
- energy_ready not being cleared when entering a new iteration
- Y (yesterday) operators failing on the initial state (use Y(TRUE) guard)

---

## Mapping to Slide 4 (Intra-Iteration Properties)

The properties from Slide 4 (P1–P8) cover intra-iteration semantics:
shot ordering, measurement basis correctness, parity correctness, etc.
These are BELOW the abstraction level of this state machine model.

To verify P1–P8, you would need a finer-grained model that expands
EXECUTE_MEASURE into sub-states (RESET, APPLY_GATES, MEASURE_QUBIT).
That would be a separate nuXmv model — a refinement of this one.

This model verifies the OUTER LOOP properties from Slides 11 and 14,
which is the "missing parts" identified on Slide 5.
