#!/usr/bin/env python3
"""compare_variants.py - stock-vs-variant comparison of the video QoE results, with a QoE-weight sensitivity check.

Input : the summary CSV written by parse_video_results.py (variant, profile, run, startup_delay_s, stall_count,
        total_stall_s, avg_bitrate_mbps, quality_switches, qoe_score).
Output: <out>/video_comparison.csv   per profile and metric: means, 95% CI, difference, Welch p-value and its Holm-adjusted value
        <out>/qoe_sensitivity.csv    per profile and weight set: mean QoE of both variants and the winner
        <out>/median_runs.csv        the median-QoE run of each variant and profile (use these for Plot 8)
and prints the same as tables.

    python experiments/video/compare_variants.py --results /tmp/parsed.csv --base stock --other k20 \
        --out experiments/video/analysis_out
    # optional: also compute a magnitude-based smoothness penalty (MPC style) from the per-segment logs
    python experiments/video/compare_variants.py --results /tmp/parsed.csv --base stock --other k20 \
        --segments-dir experiments/video/provisional_results/video_provisional --out experiments/video/analysis_out

Why a sensitivity check: the Day 0 QoE counts every rung change as a fixed 0.1 penalty, on a ladder whose lowest rung
is 0.25 Mbps. A variant that gets more bandwidth also moves between rungs more often, so the headline QoE can rank
variants differently from bitrate and stalls. The sets below show which conclusions survive a change of weights.
The Welch p-values need scipy (optional). welch_p_holm adjusts them across the profiles of each metric (Holm, as in the
bulk statistics); with n = 5 runs per cell they are still a rough guide. diff_pct is left empty for QoE (its base can be negative).
"""
import argparse
import os
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

PROFILE_ORDER = ["baseline", "mild", "moderate", "severe", "handover"]
METRICS = ["startup_delay_s", "stall_count", "total_stall_s", "avg_bitrate_mbps", "quality_switches", "qoe_score"]
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228}

# (name, penalty per stall, per stall second, per quality switch)
WEIGHT_SETS = [
    ("contract (0.3 / 0.05 / 0.1)", 0.3, 0.05, 0.10),
    ("no switch penalty", 0.3, 0.05, 0.00),
    ("light switch penalty (0.05)", 0.3, 0.05, 0.05),
    ("heavy switch penalty (0.2)", 0.3, 0.05, 0.20),
    ("stall-heavy (1.0 / 0.2 / 0.1)", 1.0, 0.20, 0.10),
    ("bitrate only", 0.0, 0.00, 0.00),
]

try:
    from scipy import stats as _scipy_stats
except Exception:                                                     # scipy is optional
    _scipy_stats = None


def ci95(x):
    n = len(x)
    return T975.get(n - 1, 1.96) * x.std(ddof=1) / n ** 0.5 if n > 1 else 0.0


def welch_p(a, b):
    if _scipy_stats is None or len(a) < 2 or len(b) < 2 or (a.std() == 0 and b.std() == 0):
        return float("nan")
    return float(_scipy_stats.ttest_ind(a, b, equal_var=False).pvalue)


def holm(pvalues):
    """Holm-Bonferroni adjusted p-values (same method as the bulk statistics in results/attribution_main).
    NaN p-values are left as NaN and do not count towards the number of tests."""
    idx = [i for i, p in enumerate(pvalues) if p == p]
    order = sorted(idx, key=lambda i: pvalues[i])
    adj, running, m = [float("nan")] * len(pvalues), 0.0, len(order)
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[i]))
        adj[i] = running
    return adj


def qoe(df, w_stall, w_stall_s, w_switch):
    return df["avg_bitrate_mbps"] - w_stall * df["stall_count"] - w_stall_s * df["total_stall_s"] \
        - w_switch * df["quality_switches"]


def switch_magnitude(segments_dir):
    """mean |bitrate change| between consecutive segments (Mbps), per (variant, profile, run), from segments*.csv."""
    out = {}
    for f in sorted(Path(segments_dir).rglob("segments*.csv")):
        df = pd.read_csv(f)
        for run_id, g in df.groupby("run_id", sort=False):
            parts = str(run_id).split("__")
            if len(parts) != 3:
                continue
            q = g.sort_values("segment_index")["bitrate_mbps"].astype(float)
            out[(parts[0], parts[1], str(parts[2]))] = float(q.diff().abs().iloc[1:].sum() / len(q))
    return out


