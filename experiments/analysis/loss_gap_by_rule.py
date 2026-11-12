#!/usr/bin/env python3
"""loss_gap_by_rule.py - which loss-detection rule can explain the declared losses?

QUIC (RFC 9002 s6.1) declares a packet lost by (a) the PACKET threshold: a packet at least
`kPacketThreshold` numbers below the largest acknowledged one, (b) the TIME threshold: it was sent
long enough ago and a later packet has been acknowledged, or (c) a PTO timeout.
The qlog does not say which rule fired, but the packet rule needs

        gap = (largest acknowledged packet number at that moment) - (lost packet number)  >=  threshold.

For every declared loss this script reconstructs the gap from the ACK frames and reports:
    pct_gap_ge_T : share of declared losses whose gap reaches the packet threshold (the packet rule COULD have fired)
    pct_gap_lt3  : share with gap < 3 (the packet rule cannot have fired even for stock QUIC)
    median_gap   : typical gap
A huge-threshold run whose declared losses mostly have gap < T was NOT driven by the packet rule.

Needs the parsed CSVs written by analyze_run.py (experiments/analysis/parsed/<tag>__<variant>__<profile>__<run>.csv).

    python experiments/analysis/loss_gap_by_rule.py --tag thr20 --huge-threshold 20
    python experiments/analysis/loss_gap_by_rule.py --tag thr100 --huge-threshold 100 --out gap_thr100.csv

Limits: this shows which rule COULD have fired, not which did; time-threshold and PTO losses cannot be told apart.
"""
import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ORDER = ["baseline", "mild", "moderate", "severe", "handover"]
NAME = re.compile(r"^(?P<tag>.+?)__(?P<variant>[^_]+(?:-[a-z]+)*)__(?P<profile>[a-z]+)__(?P<run>\d+)\.csv$")


def run_gaps(df, space="application"):
    d = df[df["pn_space"] == space]
    lost = d[d["event_type"] == "lost"].drop_duplicates("packet_number")
    ack = d[d["event_type"] == "acked"].sort_values("time_s")
    if lost.empty or ack.empty:
        return np.array([])
    running_max = np.maximum.accumulate(ack["packet_number"].values)
    idx = np.searchsorted(ack["time_s"].values, lost["time_s"].values, side="right") - 1
    largest = np.where(idx >= 0, running_max[np.clip(idx, 0, None)], -1)
    return largest - lost["packet_number"].values


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parsed-dir", default=str(HERE / "parsed"))
    ap.add_argument("--tag", required=True, help="tag used when running analyze_run.py --tag")
    ap.add_argument("--huge-threshold", type=int, required=True, help="packet threshold of the huge-threshold variant")
    ap.add_argument("--stock-threshold", type=int, default=3)
    ap.add_argument("--out", help="optional CSV for the per-profile table")
    a = ap.parse_args(argv)

    rows = []
    for f in sorted(Path(a.parsed_dir).glob("%s__*.csv" % a.tag)):
        m = NAME.match(f.name)
        if not m:
            continue
        v = m.groupdict()
        T = a.stock_threshold if v["variant"] == "stock" else a.huge_threshold
        gap = run_gaps(pd.read_csv(f))
        if len(gap) == 0:
            continue
        rows.append(dict(variant=v["variant"], profile=v["profile"], run=int(v["run"]), T=T,
                         declared=len(gap), pct_gap_ge_T=100 * (gap >= T).mean(),
                         pct_gap_lt3=100 * (gap < 3).mean(), median_gap=float(np.median(gap))))
    if not rows:
        print("No parsed CSVs with losses found for tag '%s' in %s" % (a.tag, a.parsed_dir), file=sys.stderr)
        return 1
    r = pd.DataFrame(rows)
    t = (r.groupby(["variant", "profile"])
          .agg(runs=("run", "count"), T=("T", "first"), declared=("declared", "mean"),
               pct_gap_ge_T=("pct_gap_ge_T", "mean"), pct_gap_lt3=("pct_gap_lt3", "mean"),
               median_gap=("median_gap", "median")).round(1).reset_index())
    t["profile"] = pd.Categorical(t["profile"], ORDER, ordered=True)
    t = t.sort_values(["variant", "profile"]).reset_index(drop=True)
    print(t.to_string(index=False))
    if a.out:
        t.to_csv(a.out, index=False)
        print("Wrote", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
