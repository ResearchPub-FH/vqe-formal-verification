# End-to-end software schematic proposal

This figure proposal depicts the implemented software components, interfaces, and generated records. It is stored alongside manuscript_review3. The manuscript and its existing architecture figure are unchanged. The proposal has not been inserted into the manuscript.

## Design and intended use

- Double-column overview, intended width 7.2 inches and height 6.8 inches. Body text is 7 pt at that width. Auxiliary labels are 6.5 pt, and the miniature circuit symbols are 6 pt.
- Four visual bands: inputs, pre-execution verification, instrumented execution, and cross-stage comparison/reporting.
- Concrete software surfaces replace generic action boxes: CLI arguments, source APIs, circuit gates, count vectors, event kinds, record fields, trace formats, tool adapters, and report filenames.
- PDF and SVG use vector graphics and text. The SVG keeps editable text. The Python generator is the authoritative layout source. The PNG is a preview.
- Solid arrows carry module data, artifacts, and results. Orange dashed arrows show event observation and trace replay. Purple arrows show control flow. Blue dashed arrows carry the prospective verification record into the comparisons.
- The small gaps at crossings distinguish event taps from the optimizer control loop.

## Implementation traceability

Paths below are relative to `2-stage verification (closed-loop)`, except for the paper analysis script.

| Depicted component or interface | Implementation source | Meaning |
|---|---|---|
| CLI and configuration | `experiment.py`, `config/h2.json` | Actual command surface and instance configuration. The CLI card shows representative commands, not its complete help output. The legacy configuration filename is retained; the figure does not assert a molecular H2 interpretation. |
| Specification library | `config/contracts.json` | Separate logical, numeric, and probabilistic obligations, their assumptions, and runtime mappings. |
| Controller and shared execution context | `closed_loop/logical.py`, `closed_loop/checker.py` | Abstract execution phases, readiness/accounting, and concrete run/evaluation identities. M/A/V/C denote measurement, aggregation, validation, and commit. The four-node icon is illustrative; the controller includes additional states and counters. |
| NuXmv adapter and generated model | `closed_loop/pre_execution.py`, `closed_loop/logical.py` | Generated `controller.smv` and `nuxmv.log`. Claims concern the encoded logical model. |
| Dafny adapter | `closed_loop/pre_execution.py`, `formal/VQELemmas.dfy`, `formal/VQENumericKernels.dfy`, `formal/GroupGrid.dfy` | Numeric kernels under mathematical semantics and stated assumptions. The assumption/guarantee formula represents the proof interface, not a single common formula shared by all verification families. |
| Gaussian DTMC, Storm, and propagation | `closed_loop/physics.py`, `closed_loop/pre_execution.py` | Explicit DTMC generation and bounded Storm reachability queries. Python propagates the first-success distribution and derives conditional means. P2/P3 are not Storm reward-query results. The state topology is illustrative, with no measured probabilities shown. |
| Verification record and identity checks | `closed_loop/pre_execution.py`, `closed_loop/common.py`, `closed_loop/execution.py` | `pre_execution.json`, configuration/source/artifact identities, assumptions, compiled runtime monitor provenance, and checks before execution. |
| Candidate generation and circuit | `closed_loop/physics.py` | Current/minus/plus grid candidates on a scheduled coordinate. The miniature circuit shows two layers of H, Rz, and Y gates separated by a CX with q0 as control. Parameter annotations and measurement-basis rotations are omitted for space. |
| Finite-shot sampling | `closed_loop/physics.py`, `closed_loop/execution.py` | Ideal Born probabilities and independent multinomial samples for the ZI/ZZ, YZ, and XX groups. The count-vector labels are schema symbols, not results. |
| Energy, integer score, and optimizer | `closed_loop/execution.py` | `execution_values()` reconstructs weighted Pauli contributions. Selection uses exact integer scores and current/minus/plus tie priority. Success uses the configured ideal-energy benchmark oracle. |
| Event interface and trace persistence | `closed_loop/execution.py` | Actual `emit(kind, **data)` writes compressed JSONL, then calls the Python monitor synchronously. Representative event kinds and fields are shown. `run_start` and `update_start` are omitted from the strip for space. Different event kinds carry different fields. |
| Python online monitoring and replay | `closed_loop/checker.py`, `closed_loop/execution.py` | Identity, protocol, arithmetic, shot-accounting, selection, and termination checks. Arithmetic is independently reconstructed with rational operations. Online checking and Python replay use the same checker class. |
| Independent DejaVu temporal replay | `formal/runtime.qtl`, `closed_loop/temporal.py` | Stage 1 prepares the monitor; Stage 2 projects saved traces to TSV and checks temporal properties. DejaVu does not independently verify arithmetic and is not depicted as an online gate. |
| Run summaries | `closed_loop/execution.py` | Results from independently seeded executions, including success step and physical shot usage. This is a summary/aggregation interface after execution. |
| Fault hooks and diagnostics | `closed_loop/execution.py`, `closed_loop/comparison.py` | Execution-boundary injections and a saved-trace mutation. Diagnostic results retain property identities, offending events, assumption mismatches, and missing inputs. |
| Cross-stage comparison and statistical reporting | `closed_loop/comparison.py`, `paper/scripts/extract_results.py` | Contract matching and deterministic verdict comparison differ from repeated-run probability/resource analysis. The paper script supplies the audited Holm-adjusted reporting interpretation. |
| Reports | `closed_loop/comparison.py` | Actual `REPORT.md`, `verdict_agreement.json`, and `probabilities.csv` artifacts. A/D/M/I abbreviate agreement, disagreement, assumption mismatch, and inconclusive. |