def comparison(df, base, other):
    rows = []
    for prof in [p for p in PROFILE_ORDER if p in set(df["profile"])]:
        a = df[(df.variant == base) & (df.profile == prof)]
        b = df[(df.variant == other) & (df.profile == prof)]
        for m in METRICS:
            ma, mb = a[m].mean(), b[m].mean()
            rows.append(dict(profile=prof, metric=m, n_base=len(a), n_other=len(b),
                             mean_base=round(ma, 4), mean_other=round(mb, 4), diff=round(mb - ma, 4),
                             diff_pct=round(100 * (mb - ma) / ma, 1) if (ma > 0 and m != "qoe_score") else float("nan"),
                             ci95_base=round(ci95(a[m]), 4), ci95_other=round(ci95(b[m]), 4),
                             welch_p=round(welch_p(a[m], b[m]), 4)))
    out = pd.DataFrame(rows)
    # Holm correction across the profiles, separately for each metric (the family compared in the bulk statistics)
    out["welch_p_holm"] = float("nan")
    for m in METRICS:
        sel = out["metric"] == m
        out.loc[sel, "welch_p_holm"] = [round(x, 4) for x in holm(out.loc[sel, "welch_p"].tolist())]
    return out


def sensitivity(df, base, other, magnitude=None):
    rows = []
    sets = list(WEIGHT_SETS)
    work = df.copy()
    if magnitude:
        work["switch_mag"] = [magnitude.get((r.variant, r.profile, str(r.run)), float("nan")) for r in work.itertuples()]
    for prof in [p for p in PROFILE_ORDER if p in set(df["profile"])]:
        sub = work[work.profile == prof]
        schemes = [(n, qoe(sub, *w)) for n, *w in sets]
        if magnitude:
            schemes.append(("MPC style: smoothness = mean |change| (weight 1)",
                            sub["avg_bitrate_mbps"] - 0.3 * sub["stall_count"] - 0.05 * sub["total_stall_s"] - 1.0 * sub["switch_mag"]))
        for name, series in schemes:
            qa, qb = series[sub.variant == base], series[sub.variant == other]
            rows.append(dict(profile=prof, weight_set=name, mean_base=round(qa.mean(), 3), mean_other=round(qb.mean(), 3),
                             diff=round(qb.mean() - qa.mean(), 3), winner=("tie" if abs(qb.mean() - qa.mean()) < 1e-9 else (other if qb.mean() > qa.mean() else base)),
                             welch_p=round(welch_p(qa, qb), 4)))
    return pd.DataFrame(rows)


def median_runs(df):
    rows = []
    for (variant, prof), g in df.groupby(["variant", "profile"]):
        g = g.sort_values("qoe_score").reset_index(drop=True)
        r = g.iloc[(len(g) - 1) // 2]
        rows.append(dict(variant=variant, profile=prof, run=r["run"], qoe_score=r["qoe_score"],
                         run_id="%s__%s__%s" % (variant, prof, r["run"])))
    return pd.DataFrame(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", required=True)
    ap.add_argument("--base", default="stock")
    ap.add_argument("--other", default="k20")
    ap.add_argument("--segments-dir", help="adds the magnitude-based smoothness scheme")
    ap.add_argument("--out", default="analysis_out")
    a = ap.parse_args(argv)

    df = pd.read_csv(a.results)
    for v in (a.base, a.other):
        if v not in set(df.variant):
            print("ERROR: variant %r not in %s (found %s)" % (v, a.results, sorted(set(df.variant))), file=sys.stderr)
            return 2
    os.makedirs(a.out, exist_ok=True)
    comp = comparison(df, a.base, a.other)
    sens = sensitivity(df, a.base, a.other, switch_magnitude(a.segments_dir) if a.segments_dir else None)
    med = median_runs(df)
    comp.to_csv(os.path.join(a.out, "video_comparison.csv"), index=False)
    sens.to_csv(os.path.join(a.out, "qoe_sensitivity.csv"), index=False)
    med.to_csv(os.path.join(a.out, "median_runs.csv"), index=False)

    pd.set_option("display.width", 200)
    print("== %s vs %s: mean per profile (diff = %s - %s; p = Welch, NaN without scipy) ==" % (a.base, a.other, a.other, a.base))
    for m in METRICS:
        t = comp[comp.metric == m][["profile", "mean_base", "mean_other", "diff", "diff_pct", "welch_p", "welch_p_holm"]]
        print("\n%s" % m)
        print(t.to_string(index=False))
    print("\n== QoE winner under different weights (winner by mean QoE) ==")
    piv = sens.pivot(index="weight_set", columns="profile", values="winner")[[p for p in PROFILE_ORDER if p in set(sens.profile)]]
    print(piv.loc[sens.weight_set.drop_duplicates()].to_string())
    print("\nWrote %s/{video_comparison,qoe_sensitivity,median_runs}.csv" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
