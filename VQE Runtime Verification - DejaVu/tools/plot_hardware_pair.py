"""Draw the one-pair hardware figure from saved results. Submits nothing.

Panel (a) is the cumulative fidelity change of one verified/unverified pair on
hardware. Panel (b) is its added client-side time, with the minimum, median, and
maximum added time of the simulator campaign on the same H-RZ-Y circuit. That
campaign timed its conditions independently, so one simulator added time is a
verified run minus the median unverified run at the same evaluation count. Run
from any directory:

    python tools/plot_hardware_pair.py --out artifacts/hardware_pair_hrzy/pair01/hardware_pair_figure.pdf
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
PAIR_REPORT = ROOT / "artifacts/hardware_pair_hrzy/pair01/pair_report.json"
SIMULATOR_DIR = ROOT / "artifacts/sampler_verification_scaling_hrzy_20261106"
PAPER_STYLE = ROOT.parent / "2-stage verification (closed-loop)/paper/scripts/figures"
HARDWARE_COLOR = "#4A90C8"
SIMULATOR_COLOR = "#E08A4A"


def simulator_added_times(bound: int, rows: list[dict[str, str]]) -> list[float]:
    def times(condition: str) -> list[float]:
        return [
            float(row["total_seconds"])
            for row in rows
            if row["condition"] == condition and int(row["evaluations"]) == bound
        ]

    baseline = statistics.median(times("baseline"))
    return [seconds - baseline for seconds in times("verified")]


def load_series() -> dict[str, list[float]]:
    pair_rows = json.loads(PAIR_REPORT.read_text())["rows"]
    bounds = [row["bound"] for row in pair_rows]
    with (SIMULATOR_DIR / "runs.csv").open(newline="") as handle:
        runs = [row for row in csv.DictReader(handle) if row["phase"] == "measured"]
    reported = {
        scale["evaluations"]: scale["direct_p50_difference_seconds"]
        for scale in json.loads((SIMULATOR_DIR / "summary.json").read_text())["scales"]
    }
    ranges = {bound: simulator_added_times(bound, runs) for bound in bounds}
    for bound, added in ranges.items():
        if not math.isclose(statistics.median(added), reported[bound], abs_tol=1e-9):
            raise ValueError(f"simulator median at {bound} differs from its saved summary")
    return {
        "bounds": bounds,
        "fidelity_change": [row["fidelity_change"] for row in pair_rows],
        "hardware_added": [row["added_seconds"] for row in pair_rows],
        "simulator_min": [min(ranges[bound]) for bound in bounds],
        "simulator_median": [statistics.median(ranges[bound]) for bound in bounds],
        "simulator_max": [max(ranges[bound]) for bound in bounds],
    }


def draw(series: dict[str, list[float]], outputs: list[Path]) -> None:
    sys.path.insert(0, str(PAPER_STYLE))
    from matplotlib.legend_handler import HandlerTuple
    from style import GRAY, ORANGE, plt  # the paper's rcParams

    bounds = series["bounds"]
    fig, (fidelity, added) = plt.subplots(1, 2, figsize=(3.5, 2.3), layout="constrained")
    line = {"color": HARDWARE_COLOR, "marker": "o", "markersize": 3.2, "lw": 1.2,
            "clip_on": False, "zorder": 3}

    fidelity.axhline(0, color=GRAY, lw=0.6, zorder=1)
    fidelity.plot(bounds, [value * 1e3 for value in series["fidelity_change"]], **line)
    fidelity.set_ylim(-0.6, 0.8)
    fidelity.set_yticks([-0.5, 0, 0.5])
    fidelity.set_title(r"(a) Fidelity change ($\times 10^{-3}$)", loc="left", fontsize=7.5, pad=4)

    medians = series["simulator_median"]
    range_bars = added.errorbar(
        bounds,
        medians,
        yerr=[
            [median - low for median, low in zip(medians, series["simulator_min"])],
            [high - median for median, high in zip(medians, series["simulator_max"])],
        ],
        fmt="none",
        ecolor=SIMULATOR_COLOR,
        elinewidth=0.7,
        capsize=2.6,
        capthick=0.6,
        zorder=2,
    )
    median_ticks, = added.plot(bounds, medians, ls="none", marker="_", markersize=7.5,
                               markeredgewidth=0.8, color=ORANGE, zorder=2.5)
    hardware, = added.plot(bounds, series["hardware_added"], **line)
    added.set_ylim(0, 3.2)
    added.set_yticks([0, 1, 2, 3])
    added.set_title("(b) Added time (s)", loc="left", fontsize=7.5, pad=4)
    added.legend([hardware, (range_bars, median_ticks)], ["Hardware", "Simulator"],
                 handler_map={tuple: HandlerTuple(ndivide=1)}, loc="upper left",
                 frameon=False, handlelength=1.4, borderaxespad=0.1)

    for axis in (fidelity, added):
        axis.set_xticks(bounds)
        axis.set_xlim(5, 55)
        axis.grid(axis="y", alpha=0.18, lw=0.5)
        axis.set_axisbelow(True)
    fig.supxlabel("Evaluations", fontsize=plt.rcParams["axes.labelsize"])

    for output in outputs:
        output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output, dpi=300)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, nargs="+", required=True)
    args = parser.parse_args()
    draw(load_series(), args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
