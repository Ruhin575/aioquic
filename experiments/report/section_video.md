# Video Workload: QoE under Reordering

*Author: Pooja (with Amrutha for the testbed part).*

**Data:** the final video matrix: stock, k20 and `dynamic_undo`, 5 profiles, 5 runs each (75 runs), run by Amrutha in one session on commit `32ca59e`. Its `src/` is identical to the Phase 1 pin `a8d846c`, and every run's `run_info.json` records `"dirty": false`. The `undo` ablation (congestion undo only, K fixed at 3; 25 runs) was run later the same day on commit `0daf55f`, clean tree, whose `src/` differs from the pin only by the added `undo` mode (12 lines in `recovery.py`); it is a separate session from the other three variants. The earlier provisional video runs (stock and k20 of 2026-11-06 from a working tree with uncommitted changes, `dynamic` of 2026-11-10) are superseded and are not used in the tables below.

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
buffered again. The original proposal planned dash.js in headless Chromium; a Python simulator was used instead because it keeps the client on the same aioquic stack as the server, makes the buffer, ABR and stall logic deterministic and testable (21 offline tests), and needs no browser inside the network namespaces. It does not exercise a real player's ABR tuning, decoding or rendering.

**Metrics per run.** Startup delay, stall count, total stall time, average bitrate, number of quality switches, and
QoE = avg_bitrate_mbps - 0.3 x stalls - 0.05 x stall_seconds - 0.1 x quality_switches (contract weights; see the sensitivity check below).

**Testbed.** Same namespace topology, netem profiles, 15 Mbit link and server as the bulk matrix; variants stock, k20 and `dynamic_undo`; 5 runs per cell; the runner records the commit and the clean-tree flag of every run. The `undo` ablation (K fixed at 3, undo mechanism only) is a fourth variant run in its own session (see above); the earlier `dynamic` variant is not part of the final comparison.

**Validation.** 21 offline tests cover the ABR rule, buffer and stall accounting and the manifest parser. Baseline trace (no netem): startup 0.18 s, 0 stalls, top (5 Mbps) rung from the second segment. The baseline profile (15 Mbit cap) gives startup 0.51 to 0.55 s, 0 stalls and 4.68 Mbps average for all three variants.

## 3. Results

Means over 5 runs per cell.

| Profile | Variant | Startup (s) | Stalls / run | Stall time (s) | Avg bitrate (Mbps) | Switches | QoE |
|---|---|---|---|---|---|---|---|
| baseline | stock | 0.55 | 0.0 | 0.00 | 4.68 | 2.0 | 4.48 |
| baseline | k20 | 0.51 | 0.0 | 0.00 | 4.68 | 2.0 | 4.48 |
| baseline | dynamic_undo | 0.51 | 0.0 | 0.00 | 4.68 | 2.0 | 4.48 |
| baseline | undo | 0.55 | 0.0 | 0.00 | 4.68 | 2.0 | 4.48 |
| mild | stock | 0.77 | 0.4 | 1.17 | 1.49 | 9.0 | 0.41 |
| mild | k20 | 0.62 | 0.0 | 0.00 | 1.96 | 10.2 | 0.94 |
| mild | dynamic_undo | 0.64 | 0.0 | 0.00 | 2.80 | 8.4 | 1.96 |
| mild | undo | 0.68 | 0.0 | 0.00 | 2.64 | 8.4 | 1.80 |
| moderate | stock | 0.87 | 1.2 | 1.55 | 0.59 | 6.0 | -0.45 |
| moderate | k20 | 0.71 | 0.2 | 0.38 | 0.85 | 7.4 | 0.03 |
| moderate | dynamic_undo | 0.79 | 0.0 | 0.00 | 1.12 | 4.4 | 0.68 |
| moderate | undo | 0.86 | 0.0 | 0.00 | 0.99 | 4.0 | 0.59 |
| severe | stock | 1.87 | 0.2 | 0.05 | 0.57 | 6.2 | -0.11 |
| severe | k20 | 1.05 | 0.4 | 0.27 | 0.60 | 5.8 | -0.12 |
| severe | dynamic_undo | 1.16 | 0.2 | 0.07 | 0.77 | 6.6 | 0.05 |
| severe | undo | 1.02 | 0.4 | 0.27 | 0.72 | 7.2 | -0.14 |
| handover | stock | 2.44 | 0.2 | 0.26 | 0.29 | 4.4 | -0.22 |
| handover | k20 | 1.66 | 0.8 | 1.27 | 0.36 | 8.6 | -0.80 |
| handover | dynamic_undo | 2.10 | 0.0 | 0.00 | 0.42 | 7.0 | -0.29 |
| handover | undo | 2.20 | 0.8 | 0.23 | 0.39 | 8.8 | -0.74 |

