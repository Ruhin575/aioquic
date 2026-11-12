#!/usr/bin/env python3
"""plot_qoe.py - video QoE plots. Every plot also writes its data (CSV) and alt-text (.alt.txt).
Bars use different hatch patterns per variant, so colour is never the only cue.

    # Plots 5, 6, 7 from the summary CSV written by parse_video_results.py
    python experiments/video/plot_qoe.py summary --results video_results.csv --out plots/

    # Plot 8: buffer level and chosen bitrate over time for one or more runs (per-segment CSV)
    python experiments/video/plot_qoe.py timeline --segments results/video_provisional \
        --run-id stock__moderate__1 --run-id k20__moderate__1 --out plots/

Plot 5  QoE score per profile and variant        (higher is better)
Plot 6  average bitrate (Mbps) per profile and variant
Plot 7  stall count per run, per profile and variant
Plot 8  buffer level (s) and bitrate over time, stalls marked
Error bars are 95% confidence intervals over the runs of a cell (none when a cell has one run).
"""
import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

PROFILE_ORDER = ["baseline", "mild", "moderate", "severe", "handover"]
VARIANT_ORDER = ["stock", "k5", "k10", "k20", "k100", "dynamic", "dynamic_undo"]
HATCHES = ["", "//", "xx", "..", "\\\\", "++", "oo"]
LINESTYLES = ["-", "--", "-.", ":"]
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228}


def ordered(values, preferred):
    present = list(dict.fromkeys(values))
    return [v for v in preferred if v in present] + sorted(v for v in present if v not in preferred)


def cell_stats(df, metric):
    rows = []
    for (variant, profile), g in df.groupby(["variant", "profile"]):
        n = len(g)
        mean = g[metric].mean()
        ci = (T975.get(n - 1, 1.96) * g[metric].std(ddof=1) / n ** 0.5) if n > 1 else 0.0
        rows.append(dict(variant=variant, profile=profile, n=n, mean=round(mean, 4), ci95=round(ci, 4)))
    return pd.DataFrame(rows)


def bar_plot(df, metric, title, ylabel, base, out_dir, note):
    stats = cell_stats(df, metric)
    profiles = ordered(stats["profile"], PROFILE_ORDER)
    variants = ordered(stats["variant"], VARIANT_ORDER)
    width = 0.8 / len(variants)
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for j, v in enumerate(variants):
        means, cis = [], []
        for p in profiles:
            row = stats[(stats.variant == v) & (stats.profile == p)]
            means.append(float(row["mean"].iloc[0]) if len(row) else 0.0)
            cis.append(float(row["ci95"].iloc[0]) if len(row) else 0.0)
        xs = [i + (j - (len(variants) - 1) / 2) * width for i in range(len(profiles))]
        ax.bar(xs, means, width, yerr=cis, capsize=3, label=v, hatch=HATCHES[j % len(HATCHES)],
               edgecolor="black", linewidth=0.8)
    ax.set_xticks(range(len(profiles)))
    ax.set_xticklabels(profiles)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.grid(axis="y", alpha=0.3)
    ax.legend(title="variant")
    fig.tight_layout()
    path = os.path.join(out_dir, base)
    fig.savefig(path + ".png", dpi=150)
    plt.close(fig)
    stats.to_csv(path + "_data.csv", index=False)
    best = stats.loc[stats["mean"].idxmax()]
    worst = stats.loc[stats["mean"].idxmin()]
    alt = ("Grouped bar chart of %s for each network profile (%s) and each variant (%s), with 95%% confidence "
           "intervals; variants use different hatch patterns. %s The highest value is %.2f (%s, %s) and the "
           "lowest is %.2f (%s, %s)." % (ylabel, ", ".join(profiles), ", ".join(variants), note,
                                         best["mean"], best["variant"], best["profile"],
                                         worst["mean"], worst["variant"], worst["profile"]))
    with open(path + ".alt.txt", "w") as f:
        f.write(alt + "\n")
    print("Wrote", path + ".png")


