from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import tomllib
from typing import Any, Mapping


CONFIG_SCHEMA_VERSION = 2
SUPPORTED_CONFIG_SCHEMA_VERSIONS = frozenset({1, 2})
_SAFE_MONITOR_ATOM = re.compile(r"^[A-Za-z0-9._:-]+$")


def _require_string(value: Any, name: str, *, atom: bool = False) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a nonempty string")
    if atom and not _SAFE_MONITOR_ATOM.fullmatch(value):
        raise ValueError(f"{name} must be a monitor-safe atom")
    return value


def _reject_unknown(
    value: Mapping[str, Any], allowed: set[str], name: str
) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"unknown {name} field(s): {sorted(unknown)}")


def _require_int(value: Any, name: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _require_float(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("ascii")).hexdigest()


def vector_digest(values: tuple[float, ...] | list[float]) -> str:
    canonical = [format(float(value), ".17g") for value in values]
    return canonical_digest(canonical)


def energy_digest(value: float) -> str:
    return canonical_digest(format(float(value), ".17g"))


@dataclass(frozen=True, slots=True)
class TermSpec:
    term_id: str
    pauli: str
    coeff_int: int

    def __post_init__(self) -> None:
        _require_string(self.term_id, "term_id", atom=True)
        _require_string(self.pauli, "pauli")
        if any(ch not in "IXYZ" for ch in self.pauli):
            raise ValueError(f"invalid Pauli label {self.pauli!r}")
        _require_int(self.coeff_int, "coeff_int")


@dataclass(frozen=True, slots=True)
class Hamiltonian:
    schema_version: int
    coeff_scale: int
    terms: tuple[TermSpec, ...]

    def __post_init__(self) -> None:
        _require_int(self.schema_version, "schema_version")
        if self.schema_version != 1:
            raise ValueError("unsupported Hamiltonian schema version")
        _require_int(self.coeff_scale, "coeff_scale", minimum=1)
        if not isinstance(self.terms, tuple) or not self.terms:
            raise ValueError("Hamiltonian must contain at least one term")
        if not all(isinstance(term, TermSpec) for term in self.terms):
            raise ValueError("Hamiltonian terms must be TermSpec values")
        widths = {len(term.pauli) for term in self.terms}
        if len(widths) != 1:
            raise ValueError("all Pauli labels must have the same width")
        term_ids = [term.term_id for term in self.terms]
        if len(set(term_ids)) != len(term_ids):
            raise ValueError("Hamiltonian term IDs must be unique")

    @property
    def num_qubits(self) -> int:
        return len(self.terms[0].pauli)

    @property
    def digest(self) -> str:
        return canonical_digest(self.as_dict())

    @property
    def coefficient_bound(self) -> float:
        return sum(abs(term.coeff_int) for term in self.terms) / self.coeff_scale

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "coeff_scale": self.coeff_scale,
            "terms": [asdict(term) for term in self.terms],
        }


