# Layer 1 — Analytical Gaussian DTMC

Every current/minus/plus energy law is approximated by a Gaussian whose mean
and variance are calculated from the ideal H2 Born probabilities with
1024 shots per commuting group. Candidate measurements are
independent. Gaussian minimum probabilities define the optimizer transition
kernel.

The physical noise stored in FakeJakarta is intentionally absent from this
analytical kernel; it appears only in Layer 4. Both layers run for up to 50
optimizer updates and stop early only upon convergence.

The Gaussian abstraction has continuous energies and therefore zero tie
probability. The direct finite-shot experiment has discrete scores and applies
the declared current/minus/plus tie priority.

Minimum/maximum analytical energy variance on the grid:
`[0.000154816103516, 0.000341500673828]`.
