"""Render a presentation-only timing figure from the completed campaign summary."""

import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SUMMARY = ROOT / "artifacts/sampler_verification_scaling_restart02_20260930/summary.json"
os.environ.setdefault("MPLCONFIGDIR", str(HERE / ".mplconfig"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator, FormatStrFormatter


def main():
    summary_bytes = SUMMARY.read_bytes()
    rows = sorted(json.loads(summary_bytes)["scales"], key=lambda row: row["evaluations"])
    counts = [row["evaluations"] for row in rows]
    styles = {
        "baseline": ("Baseline VQE", "#111111"),
        "verified": ("VQE + runtime verification", "#1d7bbd"),
    }
    navy, muted, grid = "#19264b", "#5a6780", "#d7e1ee"
    with plt.rc_context({
        "font.family": "DejaVu Sans",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": "path",
        "font.size": 12,
        "axes.labelsize": 13,
        "xtick.labelsize": 12,
        "ytick.labelsize": 12,
    }):
        figure, axes = plt.subplots(figsize=(7.2, 4.2))
        figure.subplots_adjust(left=0.135, right=0.98, top=0.82, bottom=0.18)
        for condition, (label, color) in styles.items():
            axes.plot(
                counts,
                [row["conditions"][condition]["execution_seconds"]["p50"] for row in rows],
                label=label, color=color, linewidth=2.4, marker="o",
                markersize=5.7, markeredgewidth=0,
            )
        axes.set_title("Comparison of Total Execution Time", loc="left", pad=16,
                       fontsize=19, fontweight="bold", color="black")
        axes.set_xlabel("Evaluation count", labelpad=9, color="black")
        axes.set_ylabel("Total Execution Time (s)", labelpad=10, color="black")
        axes.set_xlim(8, 52)
        axes.set_ylim(0, 2.1)
        axes.set_xticks(counts)
        axes.yaxis.set_major_locator(MultipleLocator(0.5))
        axes.yaxis.set_major_formatter(FormatStrFormatter("%.1f"))
        axes.tick_params(axis="both", colors=muted, length=3, width=0.6, pad=4)
        axes.spines[["top", "right"]].set_visible(False)
        for name in ["left", "bottom"]:
            axes.spines[name].set_color("#8d95a3")
            axes.spines[name].set_linewidth(0.7)
        axes.grid(axis="y", color=grid, linewidth=0.7)
        axes.set_axisbelow(True)
        axes.legend(loc="upper left", frameon=False, fontsize=12,
                    handlelength=2.4, handletextpad=0.6, borderaxespad=0.7)
        for extension in ["pdf", "svg", "png"]:
            figure.savefig(HERE / f"timing_comparison_reference_style.{extension}",
                           dpi=300, facecolor="white")
        plt.close(figure)
    provenance = {
        "source_summary": str(SUMMARY),
        "source_sha256": hashlib.sha256(summary_bytes).hexdigest(),
        "data": [{"evaluations": row["evaluations"],
                  **{condition: row["conditions"][condition]["execution_seconds"]["p50"]
                     for condition in styles}} for row in rows],
        "change": "Presentation only; saved medians used without recomputation.",
        "font": "DejaVu Sans; PDF embeds TrueType fonts; SVG uses font outlines.",
    }
    (HERE / "figure_provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    assert SUMMARY.read_bytes() == summary_bytes
    print(json.dumps(provenance, indent=2))


if __name__ == "__main__":
    main()
