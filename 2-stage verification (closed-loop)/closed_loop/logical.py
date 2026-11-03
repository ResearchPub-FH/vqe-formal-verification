"""Generate the VQE logical model, its property suite, non-vacuity obligations and seeded mutants.

This is the single nuXmv model of the logical layer. It merges the earlier reference models
(refined-ABORT, canonical) with the two-stage controller: the shared-model states of Table III,
the configured candidate search (NCANDS candidates of NTERMS measurement groups per iteration),
per-phase faults with an explicit termination reason, and iteration/candidate version numbers
for freshness. Stage 1 checks it, and the layer-wise evaluation in NuXmv Files/VQE_Logical_Model
is generated from the same functions.
"""


def bounds(c):
    """(MAX_ITERS, NTERMS, NCANDS): update budget, measurement groups, candidates per iteration."""
    return c["maximum_updates"], len(c["measurement_groups"]), len(c["candidate_order"])


def state_branches(c):
    """The next(state) case list; nuXmv takes the first matching guard, so errors take priority."""
    return [
        ("terminal", "state"),
        ("error", "ABORT"),
        ("state = S_INIT", "CHECK_STOP"),
        ("state = CHECK_STOP & converged", "DONE"),
        ("state = CHECK_STOP & !converged & iter = MAX_ITERS", "DONE"),
        ("state = CHECK_STOP & !converged & iter < MAX_ITERS", "BIND"),
        ("state = BIND", "EXECUTE_MEASURE"),
        ("state = EXECUTE_MEASURE & terms_done + 1 < NTERMS", "EXECUTE_MEASURE"),
        ("state = EXECUTE_MEASURE & terms_done + 1 = NTERMS", "COMPUTE_ENERGY"),
        ("state = COMPUTE_ENERGY & cands_done + 1 < NCANDS", "BIND"),
        ("state = COMPUTE_ENERGY & cands_done + 1 = NCANDS", "OPTIMIZER_STEP"),
        ("state = OPTIMIZER_STEP", "CHECK_STOP"),
        ("TRUE", "ABORT"),
    ]


# Defensive guards that must be unreachable; their witnesses are expected false.
DEFENSIVE_GUARDS = {"TRUE"}

ERROR_CAUSES = [
    ("bind_fails", "ABORT_BIND_ERROR", "E1", "a binding"),
    ("measure_fails", "ABORT_QPU_ERROR", "E2", "a backend/measurement"),
    ("energy_fails", "ABORT_ENERGY_ERROR", "E3", "an aggregation/validation"),
    ("optimizer_fails", "ABORT_OPTIMIZER_ERROR", "E4", "a selection/commitment"),
]


def prop(name, contract, kind, formula, witnesses, probe, comment):
    return {"name": name, "contract": contract, "kind": kind, "formula": formula,
            "witnesses": witnesses, "probe": probe, "comment": comment}


