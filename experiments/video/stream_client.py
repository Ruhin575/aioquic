#!/usr/bin/env python3
"""stream_client.py - DASH playback simulator over ONE persistent HTTP/3 (aioquic) connection.

Agreed command line (Day 0 interface block):

    python experiments/video/stream_client.py \
        --url https://10.10.2.2:4433/manifest.mpd --ca-certs experiments/transfer/ns-cert.pem \
        --run-id stock__moderate__1 --segments-out results/video/stock/moderate/run_1/segments.csv \
        --qlog-dir results/video/stock/moderate/run_1/client-qlog

What it does
  1. connects once (Cubic, like the rest of the experiments) and fetches the manifest,
  2. requests the 4 s segments one after another, choosing the bitrate with HarmonicABR
     (harmonic mean of the last 3 download throughputs x 0.8; first segment on the lowest rung),
  3. keeps a simulated playback buffer in real time (PlaybackBuffer): startup delay, stalls, stall seconds,
     and stops requesting while the buffer is full (--max-buffer-s, default 12 s as in dash.js),
  4. writes one CSV row per segment (video_core.ROW_COLUMNS) and a small <segments-out>.meta.json.

The ABR and buffer rules live in video_core.py and are unit-tested offline. Only audio is ignored.
Timing: t0 is taken before the connection is opened, so startup delay includes the QUIC handshake and
the manifest fetch. A segment's download time runs from sending the request to receiving the last byte.
"""
import argparse
import asyncio
import csv
import json
import ssl
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from aioquic.asyncio.client import connect
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.h3.connection import H3_ALPN, H3Connection
from aioquic.h3.events import DataReceived, HeadersReceived
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import ConnectionTerminated, QuicEvent
from aioquic.quic.logger import QuicFileLogger

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import video_core as vc  # noqa: E402


class H3Client(QuicConnectionProtocol):
    """Minimal HTTP/3 GET client (modelled on examples/http3_client.py)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._http = H3Connection(self._quic)
        self._events = {}
        self._waiters = {}

    async def get(self, authority, path):
        """Return (status, body_bytes) for GET https://authority/path."""
        stream_id = self._quic.get_next_available_stream_id()
        self._http.send_headers(
            stream_id=stream_id,
            headers=[(b":method", b"GET"), (b":scheme", b"https"),
                     (b":authority", authority.encode()), (b":path", ("/" + path.lstrip("/")).encode()),
                     (b"user-agent", b"stream_client")],
            end_stream=True)
        waiter = self._loop.create_future()
        self._events[stream_id] = []
        self._waiters[stream_id] = waiter
        self.transmit()
        events = await asyncio.shield(waiter)
        status, body = None, bytearray()
        for ev in events:
            if isinstance(ev, HeadersReceived):
                status = int(dict(ev.headers).get(b":status", b"0"))
            elif isinstance(ev, DataReceived):
                body += ev.data
        return status, bytes(body)

    def quic_event_received(self, event: QuicEvent) -> None:
        for h3 in self._http.handle_event(event):
            if isinstance(h3, (HeadersReceived, DataReceived)) and h3.stream_id in self._events:
                self._events[h3.stream_id].append(h3)
                if h3.stream_ended:
                    self._waiters.pop(h3.stream_id).set_result(self._events.pop(h3.stream_id))
        if isinstance(event, ConnectionTerminated):
            for w in self._waiters.values():
                if not w.done():
                    w.set_exception(ConnectionError("connection terminated: %s" % event.reason_phrase))
            self._events.clear()
            self._waiters.clear()


async def fetch(client, authority, path, timeout):
    status, body = await asyncio.wait_for(client.get(authority, path), timeout)
    if status != 200:
        raise RuntimeError("GET /%s returned HTTP %s" % (path.lstrip("/"), status))
    return body


async def run_session(client, authority, base_path, args, t0, rows):
    """Play the whole video. Appends one row per segment to `rows`; returns the session summary."""
    manifest_path = base_path.rsplit("/", 1)[-1] or "manifest.mpd"
    base_dir = base_path.rsplit("/", 1)[0].strip("/") if "/" in base_path.strip("/") else ""
    prefix = (base_dir + "/") if base_dir else ""
    manifest = vc.parse_mpd((await fetch(client, authority, prefix + manifest_path, args.request_timeout)).decode())
    reps = manifest.representations
    n = manifest.n_segments if args.max_segments is None else min(args.max_segments, manifest.n_segments)
    startup = args.startup_buffer_s if args.startup_buffer_s is not None else manifest.segment_durations[0]
    buf = vc.PlaybackBuffer(t0, startup, args.resume_buffer_s)
    abr = vc.HarmonicABR(window=args.abr_window, safety=args.safety, initial_index=args.initial_index)
    init_done, prev_stalls, prev_stall_s = set(), 0, 0.0

    for idx in range(n):
        seg_s = manifest.segment_durations[idx]
        buf.advance(time.monotonic())
        if buf.playing and buf.level + seg_s > args.max_buffer_s:          # buffer full: wait
            await asyncio.sleep(buf.level + seg_s - args.max_buffer_s)
        rep = abr.choose(reps)
        if rep.id not in init_done and not args.no_init:
            await fetch(client, authority, prefix + vc.init_path(rep), args.request_timeout)
            init_done.add(rep.id)
        t_req = time.monotonic()
        body = await fetch(client, authority, prefix + vc.segment_path(rep, idx), args.request_timeout)
        t_done = time.monotonic()
        dl = t_done - t_req
        abr.add_sample(len(body) * 8 / dl)
        buf.add_segment(t_done, seg_s)
        rows.append(dict(run_id=args.run_id, segment_index=idx, timestamp=round(t_done - t0, 4),
                         bitrate_mbps=rep.bandwidth / 1e6, download_time_s=round(dl, 4),
                         buffer_level_s=round(buf.level, 4), stall=buf.stall_count - prev_stalls,
                         stall_s=round(buf.total_stall_s - prev_stall_s, 4)))
        prev_stalls, prev_stall_s = buf.stall_count, buf.total_stall_s
        print("seg %3d  rung %5.2f Mbps  dl %.2fs  %.2f Mbps  buffer %.1fs%s" % (
            idx, rep.bandwidth / 1e6, dl, len(body) * 8 / dl / 1e6, buf.level,
            "  STALL" if rows[-1]["stall"] else ""), flush=True)

    buf.mark_all_downloaded(time.monotonic())
    if rows and (buf.stall_count > prev_stalls or buf.total_stall_s > prev_stall_s):
        rows[-1]["stall"] += buf.stall_count - prev_stalls
        rows[-1]["stall_s"] = round(rows[-1]["stall_s"] + buf.total_stall_s - prev_stall_s, 4)
    return dict(run_id=args.run_id, startup_delay_s=buf.startup_delay, stall_count=buf.stall_count,
                total_stall_s=round(buf.total_stall_s, 4), n_segments=n,
                video_duration_s=sum(manifest.segment_durations[:n]),
                ladder_mbps=[r.bandwidth / 1e6 for r in reps])


