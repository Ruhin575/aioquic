#!/usr/bin/env bash
# experiments/video/run_video_analysis.sh RESULTS_DIR OUT_DIR [OTHER_VARIANT ...]
#
# The whole video analysis in one command (default comparison: stock vs k20). Use it for the provisional matrix now,
# and again, unchanged, on the final matrix and for dynamic:
#     bash experiments/video/run_video_analysis.sh experiments/video/provisional_results/video_provisional /tmp/video_analysis
#     bash experiments/video/run_video_analysis.sh <final results dir> experiments/video/analysis_final k20 dynamic
#
# Steps: 1 parse every run -> summary CSV   2 stock-vs-variant comparison with Holm-adjusted p-values and a
# QoE-weight sensitivity check   3 Plots 5-7   4 Plot 8 (median-QoE stock and first-variant run, TIMELINE_PROFILE,
# default severe)   5 loss analysis from server qlogs, only if server-qlog folders exist.
# Needs pandas and matplotlib; scipy is optional (p-values are NaN without it).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
[ $# -ge 2 ] || { sed -n '2,13p' "$0"; exit 2; }
RESULTS="$1"; OUT="$2"; shift 2
OTHERS=("$@"); [ ${#OTHERS[@]} -eq 0 ] && OTHERS=(k20)
PROFILE="${TIMELINE_PROFILE:-severe}"
mkdir -p "$OUT/plots"

echo "== 1. parse runs"
python "$HERE/parse_video_results.py" "$RESULTS" --output "$OUT/video_results_parsed.csv"

for V in "${OTHERS[@]}"; do
    echo "== 2. compare stock vs $V"
    python "$HERE/compare_variants.py" --results "$OUT/video_results_parsed.csv" --base stock --other "$V" \
        --segments-dir "$RESULTS" --out "$OUT/compare_stock_vs_$V" > "$OUT/compare_stock_vs_$V.txt"
    echo "   tables: $OUT/compare_stock_vs_$V/ and $OUT/compare_stock_vs_$V.txt"
done

echo "== 3. plots 5-7"
python "$HERE/plot_qoe.py" summary --results "$OUT/video_results_parsed.csv" --out "$OUT/plots" > /dev/null

echo "== 4. plot 8 ($PROFILE, median-QoE runs of stock and ${OTHERS[0]})"
IDS=$(python - "$OUT/compare_stock_vs_${OTHERS[0]}/median_runs.csv" "$PROFILE" "${OTHERS[0]}" <<'PY'
import sys, pandas as pd
df = pd.read_csv(sys.argv[1]); prof, other = sys.argv[2], sys.argv[3]
ids = df[(df.profile == prof) & (df.variant.isin(["stock", other]))]["run_id"].tolist()
print(" ".join("--run-id " + i for i in ids))
PY
)
# shellcheck disable=SC2086
python "$HERE/plot_qoe.py" timeline --segments "$RESULTS" $IDS --out "$OUT/plots" > /dev/null

echo "== 5. loss analysis from server qlogs"
if [ -n "$(find "$RESULTS" -type d -name server-qlog -print -quit 2>/dev/null)" ]; then
    python "$HERE/video_loss_analysis.py" "$RESULTS" --out "$OUT/video_loss_per_run.csv" --summary-out "$OUT/video_loss_summary.csv" \
        | tee "$OUT/video_loss_report.txt"
else
    echo "   no server-qlog folders under $RESULTS: skipped (ask Amrutha for the server qlogs of the runs)"
fi
echo; echo "Done. Everything is in $OUT"
