
#!/usr/bin/env python3
"""Plot experiment results: goodput (Plot 1) and spurious-loss rate (Plot 3)."""

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROFILES = ["baseline", "mild", "moderate", "severe", "handover"]
OUT_DEFAULT = "experiments/report/plots"


def read_csv(path):
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    return df


def valid_run_rows(df):
    """Keep successful 10 MB runs; tolerate byte counts and labels like 10MB."""
    required = {
        "variant", "profile", "file_size", "run",
        "download_time_s", "goodput_mbps", "sha256_ok",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    df = df.copy()
    size = df["file_size"].astype(str).str.strip().str.upper()
    df = df[size.isin({"10MB", "10485760", "10000000"})]

    ok = df["sha256_ok"].astype(str).str.strip().str.lower().isin(
        {"true", "1", "yes", "ok"}
    )
    df = df[ok]
    df["goodput_mbps"] = pd.to_numeric(df["goodput_mbps"], errors="coerce")
    df["download_time_s"] = pd.to_numeric(df["download_time_s"], errors="coerce")
    df = df.dropna(subset=["goodput_mbps", "download_time_s"])
    df = df[df["profile"].isin(PROFILES)]
    return df


def save_plot(fig, out_dir, stem, table):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / f"{stem}.png", dpi=180, bbox_inches="tight")
    table.to_csv(out_dir / f"{stem}_data.csv", index=False)
    plt.close(fig)

    alt = out_dir / f"{stem}.alt.txt"
    alt.write_text(
        f"{stem}: Plot generated from the filtered experiment data. "
        f"Underlying plotted values are in {stem}_data.csv.\n",
        encoding="utf-8",
    )
    print(f"Wrote {out_dir / (stem + '.png')}")
    print(f"Wrote {out_dir / (stem + '_data.csv')}")
    print(f"Wrote {alt}")


def plot_goodput(quic_path, tcp_path, out_dir):
    quic = valid_run_rows(read_csv(quic_path))
    tcp = valid_run_rows(read_csv(tcp_path))

    # Normalize the names used by the experiment scripts.
    aliases = {
        "auto_server_stock": "stock",
        "stock": "stock",
        "quic_stock": "stock",
        "auto_server_high_threshold": "huge-threshold",
        "huge_threshold": "huge-threshold",
        "huge-threshold": "huge-threshold",
        "tcp": "tcp",
    }
    quic["series"] = quic["variant"].astype(str).map(aliases)
    tcp["series"] = "tcp"
    all_runs = pd.concat([quic, tcp], ignore_index=True)
    all_runs = all_runs[all_runs["series"].isin(["stock", "huge-threshold", "tcp"])]

    if all_runs.empty:
        raise ValueError(
            "No valid 10 MB runs found. Check that main-matrix CSVs are available; "
            "smoke-test and 50 MB runs are intentionally excluded."
        )

    required_series = {"stock", "huge-threshold", "tcp"}
    present_series = set(all_runs["series"].dropna().unique())
    missing_series = sorted(required_series - present_series)

    if missing_series:
        raise ValueError(
            "Cannot create the complete Plot 1 comparison: missing variant(s): "
            + ", ".join(missing_series)
            + ". Check that the main 10 MB experiment results are available."
        )

    grouped = (
        all_runs.groupby(["profile", "series"])["goodput_mbps"]
        .agg(mean="mean", sd="std", n="count")
        .reset_index()
    )
    grouped["sd"] = grouped["sd"].fillna(0)

    fig, ax = plt.subplots(figsize=(10, 5.5))
    x = np.arange(len(PROFILES))
    styles = {
        "stock": ("o", "-"),
        "huge-threshold": ("s", "--"),
        "tcp": ("^", "-."),
    }
    plotted = []
    for series in ["stock", "huge-threshold", "tcp"]:
        subset = grouped[grouped["series"] == series].set_index("profile")
        means = [subset.loc[p, "mean"] if p in subset.index else np.nan for p in PROFILES]
        sds = [subset.loc[p, "sd"] if p in subset.index else 0 for p in PROFILES]
        if not np.isfinite(means).any():
            continue
        marker, linestyle = styles[series]
        ax.errorbar(
            x, means, yerr=sds, label=series, marker=marker,
            linestyle=linestyle, capsize=4,
        )
        plotted.append(series)

    ax.set_xticks(x, PROFILES)
    ax.set_ylabel("Goodput (Mbit/s)")
    ax.set_xlabel("Network profile")
    ax.set_title("Plot 1 — Mean goodput by network profile")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(title="Variant")
    fig.tight_layout()

    save_plot(fig, out_dir, "plot1_goodput", grouped)
    print("Variants plotted:", ", ".join(plotted) if plotted else "none")
    print("Error bars show sample standard deviation across runs.")