Differences (Welch t-test, 5 runs per cell; p-values **Holm-adjusted across the profiles of each metric**, the same method as the bulk statistics, so still a rough guide with n = 5):

**dynamic_undo minus stock**

* Average bitrate: +88% mild (adjusted p = 0.0003), +88% moderate (< 0.0001), +35% severe (0.0008), +43% handover (0.0008). All four survive the correction.
* QoE (contract formula): significantly higher in mild (+1.55, adjusted p = 0.003) and moderate (+1.12, 0.025). Severe (+0.16, 0.38) and handover (-0.06, 0.69) are not significant.
* Stalls: moderate 1.2 vs 0.0 per run (raw p = 0.033, **adjusted p = 0.13, not significant**); mild 0.4 vs 0.0, handover 0.2 vs 0.0, severe 0.2 vs 0.2. Stall time and startup delay show no significant difference (severe startup 1.87 vs 1.16 s: raw p = 0.042, adjusted 0.21).
* Quality switches: no significant difference (moderate 6.0 vs 4.4, adjusted p = 0.64; handover 4.4 vs 7.0, adjusted p = 0.27).

**k20 minus stock**

* Average bitrate: +32% mild (adjusted p = 0.0015), +43% moderate (< 0.0001), +25% handover (0.0066); severe +4% (0.54) is not significant.
* Stalls, switches and QoE: no significant difference after correction (QoE: mild +0.54, moderate +0.48, severe -0.01, handover -0.58; handover switches 4.4 vs 8.6, raw p = 0.028, adjusted 0.11).

**dynamic_undo minus k20**

* Average bitrate: +42% mild (adjusted p = 0.0018), +31% moderate (< 0.0001), +30% severe (0.0018), +14% handover (0.029).
* QoE: significantly higher in mild (+1.01, adjusted p = 0.0004) and moderate (+0.65, 0.027); severe and handover are not significant. Quality switches in moderate are lower (7.4 vs 4.4, adjusted p = 0.048).

**undo (ablation: congestion undo only, K fixed at 3)**

* Against stock, average bitrate: +77% mild (adjusted p < 0.0001), +68% moderate (< 0.0001), +26% severe (0.013), +35% handover (0.0016). `undo` alone therefore delivers most of the video gain.
* QoE against stock (contract weights): higher in mild (+1.39, adjusted p = 0.003) and moderate (+1.04, 0.031); severe is no different (-0.02, 0.85); at handover it is **significantly lower** (-0.74 against -0.22, adjusted p = 0.046). The cause is quality switches: 8.8 against 4.4 per run at handover (adjusted p = 0.023). With bitrate only, `undo` is higher than stock at handover; under the contract, heavy-switch and stall-heavy weights stock is higher there. `undo` also had 6 stalls in 25 runs, against 1 for `dynamic_undo` (stock 10 in 25, k20 7 in 25).
* Against `dynamic_undo`, adding adaptive K changes little: bitrate is +6% (mild), +12% (moderate), +7% (severe) and +6% (handover), and only the moderate difference is significant after correction (adjusted p = 0.0004). QoE differences are not significant (handover +0.45, adjusted p = 0.15; `dynamic_undo` is ahead under every weight set at handover). The stall difference (handover 0.8 against 0.0 per run) is not significant (adjusted p = 0.20).
* Reading: most of the video gain comes from the undo mechanism. Adaptive K adds a measurable bitrate gain on moderate and a trend towards fewer stalls and fewer quality switches at handover, but with 5 runs per cell this is a trend, not a finding. The `undo` runs come from a separate session, so the comparison with the other three variants also carries session-to-session variation (the k20 severe result already showed that this variation can be large).