def requirements(c):
    """Each property with one EF witness per antecedent disjunct and a consequent probe.

    A witness shows the antecedent is reachable; the probe shows the consequent is not
    invariant on its own. Either failing makes the property vacuous. Comments give the
    paper's property ID (Table VI) where one exists.
    """
    current = "bound_version = iter & bound_cand = cands_done"
    done_reason = "term_reason = DONE_CONVERGED | (term_reason = DONE_MAX_ITERS & iter = MAX_ITERS)"
    success = "state = CHECK_STOP & converged"
    budget = "state = CHECK_STOP & !converged & iter = MAX_ITERS"
    commit = "state = OPTIMIZER_STEP & !optimizer_error"
    props = [
        # Readiness: a phase is entered only after its inputs exist.
        prop("R1_groups_before_aggregation", "L1", "INVARSPEC", "state = COMPUTE_ENERGY -> terms_done = NTERMS",
             ["EF (state = COMPUTE_ENERGY)"], "EF !(terms_done = NTERMS)",
             "R1 (P1, L1): every measurement group of the evaluation is complete before aggregation."),
        prop("R2_energy_before_check", "L2", "INVARSPEC", "(state = CHECK_STOP & iter > 0) -> energy_ready",
             ["EF (state = CHECK_STOP & iter > 0)"], "EF !energy_ready",
             "R2 (P2): every stop decision after an update follows validated energies (the initial point is checked by the ideal-energy oracle)."),
        prop("R3_bound_before_measure", "L3", "INVARSPEC", "state = EXECUTE_MEASURE -> (circ_ready & params_ready)",
             ["EF (state = EXECUTE_MEASURE)"], "EF !(circ_ready & params_ready)",
             "R3 (P3): measurement runs only on a bound circuit with available parameters."),
        prop("R4_candidates_before_commit", "L2", "INVARSPEC", "state = OPTIMIZER_STEP -> (cands_done = NCANDS & energy_ready)",
             ["EF (state = OPTIMIZER_STEP)"], "EF !(cands_done = NCANDS & energy_ready)",
             "R4 (L2): all candidate energies are validated before selection and commitment."),
        # Freshness: data belongs to the current evaluation and iteration.
        prop("F1_current_evaluation", "L3", "INVARSPEC", f"(state = EXECUTE_MEASURE | state = COMPUTE_ENERGY) -> ({current})",
             ["EF (state = EXECUTE_MEASURE)", "EF (state = COMPUTE_ENERGY)"], f"EF !({current})",
             "F1 (P4, L3): measurement and aggregation use the circuit bound for the current iteration and candidate."),
        prop("F2_current_energy", "L3", "INVARSPEC", "state = OPTIMIZER_STEP -> energy_version = iter",
             ["EF (state = OPTIMIZER_STEP)"], "EF !(energy_version = iter)",
             "F2 (P5, L3): the optimizer consumes energies of the current iteration."),
        prop("F3_evaluation_reset", "L3", "INVARSPEC", "state = BIND -> (terms_done = 0 & !energy_ready)",
             ["EF (state = BIND)"], "EF !(terms_done = 0 & !energy_ready)",
             "F3 (P6, L3): each new evaluation starts with no measured groups and no ready energy."),
        prop("F4_iteration_reset", "L3", "LTLSPEC", "G ((state = CHECK_STOP & !converged & iter < MAX_ITERS) -> X (state = BIND & cands_done = 0))",
             ["EF (state = CHECK_STOP & !converged & iter < MAX_ITERS)"], "EF !(state = BIND & cands_done = 0)",
             "F4 (L3): a new iteration starts with no validated candidates."),
        prop("F5_returned_energy", "L4", "INVARSPEC", "(state = DONE & iter > 0) -> (energy_ready & energy_version + 1 = iter)",
             ["EF (state = DONE & iter > 0)"], "EF !(energy_ready & energy_version + 1 = iter)",
             "F5 (L4): DONE returns the validated energy that selected the returned parameters."),
        # Termination: bounded, absorbing, and classified by cause.
        prop("T1_termination", "L4", "CTLSPEC", "AG (!terminal -> AF terminal)",
             ["EF !terminal"], "EF !terminal",
             "T1 (P7, L4): every execution eventually stops."),
        prop("T2_done_reason", "L4", "INVARSPEC", f"state = DONE -> ({done_reason})",
             ["EF (state = DONE)"], f"EF !({done_reason})",
             "T2 (P8, L4): DONE means convergence, or an exhausted budget recorded as such."),
        prop("T3_done_absorbing", "L4", "CTLSPEC", "AG (state = DONE -> AX state = DONE)",
             ["EF (state = DONE)"], "EF !(state = DONE)",
             "T3 (P9, L4): DONE is absorbing."),
        prop("T4_abort_absorbing", "L4", "CTLSPEC", "AG (state = ABORT -> AX state = ABORT)",
             ["EF (state = ABORT)"], "EF !(state = ABORT)",
             "T4 (P10, L4): ABORT is absorbing."),
        prop("T5_success_reason", "L4", "LTLSPEC", f"G (({success}) -> X (state = DONE & term_reason = DONE_CONVERGED))",
             [f"EF ({success})"], "EF !(state = DONE & term_reason = DONE_CONVERGED)",
             "T5 (L4): success stops at once with reason DONE_CONVERGED."),
        prop("T6_budget_reason", "L4", "LTLSPEC", f"G (({budget}) -> X (state = DONE & term_reason = DONE_MAX_ITERS))",
             [f"EF ({budget})"], "EF !(state = DONE & term_reason = DONE_MAX_ITERS)",
             "T6 (L4): an exhausted budget is a normal stop with reason DONE_MAX_ITERS, not an error."),
        prop("T7_abort_reason", "L4", "INVARSPEC", "state = ABORT -> !(term_reason in {NO_TERM, DONE_CONVERGED, DONE_MAX_ITERS})",
             ["EF (state = ABORT)"], "EF (term_reason in {NO_TERM, DONE_CONVERGED, DONE_MAX_ITERS})",
             "T7 (L4): ABORT always carries an error cause."),
        prop("T8_no_early_reason", "L4", "INVARSPEC", "!terminal -> term_reason = NO_TERM",
             ["EF !terminal"], "EF !(term_reason = NO_TERM)",
             "T8 (L4): no termination reason is recorded before the run stops."),
        prop("T9_update_accounting", "L4", "LTLSPEC", f"G ((next(iter) = iter | next(iter) = iter + 1) & (next(iter) = iter + 1 <-> ({commit})))",
             [f"EF ({commit})"], f"EF !({commit})",
             "T9 (L4): the update counter advances by one exactly at each successful commitment."),
    ]
    # Failure handling: every modeled error aborts at once with its cause (P11), and nothing else aborts.
    for fails, reason, name, what in ERROR_CAUSES:
        props.append(prop(f"{name}_{fails}", "L4", "LTLSPEC", f"G ({fails} -> X (state = ABORT & term_reason = {reason}))",
                          [f"EF {fails}"], f"EF !(state = ABORT & term_reason = {reason})",
                          f"{name} (P11, L4): {what} error aborts at once with reason {reason}."))
    props += [
        prop("E5_abort_only_on_error", "L4", "LTLSPEC", "G ((!terminal & X state = ABORT) -> error)",
             ["EF (!terminal & EX state = ABORT)"], "EF !error",
             "E5 (L4): ABORT is entered only from an observed error."),
        prop("E6_update_bound", "L4", "INVARSPEC", "state = OPTIMIZER_STEP -> iter < MAX_ITERS",
             ["EF (state = OPTIMIZER_STEP)"], "EF !(iter < MAX_ITERS)",
             "E6 (P12, L4): no update is committed once the budget is spent."),
    ]
    return props


