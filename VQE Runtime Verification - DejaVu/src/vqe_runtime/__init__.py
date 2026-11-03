"""Three-level runtime verification for hybrid VQE execution traces."""

from __future__ import annotations

import sys


if sys.version_info < (3, 11):
    raise RuntimeError(
        "vqe-dejavu-runtime requires Python 3.11 or newer "
        f"(detected {sys.version_info.major}.{sys.version_info.minor})"
    )

from .config import (
    Hamiltonian,
    OptimizerPolicy,
    RuntimeConfig,
    SamplerPolicy,
    TermSpec,
    load_config,
)
from .events import EventJournal, RuntimeEvent
from .report import Level, Status, VerificationReport
from .session import (
    RuntimeSession,
    TermObservation,
    TerminationReason,
    VerificationAbort,
)

__all__ = [
    "EventJournal",
    "Hamiltonian",
    "Level",
    "OptimizerPolicy",
    "RuntimeConfig",
    "RuntimeEvent",
    "RuntimeSession",
    "SamplerPolicy",
    "Status",
    "TermObservation",
    "TermSpec",
    "TerminationReason",
    "VerificationAbort",
    "VerificationReport",
    "load_config",
]
