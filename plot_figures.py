"""
Plot Figs. 3 and 4 of the paper from results/summary_with_95CI.csv.

Does not rerun the simulation. Run simulate.py first, or use the
precomputed results included in this repository.

Usage:
    python plot_figures.py
    python plot_figures.py --summary results/summary_with_95CI.csv --outdir figures
"""

import argparse
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

FONT_SIZE = 12
FIG_WIDTH = 7.16    # inches (IEEE two-column width)
FIG_HEIGHT = 3.15
DPI = 600

POLICIES = ["strict_priority", "fixed_fl_reservation"]
POLICY_LABELS = {"strict_priority": "Strict priority", "fixed_fl_reservation": "Fixed FL reservation"}
TRAFFIC_TYPES = ["steady", "bursty"]
TRAFFIC_LABELS = {"steady": "Steady traffic", "bursty": "Bursty traffic"}
X_TICKS = [20, 40, 60, 70, 80, 90, 100, 110, 120]

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "Nimbus Roman", "DejaVu Serif"],
    "font.size": FONT_SIZE,
    "axes.labelsize": FONT_SIZE,
    "xtick.labelsize": FONT_SIZE,
    "ytick.labelsize": FONT_SIZE,
    "legend.fontsize": FONT_SIZE,
    "axes.titlesize": FONT_SIZE,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})


def plot_metric(summary, metric, ylabel, filename, outdir, ylim, yticks):
    fig, axes = plt.subplots(1, 2, figsize=(FIG_WIDTH, FIG_HEIGHT), sharey=True)

    for ax, traffic in zip(axes, TRAFFIC_TYPES):
        sub = summary[summary["traffic"] == traffic]
        for policy in POLICIES:
            d = sub[sub["policy"] == policy].sort_values("load_packets_per_ms")
            x = d["load_packets_per_ms"].to_numpy(dtype=float)
            y = d[f"{metric}_mean"].to_numpy(dtype=float)
            lo = d[f"{metric}_ci95_low"].to_numpy(dtype=float)
            hi = d[f"{metric}_ci95_high"].to_numpy(dtype=float)
            yerr = np.vstack([np.maximum(y - lo, 0), np.maximum(hi - y, 0)])
            strict = policy == "strict_priority"
            ax.errorbar(x, y, yerr=yerr, marker="o" if strict else "s",
                        linestyle="-" if strict else "--", linewidth=1.5,
                        markersize=3.5, capsize=2.5, elinewidth=0.9,
                        label=POLICY_LABELS[policy])

        ax.set_title(TRAFFIC_LABELS[traffic])
        ax.set_xlabel("Offered URLLC load (packets/ms)")
        ax.set_xticks(X_TICKS)
        ax.set_ylim(*ylim)
        ax.set_yticks(yticks)
        ax.grid(True, linestyle=":", linewidth=0.6, alpha=0.8)
        ax.set_axisbelow(True)
        ax.legend(loc="best", frameon=True, handlelength=2.0, borderpad=0.35)

    axes[0].set_ylabel(ylabel)
    fig.tight_layout(pad=0.8)

    for ext in ("png", "pdf"):
        path = os.path.join(outdir, f"{filename}.{ext}")
        fig.savefig(path, dpi=DPI, bbox_inches="tight")
        print("Saved:", path)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--summary", default="results/summary_with_95CI.csv")
    parser.add_argument("--outdir", default="figures")
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    summary = pd.read_csv(args.summary)
    summary = summary[summary["policy"].isin(POLICIES) & summary["traffic"].isin(TRAFFIC_TYPES)]

    plot_metric(summary, "urllc_deadline_violation_pct", "URLLC deadline violations (%)",
                "Fig3_URLLC_Deadline_Violations", args.outdir, (0, 45), np.arange(0, 46, 5))
    plot_metric(summary, "fl_rounds_completed", "Completed FL rounds (out of 10)",
                "Fig4_FL_Round_Completion", args.outdir, (0, 10.5), np.arange(0, 11, 2))


if __name__ == "__main__":
    main()