def nonvacuity_queries(c, props, branches=True):
    """CTL queries with their expected results, in the order they are checked."""
    queries = []
    for p in props:
        for i, formula in enumerate(p["witnesses"]):
            queries.append({"id": f"W_{p['name']}_{i}", "kind": "antecedent", "property": p["name"],
                            "contract": p["contract"], "formula": formula, "expected": True})
        queries.append({"id": f"C_{p['name']}", "kind": "consequent", "property": p["name"],
                        "contract": p["contract"], "formula": p["probe"], "expected": True})
    if branches:
        earlier = []
        for i, (guard, target) in enumerate(state_branches(c)):
            first_match = " & ".join([f"({guard})"] + [f"!({g})" for g in earlier])
            queries.append({"id": f"B_{i}", "kind": "branch", "branch": f"{guard} : {target}",
                            "formula": f"EF ({first_match})", "expected": guard not in DEFENSIVE_GUARDS})
            earlier.append(guard)
    return queries


def mutants(c):
    """Seeded control faults, each expected to be detected by its contract."""
    return [
        {"name": "M1_early_aggregation", "contract": "L1", "edits": [
            ("state = EXECUTE_MEASURE & terms_done + 1 < NTERMS : EXECUTE_MEASURE;", "state = EXECUTE_MEASURE & terms_done + 1 < 1 : EXECUTE_MEASURE;"),
            ("state = EXECUTE_MEASURE & terms_done + 1 = NTERMS : COMPUTE_ENERGY;", "state = EXECUTE_MEASURE & terms_done + 1 >= 1 : COMPUTE_ENERGY;")]},
        {"name": "M2_skipped_candidate", "contract": "L2", "edits": [
            ("state = COMPUTE_ENERGY & cands_done + 1 < NCANDS : BIND;", "state = COMPUTE_ENERGY & cands_done + 1 < 1 : BIND;"),
            ("state = COMPUTE_ENERGY & cands_done + 1 = NCANDS : OPTIMIZER_STEP;", "state = COMPUTE_ENERGY & cands_done + 1 >= 1 : OPTIMIZER_STEP;")]},
        {"name": "M3_no_candidate_reset", "contract": "L3", "edits": [
            ("next(cands_done) := case\n    state = CHECK_STOP : 0;", "next(cands_done) := case\n    state = CHECK_STOP : cands_done;")]},
        {"name": "M4_stale_energy_ready", "contract": "L3", "edits": [
            ("state = CHECK_STOP & !converged & iter < MAX_ITERS : FALSE;", "state = CHECK_STOP & !converged & iter < MAX_ITERS : energy_ready;")]},
        {"name": "M5_skipped_rebind", "contract": "L3", "edits": [
            ("state = COMPUTE_ENERGY & cands_done + 1 < NCANDS : BIND;", "state = COMPUTE_ENERGY & cands_done + 1 < NCANDS : EXECUTE_MEASURE;")]},
        {"name": "M6_stale_binding", "contract": "L3", "edits": [
            ("state = BIND & !bind_error : iter;", "state = BIND & !bind_error & iter = 0 : iter;")]},
        {"name": "M7_wrong_candidate", "contract": "L3", "edits": [
            ("state = BIND & !bind_error : cands_done;", "state = BIND & !bind_error : 0;")]},
        {"name": "M8_stale_energy_epoch", "contract": "L3", "edits": [
            ("state = COMPUTE_ENERGY & !energy_error : bound_version;", "state = COMPUTE_ENERGY & !energy_error & iter = 0 : bound_version;")]},
        {"name": "M9_measurement_error_ignored", "contract": "L4", "edits": [
            ("error := bind_fails | measure_fails | energy_fails | optimizer_fails;", "error := bind_fails | energy_fails | optimizer_fails;")]},
        {"name": "M10_budget_as_abort", "contract": "L4", "edits": [
            ("state = CHECK_STOP & !converged & iter = MAX_ITERS : DONE;", "state = CHECK_STOP & !converged & iter = MAX_ITERS : ABORT;")]},
        {"name": "M11_success_as_abort", "contract": "L4", "edits": [
            ("state = CHECK_STOP & converged : DONE;", "state = CHECK_STOP & converged & iter = MAX_ITERS : DONE;")]},
        {"name": "M12_budget_overrun", "contract": "L4", "edits": [
            ("state = CHECK_STOP & !converged & iter = MAX_ITERS : DONE;", "state = CHECK_STOP & !converged & iter = MAX_ITERS : BIND;")]},
    ]


