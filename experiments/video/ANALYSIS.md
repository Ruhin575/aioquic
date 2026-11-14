# Video QoE analysis (Pooja)

How the video results are analysed, how to rerun it on new data, and what is still provisional. The data is produced
by Amrutha's `run_video_matrix.sh`; nothing here needs fake data any more.

## One command
```bash
bash experiments/video/run_video_analysis.sh RESULTS_DIR OUT_DIR [OTHER_VARIANT ...]
# final matrix (stock, k20, dynamic_undo; commit 32ca59e = pin a8d846c source, clean tree):
TIMELINE_PROFILE=moderate bash experiments/video/run_video_analysis.sh \
    experiments/video/provisional_results/video_phase1_final /tmp/video_final dynamic_undo k20
# the k20-vs-dynamic_undo comparison (second command of the report section):
python experiments/video/compare_variants.py --results /tmp/video_final/video_results_parsed.csv \
    --base k20 --other dynamic_undo --out /tmp/video_final/cmp_k20_vs_undo
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

## Reading the results (final matrix: stock, k20, dynamic_undo; 5 runs per cell)
* `dynamic_undo` plays 35 to 88% higher bitrate than stock on every impaired profile (+88% mild, +88% moderate, +35% severe,
  +43% handover), all significant after Holm correction. It is also 14 to 42% above k20.
* k20 plays +32% (mild), +43% (moderate), +25% (handover) above stock; severe (+4%) is not significant. The earlier
  provisional k20 runs showed +19 to +29% on all four profiles, so the severe gain did not reproduce in the rerun.
* Stalls are rare (18 events in 75 runs: stock 10, k20 7, dynamic_undo 1; 16 of them in the first four segments). No
  stall difference survives Holm correction (moderate stock 1.2 vs dynamic_undo 0.0 per run: raw p = 0.033, adjusted 0.13).
* QoE with the contract weights is significantly higher for dynamic_undo than stock in mild and moderate; severe and
  handover are not significant. At handover dynamic_undo ranks lower than stock under the contract and heavy-switch
  weights (-0.29 vs -0.22) and higher under five other weight sets; k20 is lowest at handover.

## Before quoting any number (checklist)
1. The final matrix was run by Amrutha in one session on commit `32ca59e`, whose `src/` is identical to the pin `a8d846c`
   (`git diff a8d846c 32ca59e -- src` is empty), with `"dirty": false` in all 75 `run_info.json` files. The older
   `video_provisional` runs (stock and k20 of 6 Nov, `dynamic` of 10 Nov) are superseded; do not mix them in one table.
2. Every run has `completed: true` in its `.meta.json`, the same buffer cap (`params.max_buffer_s`) and the same congestion
   control. `parse_video_results.py` skips incomplete runs with a warning: count the runs per cell (5 expected).
3. Compare the parsed summary with the runner's own `video_results.csv`; they should agree within rounding.
4. Do not mix variants or profiles from different pins in one table.

## Open items
| Item | Waiting for |
|---|---|
| Video-run spurious share, rule shares and undo events (`cwnd_restored`, `undo_abandoned`) for the final runs (step 5) | the server qlogs of the final runs (Amrutha has them; they are not on GitHub) |
| `undo` (K fixed at 3) ablation on video | merged by Ruhin; Amrutha has not run it |
| Video section in `REPORT.md` | Reethika, from `section_video.md` |