**Sensitivity of the QoE ranking to the weights** (winner by mean QoE, stock vs `dynamic_undo`; `compare_variants.py`; for stock vs `undo` the handover winner is stock under five of the seven weight sets, severe is split):

| Weight set | baseline | mild | moderate | severe | handover |
|---|---|---|---|---|---|
| contract (0.3 / 0.05 / 0.1) | tie | dynamic_undo | dynamic_undo | dynamic_undo | stock |
| no switch penalty | tie | dynamic_undo | dynamic_undo | dynamic_undo | dynamic_undo |
| light switch penalty (0.05) | tie | dynamic_undo | dynamic_undo | dynamic_undo | dynamic_undo |
| heavy switch penalty (0.2) | tie | dynamic_undo | dynamic_undo | dynamic_undo | stock |
| stall-heavy (1.0 / 0.2 / 0.1) | tie | dynamic_undo | dynamic_undo | dynamic_undo | dynamic_undo |
| bitrate only | tie | dynamic_undo | dynamic_undo | dynamic_undo | dynamic_undo |
| MPC style: smoothness = mean abs change (weight 1) | tie | dynamic_undo | dynamic_undo | dynamic_undo | dynamic_undo |

The ranking for mild, moderate and severe does not change with the weights. Handover is the exception: under the contract weights and a heavier switch penalty stock scores slightly higher (-0.22 against -0.29), because `dynamic_undo` changes rung more often there (7.0 against 4.4 switches; not significant after correction), and `dynamic_undo` wins under the other five weight sets. For k20 at handover the switch count is higher still (8.6) and its QoE is the lowest of the three (-0.80). Handover is also the profile where the player sits near the bottom of the ladder (0.29 to 0.42 Mbps against a 0.25 Mbps lowest rung), so a count-based switch penalty is least meaningful there. The headline QoE is therefore reported with the contract formula, and bitrate, stalls and switches are always shown separately.

## 4. Figures

* Figure 5 (`plots/video/plot5_qoe.png`): QoE per profile and variant (stock, k20, `dynamic_undo`, `undo`; contract weights). Caption: `dynamic_undo` has the highest QoE in mild, moderate and severe and the three variants are identical in baseline; at handover all three are negative and stock is highest under the contract formula, an effect of the switch penalty (see the sensitivity table).
* Figure 6 (`plots/video/plot6_bitrate.png`): average bitrate. Caption: `dynamic_undo` plays the highest bitrate on every impaired profile (2.80, 1.12, 0.77 and 0.42 Mbps against 1.49, 0.59, 0.57 and 0.29 for stock); all variants reach the same 4.68 Mbps on baseline.
* Figure 7 (`plots/video/plot7_stalls.png`): stalls per run. Caption: stalls are rare; stock stalls most in moderate (1.2 per run), k20 and `undo` most at handover (0.8 each), and `dynamic_undo` stalled once in its 25 runs.
* Figure 8 (`plots/video/plot8_timeline.png`): buffer level and bitrate over time for the median-QoE stock and `dynamic_undo` run of the moderate profile (stock run 1, `dynamic_undo` run 5). Caption: stock stalls once at about 9 s and then stays on the 0.5 Mbps rung for most of 12 to 52 s and 64 to 98 s; `dynamic_undo` holds 1 Mbps, climbs to 2.5 Mbps twice (about 49 to 57 s and 90 to 93 s), and both keep the buffer between about 6 and 11 s after the opening.

All figures come with CSV data and alt-text files. Error bars are 95% confidence intervals over the runs of a cell.

## 5. Interpretation

