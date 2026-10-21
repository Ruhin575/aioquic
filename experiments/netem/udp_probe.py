#!/usr/bin/env python3
"""
Two modes:
  sender  : send N packets to <host:port> at a fixed interval. Each payload
            carries (seq:uint32, send_ts_ns:int64, pad...).
  receiver: listen on <port> and record every arrival to <out.csv>. Each row
            is (seq, send_ts_ns, recv_ts_ns, arrival_index).

Analysis is intentionally kept out of this script so the receiver stays
cheap and never drops packets due to CPU work. Analysis is done after the
run by analyze_probe.py.
Clocks: both namespaces run on the same host kernel, so time.monotonic_ns()
is directly comparable between sender and receiver.
"""

from __future__ import annotations

import argparse
import csv
import signal
import socket
import struct
import sys
import time

PAYLOAD_FMT = "!IQ"                 # uint32 seq, int64 send_ts_ns (big-endian)
PAYLOAD_SIZE = struct.calcsize(PAYLOAD_FMT)
PADDING = 1200 - PAYLOAD_SIZE       # pad to typical LTE MTU-ish datagram


def run_sender(host: str, port: int, count: int, interval_s: float) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    pad = b"\x00" * PADDING
    next_send = time.monotonic()
    for seq in range(count):
        ts_ns = time.monotonic_ns()
        header = struct.pack(PAYLOAD_FMT, seq, ts_ns)
        sock.sendto(header + pad, (host, port))
        next_send += interval_s
        delay = next_send - time.monotonic()
        if delay > 0:
            time.sleep(delay)
    # Give the receiver a moment to catch stragglers before caller exits.
    time.sleep(0.5)
    sock.close()


def run_receiver(port: int, out_path: str, duration_s: float) -> None:
    stop = {"flag": False}

    def _handle(_signo, _frame):   # type: ignore[no-untyped-def]
        stop["flag"] = True

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
    except OSError:
        pass
    sock.bind(("0.0.0.0", port))
    sock.settimeout(0.5)

    arrival = 0
    try:
        with open(out_path, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["seq", "send_ns", "recv_ns", "arrival_index"])
            fh.flush()

            deadline = time.monotonic() + duration_s
            while not stop["flag"] and time.monotonic() < deadline:
                try:
                    data, _addr = sock.recvfrom(2048)
                except socket.timeout:
                    continue
                recv_ns = time.monotonic_ns()
                if len(data) < PAYLOAD_SIZE:
                    continue
                seq, send_ns = struct.unpack(PAYLOAD_FMT, data[:PAYLOAD_SIZE])
                w.writerow([seq, send_ns, recv_ns, arrival])
                arrival += 1
                if arrival % 100 == 0:
                    fh.flush()
            # Final flush is handled by `with` -> fh.close().
    finally:
        sock.close()
    print(f"[udp_probe receiver] wrote {arrival} rows to {out_path}",
          flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)

    s = sub.add_parser("sender")
    s.add_argument("host")
    s.add_argument("port", type=int)
    s.add_argument("--count", type=int, default=2000)
    s.add_argument("--interval", type=float, default=0.005)  # 5 ms -> 200 pps

    r = sub.add_parser("receiver")
    r.add_argument("port", type=int)
    r.add_argument("out")
    r.add_argument("--duration", type=float, default=30.0)

    args = ap.parse_args()
    if args.mode == "sender":
        run_sender(args.host, args.port, args.count, args.interval)
    elif args.mode == "receiver":
        run_receiver(args.port, args.out, args.duration)
    else:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
