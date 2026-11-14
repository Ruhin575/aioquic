#!/usr/bin/env python3
"""Run a QUIC experiment matrix with dry-run and resume support."""

import argparse
import csv
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RUNNER = HERE / "run_experiment.py"
DEFAULT_OUTPUT = HERE / "results"

PROFILES = ["baseline", "mild", "moderate", "severe", "handover"]
VARIANTS = [
    "stock",
    "k5",
    "k10",
    "k20",
    "k100",
    "dynamic",
    "dynamic_undo",
    "undo",
]
STAGES = {
    "smoke": {
        "files": ["1MB.bin"],
        "profiles": ["baseline", "severe"],
        "variants": ["stock"],
        "runs": 1,
    },
    "main": {
        "files": ["10MB.bin"],
        "profiles": PROFILES,
        "variants": ["stock", "k20"],
        "runs": 5,
    },
    "validation": {
        "files": ["50MB.bin"],
        "profiles": ["baseline", "severe"],
        "variants": ["stock", "k20"],
        "runs": 3,
    },
}


def successful_runs(path):
    """Return successful runs recorded in the current CSV schema."""
    completed = set()

    if not path.exists() or path.stat().st_size == 0:
        return completed

    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        required = {
            "variant", "profile", "file_size", "run", "sha256_ok"
        }

        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            print(
                f"WARNING: {path} has an old or unrecognized CSV schema. "
                "Resume will not skip any runs."
            )
            return completed

        for row in reader:
            try:
                success = row["sha256_ok"].strip().lower() in {
                    "true", "1", "yes"
                }

                if success:
                    completed.add((
                        row["variant"],
                        row["profile"],
                        int(row["file_size"]),
                        int(row["run"]),
                    ))
            except (KeyError, ValueError, TypeError):
                continue

    return completed


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument("--stage", choices=STAGES, default="main")
    parser.add_argument(
        "--variants",
        nargs="+",
        choices=VARIANTS,
        help="Override variants, e.g. --variants stock k5 k10",
    )
    parser.add_argument(
        "--profiles",
        nargs="+",
        choices=PROFILES,
        help="Override profiles, e.g. --profiles moderate severe",
    )
    parser.add_argument("--runs", type=int, help="Override repetitions")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--results", help="Explicit results CSV path")
    parser.add_argument("--dl-if", default="rc0")
    parser.add_argument("--ul-if", default="rs0")
    parser.add_argument("--router-ns", default="ns-router")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")

    args = parser.parse_args()

    if not RUNNER.is_file():
        parser.error(f"QUIC runner not found: {RUNNER}")

    if args.runs is not None and args.runs < 1:
        parser.error("--runs must be at least 1")

    stage = STAGES[args.stage]
    variants = args.variants or stage["variants"]
    profiles = args.profiles or stage["profiles"]
    runs = args.runs or stage["runs"]

    results = (
        Path(args.results).resolve()
        if args.results
        else Path(args.output).resolve() / "transfers.csv"
    )
    results.parent.mkdir(parents=True, exist_ok=True)

    completed = successful_runs(results) if args.resume else set()
    planned = skipped = failed = 0

    for filename in stage["files"]:
        size_bytes = (
            int(filename.removesuffix(".bin").replace("MB", ""))
            * 1024 * 1024
        )

        for variant in variants:
            for profile in profiles:
                for run_number in range(1, runs + 1):
                    key = (variant, profile, size_bytes, run_number)

                    if key in completed:
                        print(
                            f"SKIP successful: {variant} {profile} "
                            f"{filename} run={run_number}"
                        )
                        skipped += 1
                        continue

                    cmd = [
                        sys.executable, str(RUNNER),
                        "--profile", profile,
                        "--file", filename,
                        "--variant", variant,
                        "--run", str(run_number),
                        "--dl-if", args.dl_if,
                        "--ul-if", args.ul_if,
                        "--router-ns", args.router_ns,
                        "--output-dir", str(results.parent),
                        "--results-file", str(results),
                    ]

                    planned += 1
                    print(
                        f"\n[{planned}] {variant} {profile} "
                        f"{filename} run={run_number}"
                    )

                    if args.dry_run:
                        print("DRY RUN:", subprocess.list2cmdline(cmd))
                        continue

                    result = subprocess.run(cmd, cwd=ROOT, check=False)

                    if result.returncode:
                        failed += 1
                        print(
                            f"FAILED (exit {result.returncode}); "
                            "continuing to the next run.",
                            file=sys.stderr,
                        )

    print("\nMatrix summary")
    print(f"Stage: {args.stage}")
    print(f"Variants: {', '.join(variants)}")
    print(f"Profiles: {', '.join(profiles)}")
    print(f"Runs per combination: {runs}")
    print(f"New runs planned/attempted: {planned}")
    print(f"Already-successful runs skipped: {skipped}")
    print(f"Failed runs: {failed}")
    print(f"Results CSV: {results}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