* Most of the goodput loss in the bulk matrix shows up as lower bitrate, not as stalls: with a 12 s buffer and a throughput-based rule the player lowers quality to stay ahead of the link, so stock plays about 0.6 Mbps in moderate where the baseline plays 4.7 Mbps. Stalls are the minority outcome (24 events in 100 runs: stock 10, k20 7, `undo` 6, `dynamic_undo` 1).
* The `dynamic_undo` gain in bulk goodput (+143% mild, +107% moderate, +53% severe, +81% handover) carries over to video as +88%, +88%, +35% and +43% average bitrate, about 0.4 to 0.8 of the bulk gain. The video gain is smaller, as expected: the player cannot use more than the 5 Mbps top rung and it stops fetching while its buffer is full. The largest effects are on mild and moderate, where QoE is also significantly higher.
* The k20 improvement is smaller and less stable than the `dynamic_undo` improvement, and `dynamic_undo` is significantly above k20 in bitrate on every impaired profile. The earlier provisional k20 runs showed +19 to +29% bitrate on all four impaired profiles; in the rerun at the pin severe is +4% and not significant. With 5 runs per cell the size of a k20 gain varies between sessions, so the k20 figures should be read as indicative.
* Stalls concentrate at the start of a session: 19 of the 24 stall events occur in the first four segments. The player starts after one 4 s segment and picks the second rung from a single throughput sample, so this is partly a property of the client and applies equally to all variants. The stall reduction for `dynamic_undo` (moderate 1.2 to 0.0 per run) does not survive Holm correction and is reported as a trend, not a finding.
* The QoE ranking at handover depends on how rung changes are penalised (see the sensitivity table); the other profiles do not.
* Link to the loss mechanism, measured on the **final** runs (server qlogs of all 100 video runs, `video_loss_analysis.py`; the qlogs are held by Amrutha and are not in the repository). On the impaired profiles 86 to 97% of declared losses are spurious for every variant (stock 86 to 96%, k20 88 to 96%, `dynamic_undo` 88 to 97%, `undo` 90 to 96%); on baseline it is 0.0 to 0.1%. The rule shares reproduce the bulk finding: stock declares 68 to 93% of its losses by the packet rule; under k20 the time rule takes over on moderate (72%), severe (70%) and handover (83%); `undo`, with K fixed at 3, stays on the packet rule like stock (79 to 94%); `dynamic_undo` sits in between (packet rule 49 to 76%, time rule 20 to 42%). Declared losses per run are higher for the two undo variants than for stock (for example moderate: 2,704 for `undo` and 3,099 for `dynamic_undo` against 964 for stock), because they send far more data in the same time, so the count is not comparable across variants as a rate.

| Undo events per run (mean of 5) | mild | moderate | severe | handover | baseline |
|---|---|---|---|---|---|
| `dynamic_undo`: cwnd restored | 112 | 167 | 69 | 51 | 0 |
| `dynamic_undo`: undo abandoned | 43 | 51 | 53 | 60 | 5 |
| `undo`: cwnd restored | 67 | 100 | 52 | 45 | 0.4 |
| `undo`: undo abandoned | 38 | 46 | 50 | 57 | 7 |

  The undo is active on every impaired profile and nearly silent on baseline (0 to 0.4 restores per run), where almost no loss is spurious. Abandoned episodes (a genuine loss was found) occur on all profiles, including baseline, so the safeguard is exercised; stock and k20 produce no undo events, as expected. Across the 80 impaired runs, declared losses correlate with average bitrate (Spearman +0.85) and QoE (+0.72), and the spurious share does not (+0.26 and +0.06); because profile and variant move both together, this is descriptive, not causal.

## 6. Limitations

* Playback is simulated: no decoding, audio ignored, one viewer, one connection.
* Synthetic content at constant bitrate; real video varies segment sizes, which changes throughput samples.
* The QoE weights are a modelling choice. The ranking is stable across the weight sets tried except at handover (see Section 3).
* Stalls are concentrated in the first segments and depend on the client's startup rule (one segment buffered, bitrate chosen from one sample). The 12 s buffer cap, startup rule and ABR parameters are identical for all variants and fixed before the final runs.
* 5 runs per cell: Holm-adjusted p-values are a rough guide, and the k20 result changed between the provisional and the final session.
* The video-run qlogs are held by Amrutha and are not in the repository, so the loss-mechanism numbers above can be reproduced only from her copy. The rule field shows which rule recorded a declaration, not why a packet was reordered.
* The `undo` ablation was run in a separate session on a commit that differs from the pin only by the added ablation mode; session-to-session variation is not controlled, and the split between undo and adaptive K rests on 5 runs per cell.
* The earlier `dynamic` matrix (2026-11-10, commit `82766da`, same `src/` as the pin) is kept under `video_provisional/` but is not part of the final comparison; its bitrate gain over stock was +5 to +13% (significant only in severe).
