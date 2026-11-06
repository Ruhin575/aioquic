
#!/usr/bin/env python3

import sys
import csv
from pathlib import Path
from bisect import bisect_left

import pandas as pd

ANALYSIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ANALYSIS_DIR))

from parse_qlog import parse_file
from detect_spurious import detect


ROOT = ANALYSIS_DIR.parents[1]

DATASETS = {
    "threshold_20": (
        ROOT / "experiments/results/threshold_20/main/huge-threshold"
    ),
    "threshold_100": (
        ROOT / "experiments/results/huge_threshold_100/main/huge-threshold"
    ),
}

PROFILES = ["moderate", "severe"]

CANDIDATE_K = [3, 5, 10, 20, 50, 100]


def analyse_qlog(qlog_path, dataset, profile, run):
    """Replay candidate packet thresholds for one qlog."""

    df = parse_file(str(qlog_path))

    # Existing project's spurious-loss detector.
    spurious_df, detector_summary = detect(df)

    late_ack_times = {
        int(row.packet_number): float(row.acked_time_s)
        for row in spurious_df.itertuples(index=False)
    }

    # Work only with application packet-number space.
    app = df[df["pn_space"] == "application"].copy()
    app = app.sort_values("time_s", kind="stable")

    # Reconstruct the progression of largest ACKed PN.
    largest_values = []
    ack_times = []
    largest_acked = -1

    acked_rows = app[app["event_type"] == "acked"]

    for row in acked_rows.itertuples(index=False):
        pn = int(row.packet_number)
        largest_acked = max(largest_acked, pn)

        largest_values.append(largest_acked)
        ack_times.append(float(row.time_s))

    results = []

    lost_rows = app[app["event_type"] == "lost"]

    for loss in lost_rows.itertuples(index=False):

        packet_number = int(loss.packet_number)
        loss_time = float(loss.time_s)

        is_spurious = packet_number in late_ack_times
        late_ack_time = late_ack_times.get(packet_number)

        label = (
            "spurious_indicator"
            if is_spurious
            else "no_observed_late_ack_proxy"
        )

        for k in CANDIDATE_K:

            target = packet_number + k

            # First ACK event at which largest ACKed reaches p + K.
            crossing_index = bisect_left(
                largest_values, target
            )

            if crossing_index < len(largest_values):
                crossing_time = ack_times[crossing_index]
            else:
                crossing_time = None

            if crossing_time is None:
                crossing_offset_ms = None
                crossed_before_loss = False
            else:
                crossing_offset_ms = (crossing_time - loss_time) * 1000.0
                crossed_before_loss = crossing_time <= loss_time

            if is_spurious:
                if crossing_time is None:
                    packet_threshold_before_ack = False
                    status = "no_packet_threshold_crossing_observed"
                elif crossing_time <= late_ack_time:
                    packet_threshold_before_ack = True
                    status = "threshold_before_late_ack"
                else:
                    packet_threshold_before_ack = False
                    status = "late_ack_before_threshold"
            else:
                packet_threshold_before_ack = None

                if crossing_time is None:
                    status = "genuine_proxy_threshold_not_observed"
                elif crossing_time > loss_time:
                    status = "genuine_proxy_detection_delayed"
                else:
                    status = "genuine_proxy_threshold_already_met"

            results.append({
                "dataset": dataset,
                "profile": profile,
                "run": run,
                "packet_number": packet_number,
                "label": label,
                "candidate_K": k,
                "observed_loss_time_s": loss_time,
                "late_ack_time_s": (
                    late_ack_time if late_ack_time is not None else ""
                ),
                "threshold_crossing_time_s": (
                    crossing_time if crossing_time is not None else ""
                ),
                "threshold_crossing_offset_ms": (
                    round(crossing_offset_ms, 4)
                    if crossing_offset_ms is not None else ""
                ),
                "crossed_before_or_at_loss": crossed_before_loss,
                "packet_threshold_before_late_ack": (
                    packet_threshold_before_ack
                    if packet_threshold_before_ack is not None
                    else ""
                ),
                "status": status,
            })

    return results, detector_summary


