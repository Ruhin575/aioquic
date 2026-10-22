
import csv
import hashlib
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRANSFER_DIR = ROOT / "experiments" / "transfer"
RESULTS_FILE = ROOT / "experiments" / "results" / "transfers.csv"

SERVER_URL = "https://10.10.2.2:4433"
PYTHON = sys.executable

CSV_COLUMNS = [
    "variant",
    "profile",
    "file_size",
    "run",
    "download_time_s",
    "goodput_mbps",
    "sha256_ok",
    "qlog_path",
]


def sha256_file(path):
    digest = hashlib.sha256()

    with open(path, "rb") as file:
        while True:
            data = file.read(1024 * 1024)

            if not data:
                break

            digest.update(data)

    return digest.hexdigest()



def start_server(threshold=None, qlog_dir=None):
    command = [
        "sudo", "ip", "netns", "exec", "ns-server",
        "env",
    ]

    if threshold is None:
        command.extend(["-u", "AIOQUIC_PACKET_THRESHOLD"])
    else:
        if threshold < 0:
            raise ValueError("Packet threshold must be non-negative")
        command.append(f"AIOQUIC_PACKET_THRESHOLD={threshold}")

    command.append(f"STATIC_ROOT={TRANSFER_DIR / 'www'}")

    # Use a separate server qlog directory for each experiment run.
    server_qlog_dir = qlog_dir or (TRANSFER_DIR / "server-qlog")
    server_qlog_dir.mkdir(parents=True, exist_ok=True)

    command.extend([
        PYTHON,
        str(ROOT / "examples" / "http3_server.py"),
        "--host", "10.10.2.2",
        "--port", "4433",
        "--certificate", str(TRANSFER_DIR / "ns-cert.pem"),
        "--private-key", str(TRANSFER_DIR / "ns-key.pem"),
        "--quic-log", str(server_qlog_dir),
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
            )

            if "10.10.2.2:4433" in check.stdout:
                return process, log_file

            time.sleep(0.2)

        raise RuntimeError(
            "HTTP/3 server did not become ready. "
            "Check experiments/transfer/server.log"
        )

    except Exception:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

        log_file.close()
        raise



def run_client(file_name, output_dir, qlog_dir, threshold=None):
    output_dir.mkdir(parents=True, exist_ok=True)
    qlog_dir.mkdir(parents=True, exist_ok=True)

    command = [
        "sudo", "ip", "netns", "exec", "ns-client",
    ]

    if threshold is None:
        command.extend(["env", "-u", "AIOQUIC_PACKET_THRESHOLD"])
    else:
        command.extend([
            "env",
            f"AIOQUIC_PACKET_THRESHOLD={threshold}",
        ])

    command.extend([
        PYTHON,
        str(ROOT / "examples" / "http3_client.py"),
        "--ca-certs", str(TRANSFER_DIR / "ns-cert.pem"),
        "--output-dir", str(output_dir),
        "--quic-log", str(qlog_dir),
        "--congestion-control-algorithm", "cubic",
        f"{SERVER_URL}/{file_name}",
    ])

    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        raise RuntimeError("HTTP/3 transfer failed")

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


def save_result(row):
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    file_exists = RESULTS_FILE.exists() and RESULTS_FILE.stat().st_size > 0

    with open(RESULTS_FILE, "a", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)

        if not file_exists:
            writer.writeheader()

        writer.writerow(row)


def wait_for_server_qlog(server_qlog_dir, timeout=15.0):
    """Wait for the server qlog to appear and stop growing."""
    deadline = time.time() + timeout
    last_size = -1

    while time.time() < deadline:
        files = list(server_qlog_dir.glob("*.qlog"))

        if files:
            size = sum(f.stat().st_size for f in files)

            if size > 0 and size == last_size:
                return True

            last_size = size

        time.sleep(0.5)

    print(
        f"WARNING: no complete server qlog appeared in "
        f"{server_qlog_dir} within {timeout}s",
        flush=True,
    )
    return False

def run_transfer(file_name, variant, profile, run_number, threshold=None):
    output_dir = TRANSFER_DIR / "downloaded" / variant / profile / str(run_number)
    qlog_dir = TRANSFER_DIR / "client-qlog" / variant / profile / str(run_number)
    server_qlog_dir = TRANSFER_DIR / "server-qlog" / variant / profile / str(run_number)

    downloaded_file = output_dir / file_name
    source_file = TRANSFER_DIR / "www" / file_name

    process = None
    log_file = None

    try:
        process, log_file = start_server(threshold, server_qlog_dir)

        transferred_bytes, download_time = run_client(
            file_name,
            output_dir,
            qlog_dir,
            threshold,
        )
        # Give aioquic time to finish writing the server-side qlog
        wait_for_server_qlog(server_qlog_dir)

        if not downloaded_file.exists():
            raise RuntimeError(f"Downloaded file not found: {downloaded_file}")

        source_hash = sha256_file(source_file)
        downloaded_hash = sha256_file(downloaded_file)

        if source_hash != downloaded_hash:
            raise RuntimeError(
                "SHA-256 mismatch: downloaded file differs from source"
            )

        actual_size = downloaded_file.stat().st_size

        if transferred_bytes != actual_size:
            raise RuntimeError(
                f"Size mismatch: client reported {transferred_bytes} bytes, "
                f"but downloaded file has {actual_size} bytes"
            )

        goodput_mbps = transferred_bytes * 8 / download_time / 1_000_000

        row = {
            "variant": variant,
            "profile": profile,
            "file_size": actual_size,
            "run": run_number,
            "download_time_s": f"{download_time:.6f}",
            "goodput_mbps": f"{goodput_mbps:.3f}",
            "sha256_ok": True,
            "qlog_path": str(qlog_dir.relative_to(ROOT)),
        }

        save_result(row)
        print("Saved result:", row)

    finally:
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


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run one HTTP/3 file transfer."
    )
    parser.add_argument("--file", default="1MB.bin", help="File to download")
    parser.add_argument("--variant", default="smoke_stock", help="Experiment variant")
    parser.add_argument("--profile", default="clean", help="Network profile name")
    parser.add_argument("--run", type=int, default=1, help="Run number")
    parser.add_argument(
        "--threshold",
        type=int,
        default=None,
        help="Packet threshold; omit to use the stock default",
    )

    args = parser.parse_args()

    run_transfer(
        file_name=args.file,
        variant=args.variant,
        profile=args.profile,
        run_number=args.run,
        threshold=args.threshold,
    )
