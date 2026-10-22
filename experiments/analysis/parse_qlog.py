#!/usr/bin/env python3
"""parse_qlog.py - turn an aioquic qlog file into one tidy CSV.

Usage (CLI):
    python parse_qlog.py --input server.qlog --output parsed.csv
    python parse_qlog.py --input experiments/transfer/server-qlog/stock/moderate/1 --output parsed.csv

Usage (module):
    from parse_qlog import parse_file
    df = parse_file("server.qlog")

Output columns (one row per event, `event_type` says what the row is):
    event_type      sent | acked | lost | metrics
    time_s          seconds since the first event in the file
    packet_number   (sent / acked / lost)
    pn_space        initial | handshake | application (0-RTT and 1-RTT share it) | unknown
    size            bytes of the whole QUIC packet (sent)
    ack_delay       as logged in the ACK frame (acked)
    cwnd, bytes_in_flight, ssthresh, latest_rtt, smoothed_rtt, min_rtt   (metrics)

Format facts CONFIRMED from aioquic src/aioquic/quic/logger.py + recovery.py:
  * one file per connection, named <ODCID>.qlog; events are dicts
    {"name": "category:event", "time": <absolute wall-clock ms>, "data": {...}}
  * ACK ranges are inclusive [start, end]
  * recovery:packet_lost data = {"type": "1RTT", "packet_number": N}
  * recovery:metrics_updated data = cwnd, bytes_in_flight, ssthresh (only when set),
    cubic-wmax; RTT fields only on some events -> parser forward-fills

Notes / assumptions:
  * Analyse the SENDER's qlog (the server, for a download).
  * "acked" rows come from ACK frames inside packet_received events. aioquic
    drops a packet's record once it is declared lost, so a late ACK would not
    show up as a packet_acked event - reading raw ACK ranges avoids that.
  * Each ACK frame repeats old ranges, so each packet number is emitted as
    "acked" only the FIRST time it appears in any ACK frame.
  * Anything unparseable is counted and reported on stderr, never skipped silently.
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

METRIC_FIELDS = ["cwnd", "bytes_in_flight", "ssthresh",
                 "latest_rtt", "smoothed_rtt", "min_rtt"]
COLUMNS = (["event_type", "time_s", "packet_number", "pn_space", "size",
            "ack_delay"] + METRIC_FIELDS)
APP_SPACE = "application"      # 0-RTT and 1-RTT packets share this packet-number space
DEFAULT_SPACE = APP_SPACE


def _warn(msg):
    print("WARNING: " + msg, file=sys.stderr)


# --------------------------------------------------------------------------
# Loading: returns a list of (time_ms, event_name, data_dict)
# --------------------------------------------------------------------------
def _norm_event(ev, fields):
    """Normalise one event in any of the qlog shapes we may meet (None = unusable)."""
    if isinstance(ev, dict):
        name = ev.get("name")
        if not name:
            name = "%s:%s" % (ev.get("category", ""), ev.get("event_type", ev.get("event", "")))
        return float(ev.get("time", 0.0)), name, ev.get("data") or {}
    if isinstance(ev, list):
        if fields:                                   # draft-02 style: event_fields header
            d = dict(zip(fields, ev))
            t = d.get("relative_time", d.get("time", 0.0))
            name = "%s:%s" % (d.get("category", ""), d.get("event_type", d.get("event", "")))
            return float(t), name, d.get("data") or {}
        if len(ev) >= 4:                             # [time, category, event, data]
            return float(ev[0]), "%s:%s" % (ev[1], ev[2]), ev[3] or {}
    return None


def _events_from_doc(doc):
    """Return (events, number_of_unusable_events)."""
    out, skipped = [], 0
    for trace in doc.get("traces") or [doc]:
        fields = trace.get("event_fields")
        for ev in trace.get("events", []):
            n = _norm_event(ev, fields)
            if n:
                out.append(n)
            else:
                skipped += 1
    return out, skipped


def load_events(path):
    """Load a .qlog (JSON) or .sqlog (JSON-SEQ / one JSON object per line)."""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    try:
        events, skipped = _events_from_doc(json.loads(text))
    except json.JSONDecodeError:
        events, skipped = [], 0
        for line in text.splitlines():
            line = line.strip().lstrip("\x1e")
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue
            if "traces" in obj or "events" in obj:
                e, s = _events_from_doc(obj)
                events.extend(e)
                skipped += s
            else:
                n = _norm_event(obj, None)
                if n:
                    events.append(n)
                else:
                    skipped += 1
    if skipped:
        _warn("%s: %d event(s)/line(s) could not be parsed and were skipped" % (path, skipped))
    return events


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------
def normalize_space(packet_type):
    """Map a qlog packet type to its packet-number space.
    initial -> initial, handshake -> handshake, 0RTT/1RTT -> application.
    A missing type gives "unknown" rather than guessing, so it can never be
    silently matched against application-space packets."""
    if not packet_type:
        return "unknown"
    t = str(packet_type).lower()
    return APP_SPACE if t in ("0rtt", "1rtt") else t


def _pn_and_space(data):
    """packet_sent / packet_received keep these in data["header"]; aioquic's
    recovery:packet_lost keeps them directly in data as "type" and "packet_number"."""
    header = data.get("header") or {}
    pn = header.get("packet_number", data.get("packet_number"))
    ptype = header.get("packet_type") or data.get("packet_type") or data.get("type")
    return pn, normalize_space(ptype)


def parse_events(events, ranges_exclusive=False):
    """events: list of (time_ms, name, data). Returns a DataFrame."""
    events = sorted(events, key=lambda e: e[0])
    if not events:
        return pd.DataFrame(columns=COLUMNS)
    t0 = events[0][0]
    rows = []
    seen_acked = {}                                  # space -> set of packet numbers
    floor = {}                                       # space -> every pn below this was already seen

    for t_ms, name, data in events:
        t = (t_ms - t0) / 1000.0
        short = name.split(":")[-1]

        if short == "packet_sent":
            pn, space = _pn_and_space(data)
            raw = data.get("raw") or {}
            size = raw.get("length", data.get("packet_size"))
            rows.append(dict(event_type="sent", time_s=t, packet_number=pn,
                             pn_space=space, size=size))

        elif short == "packet_received":
            _, space = _pn_and_space(data)           # an ACK acknowledges its own packet-number space
            seen = seen_acked.setdefault(space, set())
            lo = floor.get(space, 0)
            for fr in data.get("frames") or []:
                if str(fr.get("frame_type", "")).lower() != "ack":
                    continue
                delay = fr.get("ack_delay")
                for a, b in fr.get("acked_ranges") or []:
                    last = b - 1 if ranges_exclusive else b
                    for pn in range(max(int(a), lo), int(last) + 1):
                        if pn not in seen:
                            seen.add(pn)
                            rows.append(dict(event_type="acked", time_s=t,
                                             packet_number=pn, pn_space=space,
                                             ack_delay=delay))
            while lo in seen:                        # advance the floor
                lo += 1
            floor[space] = lo

        elif short == "packet_lost":
            pn, space = _pn_and_space(data)
            rows.append(dict(event_type="lost", time_s=t, packet_number=pn,
                             pn_space=space))

        elif short == "metrics_updated":
            row = dict(event_type="metrics", time_s=t)
            for k in METRIC_FIELDS:
                if k in data:
                    row[k] = data[k]
            rows.append(row)

    df = pd.DataFrame(rows)
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = pd.NA
    df = df[COLUMNS].sort_values("time_s", kind="stable").reset_index(drop=True)

    # aioquic logs only the metrics that changed, so carry values forward.
    m = df["event_type"] == "metrics"
    for k in METRIC_FIELDS:
        df[k] = pd.to_numeric(df[k], errors="coerce")
    df.loc[m, METRIC_FIELDS] = df.loc[m, METRIC_FIELDS].ffill()
    return df


def find_qlog(path, strict=False):
    """Accept a .qlog file OR a run directory (as written by run_transfer.py).

    A run directory should hold exactly one data connection. If it holds several,
    strict=True raises (the caller must choose); otherwise the largest is used
    and a warning names the files."""
    p = Path(path)
    if not p.is_dir():
        return str(p)
    files = sorted(p.glob("*.qlog"), key=lambda f: f.stat().st_size, reverse=True)
    if not files:
        raise FileNotFoundError("no .qlog files in %s" % path)
    if len(files) > 1:
        msg = "%d qlog files in %s: %s" % (len(files), path, ", ".join(f.name for f in files))
        if strict:
            raise ValueError(msg + " - ambiguous, pass one file explicitly")
        _warn(msg + " - using the largest (%s)" % files[0].name)
    return str(files[0])


def parse_file(path, ranges_exclusive=False, strict=False):
    return parse_events(load_events(find_qlog(path, strict=strict)),
                        ranges_exclusive=ranges_exclusive)


def summarize(df):
    counts = df["event_type"].value_counts().to_dict()
    return {k: int(counts.get(k, 0)) for k in ("sent", "acked", "lost", "metrics")}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Parse an aioquic qlog into a tidy CSV.")
    ap.add_argument("--input", required=True,
                    help="a .qlog file, or a run directory containing .qlog files")
    ap.add_argument("--output", required=True, help="path of CSV to write")
    ap.add_argument("--ranges-exclusive", action="store_true",
                    help="ACK ranges are half-open, i.e. the END value is NOT acknowledged. "
                         "Default (and what aioquic writes): closed ranges, END is acknowledged.")
    ap.add_argument("--strict", action="store_true",
                    help="fail if a run directory holds more than one .qlog file")
    args = ap.parse_args(argv)

    try:
        df = parse_file(args.input, ranges_exclusive=args.ranges_exclusive, strict=args.strict)
    except (FileNotFoundError, ValueError) as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 2
    if df.empty:
        print("No events found - check QLOG_FINDINGS.md / the file format.", file=sys.stderr)
        return 1
    m = df[df["event_type"] == "metrics"]
    if m["cwnd"].dropna().empty:
        _warn("no numeric cwnd values found - cwnd plots and cwnd metrics will be unavailable")
    df.to_csv(args.output, index=False)
    print("Wrote %s  rows=%d  %s" % (args.output, len(df), summarize(df)))
    return 0


if __name__ == "__main__":
    sys.exit(main())