#!/usr/bin/env python3
"""parse_video_results.py - per-segment logs -> one QoE summary row per run.

Input : per-segment CSVs written by stream_client.py (columns run_id, segment_index, timestamp,
        bitrate_mbps, download_time_s, buffer_level_s, stall, stall_s), given as files or as
        directories that are searched recursively for segments*.csv.
Output: CSV in the Day 0 contract schema
        variant, profile, run, startup_delay_s, stall_count, total_stall_s,
        avg_bitrate_mbps, quality_switches, qoe_score

run_id convention (so no extra files are needed to know what a run was):
        <variant>__<profile>__<run>        e.g.  stock__moderate__3,  k20__severe__1

Metric definitions
  startup_delay_s    from <segments>.meta.json if present (written by stream_client.py), otherwise the
                     timestamp of the --startup-segments-th segment (default 1)
  stall_count        sum of the `stall` column (stall events that began since the previous segment)
  total_stall_s      sum of the `stall_s` column
  avg_bitrate_mbps   mean of bitrate_mbps over the segments (all segments have the same duration)
  quality_switches   number of times the bitrate differs from the previous segment's
  qoe_score          video_core.qoe_score(...)  (formula in the Day 0 contract)

    python experiments/video/parse_video_results.py results/video --output video_results.csv
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from video_core import qoe_score  # noqa: E402

OUT_COLUMNS = ["variant", "profile", "run", "startup_delay_s", "stall_count", "total_stall_s",
               "avg_bitrate_mbps", "quality_switches", "qoe_score"]
REQUIRED = ["run_id", "segment_index", "timestamp", "bitrate_mbps", "stall"]


def find_inputs(paths):
    files = []
    for p in map(Path, paths):
        if p.is_dir():
            files += sorted(p.rglob("segments*.csv"))
        elif p.is_file():
            files.append(p)
        else:
            raise FileNotFoundError(p)
    return files


def split_run_id(run_id):
    parts = str(run_id).split("__")
    if len(parts) == 3:
        return parts[0], parts[1], parts[2]
    print("WARNING: run_id %r does not look like variant__profile__run" % run_id, file=sys.stderr)
    return str(run_id), "unknown", "0"


def read_meta(csv_path, run_id):
    meta = Path(str(csv_path) + ".meta.json")
    if meta.is_file():
        m = json.loads(meta.read_text())
        if m.get("run_id") in (None, run_id):
            return m
    return {}


def summarize_run(g, startup_segments, meta):
    g = g.sort_values("segment_index")
    bitrate = g["bitrate_mbps"].astype(float).tolist()
    switches = sum(1 for a, b in zip(bitrate, bitrate[1:]) if a != b)
    if meta.get("startup_delay_s") is not None:
        startup = float(meta["startup_delay_s"])
    else:
        idx = min(startup_segments, len(g)) - 1
        startup = float(g["timestamp"].iloc[idx])
    stall_count = int(g["stall"].sum())
    if "stall_s" in g.columns:
        stall_s = float(g["stall_s"].sum())
    else:
        print("WARNING: no stall_s column; total_stall_s set to 0", file=sys.stderr)
        stall_s = 0.0
    avg = sum(bitrate) / len(bitrate)
    return dict(startup_delay_s=round(startup, 4), stall_count=stall_count,
                total_stall_s=round(stall_s, 4), avg_bitrate_mbps=round(avg, 4),
                quality_switches=switches,
                qoe_score=round(qoe_score(avg, stall_count, stall_s, switches), 4))


def parse_files(files, startup_segments=1):
    rows = []
    for f in files:
        meta_file = Path(str(f) + ".meta.json")
        if meta_file.is_file() and json.loads(meta_file.read_text()).get("completed") is False:
            print("WARNING: %s is from an INCOMPLETE run (meta completed=false); skipped" % f, file=sys.stderr)
            continue
        df = pd.read_csv(f)
        if df.empty:
            print("WARNING: %s has no segment rows; skipped" % f, file=sys.stderr)
            continue
        missing = [c for c in REQUIRED if c not in df.columns]
        if missing:
            raise ValueError("%s: missing column(s) %s" % (f, ", ".join(missing)))
        for run_id, g in df.groupby("run_id", sort=False):
            variant, profile, run = split_run_id(run_id)
            s = summarize_run(g, startup_segments, read_meta(f, run_id))
            rows.append(dict(variant=variant, profile=profile, run=run, **s))
    return pd.DataFrame(rows, columns=OUT_COLUMNS)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help="segment CSV files or directories")
    ap.add_argument("--output", required=True)
    ap.add_argument("--startup-segments", type=int, default=1,
                    help="segments needed before playback starts (only used when no .meta.json exists)")
    a = ap.parse_args(argv)
    try:
        files = find_inputs(a.inputs)
        if not files:
            print("No segments*.csv files found.", file=sys.stderr)
            return 1
        out = parse_files(files, a.startup_segments)
    except (FileNotFoundError, ValueError) as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 2
    out.to_csv(a.output, index=False)
    print("Wrote %s  (%d runs from %d file(s))" % (a.output, len(out), len(files)))
    return 0


if __name__ == "__main__":
    sys.exit(main())