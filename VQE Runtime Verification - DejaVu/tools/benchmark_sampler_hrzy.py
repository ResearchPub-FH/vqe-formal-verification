#!/usr/bin/env python3
"""Run the simulator scaling campaign on the hardware pair's H-RZ-Y circuit.

benchmark_sampler_verification_scaling.py takes its circuit from helpers written
for the RY ansatz, and its saved campaign records that file's checksum. It stays
unchanged: this launcher replaces only those two helpers, so the protocol and
every command-line option still come from that tool.

    python tools/benchmark_sampler_hrzy.py --out-dir artifacts/<new directory>
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import benchmark_sampler_verification_scaling as campaign  # noqa: E402
import run_hardware_pair as pair  # noqa: E402

_ry_provenance = campaign._sampler_experiment_provenance


def make_circuits(config: Any) -> tuple[Any, tuple[Any, ...]]:
    return pair.build_ansatz(config)


def provenance(config: Any, **fields: Any) -> dict[str, Any]:
    record = _ry_provenance(config, **fields)
    record["ansatz"]["su2_gates"] = list(pair.SU2_GATES)
    return record


def main() -> None:
    campaign._make_circuits = make_circuits
    campaign._sampler_experiment_provenance = provenance
    campaign.main()


if __name__ == "__main__":
    main()
