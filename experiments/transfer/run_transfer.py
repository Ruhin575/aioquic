#!/usr/bin/env python3
"""Run one HTTP/3 file transfer and save its results and qlogs."""

import argparse
import csv
import hashlib
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRANSFER_DIR = ROOT / "experiments" / "transfer"
SERVER_URL = "https://10.10.2.2:4433"
PYTHON = sys.executable

CSV_COLUMNS = [
    "variant",
    "profile",
    "threshold",
    "file_size",
    "run",
    "download_time_s",
    "goodput_mbps",
    "sha256_ok",
    "congestion_control",
    "qlog_path",
]


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for data in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(data)
    return digest.hexdigest()


def start_server(threshold, qlog_dir):
    command = [
        "sudo", "ip", "netns", "exec", "ns-server", "env",
    ]

    if threshold is None:
        command.extend(["-u", "AIOQUIC_PACKET_THRESHOLD"])
    else:
        if threshold <= 0:
            raise ValueError("Packet threshold must be positive")
        command.append(f"AIOQUIC_PACKET_THRESHOLD={threshold}")

    command.append(f"STATIC_ROOT={TRANSFER_DIR / 'www'}")
    qlog_dir.mkdir(parents=True, exist_ok=True)

    command.extend([
        PYTHON,
        str(ROOT / "examples" / "http3_server.py"),
        "--host", "10.10.2.2",
        "--port", "4433",
        "--certificate", str(TRANSFER_DIR / "ns-cert.pem"),
        "--private-key", str(TRANSFER_DIR / "ns-key.pem"),
        "--quic-log", str(qlog_dir),
        "--congestion-control-algorithm", "cubic",
    ])

    log_file = open(TRANSFER_DIR / "server.log", "a")
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        for _ in range(50):
            if process.poll() is not None:
                raise RuntimeError(
                    "HTTP/3 server exited during startup. "
                    "Check experiments/transfer/server.log"
                )

            check = subprocess.run(
                [
                    "sudo", "ip", "netns", "exec", "ns-server",
                    "ss", "-lun",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            if check.returncode == 0 and "10.10.2.2:4433" in check.stdout:
                return process, log_file

            time.sleep(0.2)

        raise RuntimeError(
            "HTTP/3 server did not become ready. "
            "Check experiments/transfer/server.log"
        )
    except Exception:
        stop_server(process, log_file)
        raise


def stop_server(process, log_file):
    if process is not None:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    if log_file is not None and not log_file.closed:
        log_file.close()


def run_client(file_name, download_dir, qlog_dir, threshold):
    download_dir.mkdir(parents=True, exist_ok=True)
    qlog_dir.mkdir(parents=True, exist_ok=True)

    command = ["sudo", "ip", "netns", "exec", "ns-client"]

    if threshold is None:
        command.extend(["env", "-u", "AIOQUIC_PACKET_THRESHOLD"])
    else:
        command.extend(["env", f"AIOQUIC_PACKET_THRESHOLD={threshold}"])

    command.extend([
        PYTHON,
        str(ROOT / "examples" / "http3_client.py"),
        "--ca-certs", str(TRANSFER_DIR / "ns-cert.pem"),
        "--output-dir", str(download_dir),
        "--quic-log", str(qlog_dir),
        "--congestion-control-algorithm", "cubic",
        f"{SERVER_URL}/{file_name}",
    ])

    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(
            f"HTTP/3 client failed with exit code {result.returncode}"
        )

    print(result.stderr)
    match = re.search(
        r"Response received for .*?: (\d+) bytes in ([\d.]+) s",
        result.stderr,
    )
    if match is None:
        raise RuntimeError("Could not extract transfer details from client log")

    transferred_bytes = int(match.group(1))
    download_time = float(match.group(2))

    if download_time <= 0:
        raise RuntimeError("Transfer duration must be positive")

    return transferred_bytes, download_time


def wait_for_server_qlog(qlog_dir, timeout=15.0):
    """Wait for server qlogs to appear and stop changing."""
    deadline = time.time() + timeout
    last_size = None
    stable_checks = 0

    while time.time() < deadline:
        files = list(qlog_dir.glob("*.qlog"))
        size = sum(f.stat().st_size for f in files)

        if files and size > 0 and size == last_size:
            stable_checks += 1
            if stable_checks >= 2:
                return True
        else:
            stable_checks = 0

        last_size = size
        time.sleep(0.5)

    print(
        f"WARNING: server qlogs were not confirmed complete in {qlog_dir}",
        file=sys.stderr,
    )
    return False


def save_result(results_file, row):
    """Append a result and preserve older rows when upgrading the CSV schema."""
    results_file = Path(results_file)
    results_file.parent.mkdir(parents=True, exist_ok=True)

    existing_rows = []
    old_columns = []

    if results_file.exists() and results_file.stat().st_size > 0:
        with results_file.open(newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            old_columns = reader.fieldnames or []
            existing_rows = list(reader)

    # Rewrite the CSV if its header differs from the current schema.
    if old_columns != CSV_COLUMNS:
        temp_file = results_file.with_suffix(results_file.suffix + ".tmp")
        with temp_file.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for old_row in existing_rows:
                migrated = {
                    column: old_row.get(column, "")
                    for column in CSV_COLUMNS
                }
                writer.writerow(migrated)
            writer.writerow(row)
        os.replace(temp_file, results_file)
        return

    # Existing CSV already has the current header; append one row.
    if not results_file.exists() or results_file.stat().st_size == 0:
        with results_file.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerow(row)
    else:
        with results_file.open("a", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
            writer.writerow(row)

def run_transfer(file_name, variant, profile, run_number,
                 threshold=None, output_dir=None, results_file=None):
    output_dir = Path(output_dir or (ROOT / "experiments" / "results")).resolve()
    results_file = Path(results_file).resolve() if results_file else output_dir / "transfers.csv"

    # Required layout: output_dir/variant/profile/run_N/
    run_dir = output_dir / variant / profile / f"run_{run_number}"
    client_qlog_dir = run_dir / "client-qlog"
    server_qlog_dir = run_dir / "server-qlog"
    download_dir = run_dir / "download"

    downloaded_file = download_dir / file_name
    source_file = TRANSFER_DIR / "www" / file_name

    process = None
    log_file = None

    try:
        process, log_file = start_server(threshold, server_qlog_dir)

        transferred_bytes, download_time = run_client(
            file_name, download_dir, client_qlog_dir, threshold
        )

        if not downloaded_file.is_file():
            raise RuntimeError(f"Downloaded file not found: {downloaded_file}")

        source_hash = sha256_file(source_file)
        downloaded_hash = sha256_file(downloaded_file)
        if source_hash != downloaded_hash:
            raise RuntimeError("SHA-256 mismatch: downloaded file differs from source")

        actual_size = downloaded_file.stat().st_size
        if transferred_bytes != actual_size:
            raise RuntimeError(
                f"Size mismatch: client reported {transferred_bytes} bytes, "
                f"downloaded file has {actual_size} bytes"
            )

        goodput_mbps = transferred_bytes * 8 / download_time / 1_000_000

        # Allow the server's QUIC connection to finish and write its qlog
        # before terminating the server.
        server_qlog_saved = wait_for_server_qlog(
            server_qlog_dir, timeout=15.0
        )

        stop_server(process, log_file)
        process = None
        log_file = None

        if not server_qlog_saved:
            print(
                "WARNING: Server qlog was not saved before server shutdown.",
                file=sys.stderr,
            )

        row = {
            "variant": variant,
            "profile": profile,
            "threshold": threshold if threshold is not None else "",
            "file_size": actual_size,
            "run": run_number,
            "download_time_s": f"{download_time:.6f}",
            "goodput_mbps": f"{goodput_mbps:.3f}",
            "sha256_ok": True,
            "congestion_control": "cubic",
            "qlog_path": str(run_dir),
        }

        save_result(results_file, row)
        print("Saved result:", row)

    finally:
        stop_server(process, log_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run one HTTP/3 file transfer.")
    parser.add_argument("--file", default="1MB.bin")
    parser.add_argument("--variant", default="stock")
    parser.add_argument("--profile", default="baseline")
    parser.add_argument("--run", type=int, default=1)
    parser.add_argument("--threshold", type=int, default=None)
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "experiments" / "results"),
        help="Directory for per-run results and qlogs",
    )
    parser.add_argument("--results-file", help="Exact CSV file to append results to")
    args = parser.parse_args()

    if args.run < 1:
        parser.error("--run must be at least 1")
    if args.threshold is not None and args.threshold <= 0:
        parser.error("--threshold must be positive")

    run_transfer(
        file_name=args.file,
        variant=args.variant,
        profile=args.profile,
        run_number=args.run,
        threshold=args.threshold,
        output_dir=args.output_dir,
        results_file=args.results_file,
    )
