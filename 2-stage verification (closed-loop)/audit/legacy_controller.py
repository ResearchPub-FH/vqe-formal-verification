"""FROZEN copy of closed_loop/logical.py as used by the approved experiment (7/10-property controller).

Kept only so audit/nonvacuity_audit.py can re-check the frozen controller of
artifacts/approved-experiment. Superseded by the logical model in closed_loop/logical.py;
do not use it for new runs.
"""


def phase_branches(c):
    """The next(phase) case list; nuXmv takes the first matching guard."""
    k = c['maximum_updates']
    return [
        ("terminal", "phase"),
        ("phase = start", "measure"),
        ("phase = measure & environment_error", "aborted"),
        ("phase = measure & groups < 3", "measure"),
        ("phase = measure & groups = 3", "aggregate"),
        ("phase = aggregate", "validate"),
        ("phase = validate & environment_error", "aborted"),
        ("phase = validate & ready < 2", "measure"),
        ("phase = validate & ready = 2", "select"),
        ("phase = select", "commit"),
        ("phase = commit", "check"),
        ("phase = check & success", "done_success"),
        (f"phase = check & !success & updates = {k}", "done_budget"),
        (f"phase = check & !success & updates < {k}", "start"),
        ("TRUE", "aborted"),
    ]


# Defensive guards that must be unreachable; their witnesses are expected false.
DEFENSIVE_GUARDS = {"TRUE"}


def requirements(c):
    """Each property with one EF witness per antecedent disjunct and a consequent probe.

    A witness shows the antecedent is reachable; the probe shows the consequent
    is not invariant on its own. Either failing makes the property vacuous.
    """
    k = c['maximum_updates']
    return [
        {"name": "L1", "contract": "L1", "comment": "L1: current candidate has all three measurement groups before aggregation.", "formula": "G (phase = aggregate -> groups = 3)",
         "witnesses": ["EF (phase = aggregate)"], "probe": "EF !(groups = 3)"},
        {"name": "L2", "contract": "L2", "comment": "L2: all candidate validations precede selecting and committing.", "formula": "G (phase in {select, commit} -> ready = 3)",
         "witnesses": ["EF (phase = select)", "EF (phase = commit)"], "probe": "EF !(ready = 3)"},
        {"name": "L3", "contract": "L3", "comment": "L3: last validation belongs to the current update; readiness resets each update.", "formula": "G (phase = commit -> energy_epoch = epoch)",
         "witnesses": ["EF (phase = commit)"], "probe": "EF !(energy_epoch = epoch)"},
        {"name": "L3_reset", "contract": "L3", "formula": "G (phase = start -> X (ready = 0 & groups = 0))",
         "witnesses": ["EF (phase = start)"], "probe": "EF !(ready = 0 & groups = 0)"},
        {"name": "L4", "contract": "L4", "comment": "L4: terminal states stay terminal; budget completion differs from error abort.", "formula": "G (terminal -> X terminal)",
         "witnesses": ["EF (phase = done_success)", "EF (phase = done_budget)", "EF (phase = aborted)"], "probe": "EF !terminal"},
        {"name": "L4_budget", "contract": "L4", "formula": f"G (phase = done_budget -> updates = {k})",
         "witnesses": ["EF (phase = done_budget)"], "probe": f"EF !(updates = {k})"},
        {"name": "L4_bound", "contract": "L4", "formula": f"G (phase = commit -> updates < {k})",
         "witnesses": ["EF (phase = commit)", f"EF (phase = commit & updates = {k - 1})"], "probe": f"EF !(updates < {k})"},
        {"name": "L4_success_reason", "contract": "L4", "comment": "L4 termination reasons: each stop is classified by its cause.", "formula": "G ((phase = check & success) -> X phase = done_success)",
         "witnesses": ["EF (phase = check & success)"], "probe": "EF !(phase = done_success)"},
        {"name": "L4_budget_reason", "contract": "L4", "formula": f"G ((phase = check & !success & updates = {k}) -> X phase = done_budget)",
         "witnesses": [f"EF (phase = check & !success & updates = {k})"], "probe": "EF !(phase = done_budget)"},
        {"name": "L4_abort_cause", "contract": "L4", "formula": "G ((!terminal & X phase = aborted) -> environment_error)",
         "witnesses": ["EF (!terminal & EX (phase = aborted))"], "probe": "EF !environment_error"},
    ]


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
        for i, (guard, target) in enumerate(phase_branches(c)):
            first_match = " & ".join([f"({guard})"] + [f"!({g})" for g in earlier])
            queries.append({"id": f"B_{i}", "kind": "branch", "branch": f"{guard} : {target}",
                            "formula": f"EF ({first_match})", "expected": guard not in DEFENSIVE_GUARDS})
            earlier.append(guard)
    return queries