def write_outputs(args, rows, summary, completed, t0):
    out = Path(args.segments_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=vc.ROW_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    meta = dict(summary or {}, run_id=args.run_id, completed=completed,
                wall_time_s=round(time.monotonic() - t0, 3),
                params=dict(url=args.url, max_buffer_s=args.max_buffer_s, abr_window=args.abr_window,
                            safety=args.safety, initial_index=args.initial_index,
                            startup_buffer_s=args.startup_buffer_s, resume_buffer_s=args.resume_buffer_s,
                            congestion_control=args.congestion_control_algorithm))
    Path(str(out) + ".meta.json").write_text(json.dumps(meta, indent=2))


async def main(args):
    t0 = time.monotonic()
    cfg = QuicConfiguration(is_client=True, alpn_protocols=H3_ALPN,
                            congestion_control_algorithm=args.congestion_control_algorithm,
                            idle_timeout=args.idle_timeout)
    if args.ca_certs:
        cfg.load_verify_locations(args.ca_certs)
    if args.insecure:
        cfg.verify_mode = ssl.CERT_NONE
    if args.qlog_dir:
        Path(args.qlog_dir).mkdir(parents=True, exist_ok=True)
        cfg.quic_logger = QuicFileLogger(args.qlog_dir)
    u = urlparse(args.url)
    host, port = u.hostname, u.port or 443
    rows, summary, completed = [], None, False
    try:
        async with connect(host, port, configuration=cfg, create_protocol=H3Client) as client:
            summary = await run_session(client, u.netloc, u.path or "/manifest.mpd", args, t0, rows)
            completed = True
            client.close()
    finally:
        write_outputs(args, rows, summary, completed, t0)      # partial runs still leave a (flagged) file
    print("startup %.2fs | stalls %d (%.1fs) | %d segments | wrote %s" % (
        summary["startup_delay_s"], summary["stall_count"], summary["total_stall_s"],
        len(rows), args.segments_out))


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True, help="https://host:port/manifest.mpd")
    ap.add_argument("--ca-certs", help="CA / self-signed certificate to trust")
    ap.add_argument("--insecure", action="store_true", help="do not verify the server certificate")
    ap.add_argument("--run-id", required=True, help="variant__profile__run, e.g. stock__moderate__1")
    ap.add_argument("--segments-out", required=True, help="per-segment CSV to write")
    ap.add_argument("--qlog-dir", help="write the client's qlog here")
    ap.add_argument("--max-segments", type=int, help="stop after N segments (testing)")
    ap.add_argument("--max-buffer-s", type=float, default=12.0,
                    help="stop requesting while the buffer is this full. Default 12 s = dash.js stableBufferTime "
                         "(its buffer target while not at top quality). FIXED for all final runs: changing it "
                         "means rerunning every variant")
    ap.add_argument("--startup-buffer-s", type=float, default=None, help="default: one segment")
    ap.add_argument("--resume-buffer-s", type=float, default=None, help="default: same as startup")
    ap.add_argument("--abr-window", type=int, default=3)
    ap.add_argument("--safety", type=float, default=0.8)
    ap.add_argument("--initial-index", type=int, default=0, help="rung of the first segment (0 = lowest)")
    ap.add_argument("--no-init", action="store_true", help="do not fetch init segments")
    ap.add_argument("--request-timeout", type=float, default=60.0, help="give up on one HTTP request after this long")
    ap.add_argument("--idle-timeout", type=float, default=30.0,
                    help="QUIC idle timeout; also how long an unreachable server is waited for")
    ap.add_argument("--congestion-control-algorithm", default="cubic")
    return ap.parse_args(argv)


if __name__ == "__main__":
    try:
        asyncio.run(main(parse_args()))
    except (ConnectionError, RuntimeError, asyncio.TimeoutError) as e:
        print("ERROR: %s: %s" % (type(e).__name__, str(e) or "no response (server unreachable or request timed out)"),
              file=sys.stderr)
        sys.exit(1)