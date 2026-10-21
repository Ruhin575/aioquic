#!/usr/bin/env python3
"""
analyze_probe.py — read the receiver CSV produced by udp_probe.py and print
observed delay, jitter, loss and reorder for one profile run.

Metric definitions:
  observed_delay_ms  : mean one-way delay (recv_ns - send_ns), over all
                       received packets, in ms.
  observed_jitter_ms : standard deviation of the per-packet one-way delay,
                       in ms. This is one of two reasonable definitions
                       (the other is RFC 3550 inter-arrival jitter, which
                       verify.sh also prints from ping / iperf3). We prefer
                       stddev of one-way delay because it is directly
                       comparable to netem's `delay <base> <jitter>` input.

  observed_loss_pct  : (expected - received) / expected * 100, where
                       expected = max(seq) + 1 (sender's count).

  observed_reorder_pct: fraction of received packets whose seq is strictly
                        less than the maximum seq seen so far at arrival
                        time. This matches netem's own definition of
                        "out of order" and is what the Linux kernel's
                        /proc/net/netstat "TcpExtTCPOFOQueue" counter also
                        reflects.

Also used as a module by verify.sh via `python3 analyze_probe.py <csv> <profile>`.
"""

from __future__ import annotations

import csv
import math
import sys
from pathlib import Path


def analyze(csv_path: Path) -> dict[str, float]:
    rows: list[tuple[int, int, int, int]] = []
    with open(csv_path) as fh:
        r = csv.reader(fh)
        next(r, None)  # header
        for row in r:
            rows.append((int(row[0]), int(row[1]), int(row[2]), int(row[3])))

    if not rows:
        return {
            "received": 0, "expected": 0,
            "delay_ms": float("nan"), "jitter_ms": float("nan"),
            "loss_pct": float("nan"), "reorder_pct": float("nan"),
        }

    seqs = [r[0] for r in rows]
    one_way_ns = [r[2] - r[1] for r in rows]

    received = len(rows)
    expected = max(seqs) + 1

    delays_ms = [d / 1e6 for d in one_way_ns]
    mean_delay = sum(delays_ms) / len(delays_ms)
    var = sum((d - mean_delay) ** 2 for d in delays_ms) / len(delays_ms)
    jitter = math.sqrt(var)

    loss_pct = 100.0 * (expected - received) / expected if expected else float("nan")

    # Reorder: at arrival index i, if seqs[i] < max(seqs[:i]) count it.
    out_of_order = 0
    max_so_far = -1
    for s in seqs:
        if s < max_so_far:
            out_of_order += 1
        else:
            max_so_far = s
    reorder_pct = 100.0 * out_of_order / received

    return {
        "received": received, "expected": expected,
        "delay_ms": mean_delay, "jitter_ms": jitter,
        "loss_pct": loss_pct, "reorder_pct": reorder_pct,
    }


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: analyze_probe.py <receiver.csv> [<profile_label>]",
              file=sys.stderr)
        return 2
    csv_path = Path(sys.argv[1])
    label = sys.argv[2] if len(sys.argv) > 2 else csv_path.stem

    stats = analyze(csv_path)
    print()
    print(f"=== Observed from pcap/probe: profile={label} ===")
    print(f"  packets expected    : {stats['expected']}")
    print(f"  packets received    : {stats['received']}")
    print(f"  one-way delay (mean): {stats['delay_ms']:.2f} ms")
    print(f"  jitter (stddev)     : {stats['jitter_ms']:.2f} ms")
    print(f"  loss                : {stats['loss_pct']:.3f} %")
    print(f"  out-of-order        : {stats['reorder_pct']:.3f} %")
    return 0


if __name__ == "__main__":
    sys.exit(main())