def mutants(c):
    """Seeded control faults, each expected to be detected by its contract."""
    k = c['maximum_updates']
    return [
        {"name": "M1_early_aggregate", "contract": "L1", "edits": [
            ("phase = measure & groups < 3 : measure;", "phase = measure & groups < 1 : measure;"),
            ("phase = measure & groups = 3 : aggregate;", "phase = measure & groups >= 1 : aggregate;")]},
        {"name": "M2_skip_candidate", "contract": "L2", "edits": [
            ("phase = validate & ready < 2 : measure;", "phase = validate & ready < 1 : measure;"),
            ("phase = validate & ready = 2 : select;", "phase = validate & ready >= 1 : select;")]},
        {"name": "M3_no_ready_reset", "contract": "L3", "edits": [
            ("phase = start : 0;\n    phase = validate & !environment_error & ready < 3 : ready + 1;",
             "phase = start : ready;\n    phase = validate & !environment_error & ready < 3 : ready + 1;")]},
        {"name": "M4_budget_as_abort", "contract": "L4", "edits": [
            (f"phase = check & !success & updates = {k} : done_budget;", f"phase = check & !success & updates = {k} : aborted;")]},
        {"name": "M5_stale_energy", "contract": "L3", "edits": [
            ("next(energy_epoch) := case phase = validate : epoch; TRUE : energy_epoch; esac;",
             "next(energy_epoch) := case TRUE : energy_epoch; esac;")]},
        {"name": "M6_success_as_abort", "contract": "L4", "edits": [
            ("phase = check & success : done_success;", f"phase = check & success & updates = {k} : done_success;")]},
    ]


def apply_mutant(text, mutant):
    for old, new in mutant["edits"]:
        if text.count(old) != 1:
            raise ValueError(f"mutant {mutant['name']} does not match the controller exactly once: {old!r}")
        text = text.replace(old, new)
    return text


def model(c, props=None):
    props = requirements(c) if props is None else props
    branches = "\n".join(f"    {guard} : {target};" for guard, target in phase_branches(c))
    specs = "\n".join((f"-- {p['comment']}\n" if "comment" in p else "") + f"LTLSPEC NAME {p['name']} := {p['formula']};" for p in props)
    return f'''-- Generated from the frozen configuration. Numerical values are abstracted.
MODULE main
VAR
  phase : {{start, measure, aggregate, validate, select, commit, check,
            done_success, done_budget, aborted}};
  updates : 0..{c['maximum_updates']};
  groups : 0..3;
  ready : 0..3;
  epoch : boolean;
  energy_epoch : boolean;
  environment_error : boolean;
  success : boolean;
DEFINE
  terminal := phase in {{done_success, done_budget, aborted}};
ASSIGN
  init(phase) := start;
  init(updates) := 0;
  init(groups) := 0;
  init(ready) := 0;
  init(epoch) := FALSE;
  init(energy_epoch) := FALSE;
  next(phase) := case
{branches}
  esac;
  next(updates) := case
    phase = commit & updates < {c['maximum_updates']} : updates + 1;
    TRUE : updates;
  esac;
  next(groups) := case
    phase = start | phase = validate : 0;
    phase = measure & !environment_error & groups < 3 : groups + 1;
    TRUE : groups;
  esac;
  next(ready) := case
    phase = start : 0;
    phase = validate & !environment_error & ready < 3 : ready + 1;
    TRUE : ready;
  esac;
  next(epoch) := case phase = start : !epoch; TRUE : epoch; esac;
  next(energy_epoch) := case phase = validate : epoch; TRUE : energy_epoch; esac;
{specs}
'''
