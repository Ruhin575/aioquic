
#!/usr/bin/env python3
"""Calculate per-run metrics from parsed qlog and spurious-loss CSVs."""

import argparse
from email import parser
from email.mime import text
import sys
from pathlib import Path
from matplotlib.pyplot import text

import pandas as pd


def normalize_file_size(value):
    text = str(value).strip().upper()

    if text.endswith("MIB"):
        try:
            return int(float(text[:-3]) * 1_048_576)
        except ValueError:
            return text

    if text.endswith("MB"):
        try:
            number = float(text[:-2])
            decimal_bytes = int(number * 1_000_000)
            binary_bytes = int(number * 1_048_576)

            # Accept decimal MB and binary MiB conventions.
            return {decimal_bytes, binary_bytes}
        except ValueError:
            return text

    try:
        return int(float(text))
    except ValueError:
        return text

def size_matches(value, target_size):
    """Check whether a CSV file-size value matches the requested size."""
    normalized = normalize_file_size(value)

    if isinstance(normalized, set):
        return bool(normalized & target_size)

    if isinstance(target_size, set):
        return normalized in target_size

    return normalized == target_size

def calculate_metrics(parsed, spurious):
    """Calculate Day 0 metrics for one run."""

    required = {
        "event_type", "time_s", "packet_number", "pn_space",
        "cwnd", "smoothed_rtt",
    }
    missing = required - set(parsed.columns)
    if missing:
        raise ValueError(f"parsed CSV missing columns: {sorted(missing)}")

    sp_required = {"packet_number", "lost_time_s", "acked_time_s"}
    sp_missing = sp_required - set(spurious.columns)
    if sp_missing:
        raise ValueError(f"spurious CSV missing columns: {sorted(sp_missing)}")

    # Packet numbers can repeat in different QUIC packet-number spaces.
    app = parsed[parsed["pn_space"] == "application"].copy()
    sent = app[app["event_type"] == "sent"]
    lost = app[app["event_type"] == "lost"]

    packets_sent = int(sent["packet_number"].nunique())
    declared_lost = int(lost["packet_number"].nunique())
    spurious_count = int(spurious["packet_number"].nunique())

    rate = (
        100.0 * spurious_count / declared_lost
        if declared_lost else 0.0
    )
    per_sent = (
        100.0 * spurious_count / packets_sent
        if packets_sent else 0.0
    )

    # Use the parser's metrics rows. RTT fields are logged in milliseconds,
    # while time_s is in seconds, so convert RTT to seconds for comparisons.
    metrics = parsed[parsed["event_type"] == "metrics"].copy()
    metrics["time_s"] = pd.to_numeric(metrics["time_s"], errors="coerce")
    metrics["cwnd"] = pd.to_numeric(metrics["cwnd"], errors="coerce")
    metrics["smoothed_rtt"] = pd.to_numeric(
        metrics["smoothed_rtt"], errors="coerce"
    )
    metrics = (
        metrics.dropna(subset=["time_s", "cwnd"])
        .sort_values("time_s")
        .reset_index(drop=True)
    )

    decreases = []
    for i in range(1, len(metrics)):
        previous = metrics.iloc[i - 1]
        current = metrics.iloc[i]
        if current["cwnd"] < previous["cwnd"]:
            decreases.append({
                "time_s": float(current["time_s"]),
                "smoothed_rtt_ms": current["smoothed_rtt"],
            })

    # A cwnd decrease is counted once if it falls in at least one
    # spurious-loss window [loss time, loss time + smoothed RTT].
    windows = []
    for _, loss in spurious.iterrows():
        loss_time = pd.to_numeric(
            pd.Series([loss["lost_time_s"]]), errors="coerce"
        ).iloc[0]
        if pd.isna(loss_time):
            continue

        candidates = metrics[metrics["time_s"] <= loss_time]
        candidates = candidates.dropna(subset=["smoothed_rtt"])
        if candidates.empty:
            continue

        rtt_ms = float(candidates.iloc[-1]["smoothed_rtt"])
        if rtt_ms < 0:
            continue
        windows.append((float(loss_time), float(loss_time) + rtt_ms / 1000.0))

    unnecessary = sum(
        any(start <= drop["time_s"] <= end for start, end in windows)
        for drop in decreases
    )

    if declared_lost == 0:
        status = "no_losses"
    elif spurious.empty:
        status = "ok"
    else:
        status = "ok"

    return {
        "packets_sent": packets_sent,
        "declared_lost": declared_lost,
        "spurious": spurious_count,
        "spurious_rate_pct": round(rate, 2),
        "spurious_per_sent_pct": round(per_sent, 2),
        "cwnd_decrease_events": len(decreases),
        "unnecessary_cwnd_reductions": int(unnecessary),
        "status": status,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Parsed qlog CSV")
    parser.add_argument("--spurious", required=True, help="Spurious-loss CSV")
    parser.add_argument("--output", help="Optional metrics output CSV")
    parser.add_argument(
        "--transfers",
        help="Optional transfer results CSV containing goodput and completion time",
    )
    parser.add_argument("--variant")
    parser.add_argument("--profile")
    parser.add_argument("--run")
    parser.add_argument(
        "--file-size",
        default="10MB",
        help="Transfer size to select, e.g. 10MB (default: 10MB)",
    )
    args = parser.parse_args()

    try:
        parsed = pd.read_csv(args.input)
        spurious = pd.read_csv(args.spurious)
        result = calculate_metrics(parsed, spurious)

        if args.transfers:
            transfers = pd.read_csv(args.transfers)
            required = {
                "variant", "profile", "run", "file_size",
                "download_time_s", "goodput_mbps",
            }
            missing = required - set(transfers.columns)
            if missing:
                raise ValueError(
                    f"transfers CSV missing columns: {sorted(missing)}"
                )
            selected = transfers.copy()

            target_size = normalize_file_size(args.file_size)

            selected = selected[
                selected["file_size"].map(
                    lambda value: size_matches(value, target_size)
                )
            ]

            for col, value in (
                ("variant", args.variant),
                ("profile", args.profile),
                ("run", args.run),
            ):
                if value is not None:
                    selected = selected[selected[col].astype(str) == str(value)]


            if len(selected) != 1:
                raise ValueError(
                    "transfer lookup must match exactly one row; "
                    "provide --variant, --profile and --run as needed"
                )

            row = selected.iloc[0]
            result.update({
                "variant": row["variant"],
                "profile": row["profile"],
                "run": row["run"],
                "goodput_mbps": float(row["goodput_mbps"]),
                "completion_time_s": float(row["download_time_s"]),
            })

        output = pd.DataFrame([result])
        print(output.to_string(index=False))

        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            output.to_csv(args.output, index=False)
            print(f"Wrote {args.output}")

    except (OSError, ValueError, KeyError, pd.errors.ParserError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
