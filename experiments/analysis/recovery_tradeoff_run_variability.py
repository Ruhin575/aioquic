#!/usr/bin/env python3

from pathlib import Path
import pandas as pd

ANALYSIS_DIR = Path(__file__).resolve().parent

INPUT_CSV = (
    ANALYSIS_DIR / "recovery_tradeoff_packet_details_corrected.csv"
)

RUN_OUTPUT = (
    ANALYSIS_DIR / "recovery_tradeoff_run_level.csv"
)

VARIABILITY_OUTPUT = (
    ANALYSIS_DIR / "recovery_tradeoff_run_variability.csv"
)


def is_true(value):
    """Safely interpret Boolean values read from CSV."""
    return str(value).strip().lower() == "true"


def analyse_run(group):
    """Calculate trade-off metrics for one run and one K."""

    spurious = group[
        group["label"] == "spurious_indicator"
    ]

    proxy = group[
        group["label"] == "no_observed_late_ack_proxy"
    ]

    # Spurious indicator outcomes.
    spurious_before = spurious[
        ~spurious["packet_threshold_before_late_ack"].apply(is_true)
    ]

    spurious_after = spurious[
        spurious["packet_threshold_before_late_ack"].apply(is_true)
    ]

    spurious_total = len(spurious)

    # Proxy packet outcomes.
    crossing_time = pd.to_numeric(
        proxy["threshold_crossing_time_s"],
        errors="coerce"
    )

    offset = pd.to_numeric(
        proxy["threshold_crossing_offset_ms"],
        errors="coerce"
    )

    crossed = proxy[crossing_time.notna()]
    censored = proxy[crossing_time.isna()]

    early_or_at = offset.notna() & (offset <= 0)
    delayed = offset.notna() & (offset > 0)

    delayed_offsets = offset[delayed].dropna()

    proxy_total = len(proxy)

    return {
        "loss_events": len(group),

        "spurious_total": spurious_total,

        "spurious_ack_before_threshold_or_no_crossing":
            len(spurious_before),

        "spurious_ack_before_threshold_pct": (
            100 * len(spurious_before) / spurious_total
            if spurious_total else None
        ),

        "spurious_threshold_before_ack":
            len(spurious_after),

        "spurious_threshold_before_ack_pct": (
            100 * len(spurious_after) / spurious_total
            if spurious_total else None
        ),

        "genuine_proxy_total": proxy_total,

        "genuine_proxy_threshold_crossed": len(crossed),

        "genuine_proxy_no_crossing_observed": len(censored),

        "genuine_proxy_crossed_before_or_at_loss":
            int(early_or_at.sum()),

        "genuine_proxy_crossed_after_loss":
            int(delayed.sum()),

        "median_positive_crossing_delay_ms": (
            delayed_offsets.median()
            if not delayed_offsets.empty else None
        ),

        "p95_positive_crossing_delay_ms": (
            delayed_offsets.quantile(0.95)
            if not delayed_offsets.empty else None
        ),
    }


def main():

    df = pd.read_csv(INPUT_CSV)

    required_columns = [
        "dataset",
        "profile",
        "run",
        "label",
        "candidate_K",
        "packet_threshold_before_late_ack",
        "threshold_crossing_time_s",
        "threshold_crossing_offset_ms",
    ]

    missing = [
        column for column in required_columns
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing required CSV columns: {missing}"
        )

    run_rows = []

    group_columns = [
        "dataset",
        "profile",
        "run",
        "candidate_K",
    ]

    for keys, group in df.groupby(group_columns):

        dataset, profile, run, k = keys

        metrics = analyse_run(group)

        run_rows.append({
            "dataset": dataset,
            "profile": profile,
            "run": run,
            "candidate_K": k,
            **metrics,
        })

    run_df = pd.DataFrame(run_rows)

    run_df = run_df.sort_values(
        ["dataset", "profile", "candidate_K", "run"]
    )

    # Aggregate the five run-level results.
    metric_columns = [
        "spurious_ack_before_threshold_pct",
        "spurious_threshold_before_ack_pct",
        "genuine_proxy_crossed_after_loss",
        "genuine_proxy_no_crossing_observed",
        "median_positive_crossing_delay_ms",
        "p95_positive_crossing_delay_ms",
    ]

    aggregate_rows = []

    aggregate_groups = run_df.groupby(
        ["dataset", "profile", "candidate_K"]
    )

    for keys, group in aggregate_groups:

        dataset, profile, k = keys

        row = {
            "dataset": dataset,
            "profile": profile,
            "candidate_K": k,
            "runs": len(group),
        }

        for metric in metric_columns:

            values = pd.to_numeric(
                group[metric],
                errors="coerce"
            ).dropna()

            row[f"{metric}_mean"] = (
                values.mean() if not values.empty else None
            )

            row[f"{metric}_sd"] = (
                values.std(ddof=1)
                if len(values) >= 2 else None
            )

            row[f"{metric}_min"] = (
                values.min() if not values.empty else None
            )

            row[f"{metric}_max"] = (
                values.max() if not values.empty else None
            )

        aggregate_rows.append(row)

    variability_df = pd.DataFrame(aggregate_rows)

    run_df.to_csv(RUN_OUTPUT, index=False)
    variability_df.to_csv(VARIABILITY_OUTPUT, index=False)

    print("Run-to-run variability analysis complete.")
    print("Run-level records:", len(run_df))
    print("Aggregate records:", len(variability_df))
    print("Saved:", RUN_OUTPUT)
    print("Saved:", VARIABILITY_OUTPUT)


if __name__ == "__main__":
    main()