def plot_spurious(metrics_path, out_dir):
    metrics = read_csv(metrics_path)
    required = {"variant", "profile", "spurious_rate_pct"}
    missing = required - set(metrics.columns)
    if missing:
        raise ValueError(f"Metrics CSV missing columns: {sorted(missing)}")

    metrics = metrics.copy()
    metrics["spurious_rate_pct"] = pd.to_numeric(
        metrics["spurious_rate_pct"], errors="coerce"
    )
    metrics = metrics[
        metrics["profile"].isin(PROFILES)
        & metrics["variant"].isin(["stock", "huge-threshold"])
    ].dropna(subset=["spurious_rate_pct"])

    if "file_size" in metrics.columns:
        size = metrics["file_size"].astype(str).str.strip().str.upper()
        metrics = metrics[size.isin({"10MB", "10485760", "10000000"})]

    if metrics.empty:
        raise ValueError(
            "No per-run spurious-loss metrics for stock/huge-threshold "
            "across the five network profiles."
        )

    grouped = (
        metrics.groupby(["profile", "variant"])["spurious_rate_pct"]
        .agg(mean="mean", sd="std", n="count")
        .reset_index()
    )
    grouped["sd"] = grouped["sd"].fillna(0)

    fig, ax = plt.subplots(figsize=(10, 5.5))
    x = np.arange(len(PROFILES))
    styles = {
        "stock": ("o", "-"),
        "huge-threshold": ("s", "--"),
    }

    for variant in ["stock", "huge-threshold"]:
        subset = grouped[grouped["variant"] == variant].set_index("profile")
        means = [
            subset.loc[p, "mean"] if p in subset.index else np.nan
            for p in PROFILES
        ]
        sds = [
            subset.loc[p, "sd"] if p in subset.index else 0
            for p in PROFILES
        ]
        if not np.isfinite(means).any():
            continue
        marker, linestyle = styles[variant]
        ax.errorbar(
            x, means, yerr=sds, label=variant, marker=marker,
            linestyle=linestyle, capsize=4,
        )

    ax.set_xticks(x, PROFILES)
    ax.set_ylabel("Spurious losses (% of declared losses)")
    ax.set_xlabel("Network profile")
    ax.set_title("Plot 3 — Spurious-loss rate by network profile")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(title="QUIC variant")
    fig.tight_layout()

    save_plot(fig, out_dir, "plot3_spurious_loss", grouped)
    print("Error bars show sample standard deviation across runs.")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    goodput = sub.add_parser("goodput")
    goodput.add_argument("--transfers", required=True, help="QUIC transfers CSV")
    goodput.add_argument("--tcp", required=True, help="TCP transfers CSV")
    goodput.add_argument("--out", default=OUT_DEFAULT)

    spurious = sub.add_parser("spurious")
    spurious.add_argument("--metrics", required=True, help="Per-run metrics CSV")
    spurious.add_argument("--out", default=OUT_DEFAULT)

    args = parser.parse_args()
    if args.command == "goodput":
        plot_goodput(args.transfers, args.tcp, args.out)
    else:
        plot_spurious(args.metrics, args.out)


if __name__ == "__main__":
    main()
