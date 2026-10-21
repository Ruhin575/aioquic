#!/usr/bin/env python3
"""
run_matrix_tcp.py — TCP baseline matrix runner.

Walks the frozen experiment matrix for the kernel-TCP baseline:
    file_size   = 10 MB (main) or 50 MB (validation)
    profiles    = baseline, mild, moderate, severe, handover
    runs        = 5 (main) or 3 (validation)
    variant     = "tcp"
  sudo python3 run_matrix_tcp.py --stage main --output results/tcp.csv \\
       --testfiles ../transfer/testfiles
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
NETEM = HERE.parent / "netem"
SETUP = NETEM / "setup.sh"
TEARDOWN = NETEM / "teardown.sh"
HTTP_SERVER = HERE / "http_server.py"

# File-size map (bytes-on-disk is what matters for goodput).
FILE_SIZES = {
    "10MB": "10mb.bin",
    "50MB": "50mb.bin",
}

STAGES = {
    "main":       {"sizes": ["10MB"],         "profiles": ["baseline", "mild", "moderate", "severe", "handover"], "runs": 5},
    "validation": {"sizes": ["50MB"],         "profiles": ["baseline", "severe"],                                 "runs": 3},
    "smoke":      {"sizes": ["10MB"],         "profiles": ["baseline"],                                           "runs": 1},
}


def need_root() -> None:
    if os.geteuid() != 0:
        sys.exit("Needs root (CAP_NET_ADMIN). Re-run with sudo.")


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def wait_for_port(ns: str, host: str, port: int, timeout_s: float = 5.0) -> bool:
    """Poll a TCP port from inside a namespace until it is accepting."""
    deadline = time.monotonic() + timeout_s
    probe = f"import socket,sys;s=socket.socket();s.settimeout(0.3);s.connect(('{host}',{port}));s.close()"
    while time.monotonic() < deadline:
        rc = subprocess.run(
            ["ip", "netns", "exec", ns, "python3", "-c", probe],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode
        if rc == 0:
            return True
        time.sleep(0.1)
    return False


def start_server(ns: str, serve_dir: Path, host: str, port: int) -> subprocess.Popen:
    return subprocess.Popen(
        ["ip", "netns", "exec", ns,
         "python3", str(HTTP_SERVER),
         "--dir", str(serve_dir), "--host", host, "--port", str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def stop_server(proc: subprocess.Popen) -> None:
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except Exception:
        proc.kill()


def apply_profile(profile: str, dl_if: str, ul_if: str, router_ns: str) -> None:
    cmd = ["bash", str(SETUP), profile, dl_if, ul_if]
    if router_ns:
        cmd.append(router_ns)
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)


def clear_profile(dl_if: str, ul_if: str, router_ns: str) -> None:
    cmd = ["bash", str(TEARDOWN), dl_if, ul_if]
    if router_ns:
        cmd.append(router_ns)
    subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL)


def curl_download(ns: str, url: str, out_path: Path) -> float:
    """Run curl in the client namespace. Return wall time in seconds.

    We measure wall time around curl ourselves rather than trusting curl's
    own `-w %{time_total}` because the latter does not include process
    startup. For an apples-to-apples comparison with the aioquic client the
    team also wraps with wall time, so both include equal overhead.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # -s silent, -S show errors, -o output file, -f fail on 4xx/5xx,
    # --http1.1 pin, --max-time safety net.
    cmd = ["ip", "netns", "exec", ns,
           "curl", "-sS", "-f", "--http1.1", "--max-time", "600",
           "-o", str(out_path), url]
    t0 = time.monotonic()
    subprocess.run(cmd, check=True)
    return time.monotonic() - t0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=sorted(STAGES.keys()), required=True)
    ap.add_argument("--output", required=True, help="CSV output path")
    ap.add_argument("--testfiles", required=True,
                    help="directory holding 10mb.bin and 50mb.bin")
    ap.add_argument("--client-ns", default="ns-client")
    ap.add_argument("--server-ns", default="ns-server")
    ap.add_argument("--server-ip", default="10.0.2.2")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--dl-if", default=os.environ.get("DL_IF", ""))
    ap.add_argument("--ul-if", default=os.environ.get("UL_IF", ""))
    ap.add_argument("--router-ns", default=os.environ.get("ROUTER_NS", "ns-router"),
                    help="network namespace that owns DL_IF/UL_IF (default: ns-router)")
    ap.add_argument("--download-dir", default="/tmp/tcp-baseline-downloads")
    ap.add_argument("--dry-run", action="store_true",
                    help="print what would run, do not touch tc or the net")
    args = ap.parse_args()

    if not args.dl_if or not args.ul_if:
        sys.exit("--dl-if and --ul-if are required (or export DL_IF / UL_IF)")

    testfiles = Path(args.testfiles).resolve()
    if not args.dry_run:
        need_root()
        for size in STAGES[args.stage]["sizes"]:
            fp = testfiles / FILE_SIZES[size]
            if not fp.is_file():
                sys.exit(f"missing test file: {fp}")

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    download_dir = Path(args.download_dir)
    if download_dir.exists():
        shutil.rmtree(download_dir)

    stage = STAGES[args.stage]
    writer_header_written = output.exists() and output.stat().st_size > 0
    with open(output, "a", newline="") as fh:
        writer = csv.writer(fh)
        if not writer_header_written:
            writer.writerow([
                "variant", "profile", "file_size", "run",
                "download_time_s", "goodput_mbps", "sha256_ok", "qlog_path",
            ])
            fh.flush()

        for size in stage["sizes"]:
            filename = FILE_SIZES[size]
            local_src = testfiles / filename
            expected_sha = (
                sha256_of_file(local_src) if not args.dry_run else "DRYRUN"
            )
            file_bytes = local_src.stat().st_size if not args.dry_run else 0

            for profile in stage["profiles"]:
                for run in range(1, stage["runs"] + 1):
                    tag = f"[tcp {profile} {size} run={run}]"
                    print(tag, "start", flush=True)

                    if args.dry_run:
                        print(tag, "would apply profile + fetch", filename)
                        continue

                    try:
                        apply_profile(profile, args.dl_if, args.ul_if, args.router_ns)

                        server = start_server(
                            args.server_ns, testfiles,
                            "0.0.0.0", args.port,
                        )
                        try:
                            if not wait_for_port(
                                args.client_ns, args.server_ip, args.port,
                            ):
                                raise RuntimeError("server port never came up")

                            url = f"http://{args.server_ip}:{args.port}/{filename}"
                            out = download_dir / profile / f"run{run}" / filename
                            dt = curl_download(args.client_ns, url, out)
                        finally:
                            stop_server(server)

                        got_sha = sha256_of_file(out)
                        ok = got_sha == expected_sha
                        goodput = (file_bytes * 8) / dt / 1e6 if dt > 0 else 0.0

                        writer.writerow([
                            "tcp", profile, size, run,
                            f"{dt:.3f}", f"{goodput:.3f}",
                            "1" if ok else "0", "n/a",
                        ])
                        fh.flush()
                        print(tag, f"ok dt={dt:.2f}s gp={goodput:.2f}Mbit/s sha_ok={ok}")

                    except Exception as exc:  # noqa: BLE001
                        # Keep going on individual failures - robustness (3h).
                        print(tag, "FAILED:", exc, file=sys.stderr)
                        writer.writerow([
                            "tcp", profile, size, run,
                            "", "", "0", "n/a",
                        ])
                        fh.flush()
                    finally:
                        clear_profile(args.dl_if, args.ul_if, args.router_ns)

    print("wrote", output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
