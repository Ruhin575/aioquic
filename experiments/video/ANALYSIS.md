# Video QoE analysis (Pooja)

How the video results are analysed, how to rerun it on new data, and what is still provisional. The data is produced
by Amrutha's `run_video_matrix.sh`; nothing here needs fake data any more.

## One command
```bash
bash experiments/video/run_video_analysis.sh RESULTS_DIR OUT_DIR [OTHER_VARIANT ...]
# now (provisional stock vs k20 matrix):
bash experiments/video/run_video_analysis.sh experiments/video/provisional_results/video_provisional /tmp/video_analysis
# final data, all variants compared with stock:
bash experiments/video/run_video_analysis.sh <final results dir> experiments/video/analysis_final k20 dynamic dynamic_undo
```
`TIMELINE_PROFILE=moderate` changes the profile used for Plot 8 (default severe). Needs pandas and matplotlib; scipy is
optional (without it the p-values are NaN).

## What it does
| Step | Script | Output (in OUT_DIR) |
|---|---|---|
| 1 | `parse_video_results.py` | `video_results_parsed.csv`: one row per run (startup, stalls, stall time, average bitrate, switches, QoE) |
| 2 | `compare_variants.py` | `compare_stock_vs_<variant>/`: `video_comparison.csv` (means, 95% CI, difference, Welch p and Holm-adjusted p), `qoe_sensitivity.csv`, `median_runs.csv` |
| 3 | `plot_qoe.py summary` | `plots/plot5_qoe`, `plot6_bitrate`, `plot7_stalls` (.png, `_data.csv`, `.alt.txt`) |
| 4 | `plot_qoe.py timeline` | `plots/plot8_timeline`: buffer and bitrate over time for the median-QoE stock and variant run |
| 5 | `video_loss_analysis.py` | `video_loss_per_run.csv`, summary and report, **only if** `run_N/server-qlog/` folders exist |

Step 5 links the loss mechanism to QoE per run (declared losses, spurious share, share of losses declared by the packet,
time, both and PTO rules, next to the run's stalls and bitrate). It needs the server qlogs of the video runs, which are
not in the repository (`provisional_results` ships no qlogs) and were not in the tarballs sent so far.
It is tested on synthetic qlogs only and has not yet been run on real video qlogs.

## Definitions
* Startup delay: from before the QUIC handshake until one 4 s segment is buffered. Stall: the buffer reaches 0 while the
  video is still downloading. Running dry after the last segment is not a stall.
* ABR: first segment on the lowest rung, then the highest rung that fits 0.8 x the harmonic mean of the last 3 downloads.
  Buffer cap 12 s (the dash.js `stableBufferTime`), fixed for all variants.
* QoE (Day 0 contract) = avg_bitrate_mbps - 0.3 x stalls - 0.05 x stall seconds - 0.1 x quality switches.
* p-values: Welch t-test, Holm-adjusted across the profiles of each metric, the same method as Reethika's bulk statistics.

## Reading the results (provisional matrix, 5 runs per cell)
* k20 plays 19 to 29% higher bitrate than stock on every impaired profile (significant after Holm correction).
* Stalls are rare (12 events in 50 runs, 9 of them in the first four segments); only severe differs significantly
  (1.2 vs 0.2 per run, adjusted p = 0.031).
* QoE with the contract weights is significantly higher for k20 only in severe. At handover k20 ranks lower under the
  contract and heavy-switch weights and higher under five other weight sets; that difference is not significant, so
  report bitrate, stalls and switches next to the headline QoE and show the sensitivity table.

## Before quoting any number (checklist)
1. `provisional_results` runs came from a working tree with uncommitted changes and from before the Phase 1 pin. Use them
   only as provisional; the final numbers must come from runs made at the pinned commit (`experiments/BASE_COMMIT.txt`,
   currently `phase1 a8d846c`), including `dynamic` and `dynamic_undo` if they go into the video comparison.
2. Every run has `completed: true` in its `.meta.json`, the same buffer cap (`params.max_buffer_s`) and the same congestion
   control. `parse_video_results.py` skips incomplete runs with a warning: count the runs per cell (5 expected).
3. Compare the parsed summary with the runner's own `video_results.csv`; they should agree within rounding (they did for
   all 50 provisional runs).
4. Do not mix variants or profiles from different pins in one table.

## Open items
| Item | Waiting for |
|---|---|
| Video-run spurious share and rule shares (step 5) | the server qlogs of the video runs (Amrutha) |
| Final stock and k20 video matrix | a rerun at the final pin (Amrutha) |
| `dynamic` / `dynamic_undo` video results | those runs (Amrutha, with Reethika), after the code is final |
| Video section in `REPORT.md` | Reethika, from `section_video.md` once it is final |
