#!/usr/bin/env python3
"""Welch t-tests of the undo-only ablation against stock, Holm-corrected across profiles.

Reproduces experiments/results/phase1_undo_ablation_5runs/undo_vs_stock_comparison.csv
with --handover-stock-runs 5, and compares handover against all 10 stock runs with
--handover-stock-runs 10 (the same stock sample the main handover analysis uses).

    python experiments/analysis/undo_ablation_stats.py --handover-stock-runs 5
    python experiments/analysis/undo_ablation_stats.py --handover-stock-runs 10 \
        --out experiments/results/phase1_undo_ablation_5runs/undo_vs_stock_comparison_handover10.csv
"""
import argparse
import csv
from pathlib import Path
from statistics import mean, stdev

from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
STOCK_175 = ROOT / "experiments/results/phase1_all_variants_final_5runs/transfers.csv"
STOCK_HANDOVER_10 = ROOT / "experiments/report/handover_update_v2/transfers_with_handover_runs_1_10.csv"
UNDO = ROOT / "experiments/results/phase1_undo_ablation_5runs/transfers.csv"
PROFILES = ["baseline", "mild", "moderate", "severe", "handover"]
COLUMNS = ["profile", "stock_n", "undo_n", "stock_mean", "undo_mean", "stock_std", "undo_std",
           "improvement_pct", "p_value", "holm_p", "significant_after_holm"]


def goodput(path, variant, profile):
    with open(path, newline="") as f:
        return [float(r["goodput_mbps"]) for r in csv.DictReader(f)
                if r["variant"] == variant and r["profile"] == profile]


def holm(pvalues):
    order = sorted(range(len(pvalues)), key=lambda i: pvalues[i])
    adjusted, running = [0.0] * len(pvalues), 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(pvalues) - rank) * pvalues[i]))
        adjusted[i] = running
    return adjusted


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--handover-stock-runs", type=int, choices=[5, 10], default=10)
    ap.add_argument("--out", help="CSV to write (default: print only)")
    a = ap.parse_args()

    rows = []
    for p in PROFILES:
        if p == "handover" and a.handover_stock_runs == 10:
            stock = goodput(STOCK_HANDOVER_10, "stock", p)
        else:
            stock = goodput(STOCK_175, "stock", p)
        undo = goodput(UNDO, "undo", p)
        p_value = stats.ttest_ind(undo, stock, equal_var=False).pvalue
        rows.append(dict(profile=p, stock_n=len(stock), undo_n=len(undo),
                         stock_mean=mean(stock), undo_mean=mean(undo),
                         stock_std=stdev(stock), undo_std=stdev(undo),
                         improvement_pct=(mean(undo) / mean(stock) - 1) * 100, p_value=p_value))
    for r, adj in zip(rows, holm([r["p_value"] for r in rows])):
        r["holm_p"], r["significant_after_holm"] = adj, adj < 0.05

    print(f"{'profile':9} {'n':>5} {'stock':>8} {'undo':>8} {'gain':>9} {'p':>9} {'holm p':>9}  sig")
    for r in rows:
        print(f"{r['profile']:9} {r['stock_n']:>2}/{r['undo_n']:<2} {r['stock_mean']:8.4f} {r['undo_mean']:8.4f} "
              f"{r['improvement_pct']:+8.2f}% {r['p_value']:9.6f} {r['holm_p']:9.6f}  {'Yes' if r['significant_after_holm'] else 'No'}")
    if a.out:
        with open(a.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            w.writerows(rows)
        print("wrote", a.out)


if __name__ == "__main__":
    main()
