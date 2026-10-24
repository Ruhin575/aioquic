
#!/usr/bin/env python3
"""Run the QUIC experiment matrix with dry-run and resume support."""

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
        "variants": ["stock", "huge-threshold"],
        "runs": 5,
    },
    "validation": {
        "files": ["50MB.bin"],
        "profiles": ["baseline", "severe"],
        "variants": ["stock", "huge-threshold"],
        "runs": 3,
    },
}


def successful_runs(path):
    """Return successful runs recorded in the current matrix's CSV."""
    completed = set()

    if not path.exists() or path.stat().st_size == 0:
        return completed

    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                size = int(row["file_size"])
                ok = row["sha256_ok"].strip().lower() in {
                    "true", "1", "yes"
                }
                threshold_text = row.get("threshold", "").strip()
                threshold = int(threshold_text) if threshold_text else None

                # Only use results matching this matrix's naming convention.
                if row["variant"] not in {"stock", "huge-threshold"}:
                    continue
                if row["profile"] not in PROFILES:
                    continue
                if row["variant"] == "huge-threshold" and threshold is None:
                    continue

                if ok:
                    completed.add((
                        row["variant"],
                        row["profile"],
                        threshold,
                        size,
                        int(row["run"]),
                    ))
            except (KeyError, ValueError, TypeError):
                continue

    return completed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage", choices=STAGES, required=True,
        help="smoke, main, or validation",
    )
    parser.add_argument(
        "--threshold", type=int,
        help="Team-agreed packet threshold for huge-threshold",
    )
    parser.add_argument(
        "--output", default=str(DEFAULT_OUTPUT),
        help="Output directory for the results CSV",
    )
    parser.add_argument(
        "--results",
        help="Optional explicit results CSV path (overrides --output)",
    )
    parser.add_argument("--dl-if", default="rc0")
    parser.add_argument("--ul-if", default="rs0")
    parser.add_argument("--router-ns", default="ns-router")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print planned commands without running experiments",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Skip successful matching runs already in the results CSV",
    )
    args = parser.parse_args()

    if not RUNNER.is_file():
        parser.error(f"QUIC runner not found: {RUNNER}")

    stage = STAGES[args.stage]
    includes_threshold_variant = "huge-threshold" in stage["variants"]

    if args.threshold is not None and args.threshold <= 0:
        parser.error("--threshold must be a positive integer")

    if includes_threshold_variant and args.threshold is None:
        if args.dry_run:
            print(
                "WARNING: dry-run will preview huge-threshold runs without "
                "a threshold. Real runs require the team's agreed value."
            )
        else:
            parser.error(
                "This stage includes huge-threshold. Ask the team for the "
                "agreed value and pass --threshold VALUE."
            )

    if args.results:
        results = Path(args.results).resolve()
    else:
        output_dir = Path(args.output).resolve()
        results = output_dir / "transfers.csv"

    results.parent.mkdir(parents=True, exist_ok=True)

    completed = successful_runs(results) if args.resume else set()
    planned = skipped = failed = 0

    for filename in stage["files"]:
        size = int(filename.removesuffix(".bin").replace("MB", ""))

        for variant in stage["variants"]:
            for profile in stage["profiles"]:
                for run_number in range(1, stage["runs"] + 1):
                    threshold_key = (
                        args.threshold if variant == "huge-threshold" else None
                    )
                    key = (
                        variant, profile, threshold_key,
                        size * 1024 * 1024, run_number,
                    )

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

                    if variant == "huge-threshold" and args.threshold is not None:
                        cmd.extend(["--threshold", str(args.threshold)])

                    planned += 1
                    print(
                        f"\n[{planned}] {variant} {profile} "
                        f"{filename} run={run_number}"
                    )

                    if args.dry_run:
                        print("DRY RUN:", subprocess.list2cmdline(cmd))
                        continue

                    result = subprocess.run(cmd, cwd=ROOT, check=False)

                    if result.returncode != 0:
                        failed += 1
                        print(
                            f"FAILED (exit {result.returncode}); "
                            "continuing to the next run.",
                            file=sys.stderr,
                        )

    print("\nMatrix summary")
    print(f"Stage: {args.stage}")
    print(f"New runs planned/attempted: {planned}")
    print(f"Already-successful runs skipped: {skipped}")
    print(f"Failed runs: {failed}")
    print(f"Results CSV: {results}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