@dataclass(frozen=True, slots=True)
class SamplerPolicy:
    pubs_per_evaluation: int
    separate_pub_per_term: bool
    measurement_type: str
    measurement_strategy: str
    bitstring_order: str
    raw_evidence_format: str
    gate_twirling: bool
    measurement_twirling: bool
    dynamical_decoupling: bool
    measurement_mitigation: str
    zne: str
    pec: str

    def __post_init__(self) -> None:
        _require_int(self.pubs_per_evaluation, "pubs_per_evaluation", minimum=1)
        for name in (
            "separate_pub_per_term",
            "gate_twirling",
            "measurement_twirling",
            "dynamical_decoupling",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be Boolean")
        for name in (
            "measurement_type",
            "measurement_strategy",
            "bitstring_order",
            "raw_evidence_format",
            "measurement_mitigation",
            "zne",
            "pec",
        ):
            _require_string(getattr(self, name), name)
        if self.measurement_type != "classified":
            raise ValueError("raw-count experiments require classified measurement")
        if self.measurement_strategy != "independent-pauli-basis-v1":
            raise ValueError("unsupported sampler measurement strategy")
        if self.bitstring_order != "qiskit-msb-qn-1-to-q0":
            raise ValueError("unsupported bitstring-order convention")
        if self.raw_evidence_format != "packed-bitarray-v1":
            raise ValueError("unsupported raw-evidence format")
        if not self.separate_pub_per_term:
            raise ValueError("each Hamiltonian term must use an independent PUB")
        if self.gate_twirling or self.measurement_twirling:
            raise ValueError("twirling must be disabled for direct count reconstruction")
        if self.dynamical_decoupling:
            raise ValueError(
                "dynamical decoupling must be disabled for the primary verification run"
            )
        for name in ("measurement_mitigation", "zne", "pec"):
            if getattr(self, name) != "not-applicable-to-samplerv2":
                raise ValueError(
                    f"{name} must explicitly be 'not-applicable-to-samplerv2'"
                )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class OptimizerPolicy:
    name: str
    initialization: str
    initial_step: float
    step_shrink: float
    improvement_tolerance: float

    def __post_init__(self) -> None:
        _require_string(self.name, "optimizer name")
        _require_string(self.initialization, "optimizer initialization")
        if self.name != "ask-tell-pattern-search-v1":
            raise ValueError("unsupported optimizer policy")
        if self.initialization != "seeded-uniform-v1":
            raise ValueError("unsupported optimizer initialization")
        initial_step = _require_float(self.initial_step, "initial_step")
        step_shrink = _require_float(self.step_shrink, "step_shrink")
        improvement = _require_float(
            self.improvement_tolerance, "improvement_tolerance"
        )
        if initial_step <= 0:
            raise ValueError("initial_step must be positive")
        if not 0 < step_shrink < 1:
            raise ValueError("step_shrink must lie strictly between zero and one")
        if improvement < 0:
            raise ValueError("improvement_tolerance must be nonnegative")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    schema_version: int
    mode: str
    system: str
    backend: str
    parameter_count: int
    max_iterations: int
    shots_per_term: int
    shot_budget: int
    seed: int
    optimizer_protocol: str
    allow_optimizer_stopped: bool
    parameter_lower: float
    parameter_upper: float
    energy_abs_tolerance: float
    expectation_abs_tolerance: float
    convergence_tolerance: float
    min_iterations: int
    convergence_patience: int
    require_raw_counts: bool
    monitor_timeout_seconds: float
    bits_per_variable: int
    hamiltonian: Hamiltonian
    source_path: str
    sampler: SamplerPolicy | None = None
    optimizer: OptimizerPolicy | None = None

    def __post_init__(self) -> None:
        _require_int(self.schema_version, "schema_version")
        if self.schema_version not in SUPPORTED_CONFIG_SCHEMA_VERSIONS:
            raise ValueError(
                f"unsupported config schema version {self.schema_version!r}"
            )
        _require_string(self.mode, "mode")
        _require_string(self.optimizer_protocol, "optimizer_protocol")
        if self.mode not in {
            "demo",
            "qiskit-statevector",
            "qiskit-runtime",
            "qiskit-statevector-sampler",
            "qiskit-runtime-sampler",
        }:
            raise ValueError(f"unsupported execution mode {self.mode!r}")
        if self.optimizer_protocol not in {"ask-tell", "opaque"}:
            raise ValueError("optimizer_protocol must be 'ask-tell' or 'opaque'")
        _require_string(self.system, "system")
        _require_string(self.backend, "backend")
        _require_string(self.source_path, "source_path")
        if not isinstance(self.hamiltonian, Hamiltonian):
            raise ValueError("hamiltonian must be a Hamiltonian")
        if self.sampler is not None and not isinstance(self.sampler, SamplerPolicy):
            raise ValueError("sampler must be a SamplerPolicy")
        if self.optimizer is not None and not isinstance(
            self.optimizer, OptimizerPolicy
        ):
            raise ValueError("optimizer must be an OptimizerPolicy")
        if not isinstance(self.require_raw_counts, bool):
            raise ValueError("require_raw_counts must be Boolean")
        if not isinstance(self.allow_optimizer_stopped, bool):
            raise ValueError("allow_optimizer_stopped must be Boolean")
        _require_int(self.max_iterations, "max_iterations", minimum=1)
        _require_int(self.parameter_count, "parameter_count", minimum=1)
        _require_int(self.shots_per_term, "shots_per_term", minimum=0)
        _require_int(self.shot_budget, "shot_budget", minimum=0)
        _require_int(self.seed, "seed")
        _require_int(self.min_iterations, "min_iterations", minimum=1)
        _require_int(self.convergence_patience, "convergence_patience", minimum=1)
        _require_int(self.bits_per_variable, "bits_per_variable", minimum=1)
        for name in (
            "parameter_lower",
            "parameter_upper",
            "energy_abs_tolerance",
            "expectation_abs_tolerance",
            "convergence_tolerance",
            "monitor_timeout_seconds",
        ):
            _require_float(getattr(self, name), name)
        if self.parameter_lower > self.parameter_upper:
            raise ValueError("parameter_lower cannot exceed parameter_upper")
        if self.energy_abs_tolerance < 0 or self.expectation_abs_tolerance < 0:
            raise ValueError("numeric tolerances must be nonnegative")
        if self.convergence_tolerance < 0:
            raise ValueError("convergence tolerance must be nonnegative")
        if self.monitor_timeout_seconds <= 0:
            raise ValueError("monitor timeout must be positive")
        if self.min_iterations > self.max_iterations:
            raise ValueError("min_iterations cannot exceed max_iterations")
        if self.mode == "qiskit-statevector" and self.shots_per_term != 0:
            raise ValueError("statevector mode must use shots_per_term = 0")
        if self.mode != "qiskit-statevector" and self.shots_per_term <= 0:
            raise ValueError("shot-based modes require positive shots_per_term")
        minimum_budget = (
            self.max_iterations * len(self.hamiltonian.terms) * self.shots_per_term
        )
        if self.shot_budget < minimum_budget:
            raise ValueError(
                "shot_budget is smaller than max_iterations * terms * shots_per_term"
            )
        sampler_mode = self.mode in {
            "qiskit-statevector-sampler",
            "qiskit-runtime-sampler",
        }
        if sampler_mode:
            if self.schema_version != 2:
                raise ValueError("SamplerV2 modes require config schema version 2")
            if self.sampler is None or self.optimizer is None:
                raise ValueError(
                    "SamplerV2 modes require explicit sampler and optimizer policies"
                )
            if self.optimizer_protocol != "ask-tell":
                raise ValueError("SamplerV2 modes require optimizer_protocol='ask-tell'")
            if self.allow_optimizer_stopped:
                raise ValueError(
                    "the fixed SamplerV2 experiment does not accept opaque optimizer stop"
                )
            if not self.require_raw_counts:
                raise ValueError("SamplerV2 modes require raw-count evidence")
            if self.sampler.pubs_per_evaluation != len(self.hamiltonian.terms):
                raise ValueError(
                    "pubs_per_evaluation must equal the Hamiltonian term count"
                )
            if self.shot_budget != minimum_budget:
                raise ValueError(
                    "the fixed SamplerV2 budget must equal max evaluations * terms * shots"
                )
        elif self.sampler is not None or self.optimizer is not None:
            raise ValueError(
                "sampler/optimizer policy tables are only valid for SamplerV2 modes"
            )

    @property
    def digest(self) -> str:
        return canonical_digest(self.as_dict(include_source=False))

    @property
    def is_sampler_mode(self) -> bool:
        return self.mode in {
            "qiskit-statevector-sampler",
            "qiskit-runtime-sampler",
        }

    def as_dict(self, *, include_source: bool = True) -> dict[str, Any]:
        value = {
            "schema_version": self.schema_version,
            "execution": {
                "mode": self.mode,
                "system": self.system,
                "backend": self.backend,
                "parameter_count": self.parameter_count,
                "max_iterations": self.max_iterations,
                "shots_per_term": self.shots_per_term,
                "shot_budget": self.shot_budget,
                "seed": self.seed,
                "optimizer_protocol": self.optimizer_protocol,
                "allow_optimizer_stopped": self.allow_optimizer_stopped,
            },
            "numeric": {
                "parameter_lower": self.parameter_lower,
                "parameter_upper": self.parameter_upper,
                "energy_abs_tolerance": self.energy_abs_tolerance,
                "expectation_abs_tolerance": self.expectation_abs_tolerance,
            },
            "convergence": {
                "tolerance": self.convergence_tolerance,
                "min_iterations": self.min_iterations,
                "patience": self.convergence_patience,
            },
            "observability": {"require_raw_counts": self.require_raw_counts},
            "monitor": {
                "timeout_seconds": self.monitor_timeout_seconds,
                "bits_per_variable": self.bits_per_variable,
            },
            "hamiltonian": self.hamiltonian.as_dict(),
            "hamiltonian_hash": self.hamiltonian.digest,
        }
        if include_source:
            value["source_path"] = self.source_path
        if self.sampler is not None:
            value["sampler"] = self.sampler.as_dict()
        if self.optimizer is not None:
            value["optimizer"] = self.optimizer.as_dict()
        return value


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a table/object")
    return value


def load_hamiltonian(path: str | Path) -> Hamiltonian:
    resolved = Path(path).resolve()
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load Hamiltonian {resolved}: {exc}") from exc
    data = _mapping(value, "Hamiltonian")
    _reject_unknown(data, {"schema_version", "coeff_scale", "terms"}, "Hamiltonian")
    raw_terms = data.get("terms")
    if not isinstance(raw_terms, list):
        raise ValueError("Hamiltonian terms must be an array")
    parsed_terms: list[TermSpec] = []
    for raw_item in raw_terms:
        item = _mapping(raw_item, "Hamiltonian term")
        _reject_unknown(item, {"term_id", "pauli", "coeff_int"}, "Hamiltonian term")
        try:
            term_id = item["term_id"]
            pauli = item["pauli"]
            coeff_int = item["coeff_int"]
        except KeyError as exc:
            raise ValueError(f"Hamiltonian term is missing {exc.args[0]!r}") from exc
        parsed_terms.append(
            TermSpec(
                term_id=_require_string(term_id, "term_id", atom=True),
                pauli=_require_string(pauli, "pauli"),
                coeff_int=_require_int(coeff_int, "coeff_int"),
            )
        )
    terms = tuple(parsed_terms)
    return Hamiltonian(
        schema_version=_require_int(data.get("schema_version"), "schema_version"),
        coeff_scale=_require_int(data.get("coeff_scale"), "coeff_scale"),
        terms=terms,
    )


def load_config(path: str | Path, **overrides: Any) -> RuntimeConfig:
    resolved = Path(path).resolve()
    try:
        data = tomllib.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"cannot load runtime config {resolved}: {exc}") from exc
    _reject_unknown(
        data,
        {
            "schema_version",
            "hamiltonian",
            "execution",
            "numeric",
            "convergence",
            "observability",
            "monitor",
            "sampler",
            "optimizer",
        },
        "top-level configuration",
    )
    execution = _mapping(data.get("execution"), "execution")
    numeric = _mapping(data.get("numeric"), "numeric")
    convergence = _mapping(data.get("convergence"), "convergence")
    observability = _mapping(data.get("observability", {}), "observability")
    monitor = _mapping(data.get("monitor", {}), "monitor")
    sampler_raw = data.get("sampler")
    optimizer_raw = data.get("optimizer")
    _reject_unknown(
        execution,
        {
            "mode",
            "system",
            "backend",
            "parameter_count",
            "max_iterations",
            "shots_per_term",
            "shot_budget",
            "seed",
            "optimizer_protocol",
            "allow_optimizer_stopped",
        },
        "execution",
    )
    _reject_unknown(
        numeric,
        {
            "parameter_lower",
            "parameter_upper",
            "energy_abs_tolerance",
            "expectation_abs_tolerance",
        },
        "numeric",
    )
    _reject_unknown(
        convergence,
        {"tolerance", "min_iterations", "patience"},
        "convergence",
    )
    _reject_unknown(observability, {"require_raw_counts"}, "observability")
    _reject_unknown(
        monitor, {"timeout_seconds", "bits_per_variable"}, "monitor"
    )
    sampler: SamplerPolicy | None = None
    if sampler_raw is not None:
        sampler_data = _mapping(sampler_raw, "sampler")
        _reject_unknown(
            sampler_data,
            {
                "pubs_per_evaluation",
                "separate_pub_per_term",
                "measurement_type",
                "measurement_strategy",
                "bitstring_order",
                "raw_evidence_format",
                "gate_twirling",
                "measurement_twirling",
                "dynamical_decoupling",
                "measurement_mitigation",
                "zne",
                "pec",
            },
            "sampler",
        )
        try:
            sampler = SamplerPolicy(**sampler_data)
        except TypeError as exc:
            raise ValueError(f"invalid sampler policy: {exc}") from exc
    optimizer: OptimizerPolicy | None = None
    if optimizer_raw is not None:
        optimizer_data = _mapping(optimizer_raw, "optimizer")
        _reject_unknown(
            optimizer_data,
            {
                "name",
                "initialization",
                "initial_step",
                "step_shrink",
                "improvement_tolerance",
            },
            "optimizer",
        )
        try:
            optimizer = OptimizerPolicy(**optimizer_data)
        except TypeError as exc:
            raise ValueError(f"invalid optimizer policy: {exc}") from exc
    hamiltonian_path = data.get("hamiltonian")
    if not isinstance(hamiltonian_path, str) or not hamiltonian_path:
        raise ValueError("hamiltonian must be a nonempty path")
    hamiltonian = load_hamiltonian(resolved.parent / hamiltonian_path)

    values: dict[str, Any] = {
        "schema_version": data.get("schema_version"),
        "mode": execution.get("mode"),
        "system": execution.get("system"),
        "backend": execution.get("backend", "local"),
        "parameter_count": execution.get("parameter_count"),
        "max_iterations": execution.get("max_iterations"),
        "shots_per_term": execution.get("shots_per_term"),
        "shot_budget": execution.get("shot_budget"),
        "seed": execution.get("seed", 0),
        "optimizer_protocol": execution.get("optimizer_protocol", "ask-tell"),
        "allow_optimizer_stopped": execution.get("allow_optimizer_stopped", False),
        "parameter_lower": numeric.get("parameter_lower"),
        "parameter_upper": numeric.get("parameter_upper"),
        "energy_abs_tolerance": numeric.get("energy_abs_tolerance", 1e-9),
        "expectation_abs_tolerance": numeric.get(
            "expectation_abs_tolerance", 1e-9
        ),
        "convergence_tolerance": convergence.get("tolerance"),
        "min_iterations": convergence.get("min_iterations", 1),
        "convergence_patience": convergence.get("patience", 1),
        "require_raw_counts": observability.get("require_raw_counts", True),
        "monitor_timeout_seconds": monitor.get("timeout_seconds", 10.0),
        "bits_per_variable": monitor.get("bits_per_variable", 24),
        "hamiltonian": hamiltonian,
        "source_path": str(resolved),
        "sampler": sampler,
        "optimizer": optimizer,
    }
    for key, value in overrides.items():
        if key not in values:
            raise ValueError(f"unknown configuration override {key!r}")
        if value is not None:
            values[key] = value
    if not isinstance(values["require_raw_counts"], bool):
        raise ValueError("require_raw_counts must be Boolean")
    return RuntimeConfig(**values)
