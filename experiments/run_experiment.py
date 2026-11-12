#!/usr/bin/env python3
"""Run one QUIC experiment with network-profile setup and cleanup."""

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NETEM = ROOT / "experiments" / "netem"
TRANSFER_DIR = ROOT / "experiments" / "transfer"
TRANSFER = TRANSFER_DIR / "run_transfer.py"
LOG = ROOT / "experiments" / "EXPERIMENT_LOG.md"

PROFILES = {"baseline", "mild", "moderate", "severe", "handover"}
ALLOWED_FILES = {"1MB.bin", "10MB.bin", "50MB.bin"}

VARIANTS = {
    "stock": None,
    "k5": "5",
    "k10": "10",
    "k20": "20",
    "k100": "100",
    "dynamic": "dynamic",
    "dynamic_undo": "dynamic_undo",
}

def run_command(command, dry_run=False, check=True):
    print("+", " ".join(map(str, command)), flush=True)
    if dry_run:
        return 0

    result = subprocess.run(command, cwd=ROOT, check=False)
    if check and result.returncode:
        raise subprocess.CalledProcessError(result.returncode, command)
    return result.returncode


def log_event(status, message):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as log:
        log.write(
            f"\n- **{datetime.now().isoformat(timespec='seconds')}** "
            f"{status}: {message}\n"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, choices=sorted(PROFILES))
    parser.add_argument("--file", default="1MB.bin", choices=sorted(ALLOWED_FILES))
    parser.add_argument("--variant", default="stock", choices=sorted(VARIANTS))
    parser.add_argument(
        "--threshold",
        help="Optional explicit threshold; must agree with the selected variant.",
    )
    parser.add_argument("--run", type=int, default=1)
    parser.add_argument("--dl-if", default="rc0")
    parser.add_argument("--ul-if", default="rs0")
    parser.add_argument("--router-ns", default="ns-router")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "experiments" / "results"),
    )
    parser.add_argument("--results-file")
    args = parser.parse_args()

    if args.run < 1:
        parser.error("--run must be at least 1")

    for path in (
        TRANSFER,
        NETEM / "setup.sh",
        NETEM / "teardown.sh",
        TRANSFER_DIR / "www" / args.file,
        TRANSFER_DIR / "ns-cert.pem",
        TRANSFER_DIR / "ns-key.pem",
    ):
        if not path.is_file():
            parser.error(f"Required file not found: {path}")

    setup = [
        "bash", str(NETEM / "setup.sh"),
        args.profile, args.dl_if, args.ul_if, args.router_ns,
    ]
    teardown = [
        "bash", str(NETEM / "teardown.sh"),
        args.dl_if, args.ul_if, args.router_ns,
    ]
    transfer = [
        sys.executable, str(TRANSFER),
        "--file", args.file,
        "--variant", args.variant,
        "--profile", args.profile,
        "--run", str(args.run),
        "--output-dir", args.output_dir,
    ]

    threshold = VARIANTS[args.variant]

    if args.threshold is not None:
        if threshold is None:
            parser.error("--threshold cannot be used with the stock variant")

        if args.threshold != threshold:
            parser.error(
                f"Variant {args.variant} requires threshold {threshold}, "
                f"but received {args.threshold}"
            )

    if threshold is not None:
        transfer.extend(["--threshold", threshold])

    if args.results_file:
        transfer.extend(["--results-file", args.results_file])

    if args.dry_run:
        print("DRY RUN: no commands will be executed.")
        run_command(["sudo", "-v"], dry_run=True)
        run_command(["sudo", *setup], dry_run=True)
        run_command(transfer, dry_run=True)
        run_command(["sudo", *teardown], dry_run=True)
        return 0

    if os.geteuid() != 0:
        try:
            result = subprocess.run(["sudo", "-v"], check=False)
        except OSError as exc:
            print(f"Could not run sudo: {exc}", file=sys.stderr)
            return 1

        if result.returncode:
            print("sudo authentication failed; stopping.", file=sys.stderr)
            return result.returncode

    failure = None
    setup_attempted = False

    try:
        setup_attempted = True
        run_command(["sudo", *setup])
        run_command(transfer)
    except Exception as exc:
        failure = str(exc)
        print(f"Experiment failed: {exc}", file=sys.stderr)
        try:
            log_event(
                "FAILED",
                f"profile={args.profile}, file={args.file}, "
                f"variant={args.variant}, run={args.run}: {exc}",
            )
        except OSError as log_exc:
            print(f"Could not write experiment log: {log_exc}", file=sys.stderr)
    finally:
        if setup_attempted:
            try:
                code = run_command(["sudo", *teardown], check=False)
                if code:
                    message = f"teardown failed with exit code {code}"
                    print(message, file=sys.stderr)
                    failure = failure or message
            except OSError as exc:
                message = f"could not execute teardown: {exc}"
                print(message, file=sys.stderr)
                failure = failure or message

    if failure:
        try:
            log_event("FAILED", failure)
        except OSError:
            pass
        return 1

    try:
        log_event(
            "SUCCESS",
            f"profile={args.profile}, file={args.file}, "
            f"variant={args.variant}, run={args.run}",
        )
    except OSError as exc:
        print(f"Could not write success log: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