def apply_mutant(text, mutant):
    for old, new in mutant["edits"]:
        if text.count(old) != 1:
            raise ValueError(f"mutant {mutant['name']} does not match the model exactly once: {old!r}")
        text = text.replace(old, new)
    return text


def model(c, props=None):
    props = requirements(c) if props is None else props
    k, groups, candidates = bounds(c)
    branches = "\n".join(f"    {guard} : {target};" for guard, target in state_branches(c))
    specs = "\n\n".join(f"-- {p['comment']}\n{p['kind']} NAME {p['name']} := {p['formula']};" for p in props)
    return f'''-- VQE logical model for nuXmv, generated by closed_loop/logical.py from the frozen configuration.
-- States follow the shared execution model (Table III). Real-valued parameters, counts and
-- energies are abstracted into counters, readiness flags and version numbers. The convergence
-- oracle and the per-phase errors are unconstrained inputs, so every combination is explored.
-- Each iteration evaluates NCANDS candidates (current, minus, plus); each evaluation binds the
-- candidate, measures NTERMS groups and aggregates/validates its energy. The optimizer then
-- selects and commits, and CHECK_STOP applies the stop rule to the committed point.
MODULE main
DEFINE
  MAX_ITERS := {k};  -- optimizer update budget K
  NTERMS    := {groups};  -- measurement groups per candidate evaluation
  NCANDS    := {candidates};  -- candidates per iteration
VAR
  state : {{S_INIT, CHECK_STOP, BIND, EXECUTE_MEASURE, COMPUTE_ENERGY, OPTIMIZER_STEP, DONE, ABORT}};
  iter           : 0..MAX_ITERS;  -- committed updates; the version of the current parameters
  cands_done     : 0..NCANDS;     -- candidate energies validated in this iteration
  terms_done     : 0..NTERMS;     -- groups measured in this evaluation
  circ_ready     : boolean;       -- a circuit is bound for this evaluation
  params_ready   : boolean;       -- parameters for this evaluation are available
  energy_ready   : boolean;       -- the energies needed by the next decision are validated
  bound_version  : 0..MAX_ITERS;  -- iteration whose parameters are bound
  bound_cand     : 0..NCANDS;     -- candidate whose parameters are bound
  energy_version : 0..MAX_ITERS;  -- iteration of the most recently validated energy
  term_reason : {{NO_TERM, DONE_CONVERGED, DONE_MAX_ITERS,
                 ABORT_BIND_ERROR, ABORT_QPU_ERROR, ABORT_ENERGY_ERROR, ABORT_OPTIMIZER_ERROR}};
  -- Environment inputs: no next() assignment, so any value is possible at every step.
  converged       : boolean;  -- the committed point satisfies the stop rule (Eq. 8)
  bind_error      : boolean;  -- parameter binding or circuit construction failed
  qpu_error       : boolean;  -- backend execution or result retrieval failed
  energy_error    : boolean;  -- energy aggregation or numeric validation failed
  optimizer_error : boolean;  -- selection or commitment failed
DEFINE
  terminal        := state in {{DONE, ABORT}};
  bind_fails      := state = BIND & bind_error;
  measure_fails   := state = EXECUTE_MEASURE & qpu_error;
  energy_fails    := state = COMPUTE_ENERGY & energy_error;
  optimizer_fails := state = OPTIMIZER_STEP & optimizer_error;
  error := bind_fails | measure_fails | energy_fails | optimizer_fails;
ASSIGN
  init(state)          := S_INIT;
  init(iter)           := 0;
  init(cands_done)     := 0;
  init(terms_done)     := 0;
  init(circ_ready)     := FALSE;
  init(params_ready)   := TRUE;   -- theta_0 is supplied
  init(energy_ready)   := FALSE;
  init(bound_version)  := 0;
  init(bound_cand)     := 0;
  init(energy_version) := 0;
  init(term_reason)    := NO_TERM;

  -- CHECK_STOP follows INIT and every commitment, as in the executor: the initial point and
  -- each committed point are tested before any further evaluation.
  next(state) := case
{branches}
  esac;

  next(term_reason) := case
    terminal : term_reason;
    bind_fails : ABORT_BIND_ERROR;
    measure_fails : ABORT_QPU_ERROR;
    energy_fails : ABORT_ENERGY_ERROR;
    optimizer_fails : ABORT_OPTIMIZER_ERROR;
    state = CHECK_STOP & converged : DONE_CONVERGED;
    state = CHECK_STOP & !converged & iter = MAX_ITERS : DONE_MAX_ITERS;
    TRUE : NO_TERM;
  esac;

  next(iter) := case
    state = OPTIMIZER_STEP & !optimizer_error & iter < MAX_ITERS : iter + 1;
    TRUE : iter;
  esac;

  next(cands_done) := case
    state = CHECK_STOP : 0;
    state = COMPUTE_ENERGY & !energy_error & cands_done < NCANDS : cands_done + 1;
    TRUE : cands_done;
  esac;

  next(terms_done) := case
    state = COMPUTE_ENERGY | state = CHECK_STOP : 0;
    state = EXECUTE_MEASURE & !qpu_error & terms_done < NTERMS : terms_done + 1;
    TRUE : terms_done;
  esac;

  next(circ_ready) := case
    error : FALSE;
    state = BIND : TRUE;              -- the candidate's circuit is bound
    state = COMPUTE_ENERGY : FALSE;   -- the evaluation is consumed; the next one must rebind
    TRUE : circ_ready;
  esac;

  next(params_ready) := case
    error : FALSE;
    state = EXECUTE_MEASURE & terms_done + 1 = NTERMS : FALSE;  -- consumed by the evaluation
    state = COMPUTE_ENERGY & cands_done + 1 < NCANDS : TRUE;    -- next candidate of the current point
    state = OPTIMIZER_STEP : TRUE;                              -- committed parameters
    TRUE : params_ready;
  esac;

  next(energy_ready) := case
    error : FALSE;
    state = COMPUTE_ENERGY & cands_done + 1 = NCANDS : TRUE;    -- all candidate energies validated
    state = COMPUTE_ENERGY : FALSE;                             -- stored; the next evaluation starts unready
    state = CHECK_STOP & !converged & iter < MAX_ITERS : FALSE; -- a new iteration starts unready
    TRUE : energy_ready;
  esac;

  next(bound_version) := case
    state = BIND & !bind_error : iter;
    TRUE : bound_version;
  esac;

  next(bound_cand) := case
    state = BIND & !bind_error : cands_done;
    TRUE : bound_cand;
  esac;

  next(energy_version) := case
    state = COMPUTE_ENERGY & !energy_error : bound_version;
    TRUE : energy_version;
  esac;

-- Property suite: {len(props)} properties. Comments give the paper ID and the Table I contract.

{specs}
'''
