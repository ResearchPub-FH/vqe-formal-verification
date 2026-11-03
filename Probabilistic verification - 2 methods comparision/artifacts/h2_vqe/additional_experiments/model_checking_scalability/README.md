# Model-checking scalability versus K

Here `K` is the maximum number of optimizer updates.  Each row is a separately
constructed, time-unrolled 1024-shot Gaussian DTMC.  A state records both the
parameter-grid point and its update depth.  Only nonzero-probability states
reachable from the fixed initial index are emitted; successful paths share one
absorbing state, and paths still running at depth `K` share one absorbing
timeout state.

| K | Reachable states | Transitions | DTMC construction | Storm checking time |
|---:|---:|---:|---:|---:|
| 10 | 3,582 | 7,900 | 0.008 s | <0.001 s |
| 20 | 70,849 | 178,378 | 0.161 s | 0.002 s |
| 30 | 435,618 | 1,143,927 | 1.067 s | 0.020 s |
| 40 | 1,086,396 | 3,014,507 | 2.821 s | 0.072 s |
| 50 | 1,741,676 | 4,889,851 | 4.663 s | 0.206 s |

DTMC construction time covers reachable-state exploration and serialization to
Storm's explicit transition/label format.  It excludes the one-time,
K-independent calculation of the 65,536-state Born/Gaussian kernel.  Storm time
is the median of 3 tool-reported model-checking
times and excludes Storm's explicit-model parsing/construction phase.

The checked unbounded property `P=? [ F "success" ]` on each truncated model
is equivalent to `P=? [ F<=K "success" ]` on the homogeneous DTMC.  Every
Storm result was compared with the independent NumPy propagation; the maximum
absolute difference was 4.4e-11.
