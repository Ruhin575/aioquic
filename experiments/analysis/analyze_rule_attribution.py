#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

# Support running this script directly from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_qlog import parse_file


def clean_value(value):
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def analyze_qlog(qlog_path):
    df = parse_file(qlog_path, strict=True)

    required = {"event_type", "time_s", "packet_number"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Parser output is missing columns: {sorted(missing)}")

    lost = df[df["event_type"] == "lost"].copy()

    details = []
    rule_counts = {}

    for _, event in lost.iterrows():
        rule = clean_value(event.get("rule"))

        if rule is None or str(rule).strip() == "":
            rule = "unavailable"

        rule_counts[rule] = rule_counts.get(rule, 0) + 1

        details.append({
            "qlog_path": str(qlog_path),
            "packet_number": clean_value(event.get("packet_number")),
            "time_s": clean_value(event.get("time_s")),
            "rule": rule,
            "by_packet": clean_value(event.get("by_packet")),
            "by_time": clean_value(event.get("by_time")),
        })

    total_lost = len(lost)
    unavailable = rule_counts.get("unavailable", 0)
    attributed = total_lost - unavailable

    summary = {
        "qlog_path": str(qlog_path),
        "total_lost": total_lost,
        "attributed": attributed,
        "unavailable": unavailable,
        "attribution_coverage_pct": (
            round(100 * attributed / total_lost, 2)
            if total_lost else None
        ),
        "rule_counts": json.dumps(rule_counts, sort_keys=True),
    }

    return summary, details


def main():
    parser = argparse.ArgumentParser(
        description="Analyze loss-rule attribution in server qlogs."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("experiments/results/attribution"),
    )
    args = parser.parse_args()

    if args.input.is_file():
        qlogs = [args.input] if args.input.suffix == ".qlog" else []
    elif args.input.is_dir():
        qlogs = sorted(
            path for path in args.input.rglob("*.qlog")
            if "server-qlog" in path.parts
        )
    else:
        parser.error(f"Input does not exist: {args.input}")

    if not qlogs:
        parser.error(f"No server .qlog files found under: {args.input}")

    summaries = []
    all_details = []
    failures = []

    for qlog_path in qlogs:
        try:
            summary, details = analyze_qlog(qlog_path)
            summaries.append(summary)
            all_details.extend(details)

            print(
                f"[OK] {qlog_path}: "
                f"lost={summary['total_lost']}, "
                f"attributed={summary['attributed']}, "
                f"unavailable={summary['unavailable']}"
            )
        except Exception as exc:
            failures.append((str(qlog_path), str(exc)))
            print(f"[ERROR] {qlog_path}: {exc}")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(summaries).to_csv(
        args.output_dir / "attribution_summary.csv", index=False
    )
    pd.DataFrame(all_details).to_csv(
        args.output_dir / "attribution_events.csv", index=False
    )

    total_lost = sum(row["total_lost"] for row in summaries)
    total_attributed = sum(row["attributed"] for row in summaries)
    total_unavailable = sum(row["unavailable"] for row in summaries)

    print("\n=== Overall attribution summary ===")
    print(f"Server qlogs found:    {len(qlogs)}")
    print(f"Qlogs processed:       {len(summaries)}")
    print(f"Qlogs failed:          {len(failures)}")
    print(f"Total loss events:     {total_lost}")
    print(f"Attributed events:     {total_attributed}")
    print(f"Unavailable events:    {total_unavailable}")

    if total_lost:
        print(
            f"Attribution coverage:  "
            f"{100 * total_attributed / total_lost:.2f}%"
        )

    print(f"\nOutput directory: {args.output_dir}")

    if failures:
        print("\nFailures:")
        for path, error in failures:
            print(f"  {path}: {error}")


if __name__ == "__main__":
    main()
