#!/usr/bin/env python3
"""detect_spurious.py - find spurious losses in a parsed qlog CSV.

Definition (Day 0 contract): a spurious loss is a packet number that was
declared lost at time L and was first acknowledged at a later time A > L.

Limitations (state them in the report):
  * "declared lost" = removed as lost by ANY recovery rule (packet threshold, time
    threshold, PTO); the qlog does not say which one fired.
  * The packet's data may have been retransmitted in a NEW packet before the late ACK;
    a late ACK does not prove the receiver got the data only once.
  * aioquic keeps a bounded number of ACK ranges, so a very old late ACK may be invisible.
    Failing to see a late ACK does NOT prove a loss was genuine.

Usage (CLI):
    python detect_spurious.py --input parsed.csv --output spurious.csv

Usage (module):
    from detect_spurious import detect
    spurious_df, summary = detect(parsed_df)
"""
import argparse
import json
import sys

import pandas as pd

DEFAULT_SPACE = "application"
REQUIRED_COLUMNS = ["event_type", "time_s", "packet_number", "pn_space"]


def detect(df, space=DEFAULT_SPACE):
    """Return (spurious DataFrame, summary dict) for one parsed qlog DataFrame.

    Only one packet-number space is analysed (default application) because packet
    numbers restart in each space and would otherwise collide.
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError("input is not a parse_qlog.py CSV; missing column(s): %s (need: %s)"
                         % (", ".join(missing), ", ".join(REQUIRED_COLUMNS)))
    d = df[df["pn_space"] == space]
    sent = d[d["event_type"] == "sent"]
    lost = d[d["event_type"] == "lost"]
    acked = d[d["event_type"] == "acked"]

    lost_first = lost.groupby("packet_number")["time_s"].min().rename("lost_time_s")
    acked_first = acked.groupby("packet_number")["time_s"].min().rename("acked_time_s")

    joined = pd.concat([lost_first, acked_first], axis=1, join="inner")
    sp = joined[joined["acked_time_s"] > joined["lost_time_s"]].copy()
    sp["delay_s"] = sp["acked_time_s"] - sp["lost_time_s"]
    sp.index.name = "packet_number"
    sp = sp.reset_index().sort_values("lost_time_s").reset_index(drop=True)

    n_lost = int(lost["packet_number"].nunique())
    n_sp = len(sp)
    summary = {
        "pn_space": space,
        "packets_sent": int(sent["packet_number"].nunique()),
        "declared_lost": n_lost,
        "spurious": n_sp,
        "spurious_rate_pct": round(100.0 * n_sp / n_lost, 2) if n_lost else 0.0,
        "median_late_ack_delay_ms": round(1000 * float(sp["delay_s"].median()), 2) if n_sp else None,
    }
    summary["ack_rows"] = int(acked["packet_number"].nunique())
    # status lets downstream code tell "no spurious losses" from "cannot tell".
    if n_lost and acked.empty:
        summary["status"] = "incomplete_no_ack_data"
        summary["warning"] = "losses present but no ACK data found - spurious count is NOT trustworthy"
    elif n_lost == 0:
        summary["status"] = "no_losses"
    else:
        summary["status"] = "ok"
    return sp, summary


def main(argv=None):
    ap = argparse.ArgumentParser(description="Detect spurious losses in a parsed qlog CSV.")
    ap.add_argument("--input", required=True, help="CSV written by parse_qlog.py")
    ap.add_argument("--output", required=True, help="CSV of spurious packets to write")
    ap.add_argument("--summary", help="optional JSON file for the summary")
    ap.add_argument("--space", default=DEFAULT_SPACE, help="packet number space (default application)")
    args = ap.parse_args(argv)

    df = pd.read_csv(args.input)
    try:
        sp, summary = detect(df, args.space)
    except ValueError as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 2
    sp.to_csv(args.output, index=False)
    if args.summary:
        with open(args.summary, "w") as f:
            json.dump(summary, f, indent=2)

    print("Packets sent        : %d" % summary["packets_sent"])
    print("Declared lost       : %d" % summary["declared_lost"])
    print("Spurious            : %d" % summary["spurious"])
    print("Spurious rate       : %.2f %%" % summary["spurious_rate_pct"])
    print("Status              : %s" % summary["status"])
    if "warning" in summary:
        print("WARNING: " + summary["warning"], file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())