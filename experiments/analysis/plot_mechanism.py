#!/usr/bin/env python3
"""plot_mechanism.py - Plot 2 (cwnd + loss markers) and Plot 4 (cumulative bytes).

Every plot also writes its underlying data (CSV) and alt-text (.alt.txt).
Distinct line styles / marker shapes are used, so colour is never the only cue.

Plot 4 measures cumulative ACKNOWLEDGED PACKET BYTES (whole QUIC packets, including
headers and retransmitted copies). It is NOT the unique file payload delivered.
Plot 2 marks "declared lost" events (any recovery rule), not necessarily congestion events.
Median run: for an even number of runs the LOWER middle run is chosen.

Examples:
    python plot_mechanism.py cwnd \
        --panel baseline=parsed_baseline.csv --panel moderate=parsed_moderate.csv \
        --out plots/

    python plot_mechanism.py cumulative \
        --series baseline=parsed_baseline.csv --series severe=parsed_severe.csv \
        --out plots/

    # pick the MEDIAN run by goodput (use this run for the final Plot 2):
    python plot_mechanism.py median-run --results results.csv \
        --variant stock --profile moderate
"""
import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from detect_spurious import detect  # noqa: E402

LINESTYLES = ["-", "--", "-.", ":"]


def _pairs(items):
    out = []
    for it in items:
        if "=" not in it:
            raise SystemExit("Expected label=path, got: %s" % it)
        label, path = it.split("=", 1)
        out.append((label, path))
    return out


def _write_alt(path, text):
    with open(path, "w") as f:
        f.write(text.strip() + "\n")


# --------------------------------------------------------------------------
# Plot 2: cwnd over time with loss markers
# --------------------------------------------------------------------------
def plot_cwnd(panels, out_dir, space="application"):
    os.makedirs(out_dir, exist_ok=True)
    n = len(panels)
    fig, axes = plt.subplots(n, 1, sharex=False, sharey=False,  # runs differ a lot in duration and in cwnd range
                             figsize=(9, 3.3 * n), squeeze=False)
    data_parts, alt = [], []

    for ax, (label, path) in zip(axes[:, 0], panels):
        df = pd.read_csv(path)
        m = df[df["event_type"] == "metrics"].dropna(subset=["cwnd"])
        lost = df[(df["event_type"] == "lost") & (df["pn_space"] == space)]
        spur, summ = detect(df, space)
        if m.empty:
            print("WARNING: %s has no cwnd samples - the cwnd line will be empty" % label, file=sys.stderr)
        if summ.get("warning"):
            print("WARNING: %s: %s" % (label, summ["warning"]), file=sys.stderr)

        cwnd_kb = m["cwnd"] / 1000.0
        ymax = (cwnd_kb.max() if len(cwnd_kb) else 1.0) * 1.08
        ax.step(m["time_s"], cwnd_kb, where="post", color="black",
                linestyle="-", linewidth=1.4, label="cwnd")
        ax.vlines(lost["time_s"], 0, ymax, colors="red", linestyles="--",
                  linewidth=0.7, alpha=0.5, label="declared lost (any rule)")
        ax.plot(spur["lost_time_s"], [ymax] * len(spur), linestyle="none",
                marker="v", color="green", markersize=5, label="spurious loss")
        ax.set_ylim(0, ymax * 1.05)
        ax.set_ylabel("cwnd (KB)  [own scale]")
        ax.set_title("%s: %d declared lost, %d spurious (%.1f%%), max cwnd %.0f KB%s" % (
            label, summ["declared_lost"], summ["spurious"], summ["spurious_rate_pct"],
            cwnd_kb.max() if len(cwnd_kb) else 0.0,
            "  [NO CWND DATA]" if m.empty else ""))
        ax.grid(alpha=0.3)

        data_parts.append(pd.DataFrame({"panel": label, "kind": "cwnd_kb",
                                        "time_s": m["time_s"], "value": cwnd_kb}))
        data_parts.append(pd.DataFrame({"panel": label, "kind": "declared_lost_packet",
                                        "time_s": lost["time_s"], "value": lost["packet_number"]}))
        data_parts.append(pd.DataFrame({"panel": label, "kind": "spurious_packet",
                                        "time_s": spur["lost_time_s"], "value": spur["packet_number"]}))
        alt.append("%s: %d packets declared lost, %d of them spurious" % (
            label, summ["declared_lost"], summ["spurious"]))

    for ax in axes[:, 0]:
        ax.set_xlabel("time (s)  [note: each panel has its own time scale]")
    axes[0, 0].legend(loc="upper right", fontsize=8)
    fig.suptitle("Plot 2: congestion window and loss events")
    fig.tight_layout()

    base = os.path.join(out_dir, "plot2_cwnd")
    fig.savefig(base + ".png", dpi=150)
    plt.close(fig)
    pd.concat(data_parts).to_csv(base + "_data.csv", index=False)
    _write_alt(base + ".alt.txt",
               "Line charts of QUIC congestion window (KB) against time, one panel per "
               "network profile. Black solid line is cwnd, red dashed vertical lines mark "
               "packets declared lost by any loss-detection rule (not necessarily congestion), "
               "and green triangles at the top mark spurious losses "
               "(packets declared lost that were later seen in an ACK). " + "; ".join(alt) + ".")
    print("Wrote", base + ".png")


