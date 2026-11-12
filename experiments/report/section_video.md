# Video Workload: QoE under Reordering

*Author: Pooja (with Amrutha for the testbed part).*

**PROVISIONAL: stock and k20 (5 runs per cell, 12 s buffer cap, Cubic) come from Amrutha's matrix of 2026-11-06, made from a working tree with uncommitted changes, before the Phase 1 pin. `dynamic` (5 runs per cell) comes from her matrix of 2026-11-10 on pin `a8d846c`. The three variants were therefore not run at the same commit: re-run stock and k20 at the pin if time allows, otherwise state this in the report. `dynamic_undo` has no video runs.**

## 1. Why a video workload

The bulk-download results measure raw goodput. A video player reacts differently: it buffers ahead, adapts its bitrate, and
only the stalls and quality drops are visible to a viewer. We therefore replay the same network profiles with a DASH playback
simulator to see how reordering-induced loss detection errors turn into startup delay, stalls and lower quality.

## 2. Method

**Content.** One 2-minute test video, five renditions (0.25, 0.5, 1, 2.5 and 5 Mbps), 4 s segments, one manifest with
keyframe-aligned representations, encoded at constant bitrate so each rung's real bitrate matches its nominal value
(verified by `check_video_content.py`: 30 segments of 4 s, 140 MB, every rung within 1.1% of its target bitrate). The ladder starts below 1 Mbps because stock QUIC reaches only
0.5 to 3 Mbps on the impaired profiles (bulk matrix, base commit 342b224).

**Client.** `stream_client.py`: one persistent HTTP/3 connection (aioquic, Cubic), sequential segment requests, throughput-based
bitrate adaptation (harmonic mean of the last 3 downloads x 0.8, first segment on the lowest rung), a 12 s playback buffer cap (the dash.js default `stableBufferTime`, its buffer target while not playing the top quality; fixed before the matrix and identical for all variants).
Playback is simulated in real time (no decoding, audio ignored). Startup delay runs from before the QUIC handshake until one
segment is buffered; a stall starts when the buffer reaches zero before the video is fully downloaded and ends when one segment is
buffered again.

**Metrics per run.** Startup delay, stall count, total stall time, average bitrate, number of quality switches, and
QoE = avg_bitrate_mbps - 0.3 x stalls - 0.05 x stall_seconds - 0.1 x quality_switches (contract weights; see the sensitivity check below).

**Testbed.** Same namespace topology, netem profiles, 15 Mbit link and server as the bulk matrix; variants stock, k20 and dynamic (`dynamic_undo` and k100 were not run on video); 5 runs per cell; client and server qlogs kept for every run.

**Validation.** 21 offline tests cover the ABR rule, buffer and stall accounting and the manifest parser. Baseline trace (no netem): startup 0.18 s, 0 stalls, top (5 Mbps) rung from the second segment. The baseline profile (15 Mbit cap) gives startup 0.55 to 0.60 s, 0 stalls and 4.68 Mbps average for both variants.

## 3. Results

Means over 5 runs per cell (provisional).

| Profile | Variant | Startup (s) | Stalls / run | Stall time (s) | Avg bitrate (Mbps) | Switches | QoE |
|---|---|---|---|---|---|---|---|
| baseline | stock | 0.60 | 0.0 | 0.00 | 4.68 | 2.0 | 4.48 |
| baseline | k20 | 0.55 | 0.0 | 0.00 | 4.68 | 2.0 | 4.48 |
| mild | stock | 0.65 | 0.2 | 0.23 | 1.39 | 7.8 | 0.54 |
| mild | k20 | 0.66 | 0.0 | 0.00 | 1.66 | 8.8 | 0.78 |
| moderate | stock | 1.16 | 0.2 | 0.08 | 0.63 | 7.6 | -0.19 |
| moderate | k20 | 1.06 | 0.0 | 0.00 | 0.81 | 7.8 | 0.03 |
| severe | stock | 1.52 | 1.2 | 2.02 | 0.50 | 9.0 | -0.86 |
| severe | k20 | 1.02 | 0.2 | 0.13 | 0.65 | 6.6 | -0.08 |
| handover | stock | 2.08 | 0.6 | 0.96 | 0.28 | 4.4 | -0.39 |
| handover | k20 | 1.77 | 0.0 | 0.00 | 0.36 | 8.6 | -0.50 |

Differences, k20 minus stock (Welch t-test, 5 runs per cell; p-values **Holm-adjusted across the profiles of each metric**, the same method as the bulk statistics, so still a rough guide):

* Average bitrate: +19% mild (adjusted p = 0.017), +28% moderate (0.0015), +29% severe (< 0.001), +29% handover (0.002). All four survive the correction.
* Stalls: severe 1.2 vs 0.2 per run (adjusted p = 0.031, the only significant stall difference); stall time 2.0 s vs 0.13 s (adjusted p = 0.34, not significant). Elsewhere stalls are rare in both variants (stock: mild 0.2, moderate 0.2, handover 0.6 per run; k20: none) and not significant.
* Quality switches: handover 4.4 vs 8.6 (raw p = 0.022, adjusted p = 0.088, **not significant after correction**); severe 9.0 vs 6.6 (not significant).
* QoE (contract formula): significantly higher for k20 only in severe (-0.86 to -0.08, adjusted p = 0.001); mild +0.24 (0.27), moderate +0.22 (0.42) and handover -0.11 (0.54) are not significant.

**Sensitivity of the QoE ranking to the weights** (winner by mean QoE; `compare_variants.py`):

