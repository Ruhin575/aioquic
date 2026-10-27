#!/usr/bin/env python3
"""run_sample_transfer.py - run ONE of P1's transfers but write the result row to a
separate CSV, so the team's experiments/results/transfers.csv is never touched.

It imports experiments/transfer/run_transfer.py, redirects its RESULTS_FILE, and calls
the same run_transfer() function. P1's code is not modified (apart from the separate
wait-for-server-qlog patch).

    python experiments/analysis/run_sample_transfer.py --file 10MB.bin --variant p3sample \
        --profile moderate --run 1 \
        --results-file experiments/analysis/sample_data/transfers_p3sample.csv
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments" / "transfer"))
import run_transfer as rt  # noqa: E402  (its CLI is guarded by __main__, so importing is safe)

TEAM_RESULTS = (ROOT / "experiments" / "results" / "transfers.csv").resolve()
TEAM_OUTPUT_DIR = (ROOT / "experiments" / "results").resolve()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", default="10MB.bin")
    ap.add_argument("--variant", default="p3sample")
    ap.add_argument("--profile", required=True)
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--threshold", type=int, default=None)
    ap.add_argument("--results-file", required=True, help="CSV to append the result row to")
    ap.add_argument("--output-dir", required=True,
                    help="where run_<N>/{client,server}-qlog and download/ are written (NOT experiments/results)")
    a = ap.parse_args(argv)

    results = Path(a.results_file).resolve()
    out_dir = Path(a.output_dir).resolve()
    if results == TEAM_RESULTS:
        raise SystemExit("Refusing to write to the team's results file; choose a different --results-file.")
    if out_dir == TEAM_OUTPUT_DIR or TEAM_OUTPUT_DIR in out_dir.parents:
        raise SystemExit("Refusing to write into the team's experiments/results directory; choose a different --output-dir.")
    if not a.variant.startswith("p3sample"):
        raise SystemExit("Sample variants must start with 'p3sample' so they stay out of final results.")
    rt.run_transfer(file_name=a.file, variant=a.variant, profile=a.profile,
                    run_number=a.run, threshold=a.threshold,
                    output_dir=out_dir, results_file=results)
    return 0


if __name__ == "__main__":
    sys.exit(main())