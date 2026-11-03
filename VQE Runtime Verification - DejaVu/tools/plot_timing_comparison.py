#!/usr/bin/env python3
"""Regenerate the timing PNG from saved results; no VQE execution is performed."""

# Change every figure font size here (Matplotlib sizes are in points).
FONT_SIZES = {
    "title": 16,
    "axis_label": 15,
    "tick_label": 13,
    "legend": 12,
}

FONT_FAMILY = "DejaVu Sans"

# Other editable figure settings.
FIGURE_SIZE = (11.5, 4.5)  # A figure spanning two paper columns
DPI = 300
TITLE = "Comparison of Total Execution Time with Runtime Verification Added"
X_LABEL = "Evaluation Count"
Y_LABEL = "Total Execution Time (s)"
COLORS = {"baseline": "#2463a9", "verified": "#c64a32"}
LABELS = {"baseline": "Baseline VQE", "verified": "VQE + runtime verification"}

import argparse
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUMMARY = (
    ROOT
    / "artifacts/sampler_verification_scaling_restart02_20260930/summary.json"
)


def plot_timing_comparison(summary_path: Path, output_path: Path) -> None:
    try:
        import matplotlib
    except ImportError as exc:
        raise SystemExit(
            "Matplotlib is required. Install it with: python -m pip install matplotlib"
        ) from exc
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FormatStrFormatter

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    rows = sorted(summary["scales"], key=lambda row: row["evaluations"])
    if not rows:
        raise ValueError("Summary contains no evaluation counts.")
    counts = [int(row["evaluations"]) for row in rows]
    times = {
        condition: [
            float(row["conditions"][condition]["execution_seconds"]["p50"])
            for row in rows
        ]
        for condition in LABELS
    }
    if any(
        not math.isfinite(value) or value < 0
        for series in times.values()
        for value in series
    ):
        raise ValueError("Median execution times must be finite and nonnegative.")

    with plt.rc_context({"font.family": FONT_FAMILY}):
        figure, axes = plt.subplots(figsize=FIGURE_SIZE, layout="constrained")
        for condition, series in times.items():
            axes.plot(
                counts,
                series,
                color=COLORS[condition],
                label=LABELS[condition],
                linewidth=2.5,
                marker="o",
                markersize=8,
                markeredgecolor="white",
                markeredgewidth=1,
            )
        axes.set_title(TITLE, fontsize=FONT_SIZES["title"], fontweight="bold", pad=22)
        axes.set_xlabel(X_LABEL, fontsize=FONT_SIZES["axis_label"], labelpad=16)
        axes.set_ylabel(Y_LABEL, fontsize=FONT_SIZES["axis_label"], labelpad=16)
        axes.set_xticks(counts)
        axes.tick_params(axis="both", labelsize=FONT_SIZES["tick_label"], pad=10)
        maximum = max(value for series in times.values() for value in series)
        upper = max(maximum, 0.001) * 1.12
        axes.set_ylim(0, upper)
        axes.set_yticks([upper * index / 5 for index in range(6)])
        axes.yaxis.set_major_formatter(FormatStrFormatter("%.2f"))
        axes.grid(axis="y", color="#d8dde3", linewidth=0.8)
        axes.set_axisbelow(True)
        axes.spines[["top", "right"]].set_visible(False)
        axes.legend(loc="upper left", fontsize=FONT_SIZES["legend"], frameon=False)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output_path, format="png", dpi=DPI, facecolor="white")
        plt.close(figure)
    print(f"Saved {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", nargs="?", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument(
        "output", nargs="?", type=Path,
        help="PNG output path; defaults to timing_comparison.png beside the summary",
    )
    args = parser.parse_args()
    output = args.output or args.summary.parent / "timing_comparison.png"
    plot_timing_comparison(args.summary, output)


if __name__ == "__main__":
    main()
