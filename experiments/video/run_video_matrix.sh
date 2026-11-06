#!/usr/bin/env bash
# Video matrix (provisional): variants x profiles x runs. Skips runs that already exist, so it is safe to restart.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
OUT=experiments/video/results/video_provisional
VARIANTS="${VARIANTS:-stock k20}"
PROFILES="${PROFILES:-baseline mild moderate severe handover}"
RUNS="${RUNS:-1 2 3 4 5}"
mkdir -p "$OUT"
sudo -v
( while true; do sudo -n true; sleep 50; kill -0 "$$" 2>/dev/null || exit; done ) &
KEEP=$!
trap 'kill $KEEP 2>/dev/null' EXIT
for r in $RUNS; do
  for p in $PROFILES; do
    for v in $VARIANTS; do
      d="$OUT/$v/$p/run_$r"
      if [ -d "$d" ] && [ -n "$(ls -A "$d")" ]; then echo "skip $v $p run $r (exists)"; continue; fi
      echo "=== $(date +%H:%M:%S) $v $p run $r ==="
      python experiments/video/run_video.py --variant "$v" --profile "$p" --run "$r" --output-dir "$OUT" \
        || echo "FAILED: $v $p $r" | tee -a "$OUT/failed.txt"
    done
  done
done
echo "finished. rows in video_results.csv (incl. header):"; wc -l < "$OUT/video_results.csv"
