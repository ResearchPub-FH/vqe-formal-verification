#!/usr/bin/env python3
"""Run the minimal H2 coordinate search on IBM Quantum hardware.

The experiment matches h2_minimal_experiment.py: 50 runs, at most 50 updates
per run, 1024 shots for each of three commuting measurement groups, and the
same parameter grid, initial point, tie-breaking, and convergence criterion.

Install:
    python -m pip install "qiskit>=2.4,<3" "qiskit-ibm-runtime>=0.46,<1"

Configure a saved IBM Quantum account before running:
    from qiskit_ibm_runtime import QiskitRuntimeService
    QiskitRuntimeService.save_account(
        channel="ibm_quantum_platform", token="YOUR_API_KEY",
        instance="YOUR_SERVICE_CRN", set_as_default=True,
    )

This is an adaptive workload: every optimizer update submits one Sampler job
containing nine circuits (three candidates times three measurement groups).
Use --runs 1 --max-steps 1 for an inexpensive first hardware check.
"""

import argparse

import numpy as np

import h2_minimal_experiment as h2


TRANSPILE_SEED = h2.SEED
GROUP_NAMES = ("zi_zz", "yz", "xx")


def build_measurement_circuits():
    """Return the four parameters and the three measured ansatz circuits."""
    from qiskit import QuantumCircuit
    from qiskit.circuit import ParameterVector

    theta = ParameterVector("theta", 4)
    state = QuantumCircuit(2)
    for offset in (0, 2):
        state.h(0)
        state.h(1)
        state.rz(theta[offset], 0)
        state.rz(theta[offset + 1], 1)
        state.y(0)
        state.y(1)
        if offset == 0:
            state.cx(0, 1)

    circuits = []
    for name in GROUP_NAMES:
        circuit = state.copy()
        circuit.name = name
        if name == "yz":
            circuit.sdg(1)
            circuit.h(1)
        elif name == "xx":
            circuit.h(0)
            circuit.h(1)
        circuit.measure_all()
        circuits.append(circuit)
    return tuple(theta), circuits


def candidate_indices(index, coordinate):
    """Return current, minus, and plus candidates in baseline tie order."""
    candidates = [index.copy(), index.copy(), index.copy()]
    candidates[1][coordinate] = (
        candidates[1][coordinate] - 1
    ) % h2.GRID_SIZE
    candidates[2][coordinate] = (
        candidates[2][coordinate] + 1
    ) % h2.GRID_SIZE
    return candidates


def score_counts(counts, group_values):
    """Return the exact integer score for one measurement-group result."""
    if sum(counts.values()) != h2.SHOTS_PER_GROUP:
        raise RuntimeError(
            f"Expected {h2.SHOTS_PER_GROUP} shots, got {sum(counts.values())}"
        )

    score = 0
    for bitstring, count in counts.items():
        bits = bitstring.replace(" ", "")
        if len(bits) != 2:
            raise RuntimeError(f"Expected a two-bit outcome, got {bitstring!r}")
        score += count * int(group_values[int(bits, 2)])
    return score


def measure_candidates(sampler, isa_circuits, parameters, candidates):
    """Measure three candidates and return their scores and Runtime job ID."""
    pubs = []
    for candidate in candidates:
        angles = 2.0 * np.pi * candidate / h2.GRID_SIZE
        bindings = {
            parameter: float(angle)
            for parameter, angle in zip(parameters, angles)
        }
        pubs.extend((circuit, bindings) for circuit in isa_circuits)

    job = sampler.run(pubs, shots=h2.SHOTS_PER_GROUP)
    job_id = job.job_id()
    print(f"  submitted {job_id}", flush=True)
    result = job.result()

    scores = []
    for candidate_number in range(3):
        score = 0
        for group_number, group_values in enumerate(h2.GROUP_VALUES):
            pub_number = 3 * candidate_number + group_number
            counts = result[pub_number].data.meas.get_counts()
            score += score_counts(counts, group_values)
        scores.append(score)
    return scores, job_id


