#!/usr/bin/env python3
"""analyze_runs.py - analyse every selected run listed in P1's results CSV.

For each selected row of experiments/results/transfers.csv it:
  1. derives the SERVER qlog directory (the sender in a download) from the CSV's
     client qlog_path by replacing the "client-qlog" path component with "server-qlog"
  2. parses it and writes experiments/analysis/parsed/<variant>__<profile>__<run>.csv
  3. detects spurious losses
  4. writes one row per run to the summary CSV, INCLUDING a status/warning column

Selection rules (so sample data never leaks into final results):
  * only rows with sha256_ok true
  * variants starting with "p3sample" (parser-development runs) are EXCLUDED unless
    --include-samples is given
  * --variant / --profile narrow the selection further
Direction: P1's run_transfer.py only performs downloads, so the server is always the sender.

A run whose qlog directory is missing or holds several .qlog files is SKIPPED and reported
(use --pick-largest to accept the largest file instead). The script exits with code 3 if
any selected run was skipped, so a partial summary cannot pass for a complete one.

Run from the repository root:
    python experiments/analysis/analyze_runs.py
    python experiments/analysis/analyze_runs.py --variant stock --profile moderate
    python experiments/analysis/analyze_runs.py --include-samples \\
        --results experiments/analysis/sample_data/transfers_p3sample.csv
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from detect_spurious import detect  # noqa: E402
from parse_qlog import parse_file   # noqa: E402

ROOT = HERE.parents[1]
REQUIRED = ["variant", "profile", "run", "sha256_ok", "qlog_path"]
SAMPLE_PREFIX = "p3sample"


def server_dir_for(qlog_path):
    parts = Path(str(qlog_path)).parts
    if "client-qlog" not in parts:
        raise ValueError("qlog_path has no 'client-qlog' component: %s" % qlog_path)
    return Path(*["server-qlog" if p == "client-qlog" else p for p in parts])


def analyze_row(row, root, parsed_dir, strict):
    srv = root / server_dir_for(row["qlog_path"])
    if not srv.is_dir():
        raise FileNotFoundError("server qlog directory not found: %s" % srv)
    df = parse_file(srv, strict=strict)
    name = "%s__%s__%s" % (row["variant"], row["profile"], row["run"])
    parsed_path = parsed_dir / (name + ".csv")
    df.to_csv(parsed_path, index=False)

    _, s = detect(df)
    cwnd = df[df["event_type"] == "metrics"]["cwnd"].dropna()
    cwnd_samples = int(len(cwnd))
    status = s["status"]
    warning = s.get("warning", "")
    if cwnd_samples < 2:
        status = "incomplete_no_cwnd" if status in ("ok", "no_losses") else status
        warning = (warning + "; " if warning else "") + "fewer than 2 cwnd samples"
    return {
        "variant": row["variant"], "profile": row["profile"], "run": row["run"],
        "goodput_mbps": row.get("goodput_mbps"), "download_time_s": row.get("download_time_s"),
        "packets_sent": s["packets_sent"], "declared_lost": s["declared_lost"],
        "spurious": s["spurious"], "spurious_rate_pct": s["spurious_rate_pct"],
        "cwnd_samples": cwnd_samples,
        # NA (not 0) when there is no usable cwnd data
        "cwnd_decrease_events": int((cwnd.diff() < 0).sum()) if cwnd_samples >= 2 else pd.NA,
        "status": status, "warning": warning,
        "parsed_csv": str(parsed_path.relative_to(root)),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(ROOT), help="repository root")
    ap.add_argument("--results", default=None, help="results CSV (default experiments/results/transfers.csv)")
    ap.add_argument("--out", default=None, help="summary CSV (default experiments/results/p3_summary.csv)")
    ap.add_argument("--variant", help="only this variant")
    ap.add_argument("--profile", help="only this profile")
    ap.add_argument("--include-samples", action="store_true", help="also analyse p3sample* variants")
    ap.add_argument("--pick-largest", action="store_true",
                    help="if a run directory has several .qlog files, use the largest instead of skipping")
    a = ap.parse_args(argv)

    root = Path(a.root)
    results = Path(a.results) if a.results else root / "experiments/results/transfers.csv"
    out = Path(a.out) if a.out else root / "experiments/results/p3_summary.csv"
    parsed_dir = root / "experiments/analysis/parsed"
    parsed_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(results)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        print("ERROR: %s is missing column(s): %s (found: %s)" % (results, ", ".join(missing), ", ".join(df.columns)),
              file=sys.stderr)
        return 2

    total = len(df)
    df = df[df["sha256_ok"].astype(str).str.lower().isin(["true", "1", "yes"])]
    n_ok = len(df)
    if not a.include_samples:
        is_sample = df["variant"].astype(str).str.startswith(SAMPLE_PREFIX)
        n_samples = int(is_sample.sum())
        df = df[~is_sample]
    else:
        n_samples = 0
    if a.variant:
        df = df[df["variant"] == a.variant]
    if a.profile:
        df = df[df["profile"] == a.profile]
    print("Rows in CSV: %d | integrity OK: %d | sample rows excluded: %d | selected: %d"
          % (total, n_ok, n_samples, len(df)))
    if df.empty:
        print("No runs selected.")
        return 1

    rows, skipped = [], []
    for _, r in df.iterrows():
        try:
            rows.append(analyze_row(r, root, parsed_dir, strict=not a.pick_largest))
            x = rows[-1]
            print("OK   %-26s %-9s run %-3s lost=%-5d spurious=%-5d (%5.1f%%)  [%s]" % (
                x["variant"], x["profile"], x["run"], x["declared_lost"], x["spurious"],
                x["spurious_rate_pct"], x["status"]))
        except Exception as e:                      # keep going, but never hide it
            skipped.append({"variant": r["variant"], "profile": r["profile"], "run": r["run"], "reason": str(e)})
            print("SKIP %s/%s/%s: %s" % (r["variant"], r["profile"], r["run"], e), file=sys.stderr)

    print("\nSelected %d | analyzed %d | skipped %d" % (len(df), len(rows), len(skipped)))
    if skipped:
        sk = out.with_name(out.stem + "_skipped.csv")
        pd.DataFrame(skipped).to_csv(sk, index=False)
        print("INCOMPLETE: skipped runs listed in", sk)
    if not rows:
        return 1

    res = pd.DataFrame(rows)
    out.parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(out, index=False)
    print("Wrote", out)
    not_ok = res[~res["status"].isin(["ok", "no_losses"])]
    if len(not_ok):
        print("WARNING: %d run(s) have status other than ok/no_losses; do not trust their spurious counts:" % len(not_ok))
        print(not_ok[["variant", "profile", "run", "status"]].to_string(index=False))
    trusted = res[res["status"].isin(["ok", "no_losses"])]
    if len(trusted):
        agg = (trusted.groupby(["variant", "profile"])
               .agg(runs=("run", "count"), declared_lost=("declared_lost", "mean"),
                    spurious=("spurious", "mean"), spurious_rate_pct=("spurious_rate_pct", "mean"))
               .round(2))
        print("\nMean per variant/profile (trusted runs only):\n", agg.to_string())
    return 3 if skipped else 0


if __name__ == "__main__":
    sys.exit(main())