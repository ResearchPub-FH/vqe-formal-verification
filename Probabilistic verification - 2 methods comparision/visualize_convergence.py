#!/usr/bin/env python3
"""Plot analytical and direct empirical H2 convergence with Matplotlib.

Edit STYLE and LAYOUT below to change fonts, component sizes, colours, and
placement.  The empirical curve is the cumulative result of the raw
FakeBackend runs; it is not an empirically fitted DTMC.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

try:
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Matplotlib is required. Install it with: python3 -m pip install matplotlib"
    ) from exc


ROOT = Path(__file__).resolve().parent
DEFAULT_ANALYTICAL = (
    ROOT / "artifacts/h2_vqe/layer1_analytical/analytical_curve.csv"
)
DEFAULT_TRACES = (
    ROOT / "artifacts/h2_vqe/layer4_empirical/fakebackend_runs.jsonl"
)
DEFAULT_OUTPUTS = (
    ROOT / "artifacts/h2_vqe/convergence_comparison.png",
    ROOT / "artifacts/h2_vqe/convergence_comparison.svg",
)


# ---------------------------------------------------------------------------
# EDIT THESE VALUES TO CHANGE THE APPEARANCE
# ---------------------------------------------------------------------------
STYLE = {
    "font_family": "DejaVu Sans",
    "header_font_size": 25,
    "title_font_size": 16,
    "axis_label_font_size": 18,
    "tick_font_size": 16,
    "legend_font_size": 16,
    "line_width": 3,
    "marker_size": 6,
    "frame_line_width": 1.7,
    "grid_line_width": 0.8,
    "analytical_colour": "#1261ad",
    "empirical_colour": "#df2b1f",
    "panel_colour": "#f7fbff",
    "plot_colour": "#ffffff",
    "frame_colour": "#67ade0",
    "grid_colour": "#d9dfe7",
    "axis_colour": "#65707f",
    "text_colour": "#172033",
}

LAYOUT = {
    "figure_size_inches": (12, 6.1),
    "dpi": 360,
    # Axes rectangle: (left, bottom, width, height), in figure coordinates.
    "axes_position": (0.105, 0.135, 0.825, 0.665),
    "header_y": 0.938,
    "title_y": 0.855,
    "legend_location": "center right",
    "legend_anchor": (0.985, 0.43),
    "marker_every_n_iterations": 2,
}


def load_analytical(path: Path) -> list[tuple[int, float]]:
    """Load P(convergence by k) from the analytical Gaussian-DTMC CSV."""
    with path.open(newline="", encoding="utf-8") as stream:
        rows = [
            (int(row["horizon"]), float(row["success_probability"]))
            for row in csv.DictReader(stream)
        ]
    if not rows:
        raise ValueError(f"No analytical rows found in {path}")
    rows.sort()
    expected = list(range(rows[-1][0] + 1))
    if [horizon for horizon, _ in rows] != expected:
        raise ValueError("Analytical horizons must be contiguous and start at zero")
    return rows


def load_empirical_cdf(path: Path, max_horizon: int) -> tuple[list[float], int]:
    """Compute the direct empirical convergence CDF from raw run outcomes."""
    success_steps: list[int | None] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            step = record.get("success_step")
            if step is not None and (not isinstance(step, int) or step < 0):
                raise ValueError(f"Invalid success_step on trace line {line_number}")
            success_steps.append(step)
    if not success_steps:
        raise ValueError(f"No empirical traces found in {path}")

    probabilities = [
        sum(step is not None and step <= horizon for step in success_steps)
        / len(success_steps)
        for horizon in range(max_horizon + 1)
    ]
    return probabilities, len(success_steps)


def create_figure(
    horizons: list[int],
    analytical: list[float],
    empirical: list[float],
    runs: int,
) -> tuple[plt.Figure, plt.Axes]:
    """Create the fully editable Matplotlib figure."""
    plt.rcParams.update(
        {
            "font.family": STYLE["font_family"],
            "text.color": STYLE["text_colour"],
            "axes.labelcolor": STYLE["text_colour"],
            "xtick.color": STYLE["text_colour"],
            "ytick.color": STYLE["text_colour"],
        }
    )

    fig = plt.figure(
        figsize=LAYOUT["figure_size_inches"],
        dpi=LAYOUT["dpi"],
        facecolor=STYLE["panel_colour"],
    )

    panel = FancyBboxPatch(
        (0.014, 0.018),
        0.972,
        0.964,
        boxstyle="round,pad=0.006,rounding_size=0.027",
        transform=fig.transFigure,
        facecolor=STYLE["panel_colour"],
        edgecolor=STYLE["frame_colour"],
        linewidth=STYLE["frame_line_width"],
        zorder=-10,
        clip_on=False,
    )
    fig.patches.append(panel)

    fig.text(
        0.5,
        LAYOUT["header_y"],
        "Convergence Probability by Iteration",
        ha="center",
        va="center",
        fontsize=STYLE["header_font_size"],
        fontweight="bold",
    )
    # fig.text(
    #     0.5,
    #     LAYOUT["title_y"],
    #     "Convergence Probability by Iteration",
    #     ha="center",
    #     va="center",
    #     fontsize=STYLE["title_font_size"],
    # )

    ax = fig.add_axes(LAYOUT["axes_position"], facecolor=STYLE["plot_colour"])
    mark_every = LAYOUT["marker_every_n_iterations"]
    ax.plot(
        horizons,
        analytical,
        color=STYLE["analytical_colour"],
        linewidth=STYLE["line_width"],
        marker="o",
        markersize=STYLE["marker_size"],
        markeredgecolor=STYLE["plot_colour"],
        markeredgewidth=0.55,
        markevery=mark_every,
        label="Gaussian DTMC\n(Analytical)",
        zorder=3,
    )
    ax.plot(
        horizons,
        empirical,
        color=STYLE["empirical_colour"],
        linewidth=STYLE["line_width"],
        linestyle="--",
        marker="o",
        markersize=STYLE["marker_size"],
        markeredgecolor=STYLE["plot_colour"],
        markeredgewidth=0.55,
        markevery=mark_every,
        label=f"Empirical result\n({runs} direct runs)",
        zorder=3,
    )

    max_horizon = horizons[-1]
    ax.set_xlim(0, max_horizon)
    ax.set_ylim(0, 1)
    ax.set_xticks(list(range(0, max_horizon + 1, 10)))
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels([f"{value:.2f}" for value in ax.get_yticks()])
    ax.set_xlabel(
        "Iteration (k)",
        fontsize=STYLE["axis_label_font_size"],
        labelpad=8,
    )
    ax.set_ylabel(
        "Probability",
        fontsize=STYLE["axis_label_font_size"],
        labelpad=9,
    )
    ax.tick_params(axis="both", labelsize=STYLE["tick_font_size"], pad=5)
    ax.grid(
        True,
        color=STYLE["grid_colour"],
        linewidth=STYLE["grid_line_width"],
        alpha=0.9,
    )
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_color(STYLE["axis_colour"])
        spine.set_linewidth(0.9)

    legend = ax.legend(
        loc=LAYOUT["legend_location"],
        bbox_to_anchor=LAYOUT["legend_anchor"],
        fontsize=STYLE["legend_font_size"],
        frameon=True,
        facecolor=STYLE["plot_colour"],
        edgecolor=STYLE["grid_colour"],
        framealpha=0.92,
        handlelength=2.6,
        borderpad=0.9,
        labelspacing=1.25,
    )
    legend.get_frame().set_linewidth(0.9)

    return fig, ax


def save_figure(fig: plt.Figure, outputs: list[Path]) -> None:
    supported = {".png", ".svg", ".pdf"}
    for output in outputs:
        if output.suffix.lower() not in supported:
            choices = ", ".join(sorted(supported))
            raise ValueError(f"Unsupported output type {output.suffix!r}; use {choices}")
        output.parent.mkdir(parents=True, exist_ok=True)
        kwargs = {"facecolor": fig.get_facecolor(), "edgecolor": "none"}
        if output.suffix.lower() == ".png":
            kwargs["dpi"] = LAYOUT["dpi"]
        fig.savefig(output, **kwargs)
        print(f"Wrote {output}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Visualize analytical and direct empirical H2 VQE convergence."
    )
    parser.add_argument("--analytical", type=Path, default=DEFAULT_ANALYTICAL)
    parser.add_argument("--traces", type=Path, default=DEFAULT_TRACES)
    parser.add_argument(
        "--output",
        type=Path,
        action="append",
        help="Output PNG, SVG, or PDF. Repeat for multiple formats.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    analytical_rows = load_analytical(args.analytical)
    horizons = [horizon for horizon, _ in analytical_rows]
    analytical = [probability for _, probability in analytical_rows]
    empirical, runs = load_empirical_cdf(args.traces, horizons[-1])
    outputs = args.output or list(DEFAULT_OUTPUTS)

    fig, _ = create_figure(horizons, analytical, empirical, runs)
    try:
        save_figure(fig, outputs)
    finally:
        plt.close(fig)

    print(
        f"P(converged by {horizons[-1]}): analytical={analytical[-1]:.4%}, "
        f"empirical={empirical[-1]:.4%} ({runs} runs)"
    )


if __name__ == "__main__":
    main()
