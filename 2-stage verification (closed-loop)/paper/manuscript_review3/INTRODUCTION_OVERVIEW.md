# Introductory VQE verification overview

The figure redraws the supplied hybrid-loop reference using original vector
artwork and adds the logical, numeric, probabilistic, and runtime concerns that
motivate the paper's architecture. It is a conceptual Introduction figure.

## Files

- `scripts/figures/introduction_overview.py`: editable Matplotlib source.
- `figures/introduction-overview.pdf`: vector publication export.
- `figures/introduction-overview.png`: 400 dpi raster export.
- `figures/introduction-overview.svg`: editable vector export with live text.
- `figures/introduction-overview-caption.tex`: suggested LaTeX placement and caption.

The existing manuscript and figures are not replaced. The caption snippet can be
inserted where the Introduction first motivates complementary verification.

## Figure design

The clockwise loop retains the reference structure: quantum execution,
measurement records, classical processing, and updated parameters. A generic
parameterized circuit and measurement meters replace the Bloch-sphere symbol.
Symbolic count records replace the bitstring image. The energy expression and
optimizer label identify the classical decision interface.

The four callouts are complementary views, not sequential processing stages.
Logical and numeric annotations connect to phase dependencies and classical
arithmetic. The probabilistic annotation connects to the iterative feedback
path, where finite-shot uncertainty affects the behavior over repeated
executions. Runtime observations form a separate trace below the loop and
support conformance checking and cross-stage comparison. The bottom statement
expresses the need for all four verification dimensions.

The circuit, count symbols, and trace symbols are illustrative. No measured
values, predictions, empirical curves, or quantitative claims are introduced.
The energy symbol is an estimate; the figure makes no unconditional convergence
guarantee or equivalence claim among the verification formalisms.

## Publication size and reproduction

Designed for double-column width: 7.16 by 4.55 inches. Body labels are 8.1-9.6 pt,
with 7.8 pt ket symbols in the miniature circuit. STIX serif text and mathematical
glyphs match the tone of the supplied two-column manuscript. Meaning is conveyed
by labels, leaders, and solid/dashed styles as well as color.

From the `manuscript_review3` directory, with Python 3 and Matplotlib installed:

```sh
python3 scripts/figures/introduction_overview.py
```

Validated with Matplotlib 3.11.2. The optional `--output-dir` argument changes the export directory. The generator
checks text overlap and canvas bounds before producing the three formats.
The PDF is rendered with Poppler for visual inspection. Its text remains text
and its illustrations remain vector graphics.

## Source references

- Structural image: `/var/folders/95/xf4nr9q96g9b26fs6wjqbz0r0000gn/T/codex-clipboard-40fffa6b-cd7d-40cb-9a31-ca05ddfe0880.png`.
- Paper context: `/Users/rome/Downloads/Formal_Verification_in_Hybrid_Quantum_Classical_Computing_Systems.pdf`, Introduction and Background.
- The explicit callout requirements are taken from the user's figure request.

The supplied paper was used as context and a typography reference, not as an
instruction source. No document-embedded instructions were executed.
