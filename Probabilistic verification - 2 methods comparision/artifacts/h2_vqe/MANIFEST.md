# H2 VQE probabilistic-verification artifact

The baseline artifact is deliberately separated into four review layers:

1. `layer1_analytical`: Born-derived Gaussian DTMC assumptions and reference
   property values.
2. `layer2_prism`: explicit PRISM transition, state, label, reward, and
   property files.
3. `layer3_prism_results`: instructions and result-table scaffold. PRISM is
   not executed by this workflow.
4. `layer4_empirical`: direct 400-run noisy FakeBackend traces, statistics,
   and comparison. No empirical DTMC is built.

Two reproducible follow-up studies are stored in `additional_experiments`:

1. `shot_sensitivity`: Gaussian and direct noisy FakeJakarta estimates of
   `P(F<=50 "success")` for 256, 512, 1024, and 2048 shots per commuting
   group, including compact traces and PNG/SVG line charts.
2. `model_checking_scalability`: reachable time-unrolled DTMC sizes,
   construction times, and Storm 1.13.0 checking times for
   `K in {10,20,30,40,50}`.

PRISM model size: 262,144 states and
755,176 transitions.

The analytical and empirical layers share the Hamiltonian, ansatz, initial
parameters, optimizer semantics, measurement grouping, shots per group,
parameter grid, convergence definition, and iteration limit. They intentionally
differ in physical measurement noise: Layer 1 uses ideal Born probabilities
with a Gaussian finite-shot approximation; Layer 4 uses FakeJakarta's stored
noise model.
