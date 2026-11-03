from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
CONTRACT_LIBRARY = json.loads((ROOT / "config/contracts.json").read_text())
CONTRACTS = {cid: record["description"] for cid, record in CONTRACT_LIBRARY.items()}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def load_json(path):
    return json.loads(Path(path).read_text())


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def source_hashes():
    files = [ROOT / "experiment.py", ROOT / "requirements.txt", ROOT / "config/contracts.json"]
    files += list((ROOT / "closed_loop").glob("*.py"))
    files += list((ROOT / "formal").glob("*.dfy"))
    files += list((ROOT / "formal").glob("*.qtl"))
    files += list((ROOT / "formal").glob("*.scala"))
    return {str(p.relative_to(ROOT)): file_hash(p) for p in sorted(files)}


def validate_config(c):
    fixed = {
        "schema_version": 1, "parameter_count": 4,
        "ansatz": "h-rz-y-on-both-cx01-h-rz-y-on-both-v1",
        "qubit_order": "q1-q0", "candidate_order": ["current", "minus", "plus"],
        "coordinate_schedule": [0, 1, 2, 3],
        "measurement_groups": [["ZI", "ZZ"], ["YZ"], ["XX"]],
        "stop_rule": "first-ideal-energy-success-or-update-budget",
        "environment": "ideal-born-finite-shot",
        "hamiltonian": {"coefficient_scale": 10000, "terms": {"YZ": 3980, "ZI": -3980, "ZZ": -113, "XX": 1810}},
    }
    for key, expected in fixed.items():
        if c.get(key) != expected:
            raise ValueError(f"unsupported {key}: this implementation requires {expected!r}")
    for key in ["grid_size", "shots_per_group", "maximum_updates", "runs", "fault_runs", "bootstrap_samples", "gauss_hermite_points"]:
        if type(c.get(key)) is not int or c[key] <= 0:
            raise ValueError(f"{key} must be a positive integer")
    if c["grid_size"] < 3:
        raise ValueError("grid_size must be at least three (distinct candidates)")
    if type(c.get("seed")) is not int or c["seed"] < 0:
        raise ValueError("seed must be a nonnegative integer")
    if len(c["initial_index"]) != 4 or any(type(i) is not int or not 0 <= i < c["grid_size"] for i in c["initial_index"]):
        raise ValueError("initial_index must have four in-domain integers")
    if not c["checkpoints"] or sorted(set(c["checkpoints"])) != c["checkpoints"] or any(type(k) is not int or not 1 <= k <= c["maximum_updates"] for k in c["checkpoints"]):
        raise ValueError("checkpoints must be increasing positive update bounds")
    if c["checkpoints"][-1] != c["maximum_updates"]:
        raise ValueError("the final checkpoint must equal maximum_updates")
    for key in ["success_gap", "energy_tolerance", "expectation_tolerance"]:
        if type(c.get(key)) not in (float, int) or not math.isfinite(c[key]) or c[key] <= 0:
            raise ValueError(f"{key} must be positive and finite")
    if c["confidence_level"] != 0.95:
        raise ValueError("this comparison implements 95% intervals")
    return c


def read_config(path):
    return validate_config(load_json(path))


def shots_per_update(c):
    return 3 * len(c["measurement_groups"]) * c["shots_per_group"]


def validate_frozen(output):
    pre_path = Path(output) / "stage1" / "pre_execution.json"
    record = load_json(pre_path)
    seal = load_json(pre_path.with_suffix(".seal.json"))
    if file_hash(pre_path) != seal["sha256"]:
        raise ValueError("Stage 1 record changed after it was sealed")
    if digest(record["configuration"]) != record["configuration_digest"]:
        raise ValueError("Stage 1 configuration digest mismatch")
    if record["sources"] != source_hashes():
        raise ValueError("implementation/proof sources changed; create a new Stage 1 output directory")
    for relative, expected in record["artifacts"].items():
        p = Path(output) / relative
        if not p.is_file() or file_hash(p) != expected:
            raise ValueError(f"Stage 1 evidence changed or is missing: {relative}")
    if not record["ready_for_execution"]:
        raise ValueError("Stage 1 has not established all required guarantees")
    return record, seal["sha256"]
