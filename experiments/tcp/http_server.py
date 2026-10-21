#!/usr/bin/env python3
"""
http_server.py - minimal HTTP/1.1 server for the TCP baseline.

Serves the test files from a given directory with `Content-Length` and
`Connection: close` (no HTTP/2, no HTTP/3, no TLS). This isolates the TCP
baseline from any HTTP-layer effects: we are comparing kernel TCP against
Python aioquic over the same netem profiles.

  python3 http_server.py --dir ../transfer/testfiles --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import argparse
import http.server
import os
import socketserver
import sys


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler, but silent and HTTP/1.1 with Connection: close."""

    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        # Silence per-request logging; run_matrix_tcp.py prints its own rows.
        return

    def end_headers(self) -> None:
        # Force connection close so curl's TCP close coincides with end of body.
        self.send_header("Connection", "close")
        super().end_headers()


class ReusableTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="directory to serve")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()

    if not os.path.isdir(args.dir):
        print(f"not a directory: {args.dir}", file=sys.stderr)
        return 2
    os.chdir(args.dir)

    with ReusableTCPServer((args.host, args.port), QuietHandler) as srv:
        print(f"[http_server] serving {args.dir} on {args.host}:{args.port}",
              flush=True)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
