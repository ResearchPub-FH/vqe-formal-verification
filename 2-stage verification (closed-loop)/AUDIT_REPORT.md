# Independent Research-Software Audit — Two-Stage (Closed-Loop) VQE Verification Experiment

| | |
|---|---|
| Audit date | 2026-10-06 |
| Auditor | Claude (AI research-software auditor), at the author's request |
| Audited experiment | `2-stage verification (closed-loop)/` — delivered result `artifacts/approved-experiment/` |
| Code version audited | Current working tree. Its source hashes equal the hashes frozen in `artifacts/approved-experiment/stage1/pre_execution.json`; verified with `validate_frozen`. |
| Manuscript audited | `../Formal_Verification_in_Hybrid_Quantum_Classical_Computing_Systems/restructured.tex` (2026-10-02, current draft); `main.tex` (2026-10-01) treated as superseded |
| Mode | Read-only with respect to experiment code and delivered artifacts. Every probe ran on copies, or in the additive `audit/` folder, which is not covered by the frozen source hashes. The only files this audit added are `AUDIT_REPORT.md` and `audit/` (11 scripts). After the audit, `validate_frozen` and the trace-hash audit still pass on `approved-experiment`. |
| Independent tooling | Python 3.8.10, NumPy 1.24.3, SciPy 1.10.1, mpmath 1.3.0, qiskit-terra 0.21.2 (a separate environment); Python 3.14.6 / NumPy 2.5.3 (the experiment's environment, used only for replica, mutation, and gate probes); nuXmv 2.1.0; Dafny 4.11.0; Storm 1.13.0; OpenJDK 17.0.4.1 |

---

## 1. Executive Verdict

### Overall assessment

The two-stage experiment is **technically sound and implemented largely as intended**:

- **One frozen configuration.** A single sealed configuration drives all three pre-execution families and the runtime campaign.
- **Prospective Stage 1.** Stage 1 is frozen and sealed before Stage 2 starts.
- **Per-contract verdicts.** Logical and numeric contracts are checked per run; probabilistic contracts per campaign. Verdicts are reported contract by contract, never as one global PASS.
- **Matched probabilistic campaign.** It uses exactly the Gaussian DTMC's circuit, optimizer, candidates, measurement groups, shots, success predicate, and update bound, with ideal Born statistics and finite-shot sampling only.

Every reported number I could recompute was reproduced, using code paths and an interpreter independent of the experiment. That includes the physics, Gaussian kernel, DTMC, Storm results, all 400 traces, shot totals, success counts, and Wilson intervals. I found **no implementation bug that changes a reported result**.

However, four **MAJOR** issues must be resolved before the results can support a publication.

1. **The benchmark is not H2.** It is labelled H2 throughout, but the operator `0.398 YZ − 0.398 ZI − 0.0113 ZZ + 0.181 XX` is not a molecular-hydrogen qubit Hamiltonian.
2. **NuXmv does not verify why runs terminate.** One logical contract (L4, "termination has the declared reason") is reported as PROVED. Yet the NuXmv properties stay true when budget exhaustion is turned back into `aborted`, which was the cross-layer inconsistency this experiment was meant to resolve.
3. **The only reported probabilistic disagreement (P2/P3) is a statistical false alarm.** The probabilistic decision scheme also has no multiplicity control and no power statement.
4. **The manuscript does not yet describe this experiment.** It still contains statements that this experiment contradicts.

### Research-ready: **CONDITIONAL**

The results are usable once F1–F4 are addressed. Most fixes are reporting or specification changes. Any fix that edits frozen sources (F2, F5, F6, and the `requirements.txt` part of F10) requires a fresh end-to-end run; the full pipeline takes about 30 s.

### Confidence in assessment

- **High** for computational correctness. Every key quantity was independently re-derived: a separate statevector implementation, cross-checked against Qiskit; a separate Gaussian kernel; a 100,000-run finite-shot Monte Carlo; re-derivation of all 40,554 evaluations from raw counts; and model-checker, prover, and monitor negative controls.
- **Medium–high** for methodological and claim judgments. The manuscript predates the experiment, so most "claims" were assessed against the experiment's own README and REPORT and against what the paper would need to say.

### Top blocking issues

| ID | Severity | Issue |
|---|---|---|
| F4 | MAJOR | The manuscript does not describe the two-stage experiment. Its text still says there is no contract library, that layers use different configurations, and that the budget stop is ABORT. Its headline probabilistic result is the unmatched noisy comparison (92.80 % vs 86.75 %). |
| F1 | MAJOR | The canonical "H2" operator is not H2: it has a `YZ` term where H2 has `IZ`, it is complex, its spectrum is ±0.703 / ±0.453, and it has no identity offset. |
| F2 | MAJOR | NuXmv L4 is reported PROVED but does not establish termination reasons. All 7 properties stay true for "budget → aborted" and "success → aborted" mutants. |
| F3 | MAJOR | The P2/P3 "DISAGREEMENT" is a type-I error. The model's conditional mean is 33.11, and the true process mean is 33.12 ± 0.05. The verdict scheme has no multiplicity control (family-wise false-alarm rate ≈ 17 %). "AGREEMENT" at n = 400 can only rule out deviations larger than about 0.036 at 80 % power. |

There are **no CRITICAL findings**. The core cross-stage claim survives: prospectively established contracts are consistent with matched runtime evidence, and the Gaussian DTMC is compatible with the matched empirical campaign.

---

## 2. Reconstructed Experiment

### 2.1 Canonical VQE configuration (reconstructed from code, not documentation)

| Item | Value as implemented | Source |
|---|---|---|
| Hamiltonian | H = 0.398·(Y⊗Z) − 0.398·(Z⊗I) − 0.0113·(Z⊗Z) + 0.181·(X⊗X), written q1⊗q0 (Qiskit labels `YZ, ZI, ZZ, XX`). Integer coefficients ×10⁻⁴: 3980, −3980, −113, 1810. No identity term. | `config/h2.json:4`, `closed_loop/physics.py:18`, enforced by `closed_loop/common.py:63` |
| Operator facts (independent) | Complex Hermitian, max \|Im H\| = 0.398. Spectrum {−0.702930, −0.453081, +0.453081, +0.702930}. E_ref = −0.7029303944595313. | `audit/indep_physics.py`, `audit/qiskit_crosscheck.py` |
| Qubit reduction / mapping | None in the repository. A fixed 2-qubit operator copied from `../vqe_qiskit.py:27–29`; no fermion-to-qubit mapping or tapering code exists. | — |
| Ansatz | EfficientSU2(2, `su2_gates=[h, rz, y]`, circular entanglement → one CX q0→q1, reps = 1): H⊗H, RZ(θ1)⊗RZ(θ0), Y⊗Y, CX(0→1), H⊗H, RZ(θ3)⊗RZ(θ2), Y⊗Y. The hand-written simulator matches Qiskit's EfficientSU2 to ≤ 3.3×10⁻¹⁶ on 203 grid points. | `closed_loop/physics.py:30–43`; `audit/qiskit_crosscheck.py` |
| Parameter dimension / domain | 4 parameters on a finite grid z ∈ {0,…,15}⁴, θ = 2πz/16, wrap-around modulo 16 | `config/h2.json`, `physics.py:23–27,32` |
| Initial parameters | z₀ = (3, 11, 6, 14); ideal energy +0.34523 | `config/h2.json` |
| Optimizer / update rule | Deterministic cyclic coordinate search. Update u uses coordinate (u−1) mod 4. Candidates are {current, current−1, current+1} on that coordinate; the one with the minimum integer score is selected. Ties go current > minus > plus. | `closed_loop/execution.py:65–117` |
| Candidates per update | 3. The current point is re-measured every update; nothing is reused. | `execution.py:78–103` |
| Measurement grouping | 3 groups: {ZI, ZZ} in the computational basis, {YZ} after H·S† on q1, {XX} after H⊗H. ZI and ZZ share bitstrings, and their covariance is retained. | `physics.py:20,49`; `common.py:60` |
| Shots | 1,024 per group per candidate → 9,216 per update, at most 460,800 per run | `execution.py:85–87`; verified in all traces |
| Maximum updates | 50 | `config/h2.json` |
| Stopping rule (runtime) | The run stops after the first update whose selected point is a *success* (ideal-energy oracle), or after 50 updates (`budget`). The initial point is also checked. Any online checker problem gives `contract_abort`. | `execution.py:63–64,118–121`; `config/h2.json:16` |
| Success predicate | E_ideal(z) − E_ref ≤ 0.02. Exactly 8 grid points qualify, with gaps 0.01209 (×4) and 0.01570 (×4). The closest non-success gap is 0.02183, so no point is near the threshold. | `physics.py:65–66,107`; `audit/indep_physics.py` |
| Seeds | Baseline run i uses `SeedSequence([20260721, 0, i])`, i = 0…399. Faults use `[20260721, 1+f, i]`. The bootstrap uses `[20260721, 99]`. | `execution.py:160,206`; `comparison.py:29` |
| Simulator / backend | Hand-written exact NumPy statevector plus `Generator.multinomial(1024, Born probabilities)` per group. No Qiskit or Aer, no backend jobs. | `physics.py`; `execution.py:82–86` |
| Noise | None (`environment = ideal-born-finite-shot`, enforced) | `common.py:62` |
| Runtime instrumentation | Events: `run_start`, `update_start`, `measurement` ×9, `evaluation` ×3, `numeric_valid` ×3, `optimizer_commit`, `terminal`. Each event is written to the trace, then checked synchronously by the Python `RuntimeChecker`; any new problem triggers fail-stop. | `execution.py:54–122`; `checker.py` |
| Trace schema | Every event carries `seq`, `type`, `run_id`, `configuration_digest`. Measurement adds update, candidate, group, index, θ, `evaluation_id`, counts[4], shots. Evaluation adds coefficients, expectations, contributions, energy, integer score. Commit adds choice, `index_after`, `energies_used`, `scores_used`, `evaluation_ids`, cumulative physical shots. Terminal adds reason, updates, index, shots. | `audit` inspection of `baseline-0000.jsonl.gz` |
| Evidence stored for replay | 460 gzip JSONL traces: 400 baseline, 40 controlled-execution fault traces, 10 missing-evidence (mutated) traces, and their 10 unmodified control traces. Each holds raw 4-outcome counts and all derived and optimizer values. Per-trace SHA-256 is in `results.json`; DejaVu input and log hashes are recorded. | `stage2/` |
| NuXmv configuration | Generated controller. Only `maximum_updates` (= 50) comes from the config; 3 groups and 3 candidates are hard-coded. `success` and `environment_error` are free inputs. | `closed_loop/logical.py` |
| Dafny configuration | Configuration-independent real/integer kernels: `VQELemmas.dfy`, `VQENumericKernels.dfy`, `GroupGrid.dfy` | `pre_execution.py:62–69` |
| Gaussian DTMC configuration | 16⁴ grid × 4 coordinate phases = 262,144 states; 755,176 transitions. Mean = ideal energy; variance = Σ_g Var_g / 1024. 24-node Gauss–Hermite quadrature with the A&S 26.2.17 normal CDF; rows renormalized (max correction 5.1×10⁻⁸). Success states are absorbing. Storm queries `P=? [F<=k "success"]` for k ∈ {10, 20, 30, 40, 50}. | `physics.py:77–170`; `stage1/quantitative.json` |
| Runtime configuration | Identical. Stage 2 reads the configuration from the sealed Stage 1 record, not from `config/`. | `execution.py:149–150` |

### 2.2 Actual pipeline (`experiment.py all`)

1. **Stage 1** (`pre_execution.py`):
   - Save the configuration and build the DejaVu monitor from `formal/runtime.qtl`.
   - Generate the controller and run nuXmv: 7 LTL properties.
   - Run Dafny on 3 files.
   - Build the Gaussian kernel, export the explicit DTMC, run Storm, and cross-check Storm against Python forward propagation.
   - Seal the record (`pre_execution.json` and `.seal.json`). Stage 1 status is PROVED / ESTABLISHED_FOR_GAUSSIAN_MODEL, and `ready_for_execution` is required to proceed.
2. **Stage 2 baseline** (`run_baseline`):
   - Refuse to run if the sources, configuration, or Stage 1 evidence changed.
   - Execute 400 runs, each with online checking and an immediate replay by the same checker class.
   - Batch-replay all traces through the DejaVu monitor.
3. **Faults** (`run_faults`): 5 fault types × 10 runs.
4. **Comparison** (`compare`):
   - Re-audit all hashes and fully replay every trace.
   - Logical/numeric rows: aggregate the per-run verdicts.
   - P1: Wilson-interval containment. P2/P3: percentile-bootstrap containment.
   - Write `REPORT.md`, `verdict_agreement.json`, and `probabilities.csv`.

Timeline of the delivered run (UTC, 2026-10-05):

| Step | Time |
|---|---|
| Stage 1 start | 23:18:41.53 |
| Stage 1 frozen | 23:18:47.28 |
| Stage 2 start | 23:18:47.30 |
| Stage 2 end | 23:19:00.77 |
| Report | 23:19:05 |

### 2.3 Important differences from the intended design

1. **The benchmark is not H2** (F1).
2. **The runtime stop rule is the ideal-energy oracle** used by the DTMC, not an observable energy-stability rule. This is deliberate, to keep the runtime matched to the DTMC (F9). The manuscript's runtime experiments use a different rule (|ΔE| ≤ 0.005, patience 3).
3. **Only the matched (ideal) campaign exists.** There is no secondary noisy campaign here; the FakeJakarta comparison exists only in the older experiment and manuscript.
4. **P2/P3 model values come from Python forward propagation**, not Storm reward queries. This is declared.
5. **DejaVu runs as a batch replay after the campaign**, not online.
6. **The logical/numeric "verdict agreement" ignores the Stage 1 status.** It is computed from runtime verdicts only; Stage 2 simply refuses to run unless Stage 1 is all PROVED (F12).
7. **No backend, job, or circuit identities exist**, because this is a direct simulator. Raw counts are trusted as evidence (F16).
8. **The "closed loop" is manual.** A correction requires a new output directory; nothing feeds back automatically.

---

## 3. Contract Traceability Matrix

Status codes: **VALID** means the prospective result and the runtime counterpart are both meaningful and the comparison is sound. **QUALIFIED** means valid with a stated limitation. **WEAK** means a Stage 1 result exists but does not establish what the contract claims.

| Contract | Family | Pre-execution formalization / tool | Assumptions | Runtime counterpart | Comparison semantics | Audit status |
|---|---|---|---|---|---|---|
| **L1** Complete measurements precede candidate-energy aggregation | Logical | nuXmv `G (phase = aggregate -> groups = 3)` = true | Group events identify the actual measurement executions | Python: unique (candidate, group) completeness before `evaluation`. DejaVu: `L1_groupsBeforeEnergy`. | Aggregate of 400 per-run verdicts | **QUALIFIED.** Non-vacuous (aggregate is reachable), and a real early-aggregation mutant is detected. But missing raw evidence is classified as an L1 *DISAGREEMENT* rather than INCONCLUSIVE (F5). |
| **L2** All three candidate validations precede optimizer commit | Logical | nuXmv `G (phase in {select, commit} -> ready = 3)` = true | Commit events correspond to the actual controller boundary | Python: three `numeric_valid` certifications before `optimizer_commit`. DejaVu: `L2_validationsBeforeCommit`. | Aggregate | **QUALIFIED.** Non-vacuous; a skipped-candidate mutant is detected; DejaVu flags 10/10 premature commits. Enforcement is emit-then-check fail-stop, not pre-authorization (F7). |
| **L3** Evaluation identity and parameter provenance remain current | Logical | nuXmv `G (phase = commit -> energy_epoch = epoch)` and `G (phase = start -> X (ready = 0 & groups = 0))` = true | The boolean epoch abstraction stands in for identities | Python: seq, run_id, update number, evaluation_id, index/θ, successor equality. DejaVu: `L3_energyAfterBegin`, `L3_validationAfterEnergy`. | Aggregate | **QUALIFIED.** Both Stage 1 properties detect their mutants. The Stage 1 abstraction is far weaker than the runtime identity checks, so the cross-stage link is nominal (declared in `contracts.json`). |
| **L4** Termination is final and has the declared reason | Logical | nuXmv `G (terminal -> X terminal)`, `G (phase = done_budget -> updates = 50)`, `G (phase = commit -> updates < 50)` = true | The `success` flag abstracts the ideal-energy oracle | Python: terminal reason vs oracle and budget, no activity after terminal. DejaVu: `L4_noActivityAfterStop`. | Aggregate | **WEAK at Stage 1** (F2). The "declared reason" part is not verified: budget→aborted and success→aborted mutants satisfy all 7 properties. The runtime side does check reasons. |
| **N1** Raw counts normalize to the reported expectations | Numeric | Dafny `NormalizeExpectation`: 0 < shots, ones ≤ shots ⇒ e = 1 − 2·ones/shots ∈ [−1, 1] | Correct Pauli, basis, and bit-order mapping (the parity count stands in for "ones"); valid raw counts | Exact `Fraction` parity reconstruction; shot metadata equals Σ counts; valid count vectors | DISAGREEMENT on output errors; ASSUMPTION_MISMATCH on invalid inputs; INCONCLUSIVE on missing counts | **QUALIFIED.** Sound. The Dafny lemma is the single-bit form; the multi-qubit parity mapping is an assumption (F11). |
| **N2** Declared coefficients and measurements produce the actual energy | Numeric | Dafny `TermEnergyContribution`, `ComputeTermEnergies`, `AggregateEnergy`, `SumProdWithinL1` (reals) | Complete, uniquely identified terms; faithful optimizer instrumentation; 10⁻¹² tolerance | Exact rational reconstruction compared against contributions, energy, integer score, `energies_used`, `scores_used` | DISAGREEMENT on any deviation beyond tolerance | **VALID.** Observed max error 5.5×10⁻¹⁷. The runtime reference is an unverified Python `Fraction` routine, not the Dafny code (F11). |
| **N3** Unique measurement groups determine physical shot consumption | Numeric | Dafny `GroupGrid.AccumulatePhysicalGroups` (a loop sums a list of naturals) | Records enumerate unique physical executions; declared allocation | Per-(candidate, group) allocation equals 1,024; no double counting; cumulative and terminal totals | DISAGREEMENT on accounting errors; ASSUMPTION_MISMATCH (invalidating P1–P3) on changed allocation | **QUALIFIED.** The runtime side is meaningful. The Stage 1 "proof" is trivial and contains no uniqueness or physical-shot semantics (F11). |
| **N4** Candidate generation and selection preserve the parameter grid | Numeric | Dafny `WrapCandidate` (modular arithmetic) and `SelectCandidate` (argmin with tie priority) | Angle conversion and gate implementation are trusted | Recomputed candidates, exact-energy argmin with tie priority, successor and θ checks | DISAGREEMENT on mismatch | **VALID.** A Dafny tie-priority mutant fails verification, as it should. |
| **P1** P(first success ≤ k), k ∈ {10, 20, 30, 40, 50} | Probabilistic | Storm `P=? [F<=k "success"]` on the Gaussian DTMC: 0, 0, 0.383940, 0.756253, 0.928027 | Same circuit, optimizer, groups, shots, stop predicate, and update unit; Gaussian approximation; independent seeds | 400 matched ideal-Born finite-shot runs; first-success proportions | AGREEMENT if the model value lies inside the empirical 95 % Wilson interval; k = 50 is primary; gate → ASSUMPTION_MISMATCH or INCONCLUSIVE | **VALID and genuinely matched.** Compatible at all checkpoints. Power is limited (F3), and k = 10, 20 are structurally zero (F19). |
| **P2** E[first-success update \| success ≤ 50] | Probabilistic | Python propagation of the same kernel: 33.1112 (Storm only checks P1) | P1 assumptions; same conditioning | Mean over 366 successful runs: 32.290, percentile bootstrap [31.58, 32.99] | AGREEMENT if the model value is inside the bootstrap interval | **VERDICT UNRELIABLE.** The reported DISAGREEMENT is a false alarm: the true process mean is 33.12 ± 0.05 (F3). |
| **P3** E[physical shots \| success ≤ 50] | Probabilistic | P2 × 9,216 = 305,152.7 | Fixed allocation, no retries | P2 × 9,216 | Same as P2 | **Redundant** with P2. Not independent evidence (declared). |

---

## 4. Critical and Major Findings

**No CRITICAL findings.** Four MAJOR findings follow, then an index of all other findings.

### F1 — The canonical "H2" benchmark is not the H2 Hamiltonian · **MAJOR**

**Location:**
- `config/h2.json:4` (`"terms": {"YZ": 3980, "ZI": -3980, "ZZ": -113, "XX": 1810}`) and the config name `h2-two-stage-closed-loop-v1`
- `closed_loop/physics.py:18`; `closed_loop/common.py:63`
- `README.md:69`
- Origin: `../vqe_qiskit.py:27–29`
- Manuscript labels "H$_2$": e.g. `restructured.tex:568, 790, 820, 825`
- Sibling docs: "molecular hydrogen, represented here by a reduced two-qubit model"

**Evidence:**
- **The operator is complex.** It contains Y⊗Z, a single-Y string with imaginary matrix elements: max |Im H| = 0.398. Standard real-orbital fermion-to-qubit encodings of H2 (Jordan–Wigner, parity, Bravyi–Kitaev, including two-qubit tapering) produce real-symmetric Hamiltonians with no odd-Y strings.
- **The standard operator differs.** The STO-3G, 0.735 Å parity-reduced H2 Hamiltonian is −1.0524·II + 0.3979·IZ − 0.3979·ZI − 0.0113·ZZ + 0.1809·XX. It has `IZ` where this benchmark has `YZ`, plus an identity offset.
- **The spectra differ.** Standard H2: {−1.8573, −1.2446, −0.8827, −0.2249}, with non-identity ground −0.80490. Benchmark: {±0.70293, ±0.45308}, symmetric about zero.
- See `audit/indep_physics.py` and `audit/qiskit_crosscheck.py`.

**Why it matters scientifically:**
- The paper's benchmark identity is factually wrong.
- "E_ref = −0.70293" is presented as the H2 reference energy.
- Any chemistry-literate reviewer will notice a complex "H2" operator with a single-Y term.
- The user requirement ("an H2 VQE instance unless another instance is documented and justified") is not met. The instance is consistent across layers, but it is not H2 and the substitution is not justified anywhere.

**Effect on reported results:** None on internal validity. Every logical, numeric, probabilistic, and runtime result is correct *for the stated operator*. Only claims that the benchmark is H2 (or molecular hydrogen) are incorrect.

**Minimal correction:** Either
- **(a) Relabel** everywhere (config name, README, manuscript, figures) as "a two-qubit benchmark Hamiltonian (operator from the Qiskit VQE tutorial used in `vqe_qiskit.py`)", and drop "molecular hydrogen" and "H2 ground energy" wording; or
- **(b) Replace it with a documented H2 operator** and rerun everything: Stage 1 (new DTMC and success set) and Stage 2.

Option (a) needs no rerun.

### F2 — nuXmv L4 is reported PROVED, but no property establishes termination *reasons* · **MAJOR**

**Location:**
- `closed_loop/logical.py:66–69` (L4, L4_budget, L4_bound)
- `config/contracts.json` (L4 description: "Termination is final and has the declared reason")
- `README.md:98` ("The controller distinguishes success, normal budget termination, and error abort")
- `stage1/pre_execution.json` (L4 → PROVED)

**Evidence:** `audit/nuxmv_negative_controls.sh` runs the frozen controller and its mutants.

- **The frozen model is non-vacuous.** Every antecedent phase is reachable: aggregate, select, commit, done_success, done_budget, aborted, and commit at updates = 49. `F terminal` holds.
- **Mutant M4 (budget exhaustion → `aborted`).** This is exactly the old "ABORT at the cap" semantics. **All 7 properties remain true.** The witness `G !(phase = done_budget)` is *true*, so `L4_budget` becomes vacuous.
- **Mutant M6 (success → `aborted`).** **All 7 properties remain true.**
- **Control mutants are detected:**

  | Mutant | Fails |
  |---|---|
  | Early aggregation | L1 |
  | Skipped candidate | L2 |
  | No readiness reset | L3_reset |
  | Stale energy epoch | L3 |

**Why it matters scientifically:**
- The DONE vs ABORT disagreement between the logical and runtime layers was the motivating cross-layer inconsistency.
- In this experiment it is fixed **only by model construction**: the `done_budget` branch exists. It is **not a verified property**.
- The "PROVED" status for L4 therefore overstates what Stage 1 establishes. The L4 cross-stage AGREEMENT pairs a weak Stage 1 property with a much stronger runtime check.

**Effect on reported results:** The L4 row's Stage 1 column is accurate only for "terminal states are absorbing" plus the budget-bound conditions. The termination-reason semantics are established at runtime only.

**Minimal correction:**
1. Add these to `logical.py`:
   - `G ((phase = check & !success & updates = K) -> X phase = done_budget)`
   - `G ((phase = check & success) -> X phase = done_success)`
   - `G ((!terminal & X phase = aborted) -> environment_error)`
   - Positive reachability witnesses (e.g. `SPEC EF phase = done_budget`, `SPEC EF phase = done_success`, `SPEC EF phase = aborted`) that are required to be true.
2. Make Stage 1 require all of them.
3. Rerun the pipeline. Sources change, so a new Stage 1 and Stage 2 are required.

### F3 — P2/P3 "DISAGREEMENT" is a false alarm, and the probabilistic verdicts lack multiplicity control and a power statement · **MAJOR**

**Location:**
- `closed_loop/comparison.py:96–118` (decision rules)
- `artifacts/approved-experiment/comparison/REPORT.md` (P2 and P3 rows: DISAGREEMENT)
- `config/contracts.json` (P1–P3 comparison rules)

**Evidence** (`audit/stats_recompute.py`, `audit/indep_montecarlo.py`, `audit/replica_executor.py`):

- **The campaign's P2 deviation is a large but chance draw.**
  - Model: E[T | T ≤ 50] = 33.111.
  - Campaign: 32.290 (n = 366), z = −2.27, raw two-sided p = 0.024.
  - Holm-adjusted across the 4 informative comparisons (P1@30, P1@40, P1@50, P2): p = 0.094.
- **The truth matches the model.**
  - Executor replica, 20,000 fresh seeds: 33.12 ± 0.10.
  - Independent finite-shot Monte Carlo, 100,000 runs: 33.12 ± 0.05.
  - The campaign's first-success distribution is consistent with the executor's: binned χ² p = 0.52; KS p = 0.10.
- **False alarms are expected under this scheme.** When the model is exactly right, the 4 informative marginal checks raise at least one false "DISAGREEMENT" in **16.8 %** of 400-run campaigns. P3 is P2 × 9,216, so it is the same test counted twice.
- **Power is limited.** For P1@50, H₀ is rejected only when |p̂ − p_G| > 0.0253. The deviation detectable with 80 % power is ≈ 0.036, and a true deviation of 0.02 is detected with only 36 % power.
- **The agreement claim itself is correct.** The independent Monte Carlo shows the actual Gaussian-model error is ≤ 0.0023 at every checkpoint, and 0.00026 at k = 50.

**Why it matters scientifically:**
- The only non-agreement in the experiment would be read as evidence that the Gaussian DTMC mispredicts time-to-success. It is not.
- Conversely, the P1 "AGREEMENT" is a non-rejection with about ±0.03 resolution, not a demonstration of accuracy.

**Effect on reported results:**
- P1 verdicts are correct as compatibility statements.
- The P2/P3 verdicts are misleading as reported.
- The probabilistic layer's actual accuracy is much better than the campaign alone can show.

**Minimal correction (reporting; no rerun needed):**
- Declare P1@50 the sole primary test and treat the others as supporting, with Holm-adjusted p-values or purely descriptive reporting.
- Report P2 as "not significant after multiplicity adjustment" and P3 as derived.
- State the minimum detectable deviation.
- Rename verdicts: "statistically compatible / deviation at α (marginal)".
- Optionally, *pre-declare* a separate large-n validation (≥ 10⁴ runs, new seed declared before running) as a supplementary experiment.

**Do not re-seed the primary campaign post hoc** to make P2 agree.

### F4 — The manuscript does not describe the two-stage experiment and contradicts it in several places · **MAJOR**

**Location** (all in `restructured.tex`):

| Line(s) | Statement |
|---|---|
| 134 | "not a released contract library" (but `config/contracts.json` now exists) |
| 205 | "We report each experiment's configuration instead of treating the four layers as checks of one identical run" |
| 128, 264–269 | NuXmv "ABORT when it reaches the limit" (the new controller has `done_budget`) |
| 537 | "The two experiments also use different circuits, optimizers, and measurements" (now matched) |
| 47, 805–813, 823–882 | The headline probabilistic result is the *noisy* FakeJakarta comparison (92.80 % vs 86.75 %); the matched campaign (91.5 %) is absent |
| 553–575 | The campaign table has no two-stage experiment |
| 487, 1097 | The runtime approval protocol (ask/tell + ACK) belongs to the older runtime project, not this experiment |

**Evidence:** The manuscript files are dated 2026-10-01/02; the experiment was created 2026-10-05. No section, table, or number in the manuscript refers to `approved-experiment`.

**Why it matters scientifically:** The new experiment is the paper's answer to RQ3 ("When do guarantees compose across layers?"). As written, the paper states the opposite design: separate configurations, no contract library, ABORT semantics. It also offers no matched validation.

**Effect on reported results:** The new results cannot be cited in the current text without contradiction.

**Minimal correction:**
- Rewrite Sections III–VI around the two-stage experiment: configuration table (§2.1 above), contract library (§3), stop and success semantics (F9), matched campaign results with F3-compliant statistics, and fault results with full verdict vectors (F5, F6).
- Keep the FakeJakarta results only as a separately labelled out-of-model robustness experiment.
- Fix F1 terminology throughout.

### Index of other findings

| ID | Severity | Finding | Section |
|---|---|---|---|
| F5 | MODERATE | Deleting raw counts from a saved trace yields an L1 *DISAGREEMENT* (a spurious logical conflict). The fault table reports only N1 = INCONCLUSIVE and hides it. | 8, 11 |
| F6 | MODERATE | The fault suite is narrow: one injection site (update 1, candidate 0); 10 "tests" per fault are replications with identical verdict vectors; `probabilistic_applicability` is hard-coded; no missing-term, stale-input, termination, or Stage 1-mutant controls. | 11 |
| F7 | MODERATE | Runtime enforcement is emit-then-check fail-stop. The commit event is persisted and `index = selected` is assigned before acceptance is consulted. This is not pre-authorization. | 8 |
| F8 | MODERATE | "Online/replay agreement" re-runs the same `RuntimeChecker` class, so it checks determinism, not independence. Independent coverage is DejaVu (5 ordering projections) plus hashes. | 8 |
| F9 | MODERATE | The runtime stop rule is the ideal-energy oracle. That is correct for matching, but it is not an observable VQE stopping rule, and it differs from the manuscript's runtime experiments. It must be stated wherever the runtime results are discussed. | 8, 9 |
| F10 | MODERATE | Reproducibility: NumPy and Python are unpinned. Bitwise reproduction needs NumPy 2.5.3: 113/400 runs diverge under 1.24.3. Tools are resolved from sibling folders and PATH; the Java version is unrecorded. The README's `audit` command rewrites the delivered comparison files, which would break `completion_audit.json`'s `result_sha256`. Stage 2 results are unsealed. | 12 |
| F11 | MODERATE | Numeric-contract mapping: the N3 Dafny lemma is a trivial list sum; N1 is the single-bit form; all N contracts receive one aggregate status; the runtime reference is unverified Python; Dafny reasons over reals. | 6 |
| F12 | MODERATE | The cross-stage logical/numeric verdict is computed from runtime verdicts only. The scheme cannot represent a (Stage 1 FAIL, runtime …) cell, and the closed-loop feedback is manual. Claims about the "closed loop" must be scoped. | 9 |
| F13 | MINOR | Prospective status: the approved run re-executes the same seeds after `primary` and `primary-v2` had already revealed the outcomes. No tuning was found (only `checker.py` and `execution.py` changed; the model and decision rules are hash-identical). This needs disclosure, and "fresh execution data" (`README.md:184`) is inaccurate. | 12, 13 |
| F14 | MINOR | NuXmv model omissions: success at 0 updates is not representable; abort causes differ (environment error in the model vs contract abort at runtime); no parameter-readiness variable; Stage 1 runs no reachability witnesses (verified manually here). | 5 |
| F15 | MINOR | The "Checks" counts are bookkeeping (e.g. +1 L4 check per event), not independent obligations. | 8 |
| F16 | MINOR | Evidence identity is trusted. Consistent relabelling or fabrication of counts passes every check. This is declared trusted base, but must be stated. | 8 |
| F17 | MINOR | The Stage 1 status of P2/P3 ("ESTABLISHED_FOR_GAUSSIAN_MODEL") is inherited from Storm's P1 check (`pre_execution.py:90`). | 7 |
| F18 | MINOR | Unconditional resource expenditure is computed (model 34.33 updates) but neither compared nor reported. The campaign gives 33.80 [32.98, 34.61]. | 10 |
| F19 | MINOR | The k = 10 and 20 checkpoints are structurally zero in both the model and the process, yet are reported as "AGREEMENT". | 10 |
| F20 | MINOR | `completion_audit.json` is not produced by the pipeline. The Stage 1 artifact hash map covers only top-level files (the `monitor-build/` subfolder is unhashed, though the jar is hashed). | 12 |
| F21 | MINOR | `main.tex` keeps superseded over-claims ("soundness w.r.t. the shared model for every property", "assume-guarantee composition results", "lifting Boolean to probabilistic guarantees"). | 13 |

---

## 5. Logical Verification Audit

**Correspondence to the workflow.** The generated controller (`logical.py`) models per update: `start → (measure ×4 steps: groups 0→3) → aggregate → validate`, repeated for 3 candidates, then `→ select → commit → check → {done_success | done_budget | start}`. Environment errors in `measure` or `validate` lead to `aborted`. This matches the executor's event order: 9 measurements, 3 evaluations, 3 validations, commit, success check.

**Guards and updates.** I traced every branch.

- `groups` increments on each `measure` step and resets at `start` or `validate`.
- `ready` increments at `validate` and resets at `start`.
- `epoch` toggles at `start`; `energy_epoch := epoch` at `validate`.
- The default `TRUE : aborted` branch is unreachable: `G ((!terminal & X phase = aborted) -> environment_error)` holds.

**Re-verification.** nuXmv 2.1.0 reproduces 7/7 true (`stage1/nuxmv.log`).

**Vacuity and reachability (manual; not part of Stage 1).**
- All antecedent phases are reachable, including `commit` at `updates = 49` and `done_budget`.
- `F terminal` is true, so every path terminates.
- Fair-cycle concerns do not arise: the model is acyclic up to the bounded counter.

**Mutation sensitivity.**

| Injected fault | Detected? |
|---|---|
| Early aggregation | Yes (L1) |
| Skipped candidate | Yes (L2) |
| Missing readiness reset | Yes (L3_reset) |
| Stale energy epoch | Yes (L3) |
| Budget → aborted | **No** (F2) |
| Success → aborted | **No** (F2) |

My first versions of the early-aggregation and skipped-candidate mutants had no effect, because earlier `case` branches shadowed them. They were rewritten as genuine faults; the effective versions are in `audit/nuxmv_negative_controls.sh`.

**DONE vs ABORT and the runtime.**
- The model distinguishes `done_success`, `done_budget`, and `aborted`.
- The runtime emits `success`, `budget`, and `contract_abort`.
- The checker enforces `budget ⇒ updates = 50 ∧ ¬success` and `success ⇒ oracle(index)` (`checker.py:261–272`).
- Budget exhaustion is therefore classified consistently *in the model and at runtime*, but this is **not a verified property** (F2).

**Three different statements.**
- *Property correctness:* the 7 properties are true of the model.
- *Model correctness:* the model is a reasonable abstraction, with the omissions listed in F14.
- *Model-to-implementation correspondence:* this is argued manually and supported by the runtime checks. It is not proved.

A nuXmv PASS is a statement about the generated model only.

---

## 6. Numeric Verification Audit

**Dafny re-verification.**
- Dafny 4.11.0 verifies 8, 11, and 5 units with 0 errors, as recorded.
- There are no `assume`, `{:axiom}`, `{:verify false}`, `{:extern}`, or bodiless lemmas.
- Negative control: changing `SelectCandidate`'s tie priority produces 1 verification error, as expected.

**Mathematical content vs claims.**

| Item | Assessment |
|---|---|
| Expectation bounds | `NormalizeExpectation` proves 1 − 2·ones/shots ∈ [−1, 1]. Correct. Applying it to multi-qubit parity counts relies on the declared mapping assumption. |
| Aggregation and energy bounds | `ComputeTermEnergies` / `AggregateEnergy` prove the sum of products and the L1 bound. Correct. |
| Term completeness and alignment | `CompleteTermRecord` is a precondition, not a runtime check. At runtime, completeness and alignment are established by checking term sets and comparing coefficients against the frozen manifest (`checker.py:187–189`). |
| Shot accounting | `AccumulatePhysicalGroups` proves only that a loop sums a sequence. Uniqueness of groups is entirely a runtime check (F11). |
| Grid and selection | `WrapCandidate` and `SelectCandidate` are meaningful and match Python semantics: Euclidean `%` and first-index argmin. |
| Convergence calculations | `EnergyDelta` and `CheckConverged` are verified but unused here, because the energy-change (\|ΔE\|) rule is not part of this experiment. |

**Assumption discharge at runtime.**

| Dafny assumption | Checked at runtime? |
|---|---|
| shots > 0 | Yes (`checker.py:159`) |
| ones ≤ shots | Yes; implied by valid count vectors |
| Valid expectations | Yes; −1 ≤ e ≤ 1 on the exact reconstruction |
| Complete, aligned term records | Yes; term sets plus coefficient manifest |
| Distinct candidates on the grid | Yes; candidate recomputation |

The runtime check is an *output* check, not merely an input-assumption check. Each reported value is compared with an exact rational reconstruction from raw counts. This is stronger than assumption discharge.

**Circularity check.**
- The checker never calls `execution_values`.
- It reconstructs from raw counts and the frozen manifest (`checker.py:32–45`).
- Optimizer inputs (`energies_used`, `scores_used`) are compared against the checker's own exact values, not against the executor's evaluation events.
- One shared dependency remains: `ideal_success` (`physics.py:65`), which the executor, checker, and DTMC all use. Its success set was confirmed independently: the same 8 points, a margin of 0.0018 to the threshold, and a match with Qiskit.

**Independent recomputation.**
- All 400 traces were re-derived with my own parser and parity tables, in exact arithmetic (`audit/trace_rederivation.py`).
- 40,554 evaluations: max energy error 5.54×10⁻¹⁷; expectation error 0.
- 0 mismatches in scores, choices, optimizer inputs, candidate generation, successors, success steps, terminal reasons, shot totals, or trace hashes.

**Floating point vs reals.**
- Tolerances are 10⁻¹² absolute. The observed maximum rounding error is 5.5×10⁻¹⁷, and the score granularity is about 10⁻⁷.
- So the tolerance is about 4 orders above actual rounding and about 5 orders below any meaningful difference. It is justified and applied consistently: exact integers for counts, shots, and indices; exact rationals as the reference.
- Expectations are exact (division by 1024 = 2¹⁰).

---

## 7. Probabilistic Verification Audit

**Mathematical reconstruction.** For grid point z and group g, let p_g(·|z) be the Born law in the rotated basis and V_g(o) the group value (Σ over terms in g of coefficient × eigenvalue).

- **Candidate estimator:** Ê(z) = Σ_g (1/1024) Σ_{shots} V_g, with mean E_ideal(z) and variance Σ_g Var_{p_g}(V_g)/1024. The ZI/ZZ covariance is retained because they share a group.
- **Selection probability:** p_j = ∫ φ_j(x) Π_{i≠j} [1 − Φ((x − μ_i)/σ_i)] dx, computed by 24-node Gauss–Hermite quadrature with the A&S normal CDF, then clipped and row-normalized.
- **State** = (z, phase = update mod 4). This is a sufficient statistic: the optimizer has no other memory, and the current point is re-measured each update. No semantically different optimizer states are merged.
- Success states are absorbing; Storm checks `F≤k`.

**Verification of the implementation.**
- **Means and variances:** an independent statevector gives the same energies (Qiskit ≤ 3.3×10⁻¹⁶). The estimator variance range is [1.548×10⁻⁴, 3.415×10⁻⁴], matching `quantitative.json`.
- **Kernel:** an independent kernel (exact `ndtr`, 160-node Gauss–Hermite, adaptive-quadrature spot checks agreeing to 1.9×10⁻¹⁵) differs from the saved kernel by at most **3.15×10⁻⁸**. Saved rows sum to 1 within 2.2×10⁻¹⁶. The renormalization correction is ≤ 5.1×10⁻⁸.
- **Normalization:** Σ_j p_j = 1 holds for every state in both kernels.
- **Exported DTMC:** 262,144 states and 755,176 transitions. 31,192 underflowed zero-probability edges are omitted (smallest kept: 1.06×10⁻³⁴). The `init` label (state 15214 = z₀ at phase 0) and 32 absorbing success states are correct. There is no duplication or omission.
- **Storm:** a re-run of Storm 1.13.0 reproduces P(≤50) = 0.92802722250063. My own sparse propagation over the exported `.tra` agrees, and so does the independent kernel's CDF (Δ ≤ 4.9×10⁻⁹). The unbounded P(F success) = 1.
- **Ties:** the continuous model has zero tie probability. In the finite-shot process, exact ties at the minimum occurred 25 times in 3.43 million updates (7.3×10⁻⁶ per update), which is negligible.
- **Rewards:** there are no Storm reward models. P2 (33.1112) and the unconditional E[min(T, 50)] (34.3267) come from Python propagation and were reproduced independently. Successful-path conditional means and unconditional means are distinct quantities, and both are computed correctly; only the conditional one is reported (F18).
- **Stage 1 labels:** P2 and P3 inherit the status "ESTABLISHED_FOR_GAUSSIAN_MODEL" from Storm's P1 checkpoint check (`pre_execution.py:90`), although Storm never computes them. The REPORT text clarifies this, but the record's per-contract status overstates it (F17).

**Is the Gaussian approximation justified?** Yes, for this configuration, and checked empirically rather than proved.
- Each candidate score sums 3,072 bounded draws.
- Per-transition differences between exact multinomial selection (400,000 samples per state) and the Gaussian kernel are **≤ 0.0007** across 10 probed states (`audit/per_transition_check.py`).
- At process level, a 100,000-run exact finite-shot Monte Carlo gives P(≤50) = **0.92829 ± 0.0016** against the model's 0.92803. The model error is ≤ 0.0023 at every checkpoint (§14).
- No certified error bound exists, and the README correctly says so.

**Exact vs approximate claims.**
- Storm's numbers are **exact properties of the constructed Gaussian DTMC**, up to floating-point and quadrature error of about 10⁻⁸.
- Statements about the **finite-shot VQE process** are approximate.
- The README and REPORT keep this distinction ("ESTABLISHED_FOR_GAUSSIAN_MODEL"; "no certified approximation-error bound"), and the paper must too.
- "Exhaustive" applies only to the Gaussian DTMC.

---

## 8. Runtime Verification Audit

**Identity preservation.**

| Identity | How it is preserved |
|---|---|
| Evaluation | `evaluation_id = run:u:c` |
| Parameters | Grid index plus θ, re-derived from the index to 10⁻¹² |
| Measurement group / term | `group` and the frozen manifest |
| Evidence | Inline raw counts |
| Reconstructed energy | `evaluation` event with the same `evaluation_id` |
| Successor parameters | `index_after = candidates[choice]`; the next `update_start.index` must equal it |
| Backend / job / circuit | None. This is a direct simulator; the circuit and basis rotations are trusted base. |

**Ordering and causality.**
- Python enforces `seq` continuity, `run_start` first, nothing after `terminal`, measurements before evaluation, unique validations before commit, and the current update number.
- DejaVu enforces 5 past-time projections.
- **Monitor negative controls** (`audit/dejavu_negative_controls.py`): each of the 5 properties fires on a crafted violation, a compliant trace passes, and cross-update identity confusion (groups recorded for update 1, energy claimed for update 2) is detected.

**Cross-evaluation confusion.** Re-inserting a measurement from update k−1 into update k is caught as L3, and also as N1/N2/N4 because the derived values no longer match. Stale optimizer inputs (update-1 energies reused at update 2) are caught as N2.

**Checker mutation probes** (`audit/checker_mutations.py`):

| Probe | Result |
|---|---|
| Commit before the last validation | L2 DISAGREEMENT |
| Duplicate commit | L2 DISAGREEMENT |
| Non-argmin choice | N4 DISAGREEMENT |
| Success relabelled as budget | L4 DISAGREEMENT |
| Shot metadata ≠ counts | N1 ASSUMPTION_MISMATCH |
| Truncated trace | L4 INCONCLUSIVE |
| Perturbation below tolerance | Accepted, by design |
| Consistent relabelling or fabrication of raw counts | **Accepted** (F16) |

**Optimizer mutation point** (F7).
- `execute_run` writes each event to the trace and *then* calls the checker (`execution.py:55–60`).
- On commit it assigns `index = selected` before testing `accepted` (`execution.py:109–117`), then aborts the run if the check failed.
- The parameter state is therefore not prevented from changing. The run fails closed immediately afterwards.
- No baseline or fault run exercises a rejected-but-applied commit: the premature-update fault breaks before assignment.
- Describe this as "synchronous fail-stop monitoring", not "approval before mutation".

**Duplicate and stale handling.**
- Duplicate group events are flagged and not double-counted (unit test plus probe).
- Duplicate evaluations, validations, and commits are flagged.

**Incomplete history.**
- A missing terminal event gives L4 INCONCLUSIVE.
- Missing counts give N1/N2/N3/N4/L2 INCONCLUSIVE but **L1 DISAGREEMENT** (`checker.py:151,179`; codified by `tests/test_experiment.py:65`). This contradicts the principle that absent evidence is INCONCLUSIVE (F5).

**Replay independence** (F8). `replay()` instantiates the same `RuntimeChecker`, so the 400/400 online/replay agreement demonstrates determinism and persistence integrity, not independent verification. Independence comes from:
- per-trace SHA-256 checks, which detect corrupted saved evidence;
- DejaVu (ordering only); and
- this audit's from-scratch re-derivation.

**Integrity limits.** Stage 2 `results.json` is not sealed. In a scratch copy, a substituted trace with a matching edited `results.json` passed the experiment's own audit. The README already disclaims cryptographic authenticity.

**Other minor points.** The "Checks" column counts `require` calls, including one L4 "check" per event (`checker.py:92`). The 1.36 million L3 checks are not independent obligations (F15).

---

## 9. Cross-Stage Consistency Audit

**Contract-wise, not global.** `compare()` produces one row per L/N contract (aggregated over 400 runs) and one row per probabilistic checkpoint or mean. No single global PASS bit exists.

**Logical/numeric classification.** The vocabulary is AGREEMENT / DISAGREEMENT / ASSUMPTION_MISMATCH / INCONCLUSIVE, with precedence DISAGREEMENT > ASSUMPTION_MISMATCH > INCONCLUSIVE > AGREEMENT.

- The row verdict is computed **from runtime verdicts only** (`comparison.py:86–94`). The Stage 1 status is displayed but not used.
- This is safe only because Stage 2 refuses to run unless every Stage 1 family is PROVED (`common.py:111–112`).
- Consequently the matrix can never show a (Stage 1 FAIL or NOT_ESTABLISHED, runtime …) cell, and the "closed loop" consists of a manual correction plus a new output directory (F12).
- Naming runtime results "AGREEMENT/DISAGREEMENT" at the run level conflates "obligation satisfied" with "stages agree". Consider SAT / VIOLATED at run level and CONSISTENT / CONFLICT at the cross-stage level.

**Probabilistic classification.**
- P verdicts are computed **only at campaign level**: Wilson containment for P1, bootstrap containment for P2/P3.
- **A single failed run never refutes a probability.** Budget-terminated runs simply count as non-successes. I checked the code paths for any per-run probabilistic verdict and found none.
- The eligibility gate (`comparison.py:96`) is sound:
  - Any run with ASSUMPTION_MISMATCH makes every P verdict ASSUMPTION_MISMATCH. I verified this end to end in `audit/gate_probe.py`: substituting one shot-mismatched run turns all P1–P3 verdicts into ASSUMPTION_MISMATCH, never FAIL.
  - Any non-standard termination, DISAGREEMENT, or INCONCLUSIVE makes them INCONCLUSIVE.
- The gate is conservative: one mismatched run invalidates applicability for the whole campaign. This is defensible.

**Semantic consistency of success vs stopping** (task item 8).
- In this experiment both stages classify success with **the same predicate**, E_ideal(z) − E_ref ≤ 0.02, from the same function.
- The success sets are identical across the DTMC, the runtime, and my independent computation.
- The older |ΔE| ≤ 0.005 patience rule is **not used** anywhere in this experiment, so there is **no semantic mixing**.
- Because the runtime stop *is* the oracle (F9), the runtime controller is a benchmark harness rather than a deployable VQE stopping policy. The paper must say this, and must not merge these results with the manuscript's |ΔE|-rule runtime experiments.

**One canonical instance (blocking requirement).** **Satisfied** for internal consistency; F1 still applies to the name.

| Aspect | Evidence |
|---|---|
| Hamiltonian, groups, candidates, schedule, stop rule, environment | Enforced by `validate_config` |
| Configuration across stages | Stage 2 uses the sealed Stage 1 configuration; the digest is identical in every event and record |
| Number of measurement groups | 3 in the DTMC variance, the NuXmv model, the runtime traces (9 measurement events per update), and the checker |
| Shots | 1,024 per group, checked exactly |
| Earlier 3-group vs 4-task mismatch | **Fully resolved in this experiment.** The 4-PUB workload survives only in the manuscript's separate runtime experiments. |

---

## 10. Statistical Rigor

**Independent runs.** The 400 runs use distinct `SeedSequence` entropy, giving statistically independent streams. Independence is also confirmed empirically: the campaign is distributed like 20,000 fresh executor runs (χ² p = 0.52).

**Data reuse.** `primary`, `primary-v2`, and `approved-experiment` share seeds and produce identical per-run outcomes. `artifacts/README.md` correctly forbids pooling them (F13).

**Probability comparison** (recomputed independently):

| k | Model p_G | Successes | p̂ | Wilson 95 % (report = mpmath, Δ ≤ 1.1×10⁻¹⁶) | Clopper–Pearson | Score-test p | \|Δp\| | Truth: independent MC (100k) | Executor (20k fresh) |
|---|---|---|---|---|---|---|---|---|---|
| 10 | 0 | 0/400 | 0 | [0, 0.0095] | [0, 0.0092] | — (structural 0) | 0 | 0 | 0 |
| 20 | 0 | 0/400 | 0 | [0, 0.0095] | [0, 0.0092] | — (structural 0) | 0 | 0 | 0 |
| 30 | 0.383940 | 169/400 | 0.4225 | [0.3751, 0.4714] | [0.3736, 0.4726] | 0.113 | 0.0386 | 0.3823 ± 0.0030 | 0.3829 ± 0.0067 |
| 40 | 0.756253 | 307/400 | 0.7675 | [0.7237, 0.8062] | [0.7230, 0.8080] | 0.600 | 0.0112 | 0.7570 ± 0.0027 | 0.7554 ± 0.0060 |
| **50** | **0.928027** | **366/400** | **0.9150** | **[0.8836, 0.9385]** | [0.8832, 0.9404] | **0.313** | **0.0130** | **0.9283 ± 0.0016** | 0.9264 ± 0.0036 |

- The mean absolute difference over the checkpoints is 0.012567, as reported.
- The Wilson implementation is correct, including the boundary cases s = 0 and s = n.
- k = 10 and 20 are uninformative: both stages are exactly 0 by construction (F19). The model assigns 1.5×10⁻⁷ to success by update 24; the earliest observed success, in both the campaign and 100,000 independent runs, is update 25.

**Pre-specification.**
- The compatibility criterion (model value inside the 95 % Wilson interval, equivalent to a two-sided score test at α = 0.05), the primary checkpoint, and the conditional-mean rule are all in `comparison.py` and `contracts.json`.
- Their hashes are identical across all three full runs, so they were fixed before any full-scale outcome existed.
- The test is defensible as non-rejection. It must not be described as equivalence, and the README already says so.

**Power** (F3). At k = 50 the rejection threshold is |p̂ − p_G| > 0.0253.

| True deviation | 0.01 | 0.02 | 0.03 | 0.04 | 0.05 |
|---|---|---|---|---|---|
| Power | 0.14 | 0.36 | 0.62 | 0.82 | 0.93 |

So "AGREEMENT" only excludes deviations larger than about 0.036 at 80 % power.

**Conditional means.**
- P2 is computed over the 366 successful runs. The bootstrap interval [31.58, 32.99] is consistent with a t-interval of [31.58, 33.00]; the endpoints differ by at most 0.008.
- **Failed runs are correctly excluded from conditional quantities and included in P1.**
- The unconditional expected updates (model 34.33; campaign 33.80, 95 % CI [32.98, 34.61]; truth 34.33) are not reported (F18). Total expenditure including failures (460,800 shots per failed run) should be reported alongside the successful-run cost.

**Multiple comparisons.**
- There are 4 informative marginal tests, plus P3 which merely duplicates P2.
- Holm-adjusted p-values: P2 0.094, P1@30 0.338, P1@50 0.627, P1@40 0.627. Nothing is significant after adjustment.
- Family-wise false-alarm rate under the true process ≈ 0.168.
- See F3 for the required changes.

---

## 11. Fault-Injection and Negative Controls

**Delivered fault suite.** Each fault is injected at update 1, candidate 0. The 10 runs per fault differ only in random counts, so each row is one scenario replicated 10 times. All 10 runs of every fault produced **identical verdict vectors**.

| Fault | Expected (checked) | Full verdict vector actually produced (10/10 identical) | DejaVu |
|---|---|---|---|
| premature_update | L2 DISAGREEMENT ✓ | L1 INCONCLUSIVE, **L2 DISAGREEMENT**, L3/L4 AGREEMENT, N1/N2 INCONCLUSIVE, N3/N4 AGREEMENT | L2 violation, 10/10 |
| corrupt_energy (+0.125 to total energy) | N2 DISAGREEMENT ✓ | **N2 DISAGREEMENT**, all others AGREEMENT | pass |
| coefficient_swap (YZ ↔ XX) | N2 DISAGREEMENT ✓ | **N2 DISAGREEMENT**, all others AGREEMENT | pass |
| shot_mismatch (512 shots) | N3 ASSUMPTION_MISMATCH ✓ | **N3 ASSUMPTION_MISMATCH**, N2 INCONCLUSIVE, others AGREEMENT; `probabilistic_applicability = ASSUMPTION_MISMATCH` is **hard-coded** (`execution.py:225`) | pass |
| missing_evidence (counts deleted from a saved trace) | N1 INCONCLUSIVE ✓ | **L1 DISAGREEMENT** (F5), L2/N1/N2/N3/N4 INCONCLUSIVE, L3/L4 AGREEMENT | pass |

**Assessment.**
- **Each fault tests a meaningful research claim.** A logical-order violation is caught by both Python and DejaVu. Arithmetic and pairing corruption is caught despite consistent metadata, because the coefficient swap is detected through the reconstructed contributions and score, not only through the reported coefficient table. An allocation change is classified as an assumption mismatch, not a failure.
- **Diversity is weak** (F6):
  - There is a single injection site.
  - No fault mid-run, at a terminal boundary, or after success.
  - No missing-term-in-aggregation fault.
  - No stale-optimizer-input fault.
  - No termination-reason fault.
  - No Stage 1 negative controls (model or proof mutants).
  - The probabilistic assumption-mismatch claim is never exercised at campaign level by the experiment itself.
- **"10/10 detected" overstates the evidence**: it is 1 scenario × 10.

**Audit supplements (not part of the delivered evidence; reproducible from `audit/`).**
- 12 checker probes (§8), covering stale inputs, reordering, duplicate commit, stale measurement, non-argmin choice, relabelled termination, metadata, dropped shot, tolerance, and truncation.
- 6 nuXmv mutants (§5), 2 of which (F2) are undetected.
- A Dafny tie-priority mutant, detected.
- 7 DejaVu traces, all behaving as expected.
- The campaign-level gate probe (§9).

---

## 12. Reproducibility

| Item | Status | Evidence / gap |
|---|---|---|
| One-command pipeline | ✔ | `experiment.py all --output <new dir>` takes about 30 s end to end |
| Deterministic config and seeds | ✔ | Sealed configuration digest `03b387a2…`; SeedSequence per run |
| Raw outputs | ✔ | Raw counts for every measurement in 460 traces (one counts vector deliberately deleted in each of the 10 missing-evidence traces) |
| Processed outputs generated from raw data | ✔ | `audit` on a scratch copy regenerated the report, JSON, and CSV byte-identically (except `generated_at`); there are no manually transcribed numbers |
| Hashes and manifests | ✔ / partial | Stage 1 sealed (sources, tool binaries, evidence). Stage 2 `results.json` is unsealed. The `monitor-build/` subfolder is unhashed (F20). |
| Tool versions | Partial | nuXmv 2.1.0, Dafny 4.11.0, and Storm 1.13.0 appear in logs, with binary SHA-256 in the record. DejaVu commit and Scala 2.12.21 are pinned. **Java is not recorded.** |
| Python and NumPy versions | ✘ | `requirements.txt` says `numpy>=1.24` only, and there is no lock file. The versions used (3.14.6 / 2.5.3) appear only in the hand-made `completion_audit.json`. **Bitwise reproduction requires NumPy 2.5.3**: the replica reproduces all 400 success steps under 2.5.3 (0 mismatches), but **113/400 runs diverge under NumPy 1.24.3** (370 vs 366 successes), from last-ulp differences in the probability arrays. |
| Self-containment | ✘ | nuXmv, Dafny, the DejaVu jar, and the Scala fetch script all come from sibling folders; Storm comes from PATH. The Scala jars need a network fetch. |
| Default interpreter | ✘ | `python3` on this machine (3.8.10) fails 13/19 unit tests. The README states ≥ 3.11, but nothing enforces it. 19/19 pass on 3.14.6. |
| Audit command mutates delivered evidence | ✘ | `experiment.py audit --output artifacts/approved-experiment` (README line 59) rewrites `comparison/*`. That changes the hash recorded as `result_sha256` in `completion_audit.json`. (This audit used a copy.) |
| Plots | n/a | The experiment produces no plots; the manuscript's figures belong to older experiments. |
| Numbers traced back to raw data | ✔ | 366/400; 124,581,888 shots (= 13,518 updates × 9,216); max energy error 5.54×10⁻¹⁷; all P1/P2 values; the Storm values. All were traced from the REPORT to traces and logs and recomputed (§14). |
| Prospective / frozen (F13) | ✔ with disclosure | In the delivered run, Stage 1 was frozen 23 ms before Stage 2 started. Two earlier full runs with identical seeds and configuration (`primary` at 23:14Z, `primary-v2` at 23:16Z) had already revealed identical outcomes. Between them only `closed_loop/checker.py` and `execution.py` changed; the model, Storm results, configuration, comparison rules, and contract library are hash-identical. **No evidence of tuning.** The model and thresholds also come from the August probabilistic experiment. Classify as confirmatory with respect to the model and decision rules, but disclose that the delivered run deterministically re-executes an already-observed sample. |

---

## 13. Claim-Evidence Matrix

### 13.1 Experiment README and REPORT claims

| Claim | Supporting evidence | Status | Required qualification |
|---|---|---|---|
| "Each pre-execution layer owns its contract family … runtime checks the corresponding obligations" | `contracts.json`; `pre_execution.py`; `checker.py`; `comparison.py` | Fully supported | — |
| "One update evaluates three candidates … 9,216 physical shots; at most 460,800" | Traces; `trace_rederivation.py` | Fully supported | — |
| "The runtime uses an exact NumPy statevector … It does not sample the Gaussian DTMC" | `execution.py:82–86`; Qiskit cross-check | Fully supported | — |
| "NuXmv checks seven temporal properties … The controller distinguishes success, normal budget termination, and error abort" | nuXmv logs; mutants | Supported with qualification | The *model* distinguishes them; no property verifies the classification (F2) |
| "Dafny checks … physical group summation" | `GroupGrid.dfy` | Overstated | The lemma is a plain list sum with no uniqueness or physical semantics (F11) |
| "Storm checks bounded reachability … independent forward propagation … compared against every Storm checkpoint" | Storm re-run; independent kernel; propagation | Fully supported | Applies to the Gaussian DTMC only |
| "Stage 2 refuses changed sources/configuration/evidence or incomplete Stage 1" | `validate_frozen`; audit copy | Fully supported | Stage 2 results are unsealed (F10) |
| "The runtime checker reconstructs … uses Fraction for an exact reference energy" | Code; 40,554 re-derived evaluations | Fully supported | — |
| "Online Python checks gate progress; replay recomputes … DejaVu independently evaluates the temporal projections" | Code; negative controls | Supported with qualification | Gating is fail-stop after the fact (F7); replay is the same code (F8); DejaVu covers 5 projections, offline |
| "Absent numeric evidence cannot become an agreement" | `checker.py`; missing-evidence fault | Supported with qualification | Absent evidence becomes an L1 DISAGREEMENT (F5) |
| "Agreement means statistical compatibility, not equivalence" | `comparison.py` | Fully supported | Add power / minimum detectable deviation (F3) |
| REPORT: P2/P3 "DISAGREEMENT" | Campaign data | **Contradicted** by high-precision evidence | Not significant after Holm; true mean 33.12 ± 0.05 vs model 33.11 (F3) |
| REPORT: P1 AGREEMENT at k = 10…50 | Campaign; independent MC | Supported with qualification | k = 10, 20 structural; resolution ±0.036 |
| "Ten seeded tests are run for each [fault]" | Fault results | Overstated | One injection site × 10 replications with identical vectors (F6) |
| "A correction … requires a new Stage 1 record and fresh execution data … does not silently tune the model" | Hashes; snapshot diffs | Supported with qualification | Re-executions reuse seeds, so the data are not "fresh" (F13) |
| "config/h2.json fixes the existing benchmark's two-qubit circuit and Hamiltonian" (H2 naming) | Operator analysis | **Contradicted** (name) | Not H2 (F1) |
| "Ideal-energy success is a simulator benchmark oracle" | `execution.py:63,118` | Fully supported | Must also appear in the paper (F9) |

### 13.2 Manuscript claims (`restructured.tex`, current draft)

| Manuscript claim (line) | Supporting artifact | Status | Required qualification |
|---|---|---|---|
| Benchmark is "H$_2$" / molecular hydrogen (568, 790, 820, 825; sibling docs) | Operator analysis | **Contradicted by implementation** | Relabel or replace (F1) |
| "The Gaussian model predicts 92.80 % … compared with 86.75 % in 400 noisy runs" (47, 805–813) | Older FakeJakarta experiment (not re-audited) | Supported with qualification | Unmatched noise model; now add the matched campaign (91.50 %, Wilson [88.4, 93.9]) and the high-precision truth (92.83 %) |
| "This result applies to the Gaussian model on the grid. It is not a probability bound for all discrete shot outcomes or a physical backend" (437) | Storm; independent checks | Fully supported | — |
| "Their difference therefore does not isolate Gaussian error" (440) | — | Fully supported | Superseded: the matched campaign plus independent MC now isolate it (≤ 0.003) |
| "This is a common description of existing requirements, not a released contract library" (134) | `config/contracts.json` | **Contradicted** by the new experiment | Update (F4) |
| "We report each experiment's configuration instead of treating the four layers as checks of one identical run" (205) | Two-stage config | **Superseded / contradicted** | Update (F4) |
| Refined NuXmv model "enters ABORT when it reaches the limit" (128, 269) | New controller | Superseded | Describe `done_budget`, and verify it (F2) |
| "The two experiments also use different circuits, optimizers, and measurements" (537) | Two-stage experiment | **Superseded / contradicted** | Matched now (F4) |
| "Dafny proves the routines over mathematical real numbers under their assumptions" (339) | Dafny re-run; no escape hatches; mutant | Fully supported | — |
| Conditional means "33.11 updates and 305,153 shots … derived by Python" (885) | Independent propagation (33.1111871) | Fully supported | — |
| "A separate phase-reachability audit reports 18/18 positive phase queries" (606) | Older models only | Supported with qualification | The two-stage controller has no reachability checks in its pipeline; this audit's witnesses show all phases reachable (F14) |
| "Online checking also precedes the protected operation" (498) and "permits them to advance only after the required checks" (1097) | Older ask/tell runtime (not re-audited); two-stage `execution.py:109–117` | Overstated *for the two-stage experiment* | Fail-stop monitoring; state is assigned before the verdict (F7) |
| "Storm and Python success probabilities differ by at most 4.4044×10⁻¹¹" (728) | Older campaign | Not re-audited | Two-stage: ≤ 1.1×10⁻¹⁶ |
| `main.tex`: "soundness w.r.t. the shared model for every property", "assume-guarantee composition results", "lifting Boolean to probabilistic guarantees" (71, 958–960) | None | **Unsupported** (superseded draft) | Do not reuse (F21) |

### 13.3 Claims the paper will need under the stated research principle

| Intended claim | Status |
|---|---|
| "Pre-execution verification establishes these contracts prospectively" | Supported with qualification: frozen and sealed before Stage 2; disclose the re-execution (F13); L4 is weak (F2) |
| "Runtime verification determines whether the corresponding obligations hold for concrete executions" | Supported: 400/400 runs satisfy L1–N4; independently re-derived |
| "The matched empirical campaign validates the Gaussian DTMC" | Supported with qualification: compatible at all informative checkpoints; resolution ±0.036; P2 false alarm (F3). Better: "is statistically compatible with", together with the high-precision supplement. |
| "Cross-stage analysis distinguishes violations, assumption mismatches and missing evidence" | Supported with qualification: gate and allocation mismatch work; missing evidence is misclassified for L1 (F5); the probabilistic mismatch is never exercised at campaign level in the delivered evidence (F6) |

---

## 14. Independent Sanity-Check Results

All checks are reproducible with the scripts in `audit/`. Scripts write to `audit/_out/`, which is safe to delete; nothing in the experiment's frozen source set is touched.

| # | Check | Method (independent of the experiment unless noted) | Result | Verdict |
|---|---|---|---|---|
| 1 | Circuit and Hamiltonian | Own explicit-matrix statevector for all 65,536 grid points; Qiskit `EfficientSU2` on 203 points | Max \|Δ\| = 3.3×10⁻¹⁶; E_ref = −0.7029303944595313 | ✔ |
| 2 | Benchmark identity | Spectrum and realness vs the standard H2 STO-3G parity-reduced operator | Complex (\|Im\| = 0.398); spectrum ±0.703 / ±0.453 vs −1.857, −1.245, −0.883, −0.225 | ✘ (F1) |
| 3 | Success set | Own energies; threshold margin | Same 8 points; min \|gap − 0.02\| = 0.00183 | ✔ |
| 4 | Gaussian means and variances | Own Born laws and group values | Variance range [1.548, 3.415]×10⁻⁴, matching the report | ✔ |
| 5 | Selection kernel | Exact `ndtr`, 160-node Gauss–Hermite, adaptive-quadrature spot checks | Max \|Δ\| vs saved = 3.15×10⁻⁸; quadrature vs Gauss–Hermite 1.9×10⁻¹⁵; rows sum to 1 | ✔ |
| 6 | Exported DTMC and Storm | Parse `.tra` and propagate (SciPy sparse); re-run Storm 1.13.0 | P(≤50) = 0.9280272225006 (all agree); 262,144 states, 755,176 transitions; absorbing successes | ✔ |
| 7 | CDF and conditional mean | Own propagation of the own kernel | P(≤50) Δ = 4.9×10⁻⁹; E[T \| succ] = 33.1111871 | ✔ |
| 8 | Gaussian vs exact multinomial, per transition | 400,000 exact draws × 10 states | Max \|Δ\| = 0.0007 (within Monte Carlo error) | ✔ |
| 9 | Gaussian vs exact finite-shot process | 100,000-run independent Monte Carlo | P(≤25/30/40/50) = 0.2014 / 0.3823 / 0.7570 / 0.9283 vs model 0.2021 / 0.3839 / 0.7563 / 0.9280; E[T \| succ] = 33.12 ± 0.05; ties 7.3×10⁻⁶ per update | ✔ (model accurate to ≤ 0.003) |
| 10 | Executor reproduces saved outcomes | Stripped-down replica of `execute_run`'s RNG and decision sequence (experiment physics, Python 3.14 / NumPy 2.5.3) | **0/400** success-step mismatches | ✔ |
| 11 | Executor law vs truth | Replica, 20,000 fresh seeds | P(≤50) = 0.9264 ± 0.0036; E[T \| succ] = 33.12 ± 0.10 | ✔ |
| 12 | Portability | Same replica under NumPy 1.24.3 | 113/400 runs diverge (370/400 successes) | ✘ (F10) |
| 13 | Energies and expectations from raw counts | Own parser and parity tables, exact Fractions, all 400 traces | 40,554 evaluations; max energy error 5.54×10⁻¹⁷; expectation error 0 | ✔ |
| 14 | Selection, successors, termination | Same re-derivation | 0 mismatches (choices, candidates, successors, success steps, reasons) | ✔ |
| 15 | Shot totals | Same re-derivation | 124,581,888 = 13,518 × 9,216; per-run and terminal totals match | ✔ |
| 16 | Success counts | Recount from traces | 366/400 at k = 50; 307 at 40; 169 at 30; 0 at 10 and 20 | ✔ |
| 17 | Wilson intervals | mpmath, 40 digits; Clopper–Pearson for comparison | Report = mpmath to 1.1×10⁻¹⁶ | ✔ |
| 18 | P2 statistics | z-test, t-interval, Holm, family-wise simulation | p = 0.024 raw, 0.094 Holm; false-alarm rate 0.168 | P2 verdict ✘ (F3) |
| 19 | nuXmv | Re-run, reachability witnesses, 6 mutants | 7/7 true; non-vacuous; 4/6 mutants detected; budget→abort and success→abort undetected | Partial ✘ (F2) |
| 20 | Dafny | Re-run; escape-hatch scan; tie-priority mutant | 8 / 11 / 5 verified, 0 errors; none found; mutant fails | ✔ |
| 21 | DejaVu monitor | 7 crafted projected traces | Compliant passes; all 5 properties fire; cross-update confusion caught | ✔ |
| 22 | Runtime checker | 12 mutation probes on trace copies | Ordering, identity, staleness, arithmetic, and termination faults caught; consistent fabrication accepted | ✔ / F16 |
| 23 | Probabilistic gate | Substitute one shot-mismatched run in a copy and run `compare()` | All P verdicts become ASSUMPTION_MISMATCH | ✔ |
| 24 | Delivered audit chain | `experiment.py audit` on a copy; `validate_frozen` and `audit_results` on the original | Passes; outputs identical except the timestamp; originals unchanged | ✔ |
| 25 | Unit tests | `unittest` | 19/19 on Python 3.14.6; 13 errors on 3.8.10 | ✔ / F10 |

**Re-running the audit** (from `2-stage verification (closed-loop)/audit/`):

- **Python ≥ 3.8 with NumPy, SciPy, mpmath** (optionally qiskit-terra). Run in this order:
  1. `indep_physics.py`
  2. `indep_montecarlo.py 100000`
  3. `per_transition_check.py`
  4. `qiskit_crosscheck.py`
  5. `trace_rederivation.py`
  6. `stats_recompute.py` (needs the replica output below)
- **The experiment interpreter** (Python 3.14.6 / NumPy 2.5.3):
  - `replica_executor.py 20000`
  - `checker_mutations.py`
  - `gate_probe.py`
- **Shell / other:**
  - `bash nuxmv_negative_controls.sh`
  - `dejavu_negative_controls.py` (needs Java)

---

## 15. Prioritized Remediation Plan

### Must fix before rerunning experiments

1. **Decide the benchmark identity (F1).** Either relabel (no rerun needed) or adopt a documented H2 operator. Adopting one means updating `config`, the `validate_config` constants, and the `physics.py` group values, then rerunning everything.
2. **Strengthen the Stage 1 logical contract L4 (F2).** Add the termination-reason properties and positive reachability witnesses (vacuity checks) listed in F2, and make Stage 1 require them.
3. **Fix missing-evidence semantics (F5).** Classify missing raw counts as INCONCLUSIVE for L1, or explicitly redefine L1 to include "evidence present". Update `tests/test_experiment.py:65` accordingly. Report the full verdict vector for every fault.
4. **Broaden the fault suite (F6).**
   - Randomize the injection update.
   - Add missing-term-in-aggregation, stale optimizer input, wrong termination reason, and continuation after success.
   - Compute probabilistic applicability through the actual gate instead of hard-coding it.
   - Optionally add Stage 1 negative controls (nuXmv and Dafny mutants) to the pipeline.
5. **Write a statistical analysis plan before the run (F3).**
   - P1@50 is primary.
   - Supporting tests are Holm-adjusted or descriptive.
   - Report power and minimum detectable deviation.
   - Report P3 as derived.
   - Settle the verdict vocabulary (e.g. COMPATIBLE / DEVIATION / ASSUMPTION_MISMATCH / INCONCLUSIVE).
6. **Pin the environment (F10).** Add a lock file or container (Python 3.14.6, NumPy 2.5.3), record Python, NumPy, and Java versions in the Stage 1 record, and make `audit` non-mutating (write to a separate directory).
7. **Rerun.** Run the whole pipeline once into a new output directory, with the seed declared before execution.
   - Keeping seed 20260721 reproduces the same sample. That is acceptable if disclosed, but it adds no new evidence.
   - A newly declared seed gives new evidence. Declare it before running; do not choose it after seeing outcomes.

### Must fix before paper submission

1. Rewrite the manuscript around the two-stage experiment (F4): configuration table, contract library, both stages, matched campaign, faults, limitations.
2. Correct all "H2 / molecular hydrogen" wording (F1).
3. Report the probabilistic results per F3: compatibility statements, power, Holm-adjusted P2, P3 as derived, k = 10/20 as structural.
4. Scope the claims:
   - L4 (F2, unless fixed).
   - Runtime "authorization" becomes "synchronous fail-stop monitoring" (F7).
   - Replay is a determinism and integrity check (F8).
   - Dafny N3 is a summation lemma (F11).
   - State the oracle stop rule and keep it separate from the |ΔE|-rule experiments (F9).
5. Keep the FakeJakarta comparison as a separately labelled out-of-model robustness study. Do not present 92.80 % vs 86.75 % as approximation error.
6. Disclose the re-executions of the same sample (`primary`, `primary-v2` → `approved-experiment`) (F13).
7. Report unconditional resource expenditure alongside successful-run means (F18).

### Recommended improvements

- Add an independent replay or checker implementation, for example promoting `audit/trace_rederivation.py` (F8).
- Seal the Stage 2 results (`results.json`, comparison outputs) the same way as Stage 1 (F10, F20).
- Map each numeric contract to its specific Dafny lemmas, with per-contract status. Strengthen the N3 contract (uniqueness of executed groups) (F11).
- Add a pre-declared, high-precision process-level validation of the Gaussian approximation (≥ 10⁴ runs or an exact small-shot model) as a supplementary experiment (F3). This would turn "compatible at ±0.036" into "accurate to ≈ ±0.003".
- Restructure the commit path to check before mutating, if pre-authorization will be claimed (F7).
- Represent Stage 1 failures in the comparison matrix, and automate the feedback step if "closed loop" is a headline claim (F12).

### Optional improvements

- A secondary noisy campaign (FakeJakarta or hardware) under the same frozen configuration, reported as robustness.
- A certified or bounded approximation error for the Gaussian kernel (e.g. a Berry–Esseen-type bound), or an exact multinomial DTMC for a reduced shot count.
- Real-backend runs with job and circuit identities and evidence digests, to exercise the identity contracts that the simulator cannot.

---

## 16. Final Assessment

**Is the experiment technically correct?**
Yes, for the operator it actually uses.

- The code does what it claims.
- All key numbers were reproduced by independent implementations and tools: physics, kernel, DTMC, Storm, traces, shots, success counts, Wilson intervals.
- No implementation bug affects a reported result.

The defects are:

- a mislabelled benchmark (F1);
- one under-specified Stage 1 contract (F2);
- one misleading statistical verdict (F3);
- several moderate classification, reporting, and reproducibility issues (F5–F12).

**Is the cross-stage design implemented as intended?**
Largely yes.

- One frozen configuration feeds every family.
- Contracts are owned by their natural family.
- Stage 1 is sealed before execution.
- Logical and numeric contracts are checked per run; probabilistic contracts per campaign.
- Verdicts are contract-wise, and there is a working ASSUMPTION_MISMATCH gate.

The deviations:

- the cross-stage logical/numeric verdict ignores Stage 1 status;
- the closed loop is manual (F12);
- DejaVu runs offline;
- runtime enforcement is fail-stop rather than pre-authorization (F7).

**Are the probabilistic and empirical experiments genuinely comparable?**
Yes. The primary campaign is matched in circuit, optimizer, candidates, initial point, groups, shots, success predicate, update bound, and noise (none). The only modelled difference is the Gaussian approximation plus tie handling, which is negligible.

- This was confirmed by code reading, exact replica reproduction, and a 100,000-run independent simulation. That simulation agrees with the Gaussian DTMC to ≤ 0.003.
- The manuscript's FakeJakarta comparison is **not** matched and must stay labelled as robustness.

**Are the reported statistical conclusions justified?**

| Conclusion | Justified? |
|---|---|
| P1 compatibility at k = 30, 40, 50 | Yes, as non-rejection statements with roughly ±0.036 resolution at k = 50 |
| k = 10, 20 | Uninformative (structural zeros) |
| **P2/P3 "DISAGREEMENT"** | **No.** It is a false alarm, not significant after multiplicity adjustment; the true conditional mean equals the model's (F3) |

**Are the formal-verification claims appropriately scoped?**
Mostly, in the experiment's own README and REPORT: Storm is restricted to the Gaussian DTMC, Dafny to reals under assumptions, and the trusted base is listed. Exceptions:

- L4 "declared reason" is not established by nuXmv (F2).
- The N3 Dafny "proof" is trivial (F11).
- "H2" is wrong (F1).
- Runtime "authorization" and replay "independence" wording needs scoping (F7, F8).

The current manuscript's own scoping is careful, but it describes the older experiments (F4).

**Can the current results be used in the paper without rerunning?**
Partly. The delivered results (366/400; P1 compatibility; L1–N4 400/400; fault detections; Storm values) can be reported **as they stand** for the stated two-qubit operator, provided that:

- the operator is relabelled (F1);
- P2/P3 are reported as a non-significant, multiplicity-adjusted supporting comparison (F3);
- L4's Stage 1 scope is narrowed (F2);
- the oracle stop rule and the re-execution history are disclosed (F9, F13).

However, any recommended fix that edits frozen sources requires a full rerun, because the pipeline binds Stage 2 to the Stage 1 source hashes. That covers the L4 properties, missing-evidence semantics, the fault suite, and environment pinning. Switching to a true H2 operator also requires a full rerun.

**If not, exactly which experiments must be rerun?**

| Fix | What must be rerun |
|---|---|
| F2 (L4 properties) and F5 / F6 / F10 (sources and environment) | Stage 1 (nuXmv with the added properties; the Dafny and Storm outputs will be identical), then the Stage 2 baseline (400 runs), the expanded fault suite, and the comparison. About 30 s in total. |
| F1, if the operator changes | Everything: a new Gaussian kernel and success set, a new Storm analysis, a new baseline campaign, faults, and comparison. |
| Recommended addition, not a rerun | A pre-declared large-n process-level validation (≥ 10⁴ runs, newly declared seed) to quantify the Gaussian approximation error precisely. |
| Do not rerun | The primary campaign with new seeds chosen to change the P2 verdict. |