def build_summary(results):
    """Build descriptive recovery trade-off statistics."""

    summary_rows = []

    for dataset in DATASETS:
        for profile in PROFILES:
            for k in CANDIDATE_K:

                subset = [
                    row for row in results
                    if row["dataset"] == dataset
                    and row["profile"] == profile
                    and row["candidate_K"] == k
                ]

                spurious = [
                    row for row in subset
                    if row["label"] == "spurious_indicator"
                ]

                genuine_proxy = [
                    row for row in subset
                    if row["label"] == "no_observed_late_ack_proxy"
                ]

                # Spurious indicators for which the late ACK arrived
                # before the candidate threshold crossing, or for
                # which no crossing was observed.
                spurious_ack_before_threshold = [
                    row for row in spurious
                    if not row["packet_threshold_before_late_ack"]
                ]

                spurious_threshold_before_ack = [
                    row for row in spurious
                    if row["packet_threshold_before_late_ack"]
                ]

                # Proxy packets for which a threshold crossing
                # was observed somewhere in the trace.
                proxy_crossed = [
                    row for row in genuine_proxy
                    if row["threshold_crossing_time_s"] != ""
                ]

                # Right-censored: no crossing observed in this trace.
                proxy_no_crossing = [
                    row for row in genuine_proxy
                    if row["threshold_crossing_time_s"] == ""
                ]

                # Crossing happened before or at the observed loss.
                proxy_early_or_at_loss = [
                    row for row in proxy_crossed
                    if float(row["threshold_crossing_offset_ms"]) <= 0
                ]

                # Crossing happened after the observed loss.
                proxy_delayed = [
                    row for row in proxy_crossed
                    if float(row["threshold_crossing_offset_ms"]) > 0
                ]

                # Calculate delay statistics only for positive delays.
                positive_delays = [
                    float(row["threshold_crossing_offset_ms"])
                    for row in proxy_delayed
                ]

                spurious_avoidance_pct = (
                    100 * len(spurious_ack_before_threshold)
                    / len(spurious)
                    if spurious else None
                )

                spurious_threshold_pct = (
                    100 * len(spurious_threshold_before_ack)
                    / len(spurious)
                    if spurious else None
                )

                summary_rows.append({
                    "dataset": dataset,
                    "profile": profile,
                    "candidate_K": k,

                    "spurious_total": len(spurious),

                    "spurious_ack_before_threshold_or_no_crossing":
                        len(spurious_ack_before_threshold),

                    "spurious_ack_before_threshold_pct": (
                        round(spurious_avoidance_pct, 2)
                        if spurious_avoidance_pct is not None else ""
                    ),

                    "spurious_threshold_before_ack":
                        len(spurious_threshold_before_ack),

                    "spurious_threshold_before_ack_pct": (
                        round(spurious_threshold_pct, 2)
                        if spurious_threshold_pct is not None else ""
                    ),

                    "genuine_proxy_total": len(genuine_proxy),

                    "genuine_proxy_threshold_crossed":
                        len(proxy_crossed),

                    "genuine_proxy_no_crossing_observed":
                        len(proxy_no_crossing),

                    "genuine_proxy_crossed_before_or_at_loss":
                        len(proxy_early_or_at_loss),

                    "genuine_proxy_crossed_after_loss":
                        len(proxy_delayed),

                    "median_positive_crossing_delay_ms": (
                        round(pd.Series(positive_delays).median(), 4)
                        if positive_delays else ""
                    ),

                    "p95_positive_crossing_delay_ms": (
                        round(pd.Series(positive_delays).quantile(0.95), 4)
                        if positive_delays else ""
                    ),
                })

    return summary_rows


def write_csv(path, rows):
    if not rows:
        print("No records to write:", path)
        return

    with path.open("w", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(rows[0].keys())
        )
        writer.writeheader()
        writer.writerows(rows)


def main():

    all_results = []

    for dataset, base_dir in DATASETS.items():
        for profile in PROFILES:

            profile_dir = base_dir / profile

            qlogs = sorted(
                profile_dir.glob("run_*/server-qlog/*.qlog")
            )

            for qlog in qlogs:

                run = qlog.parent.parent.name

                print(f"Analysing {dataset}/{profile}/{run}")

                rows, detector_summary = analyse_qlog(
                    qlog, dataset, profile, run
                )

                all_results.extend(rows)

                print(
                    f"  Losses: {detector_summary['declared_lost']}, "
                    f"Spurious indicators: {detector_summary['spurious']}"
                )

    summary = build_summary(all_results)

    packet_csv = (
        ANALYSIS_DIR / "recovery_tradeoff_packet_details_corrected.csv"
    )

    summary_csv = (
        ANALYSIS_DIR / "recovery_tradeoff_summary_corrected.csv"
    )

    write_csv(packet_csv, all_results)
    write_csv(summary_csv, summary)

    print("\nDay 2 analysis complete.")
    print("Packet-level records:", len(all_results))
    print("Summary records:", len(summary))
    print("Saved:", packet_csv)
    print("Saved:", summary_csv)


if __name__ == "__main__":
    main()
