**refined_abort: a concrete execution that visits all six phases**

Extracted from trace 7 of `refined_abort_witnesses.log`. Step 0 is the initial state; unprinted state variables in nuXmv traces retain their previous values.

| Step | state | iter | terms_done | params_ready | energy_ready |
| --- | --- | --- | --- | --- | --- |
| 0 | S_INIT | 0 | 0 | TRUE | FALSE |
| 1 | BIND | 0 | 0 | TRUE | FALSE |
| 2 | EXECUTE_MEASURE | 0 | 0 | TRUE | FALSE |
| 3 | EXECUTE_MEASURE | 0 | 1 | TRUE | FALSE |
| 4 | EXECUTE_MEASURE | 0 | 2 | TRUE | FALSE |
| 5 | EXECUTE_MEASURE | 0 | 3 | TRUE | FALSE |
| 6 | COMPUTE_ENERGY | 0 | 3 | FALSE | FALSE |
| 7 | CHECK_STOP | 0 | 3 | FALSE | TRUE |
| 8 | OPTIMIZER_STEP | 0 | 3 | FALSE | TRUE |
| 9 | BIND | 1 | 0 | TRUE | FALSE |
| 10 | EXECUTE_MEASURE | 1 | 0 | TRUE | FALSE |
| 11 | EXECUTE_MEASURE | 1 | 1 | TRUE | FALSE |
| 12 | EXECUTE_MEASURE | 1 | 2 | TRUE | FALSE |
| 13 | EXECUTE_MEASURE | 1 | 3 | TRUE | FALSE |
| 14 | COMPUTE_ENERGY | 1 | 3 | FALSE | FALSE |
| 15 | CHECK_STOP | 1 | 3 | FALSE | TRUE |
| 16 | DONE | 1 | 3 | FALSE | TRUE |

The stop check at step 7 takes the non-converged branch, and the stop check at step 15 takes the converged branch. In the refined models, relevant fault inputs are false along this execution. The original logs preserve those choices.