| Weight set | baseline | mild | moderate | severe | handover |
|---|---|---|---|---|---|
| contract (0.3 / 0.05 / 0.1) | tie | k20 | k20 | k20 | stock |
| no switch penalty | tie | k20 | k20 | k20 | k20 |
| light switch penalty (0.05) | tie | k20 | k20 | k20 | k20 |
| heavy switch penalty (0.2) | tie | k20 | k20 | k20 | stock |
| stall-heavy (1.0 / 0.2 / 0.1) | tie | k20 | k20 | k20 | k20 |
| bitrate only | tie | k20 | k20 | k20 | k20 |
| MPC style: smoothness = mean abs change (weight 1) | tie | k20 | k20 | k20 | k20 |

The ranking for mild, moderate and severe does not change with the weights. Handover is the exception: k20 loses under the contract weights and under a heavier switch penalty, because it tends to move between the 0.25 and 0.5 Mbps rungs more often (suggestive: the switch difference is not significant after correction) (stock sits on the 0.25 Mbps floor for 87% of segments, k20 for 56% with 43% on 0.5 Mbps), but wins when switches are penalised less, when stalls are weighted more, and under a magnitude-based smoothness penalty. Handover is also the profile where the player sits near the bottom of the ladder (0.28 to 0.36 Mbps against a 0.25 Mbps lowest rung), so a count-based switch penalty is least meaningful there. The headline QoE is therefore reported with the contract formula, and bitrate, stalls and switches are always shown separately.

## 4. Figures

* Figure 5 (`plots/video/plot5_qoe.png`): QoE per profile and variant (contract weights). Caption: k20 has higher QoE than stock in mild, moderate and severe, and the same QoE in baseline; handover is the one profile where the contract formula ranks stock higher, an effect of the switch penalty (see the sensitivity table).
* Figure 6 (`plots/video/plot6_bitrate.png`): average bitrate. Caption: k20 plays 19 to 29% higher bitrate on every impaired profile; both variants reach the same 4.68 Mbps on baseline.
* Figure 7 (`plots/video/plot7_stalls.png`): stalls per run. Caption: stalls are rare; stock stalls most in severe (1.2 per run against 0.2 for k20).
* Figure 8 (`plots/video/plot8_timeline.png`): buffer level and bitrate over time for the median-QoE stock and k20 run of the severe profile (run 1 of each). Caption: after the opening segment stock drops to the 0.25 Mbps floor twice and stalls once near the start; k20 holds 1 Mbps for longer stretches, and after the first 20 s both keep the buffer between about 5 and 11 s.

All figures come with CSV data and alt-text files. Error bars are 95% confidence intervals over the runs of a cell.

## 5. Interpretation (provisional)

* Most of the goodput loss in the bulk matrix shows up as lower bitrate, not as stalls: with a 12 s buffer and a throughput-based rule the player lowers quality to stay ahead of the link, so stock plays about 0.5 Mbps in severe where the baseline plays 4.7 Mbps. Stalls are the minority outcome (12 stall events in 50 runs).
* The k20 improvement in bulk goodput (+23 to +35%) carries over to video as +19 to +29% average bitrate on all four impaired profiles, and as fewer stalls in severe. Stalls do not otherwise differ significantly with 5 runs per cell.
* Stalls concentrate at the start of a session: 9 of the 12 stall events occur in the first four segments, mostly the second one. The player starts after one 4 s segment and picks the second rung from a single throughput sample, so this is partly a property of the client and applies equally to all variants.
* The QoE ranking at handover depends on how rung changes are penalised (see the sensitivity table); the other profiles do not.
* Link to the loss mechanism, measured on the video runs themselves (server qlogs of the 50 stock and k20 runs, `video_loss_analysis.py`): on the impaired profiles 86 to 96% of declared losses are spurious (stock 87 to 96%, k20 86 to 95%); on baseline it is 0.1 to 1.4%. Stock declares 68 to 90% of its losses by the packet rule on the impaired profiles. Under k20 the time rule takes over on moderate (76%), severe (70%) and handover (87%), the same shift as in the bulk data; on mild the packet rule still declares 59%. Across the 40 stock and k20 impaired runs, more declared losses go with a higher bitrate (Spearman +0.94), because the faster profiles send more packets; this reflects the profile, not a causal effect of loss, so we do not use it as evidence. Rule shares come from the qlog's own `rule` field.
* Does `dynamic` improve on stock or k20? Only slightly. Against stock, dynamic raises the average bitrate by 5.5, 9.0, 13.0 and 10.1% on mild, moderate, severe and handover; after Holm correction only severe is significant (p = 0.006). Stall count, stall seconds, quality switches and QoE show no significant difference in any profile (severe stalls 1.2 for stock against 0.6 for dynamic, adjusted p = 0.38; handover stalls rise from 0.6 to 1.2, not significant). Dynamic's QoE is higher than stock's on moderate and severe and lower on mild and handover, and none of these differences is significant. k20 gains 19 to 29% in bitrate over stock, so dynamic is clearly weaker than k20 on video. The dynamic qlogs show why: 87 to 96% of its declared losses on the impaired profiles are still spurious, and the packet rule still declares 56 to 82% of them, much closer to stock than to k20. Caveat: dynamic ran on a different commit and date than stock and k20.

## 6. Limitations

* Playback is simulated: no decoding, audio ignored, one viewer, one connection.
* Synthetic content at constant bitrate; real video varies segment sizes, which changes throughput samples.
* The QoE weights are a modelling choice. The ranking is stable across the weight sets tried except at handover (see Section 3).
* Stalls are concentrated in the first segments and depend on the client's startup rule (one segment buffered, bitrate chosen from one sample). The 12 s buffer cap, startup rule and ABR parameters are identical for all variants and fixed before the final runs.
* 5 runs per cell: Holm-adjusted p-values are a rough guide; the final claims should use the same correction on the final matrix.
* The provisional runs were made from a working tree with uncommitted changes and before the Phase 1 pin; they must be repeated from the pinned commit.