def one_run(sampler, isa_circuits, parameters, run_number, max_steps):
    """Run one adaptive coordinate search on the selected QPU."""
    index = np.array(h2.INITIAL_INDEX, dtype=int)
    for step in range(max_steps):
        coordinate = step % 4
        candidates = candidate_indices(index, coordinate)
        print(
            f"Run {run_number}, update {step + 1}/{max_steps}, "
            f"coordinate {coordinate}",
            flush=True,
        )
        scores, job_id = measure_candidates(
            sampler, isa_circuits, parameters, candidates
        )

        # np.argmin preserves the baseline tie order: current, minus, plus.
        choice = int(np.argmin(scores))
        index = candidates[choice]
        exact_energy, _ = h2.state_data(tuple(index))
        measured_energies = np.asarray(scores) / (
            h2.SHOTS_PER_GROUP * 10_000.0
        )
        print(
            f"  job={job_id} choice={choice} index={tuple(index)} "
            f"measured={measured_energies.round(6).tolist()} "
            f"exact={exact_energy:.12f}",
            flush=True,
        )
        if exact_energy - h2.GROUND_ENERGY <= h2.CONVERGENCE_TOLERANCE:
            return True, step + 1
    return False, max_steps


def sampler_options():
    """Disable optional suppression so 1024 raw shots match the baseline."""
    return {
        "default_shots": h2.SHOTS_PER_GROUP,
        "dynamical_decoupling": {"enable": False},
        "twirling": {"enable_gates": False, "enable_measure": False},
        "environment": {"job_tags": ["h2-minimal-coordinate-search"]},
    }


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend",
        help="IBM backend name; default: least-busy operational QPU",
    )
    parser.add_argument("--runs", type=int, default=h2.RUNS)
    parser.add_argument("--max-steps", type=int, default=h2.MAX_STEPS)
    parser.add_argument(
        "--session",
        action="store_true",
        help="Use one Runtime Session per run (requires a paid plan)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Select a backend and transpile, but submit no QPU jobs",
    )
    args = parser.parse_args()
    if args.runs < 1 or args.max_steps < 1:
        parser.error("--runs and --max-steps must both be positive")
    return args


def main():
    from qiskit.transpiler import generate_preset_pass_manager
    from qiskit_ibm_runtime import (
        QiskitRuntimeService,
        SamplerV2 as Sampler,
        Session,
    )

    args = parse_args()
    service = QiskitRuntimeService()
    backend = (
        service.backend(args.backend)
        if args.backend
        else service.least_busy(
            operational=True, simulator=False, min_num_qubits=2
        )
    )
    parameters, circuits = build_measurement_circuits()
    pass_manager = generate_preset_pass_manager(
        backend=backend,
        optimization_level=3,
        seed_transpiler=TRANSPILE_SEED,
    )
    isa_circuits = pass_manager.run(circuits)

    print(f"Backend: {backend.name}")
    print(f"Exact ground energy: {h2.GROUND_ENERGY:.12f}")
    print(
        f"Configuration: {args.runs} runs, {args.max_steps} updates/run, "
        f"{h2.SHOTS_PER_GROUP} shots/group, "
        f"epsilon={h2.CONVERGENCE_TOLERANCE}"
    )
    print(
        f"Maximum workload: {args.runs * args.max_steps} jobs, "
        f"{args.runs * args.max_steps * 9 * h2.SHOTS_PER_GROUP:,} "
        "circuit shots"
    )
    if args.dry_run:
        print("Dry run complete; no hardware jobs were submitted.")
        return

    results = []
    if args.session:
        for run_number in range(1, args.runs + 1):
            with Session(backend=backend) as session:
                sampler = Sampler(mode=session, options=sampler_options())
                results.append(
                    one_run(
                        sampler,
                        isa_circuits,
                        parameters,
                        run_number,
                        args.max_steps,
                    )
                )
    else:
        sampler = Sampler(mode=backend, options=sampler_options())
        for run_number in range(1, args.runs + 1):
            results.append(
                one_run(
                    sampler,
                    isa_circuits,
                    parameters,
                    run_number,
                    args.max_steps,
                )
            )

    converged_steps = [step for converged, step in results if converged]
    successes = len(converged_steps)
    print(f"Converged: {successes}/{args.runs}")
    print(f"Observed convergence rate: {successes / args.runs:.1%}")
    if converged_steps:
        print(f"Convergence steps: {converged_steps}")


if __name__ == "__main__":
    main()
