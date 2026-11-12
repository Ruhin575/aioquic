#!/usr/bin/env python3
"""video_loss_analysis.py - link the loss mechanism to the video QoE, per run, from the SERVER qlogs.

For every run folder under RESULTS_DIR that holds a segments.csv (written by stream_client.py) and a server-qlog/
directory it
  1. parses the server qlog with experiments/analysis/parse_qlog.py (which keeps the loss `rule`, `by_packet`, `by_time`),
  2. finds spurious losses with experiments/analysis/detect_spurious.py,
  3. counts declared losses and spurious losses per rule (packet / time / both / pto; `unavailable` when the qlog has no rule),
  4. joins the run's QoE metrics from parse_video_results.py,
and writes one row per run. Runs without a usable qlog are listed with a status, never silently dropped.

    python experiments/video/video_loss_analysis.py RESULTS_DIR --out video_loss_per_run.csv

Layout it expects (what run_video.py writes, plus the qlog directory):
    RESULTS_DIR/<variant>/<profile>/run_N/{segments.csv, segments.csv.meta.json, server-qlog/*.qlog}

Needs qlogs made with the instrumented build (Ruhin's rule patch). Older qlogs still work but every loss is `unavailable`.
Not yet validated on real video qlogs (none were available when this was written); it was tested on synthetic ones.
The rule of a loss is what the qlog says. Which rule declared a packet is not the same as why it was reordered.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "analysis"))
from detect_spurious import detect  # noqa: E402  # type: ignore
from parse_qlog import parse_file   # noqa: E402  # type: ignore
from parse_video_results import parse_files, split_run_id  # noqa: E402

RULES = ["packet", "time", "both", "pto"]
QOE_COLS = ["stall_count", "total_stall_s", "avg_bitrate_mbps", "quality_switches", "qoe_score"]


def rule_counts(series):
    """Counts of each rule in a Series of rule strings; missing values count as 'unavailable'."""
    s = series.astype(object).where(series.notna(), "unavailable").astype(str).str.lower()
    out = {r: int((s == r).sum()) for r in RULES}
    out["unavailable"] = int(len(s) - sum(out.values()))
    return out


def analyze_run(seg_csv):
    run_dir = seg_csv.parent
    first = pd.read_csv(seg_csv, nrows=1)
    variant, profile, run = split_run_id(first["run_id"].iloc[0])
    row = dict(variant=variant, profile=profile, run=run, run_dir=str(run_dir))
    qdir = run_dir / "server-qlog"
    if not qdir.is_dir():
        return dict(row, status="no_server_qlog")
    try:
        df = parse_file(qdir, strict=True)
    except (FileNotFoundError, ValueError) as e:
        return dict(row, status="qlog_error: %s" % e)
    sp, summ = detect(df)
    lost = df[(df["event_type"] == "lost") & (df["pn_space"] == "application")].drop_duplicates("packet_number")
    n = len(lost)
    lr = rule_counts(lost["rule"]) if "rule" in lost.columns else dict(packet=0, time=0, both=0, pto=0, unavailable=n)
    sr = rule_counts(sp["loss_rule"]) if "loss_rule" in sp.columns and len(sp) else dict(packet=0, time=0, both=0, pto=0, unavailable=len(sp))
    row.update(declared_lost=summ["declared_lost"], spurious=summ["spurious"], spurious_rate_pct=summ["spurious_rate_pct"],
               rule_coverage_pct=round(100.0 * (n - lr["unavailable"]) / n, 1) if n else float("nan"),
               status=summ["status"])
    row.update({"lost_" + k: v for k, v in lr.items()})
    row.update({"spurious_" + k: v for k, v in sr.items()})
    return row


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results_dir")
    ap.add_argument("--out", default="video_loss_per_run.csv")
    ap.add_argument("--summary-out", help="optional CSV for the per variant/profile summary")
    a = ap.parse_args(argv)

    files = sorted(Path(a.results_dir).rglob("segments.csv"))
    if not files:
        print("No segments.csv found under %s" % a.results_dir, file=sys.stderr)
        return 1
    rows = [analyze_run(f) for f in files]
    loss = pd.DataFrame(rows)
    qoe = parse_files(files)[["variant", "profile", "run"] + QOE_COLS]
    qoe["run"] = qoe["run"].astype(str)
    loss["run"] = loss["run"].astype(str)
    out = loss.merge(qoe, on=["variant", "profile", "run"], how="left")
    out.to_csv(a.out, index=False)

    ok = out[out["status"].isin(["ok", "no_losses"])]
    print("runs found: %d | with a usable qlog: %d | without: %d" % (len(out), len(ok), len(out) - len(ok)))
    bad = out[~out["status"].isin(["ok", "no_losses"])]
    if len(bad):
        print(bad[["variant", "profile", "run", "status"]].to_string(index=False))
    if ok.empty:
        print("Nothing to summarise: no run has a usable server qlog.")
        return 2
    g = ok.groupby(["variant", "profile"]).agg(
        runs=("run", "count"), declared_lost=("declared_lost", "mean"), spurious_pct=("spurious_rate_pct", "mean"),
        packet=("lost_packet", "sum"), time=("lost_time", "sum"), both=("lost_both", "sum"), pto=("lost_pto", "sum"),
        unavailable=("lost_unavailable", "sum"), stalls=("stall_count", "mean"), bitrate=("avg_bitrate_mbps", "mean")).round(2)
    known = g[["packet", "time", "both", "pto"]].sum(axis=1).replace(0, float("nan"))     # losses that carry a rule
    allv = g[["packet", "time", "both", "pto", "unavailable"]].sum(axis=1).replace(0, float("nan"))
    for r in ["packet", "time", "both", "pto"]:
        g[r + "_pct"] = (100 * g[r] / known).round(1)                                       # share among losses WITH a rule
    g["rule_coverage_pct"] = (100 * known.fillna(0) / allv).round(1)
    pd.set_option("display.width", 220)
    print("\nPer variant and profile. Rule shares are among the declared losses that carry a rule (summed over the runs);")
    print("rule_coverage_pct is the share of declared losses that carry one (0 = qlogs from a build without the rule patch).")
    print(g[["runs", "declared_lost", "spurious_pct", "packet_pct", "time_pct", "both_pct", "pto_pct",
             "rule_coverage_pct", "stalls", "bitrate"]].to_string())
    if a.summary_out:
        g.to_csv(a.summary_out)

    imp = ok[ok["profile"] != "baseline"]
    if len(imp) >= 5:
        print("\nSpearman correlation across impaired runs (all variants together, n=%d):" % len(imp))
        for x in ("declared_lost", "spurious_rate_pct"):
            for y in ("avg_bitrate_mbps", "stall_count", "qoe_score"):
                c = imp[x].rank().corr(imp[y].rank())
                print("  %-18s vs %-17s %s" % (x, y, "n/a (constant column)" if c != c else "%+.2f" % c))
        print("  (profile and variant both move these together, so this is descriptive, not causal)")
    print("\nWrote", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
