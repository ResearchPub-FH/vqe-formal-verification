#!/usr/bin/env python3
"""Plot the Gaussian and direct empirical P(50) shot sensitivity results."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = (
    ROOT
    / "artifacts/h2_vqe/additional_experiments/shot_sensitivity/shot_sensitivity.csv"
)
DEFAULT_OUTPUTS = (
    ROOT
    / "artifacts/h2_vqe/additional_experiments/shot_sensitivity/shot_sensitivity.png",
    ROOT
    / "artifacts/h2_vqe/additional_experiments/shot_sensitivity/shot_sensitivity.svg",
)


def load_rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"No rows found in {path}")
    rows.sort(key=lambda row: int(row["shots_per_group"]))
    return rows


def create_figure(rows):
    shots = [int(row["shots_per_group"]) for row in rows]
    gaussian = [float(row["gaussian_p50"]) for row in rows]
    empirical = [float(row["empirical_p50"]) for row in rows]
    lows = [float(row["empirical_ci95_low"]) for row in rows]
    highs = [float(row["empirical_ci95_high"]) for row in rows]

    colours = {
        "gaussian": "#1261ad",
        "empirical": "#df2b1f",
        "grid": "#d9dfe7",
        "text": "#172033",
    }
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "text.color": colours["text"],
            "axes.labelcolor": colours["text"],
            "xtick.color": colours["text"],
            "ytick.color": colours["text"],
        }
    )
    fig = plt.figure(figsize=(11.5, 6.5), dpi=360, facecolor="white")
    fig.text(
        0.5,
        0.93,
        "Shot-count Effect on Probability of P(50)",
        ha="center",
        va="center",
        fontsize=28,
        fontweight="bold",
    )
    ax = fig.add_axes((0.12, 0.16, 0.84, 0.67), facecolor="white")
    ax.plot(
        shots,
        gaussian,
        color=colours["gaussian"],
        linewidth=4.5,
        marker="o",
        markersize=10,
        markeredgecolor="white",
        markeredgewidth=1.0,
        label="Gaussian DTMC",
        zorder=4,
    )
    asymmetric_error = [
        [estimate - low for estimate, low in zip(empirical, lows)],
        [high - estimate for estimate, high in zip(empirical, highs)],
    ]
    ax.errorbar(
        shots,
        empirical,
        yerr=asymmetric_error,
        color=colours["empirical"],
        linewidth=4.5,
        linestyle="--",
        marker="o",
        markersize=10,
        markeredgecolor="white",
        markeredgewidth=1.0,
        capsize=7,
        capthick=2.4,
        elinewidth=2.4,
        label="Empirical result",
        zorder=5,
    )
    for x, y in zip(shots, gaussian):
        ax.annotate(
            f"{y:.3f}",
            (x, y),
            xytext=(0, 12),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=17,
            color=colours["gaussian"],
        )
    for x, y in zip(shots, empirical):
        ax.annotate(
            f"{y:.3f}",
            (x, y),
            xytext=(0, -17),
            textcoords="offset points",
            ha="center",
            va="top",
            fontsize=17,
            color=colours["empirical"],
        )

    ax.set_xscale("log", base=2)
    ax.set_xlim(220, 2380)
    minimum = min(min(gaussian), min(lows))
    maximum = max(max(gaussian), max(highs))
    padding = max(0.03, 0.12 * (maximum - minimum))
    ax.set_ylim(max(0.0, minimum - padding), min(1.0, maximum + padding))
    ax.set_xticks(shots)
    ax.set_xticklabels([str(value) for value in shots])
    ax.set_xlabel("Shots", fontsize=23, labelpad=11)
    ax.set_ylabel('P(F≤50 "success")', fontsize=23, labelpad=12)
    ax.tick_params(axis="both", labelsize=19, width=1.5, length=6, pad=6)
    ax.grid(True, color=colours["grid"], linewidth=1.2, alpha=0.9)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_color("#65707f")
        spine.set_linewidth(1.5)
    legend = ax.legend(
        loc="lower right",
        fontsize=18,
        frameon=True,
        facecolor="white",
        edgecolor=colours["grid"],
        framealpha=0.94,
        handlelength=3.0,
        borderpad=0.9,
        labelspacing=1.0,
    )
    legend.get_frame().set_linewidth(1.2)
    return fig


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, action="append")
    return parser.parse_args()


def main():
    args = parse_args()
    rows = load_rows(args.input)
    fig = create_figure(rows)
    try:
        for output in args.output or DEFAULT_OUTPUTS:
            if output.suffix.lower() not in {".png", ".svg", ".pdf"}:
                raise ValueError(f"Unsupported chart format: {output.suffix}")
            output.parent.mkdir(parents=True, exist_ok=True)
            kwargs = {"facecolor": fig.get_facecolor(), "edgecolor": "none"}
            if output.suffix.lower() == ".png":
                kwargs["dpi"] = 360
            fig.savefig(output, **kwargs)
            print(f"Wrote {output}")
    finally:
        plt.close(fig)


if __name__ == "__main__":
    main()