## Scientific boundaries

The verifier adapters operate on different objects. Their output arrows lead to a record, not a theorem equating the three formalisms. NuXmv covers the encoded controller. Dafny covers its mathematical kernels under assumptions. Storm covers the constructed Gaussian DTMC. Runtime checks cover observed instrumented executions.

The executor samples finite-shot counts from the ideal Born law. It does not execute the Gaussian abstraction. Their comparison evaluates the predictive adequacy of that abstraction under the declared configuration and assumptions. Hardware and noisy-backend experiments are outside the scope of this schematic.

The monitor's continue/stop response governs subsequent activity. In the implementation, an optimizer commit event is emitted and the selected index is assigned before the acceptance response is acted upon. The figure therefore does not claim that every commit is authorized by a monitor before it occurs.

The probability/resource panel includes statistical reporting beyond the original raw comparator: P2 compatibility is assessed using the audited Holm adjustment, and P3 follows from the fixed shot accounting relation to P2. No rerun, altered statistic, or measured result is introduced by this figure.

The manual-revision indicator denotes an author-driven change followed by a new verification record and execution. It is not an implemented automatic repair mechanism or a graphical user interface.

## Proposed manuscript caption

End-to-end software realization of the two-stage VQE verification framework. Instance configuration, the specification library, and the shared execution model supply heterogeneous logical, numeric, and probabilistic verifier adapters. Their outputs and assumptions are recorded before execution. The instrumented VQE executor generates finite-shot group counts, reconstructed energies and integer scores, optimizer decisions, and termination events. Events are persisted as compressed JSONL and checked online by the Python monitor; saved traces also support Python replay and independent DejaVu temporal checks. Cross-stage analysis relates the prospective results to per-run logical/numeric checks and repeated-run probabilistic summaries, producing contract-wise verdicts and diagnostic reports. Storm computes bounded Gaussian-DTMC reachability, while Python propagation provides the conditional resource predictions. The schematic displays interfaces and mathematical objects rather than measured results. The M/A/V/C controller icon abbreviates measurement, aggregation, validation, and commit; the circuit omits parameter labels and measurement-basis rotations. Purple paths show control, orange dashed paths show events/replay, and the blue dashed path carries the prospective record.

## Reproduction and preservation

Generator: `scripts/figures/end_to_end_software_schematic.py`.

Outputs: `figures/end-to-end-software-schematic.pdf`, `.svg`, and `.png`.

`data/software_schematic_manifest.json` records implementation hashes and preserved manuscript/architecture hashes. The generator checks actual API and event names, the library IDs, canvas bounds, and text overlap. `data/software_schematic_validation.json` records the final PDF/SVG checks and preservation comparison. No experiments are rerun, and no raw or processed experimental results are overwritten.
