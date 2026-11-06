
#!/usr/bin/env python3

"""
Gap distribution analysis for QUIC packet losses.

Uses the existing project parser and spurious-loss detector.

Outputs:
1. gap_distribution_validated.csv
2. gap_threshold_comparison.csv

Only application packet-number space is analysed.
"""

import sys
import csv
from pathlib import Path

import pandas as pd

# Import existing project analysis modules.
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
    """Calculate gap at each loss event in one qlog."""

    df = parse_file(str(qlog_path))

    # Use the project's existing spurious-loss detector.
    spurious_df, detector_summary = detect(df)

    spurious_packets = set(
        spurious_df["packet_number"].astype(int).tolist()
    )

    # Restrict the gap analysis to application packet-number space.
    app = df[df["pn_space"] == "application"].copy()

    # Preserve chronological ordering, including equal-time events.
    app = app.sort_values("time_s", kind="stable")

    largest_acked = None
    results = []

    for row in app.itertuples(index=False):

        packet_number = row.packet_number

        if pd.isna(packet_number):
            continue

        packet_number = int(packet_number)

        # Update largest ACKed only when an ACK event is encountered.
        if row.event_type == "acked":

            if largest_acked is None:
                largest_acked = packet_number
            else:
                largest_acked = max(
                    largest_acked, packet_number
                )

        elif row.event_type == "lost":

            gap = (
                largest_acked - packet_number
                if largest_acked is not None
                else None
            )

            results.append({
                "dataset": dataset,
                "profile": profile,
                "run": run,
                "packet_number": packet_number,
                "loss_time_s": row.time_s,
                "largest_acked_at_loss": (
                    largest_acked
                    if largest_acked is not None
                    else ""
                ),
                "gap": gap if gap is not None else "",
                "spurious": packet_number in spurious_packets,
            })

    return results, detector_summary


def build_threshold_comparison(results):
    """
    Calculate the fraction of observed spurious losses
    whose gap is below each candidate packet threshold.

    This is NOT proof that time-threshold losses would be prevented.
    """

    rows = []

    for dataset in sorted(set(r["dataset"] for r in results)):
        for profile in PROFILES:

            spurious = [
                r for r in results
                if r["dataset"] == dataset
                and r["profile"] == profile
                and r["spurious"]
                and r["gap"] != ""
                and int(r["gap"]) >= 0
            ]

            gaps = [int(r["gap"]) for r in spurious]
            total = len(gaps)

            for k in CANDIDATE_K:

                below = sum(gap < k for gap in gaps)

                rows.append({
                    "dataset": dataset,
                    "profile": profile,
                    "candidate_K": k,
                    "spurious_losses_with_gap": total,
                    "gap_below_K_count": below,
                    "gap_below_K_pct": (
                        round(100 * below / total, 2)
                        if total else 0
                    ),
                })

    return rows


def main():

    all_results = []

    for dataset, base_dir in DATASETS.items():

        for profile in PROFILES:

            profile_dir = base_dir / profile

            if not profile_dir.exists():
                print("Skipping missing directory:", profile_dir)
                continue

            qlogs = sorted(
                profile_dir.glob("run_*/server-qlog/*.qlog")
            )

            for qlog in qlogs:

                run = qlog.parent.parent.name

                print(f"Analysing {dataset}/{profile}/{run}")

                rows, summary = analyse_qlog(
                    qlog, dataset, profile, run
                )

                all_results.extend(rows)

                print(
                    f"  Lost: {summary['declared_lost']}, "
                    f"Spurious: {summary['spurious']}"
                )

    output_dir = ANALYSIS_DIR

    # Save one row per loss event.
    gap_csv = output_dir / "gap_distribution_validated.csv"

    fieldnames = [
        "dataset",
        "profile",
        "run",
        "packet_number",
        "loss_time_s",
        "largest_acked_at_loss",
        "gap",
        "spurious",
    ]

    with gap_csv.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_results)

    # Generate candidate K comparison.
    comparison = build_threshold_comparison(all_results)

    comparison_csv = (
        output_dir / "gap_threshold_comparison.csv"
    )

    with comparison_csv.open("w", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "dataset",
                "profile",
                "candidate_K",
                "spurious_losses_with_gap",
                "gap_below_K_count",
                "gap_below_K_pct",
            ],
        )
        writer.writeheader()
        writer.writerows(comparison)

    # Print summary.
    print("\n" + "=" * 65)
    print("VALIDATED GAP ANALYSIS SUMMARY")
    print("=" * 65)

    for dataset in DATASETS:
        for profile in PROFILES:

            subset = [
                r for r in all_results
                if r["dataset"] == dataset
                and r["profile"] == profile
            ]

            spurious = [
                r for r in subset if r["spurious"]
            ]

            valid_gaps = [
                int(r["gap"])
                for r in subset
                if r["gap"] != ""
            ]

            negative = sum(gap < 0 for gap in valid_gaps)

            print(f"\n{dataset} / {profile}")
            print("Loss events:", len(subset))
            print("Spurious losses:", len(spurious))
            print("Events with gap:", len(valid_gaps))
            print("Negative gaps:", negative)

            if valid_gaps:
                print("Minimum gap:", min(valid_gaps))
                print("Maximum gap:", max(valid_gaps))

    print("\nFiles saved:")
    print(gap_csv)
    print(comparison_csv)


if __name__ == "__main__":
    main()
