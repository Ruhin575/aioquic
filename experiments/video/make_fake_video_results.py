#!/usr/bin/env python3
"""Writes experiments/video/fake_video_results.csv (Day 0 stub, Amrutha).

Synthetic QoE summary rows in the agreed schema, so Pooja's plot_qoe.py can be built before real runs exist.
3 variants (stock, k20, dynamic) x 5 profiles x 5 runs. The numbers are INVENTED but ordered the way we
expect (worse profile -> more stalls, lower bitrate; k20/dynamic a bit better than stock). Not real results.
Seeded, so re-running gives the same file.
"""
import csv
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from video_core import qoe_score  # the team's QoE formula

COLUMNS = ["variant", "profile", "run", "startup_delay_s", "stall_count", "total_stall_s",
           "avg_bitrate_mbps", "quality_switches", "qoe_score"]
PROFILES = ["baseline", "mild", "moderate", "severe", "handover"]
VARIANTS = ["stock", "k20", "dynamic"]
# profile -> (mean bitrate Mbps, mean stalls, mean startup s, mean switches)
BASE = {"baseline": (4.2, 0.0, 1.6, 1.0), "mild": (3.2, 0.8, 1.9, 3.0), "moderate": (2.0, 2.2, 2.4, 5.0),
        "severe": (1.2, 3.5, 2.8, 7.0), "handover": (0.8, 4.5, 3.2, 8.0)}
# variant -> how much better than stock (fraction)
GAIN = {"stock": 0.0, "k20": 0.15, "dynamic": 0.25}


def main():
    rng = random.Random(1)
    out = Path(__file__).resolve().parent / "fake_video_results.csv"
    rows = []
    for v in VARIANTS:
        for p in PROFILES:
            br, st, su, sw = BASE[p]
            g = GAIN[v] if p != "baseline" else 0.0
            for run in range(1, 6):
                stalls = max(0, round(rng.gauss(st * (1 - g), 0.7))) if st else 0
                stall_s = round(sum(rng.uniform(1.5, 6.0) for _ in range(stalls)), 3)
                bitrate = round(min(5.0, max(0.25, rng.gauss(br * (1 + g), 0.15 * br))), 3)
                startup = round(max(0.8, rng.gauss(su, 0.2)), 3)
                switches = max(0, round(rng.gauss(sw * (1 - g / 2), 1.0)))
                rows.append(dict(variant=v, profile=p, run=run, startup_delay_s=startup, stall_count=stalls,
                                 total_stall_s=stall_s, avg_bitrate_mbps=bitrate, quality_switches=switches,
                                 qoe_score=round(qoe_score(bitrate, stalls, stall_s, switches), 4)))
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print("wrote %d rows to %s" % (len(rows), out))


if __name__ == "__main__":
    main()
