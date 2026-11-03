# Online enforcement and offline replay

This figure illustrates the relationship between two verification paths that use
shared specifications and event semantics. It complements the existing runtime
overview figure by focusing on the reuse of the execution record, the different
timing and operational roles, and the comparison of verdicts.

## Deliverables

- `figures/runtime_verification_online_offline.pdf`: vector publication export.
- `figures/runtime_verification_online_offline.png`: 400 dpi PNG.
- `figures/runtime_verification_online_offline.svg`: editable SVG with live text.
- `scripts/figures/runtime_verification_online_offline.py`: editable Matplotlib source.
- `figures/runtime_verification_online_offline-caption.tex`: double-column LaTeX snippet and caption.
- `data/runtime_paths_layout.json`: generator layout checks and preserved-file hashes.
- `data/runtime_paths_validation.json`: final vector, font, label, and export checks.

## Design

The neutral specification panel feeds both mode containers. The green online and
blue offline paths match the color roles in the supplied runtime overview. The
event positions and labels align across the rows to show their correspondence.
The compact shared panel is centered over the two path containers. The central record
connects recording during execution with replay after execution. The only
control-feedback arrow returns from online checking to the online mode's
execution boundary, identifying its effect on the next instrumented operation.

Both verdicts feed a consistency comparison. This depicts an assessment to
perform and does not assert automatic equality or a theorem of equivalence.
The reused notation $a_i$ and $\tau$ follows the runtime methodology in the
current manuscript source. The symbols are illustrative, not experimental
outputs. No numerical findings, verifier statuses, or raw records are modified.

The archive includes the observed trace and the supporting records and
configuration needed for replay, as explained in the caption. The online trace
may terminate early if enforcement blocks progress. Replay concerns the events
actually recorded. Verdicts should be compared at the same property/trace scope
and under consistent specifications, configuration, and monitor semantics, with
sufficiently complete inputs. Online verdicts are incremental; the lane represents
that repeated process schematically.

## Size and reproduction

Intended placement: double-column, 7.16 by 3.80 inches. Text uses STIX serif fonts
and mathematics, with 8.7-11 pt labels and a 13 pt shared-specifications heading.
Mode and action labels are bold in both
paths, as are the record, replay, and feedback labels. Neutral foregrounds,
including connectors, outlines, the document icon, and shared text, are black.
Labels and spatial organization convey the meaning in grayscale as well as color.

From this directory, with Python 3 and Matplotlib 3.11.2 installed:

```sh
python3 scripts/figures/runtime_verification_online_offline.py
```

Use `--output-dir PATH` to change the export destination. The script uses native
vector shapes and text and checks text overlap and canvas bounds before export.
The exported PDF is rendered and inspected in both color and grayscale.

The main manuscript and the preceding overview figures remain unchanged. The
LaTeX snippet is supplied for replacing the existing figure when integrating
this export; its existing figure label is retained.

## Context

### First annotated revision

The user confirmed the following changes from the annotated PNG:

1. Removed the side note, "Same events / same order."
2. Removed all four vertical dashed correspondence guides.
3. Removed the dashed-line legend and trimmed the resulting bottom whitespace.
4. Applied bold styling consistently to the online and offline mode, action,
   and timing labels.
5. Shortened the shared-specifications panel and centered it on the vertical
   axis through the two path containers. Its supply connector follows the new edge.

### Second annotated revision

Applied corresponding changes across the whole figure:

1. Removed both timing subtitles, "During execution" and "After execution,"
   and centered the remaining mode/action pairs vertically in their label areas.
2. Bolded both bridge labels, "Record" and "Replay."
3. Bolded the complete online feedback label.
4. Changed all neutral foregrounds from gray to black, including the shared
   specification connector, both bridge arrows, all neutral box outlines,
   document-icon strokes, shared text, and trace notation. The pale backgrounds
   and the green/blue path colors retain their roles.

### Third annotated revision

1. Enlarged the shared-specifications heading from 11 to 13 pt, retaining its
   centered alignment and compact panel.
2. Changed the feedback label to "Continue / block the next instrumented
   operation" and updated the corresponding caption and description.
3. Removed the verdict symbols from both online and replay boxes. Centered both
   descriptive verdict labels, reduced both box heights consistently, and
   reattached the online feedback connector to the revised box boundary.

The PDF, PNG, SVG, editable source, caption, and validation records retain their
existing filenames. Main manuscript files and experimental artifacts are unchanged.

Structural reference: `/Users/rome/Downloads/runtime_verification_online_offline.pdf`.
Preceding overview: `/Users/rome/Downloads/runtime_overview.png`.
Notation and methodological scope:
`Formal_Verification_in_Hybrid_Quantum_Classical_Computing_Systems/restructured.tex`,
runtime verification procedure and replay description.

The user's discussion defines the requested redesign. The supplied documents
were treated as reference material, not as instructions to execute.