def summary(results_csv, out_dir):
    df = pd.read_csv(results_csv)
    os.makedirs(out_dir, exist_ok=True)
    bar_plot(df, "qoe_score", "Plot 5: QoE score per profile", "QoE score", "plot5_qoe", out_dir,
             "Higher is better; the score is average bitrate minus penalties for stalls and quality switches.")
    bar_plot(df, "avg_bitrate_mbps", "Plot 6: average bitrate per profile", "average bitrate (Mbps)",
             "plot6_bitrate", out_dir, "Higher is better.")
    bar_plot(df, "stall_count", "Plot 7: stalls per run", "stall count per run", "plot7_stalls", out_dir,
             "Lower is better.")


def load_segments(paths):
    """One or more segments CSVs or directories (searched recursively for segments*.csv)."""
    from pathlib import Path
    files = []
    for p in map(Path, paths):
        files += sorted(p.rglob("segments*.csv")) if p.is_dir() else [p]
    if not files:
        raise SystemExit("no segments*.csv found in %s" % ", ".join(map(str, paths)))
    return pd.concat([pd.read_csv(f) for f in files], ignore_index=True)


def timeline(segments_paths, run_ids, out_dir):
    df = load_segments(segments_paths)
    os.makedirs(out_dir, exist_ok=True)
    fig, (ax_b, ax_q) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    parts, alt = [], []
    for i, rid in enumerate(run_ids):
        g = df[df["run_id"] == rid].sort_values("segment_index")
        if g.empty:
            raise SystemExit("run_id %r not found in the given segment files" % rid)
        ls = LINESTYLES[i % len(LINESTYLES)]
        ax_b.plot(g["timestamp"], g["buffer_level_s"], linestyle=ls, linewidth=1.6, label=rid)
        st = g[g["stall"] > 0]
        ax_b.plot(st["timestamp"], st["buffer_level_s"], linestyle="none", marker="v", color="red", markersize=7)
        ax_q.step(g["timestamp"], g["bitrate_mbps"], where="post", linestyle=ls, linewidth=1.6, label=rid)
        part = g[["run_id", "segment_index", "timestamp", "bitrate_mbps", "buffer_level_s", "stall"]]
        parts.append(part)
        alt.append("%s has %d stall events and %d bitrate switches" % (
            rid, int(g["stall"].sum()), int((g["bitrate_mbps"].diff().fillna(0) != 0).sum())))
    ax_b.set_ylabel("buffer level (s)")
    ax_b.set_title("Plot 8: buffer level and bitrate over time (red triangles = stalls)")
    ax_b.grid(alpha=0.3)
    ax_b.legend(fontsize=8)
    ax_q.set_ylabel("bitrate (Mbps)")
    ax_q.set_xlabel("time since start of run (s)")
    ax_q.grid(alpha=0.3)
    fig.tight_layout()
    path = os.path.join(out_dir, "plot8_timeline")
    fig.savefig(path + ".png", dpi=150)
    plt.close(fig)
    pd.concat(parts).to_csv(path + "_data.csv", index=False)
    with open(path + ".alt.txt", "w") as f:
        f.write("Two stacked line charts over time. Top: playback buffer level in seconds, with red triangles at "
                "stalls. Bottom: selected video bitrate in Mbps as a step line. Runs use different line styles. "
                + "; ".join(alt) + ".\n")
    print("Wrote", path + ".png")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("summary", help="Plots 5, 6, 7")
    s.add_argument("--results", required=True)
    s.add_argument("--out", default="plots")
    t = sub.add_parser("timeline", help="Plot 8")
    t.add_argument("--segments", action="append", required=True,
                   help="segments CSV file or directory (repeat, or pass the results directory)")
    t.add_argument("--run-id", action="append", required=True)
    t.add_argument("--out", default="plots")
    a = ap.parse_args(argv)
    if a.cmd == "summary":
        summary(a.results, a.out)
    else:
        timeline(a.segments, a.run_id, a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