# --------------------------------------------------------------------------
# Plot 4: cumulative acknowledged bytes over time
# --------------------------------------------------------------------------
def cumulative_bytes(df, space="application"):
    d = df[df["pn_space"] == space]
    sent = d[d["event_type"] == "sent"][["packet_number", "size"]].drop_duplicates("packet_number")
    acked = (d[d["event_type"] == "acked"].groupby("packet_number")["time_s"]
             .min().reset_index())
    j = acked.merge(sent, on="packet_number", how="inner").sort_values("time_s")
    j["cum_acked_packet_mb"] = j["size"].astype(float).cumsum() / 1e6
    return j[["time_s", "cum_acked_packet_mb"]]


def plot_cumulative(series, out_dir, space="application"):
    os.makedirs(out_dir, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 4.2))
    data_parts, alt = [], []
    for i, (label, path) in enumerate(series):
        c = cumulative_bytes(pd.read_csv(path), space)
        ax.plot(c["time_s"], c["cum_acked_packet_mb"], linestyle=LINESTYLES[i % len(LINESTYLES)],
                linewidth=1.8, label=label)
        part = c.copy()
        part.insert(0, "series", label)
        data_parts.append(part)
        if len(c):
            alt.append("%s reaches %.1f MB of acknowledged packet bytes at %.1f s" % (
                label, c["cum_acked_packet_mb"].iloc[-1], c["time_s"].iloc[-1]))
    ax.set_xlabel("time (s)")
    ax.set_ylabel("cumulative acknowledged packet bytes (MB)")
    ax.set_title("Plot 4: cumulative acknowledged packet bytes")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()

    base = os.path.join(out_dir, "plot4_cumulative")
    fig.savefig(base + ".png", dpi=150)
    plt.close(fig)
    pd.concat(data_parts).to_csv(base + "_data.csv", index=False)
    _write_alt(base + ".alt.txt",
               "Line chart of cumulative acknowledged packet bytes (whole QUIC packets including "
               "overhead and retransmitted copies, not unique file data) in MB against time in "
               "seconds, one line per network profile with different line styles. A line that "
               "rises more slowly means slower progress. " + "; ".join(alt) + ".")
    print("Wrote", base + ".png")


# --------------------------------------------------------------------------
# Median run picker
# --------------------------------------------------------------------------
def pick_median_run(results_csv, variant, profile):
    """Return the row of the median-goodput run for one variant+profile."""
    df = pd.read_csv(results_csv)
    sub = df[(df["variant"] == variant) & (df["profile"] == profile)]
    if "sha256_ok" in sub.columns:
        sub = sub[sub["sha256_ok"].astype(str).str.lower().isin(["true", "1", "yes"])]
    if sub.empty:
        raise SystemExit("No matching successful runs.")
    sub = sub.sort_values("goodput_mbps").reset_index(drop=True)
    return sub.iloc[(len(sub) - 1) // 2]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p2 = sub.add_parser("cwnd", help="Plot 2")
    p2.add_argument("--panel", action="append", required=True, help="label=parsed.csv (repeat)")
    p2.add_argument("--out", default="plots")
    p2.add_argument("--space", default="application")

    p4 = sub.add_parser("cumulative", help="Plot 4")
    p4.add_argument("--series", action="append", required=True, help="label=parsed.csv (repeat)")
    p4.add_argument("--out", default="plots")
    p4.add_argument("--space", default="application")

    pm = sub.add_parser("median-run", help="pick the median-goodput run")
    pm.add_argument("--results", required=True)
    pm.add_argument("--variant", required=True)
    pm.add_argument("--profile", required=True)

    a = ap.parse_args(argv)
    if a.cmd == "cwnd":
        plot_cwnd(_pairs(a.panel), a.out, a.space)
    elif a.cmd == "cumulative":
        plot_cumulative(_pairs(a.series), a.out, a.space)
    else:
        r = pick_median_run(a.results, a.variant, a.profile)
        print("Median run: run=%s goodput=%.2f Mbps\nqlog_path=%s" % (r.get("run"), r["goodput_mbps"], r.get("qlog_path")))
    return 0


if __name__ == "__main__":
    sys.exit(main())