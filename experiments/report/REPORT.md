# **Reordering-Resilient QUIC for HTTP/3 Video Streaming on Mobile Paths**

## Introduction

QUIC is a transport protocol used by HTTP/3 to transfer data between a client and a server. It is designed to provide reliable and secure communication. However, when the network connection changes or packets arrive out of order, QUIC may face performance issues.

These situations are common in mobile networks, where the connection quality can change frequently. When a packet does not arrive within the expected time, the sender may consider it lost and retransmit the data. Sometimes, the packet is not actually lost but is only delayed. This can lead to unnecessary retransmissions and changes in the congestion window, which may affect the overall transfer speed.

In this project, we study how packet reordering and changing network conditions affect QUIC performance. We compare the default QUIC configuration with a modified configuration that uses a larger threshold for loss detection. We also compare the results with TCP under different network conditions.

The main aim is to understand whether changing the loss-detection threshold can improve QUIC performance when the network experiences delay, packet reordering, and handover-like conditions.

## Problem Statement

In mobile networks, packets may arrive later than expected or in a different order because of changing network paths and network conditions. QUIC may interpret some delayed packets as lost, even when they eventually arrive. These spurious loss declarations can affect congestion control and reduce transfer performance.

The problem addressed in this project is to understand how QUIC behaves under different levels of network impairment and whether increasing the loss-detection threshold can reduce the impact of packet reordering and improve data transfer performance.

## Objectives

The main objectives of this project are:

1. To study the performance of QUIC under different network conditions.

2. To compare the default QUIC configuration with a modified configuration using a larger loss-detection threshold.

3. To measure metrics such as goodput, completion time, declared packet loss, spurious loss, and congestion-window behavior.

4. To compare QUIC performance with TCP under the tested network profiles.

5. To generate plots and analyze the results to understand the effect of the threshold modification.

## Experimental Setup

The experiments were conducted using the aioquic implementation. A 10 MB file transfer was used to evaluate the performance of the different configurations.

Two QUIC configurations were tested:

* Stock QUIC: The default QUIC configuration.

* Huge-threshold QUIC: A modified configuration using a larger loss-detection threshold, set to 20 for these experiments.

TCP results were also collected to provide a comparison with the QUIC configurations.

The experiments used five network profiles:

* Baseline: Represents the normal network condition used as the reference.

* Mild: Represents a mildly impaired network.

* Moderate: Represents a moderately impaired network.

* Severe: Represents a heavily impaired network.

* Handover: Represents a network condition intended to model changes in the connection or network path.

For each QUIC configuration, five runs were performed for each of the five profiles. This resulted in 50 planned QUIC runs: 25 for stock QUIC and 25 for huge-threshold QUIC. The TCP results were collected separately.

The experiment results were stored in CSV files, and the QUIC logs were analyzed to calculate the performance metrics. Plots were then generated to compare the configurations across the different profiles.

## Performance Metrics

The following metrics were used to analyze the experiment results.

* Goodput: Goodput measures the rate at which useful application data is transferred successfully. It is measured in Mbps. Higher goodput indicates that the file is being transferred more quickly.

* Completion Time : Completion time is the time required to complete the file transfer. A lower completion time indicates better transfer performance.

* Declared Packet Loss : This metric represents the number of packets that the QUIC implementation declared lost during a transfer. A high value does not necessarily mean that all those packets were permanently lost.

* Spurious Loss : Spurious loss occurs when a packet is declared lost but is subsequently received. This metric helps us understand how delayed or reordered packets may affect QUIC's loss detection.

* Congestion-Window Behavior: The congestion window controls how much data can be in flight before acknowledgements are received. Studying congestion-window changes helps us understand how loss detection and congestion control may affect transfer performance.

## Results and Discussion

The results were calculated from the 50 QUIC runs, with five repetitions for each configuration and network profile. The following table shows the average goodput obtained for each configuration.

| Network profile | Stock QUIC(Mbps) | Huge-threshold QUIC(Mbps) | TCP(Mbps) |
| --- | --- | --- | --- |
| Baseline | 14.35 | 14.43 | 13.86 |
| Mild | 2.30 | 3.16 | 10.95 |
| Moderate | 1.03 | 1.49 | 5.27 |
| Severe | 0.84 | 1.07 | 2.66 |
| Handover | 0.50 | 0.59 | 1.43 |

### Comparison Between Stock and Huge-Threshold QUIC

Under baseline conditions, both QUIC configurations achieved similar goodput. Stock QUIC achieved an average of 14.35 Mbps, while huge-threshold QUIC achieved 14.43 Mbps. This indicates that the threshold modification had very little effect under the baseline condition.

Under mild network conditions, stock QUIC achieved 2.30 Mbps, while huge-threshold QUIC achieved 3.16 Mbps. This is an improvement of approximately 37.5%.

Under moderate conditions, the average goodput increased from 1.03 Mbps for stock QUIC to 1.49 Mbps for huge-threshold QUIC, an improvement of approximately 44.1%.

Under severe conditions, huge-threshold QUIC achieved 1.07 Mbps compared with 0.84 Mbps for stock QUIC. During handover, the average goodput increased from 0.50 Mbps to 0.59 Mbps.

Overall, huge-threshold QUIC achieved higher mean goodput than stock QUIC in all five tested profiles. The largest relative improvements were observed under mild and moderate network conditions.

### Comparison with TCP

TCP achieved higher average goodput than both QUIC configurations in all four impaired network profiles. For example, under mild conditions, TCP achieved 10.95 Mbps, compared with 3.16 Mbps for huge-threshold QUIC. Under moderate conditions, TCP achieved 5.27 Mbps, compared with 1.49 Mbps for huge-threshold QUIC.

Under severe and handover conditions, the goodput of all configurations decreased. However, TCP maintained a higher average goodput than either QUIC configuration in these tests.

These results show that the threshold modification improved QUIC's performance relative to stock QUIC, but it did not make QUIC outperform TCP under the tested impaired network conditions.

### Completion Time

The average completion time also improved with the huge-threshold configuration across all five network profiles.

For example, under handover conditions, stock QUIC required an average of 167.71 seconds to complete a transfer, while huge-threshold QUIC required 142.54 seconds. This represents a reduction of approximately 15.0% in average completion time.

Under baseline conditions, the completion times were almost identical: 5.95 seconds for stock QUIC and 5.94 seconds for huge-threshold QUIC.

This follows the same general pattern as the goodput results, where the modified configuration showed more noticeable improvements under impaired network conditions.

### Packet Loss and Spurious Loss

The packet-loss analysis showed that stock QUIC and huge-threshold QUIC behaved differently in terms of declared losses and spurious losses.

Under impaired network conditions, both configurations showed high spurious-loss rates. For example, the average spurious-loss rate under mild conditions was 95.87% for stock QUIC and 90.81% for huge-threshold QUIC. Under moderate conditions, the corresponding values were 93.28% and 91.67%.

During handover, the rates were similar for both configurations, at approximately 83%.

These results suggest that many packets declared lost during impaired network conditions were subsequently received. However, the results alone do not establish why this occurred or whether the threshold modification was the only factor responsible for the observed differences.

Further analysis of the packet logs and congestion-window behavior is needed to understand the relationship between packet reordering, loss detection, and transfer performance.

### Loss Rule Attribution

The historical attribution analysis processed 100 server-side qlogs containing 53,855 loss events. These qlogs did not contain the required attribution metadata (`rule`, `by_packet`, and `by_time`), resulting in 0% attribution coverage.

To address this limitation, we conducted a new instrumented experiment matrix containing 50 runs across stock and K20 variants and all five network profiles. The analysis processed 50 server-side qlogs and identified 26,786 application-level loss events. All these events contained usable attribution metadata, giving 100% attribution coverage.

The new results show differences in the distribution of packet-based, time-based, combined, and PTO-based loss attribution between stock and K20. The detailed methodology, historical results, and new instrumented results are presented in [Loss Rule Attribution Analysis](section_attribution.md).


### New Instrumented Experiment: Goodput and Statistical Analysis

A separate performance analysis was conducted using the new instrumented experiment matrix described in the loss rule attribution section. This dataset contains five runs for each variant-profile combination, comparing stock QUIC with K20.

The table reports the mean goodput, the difference between K20 and stock, and the results of Welch's t-test.

| Profile | Stock (Mbps) | K20 (Mbps) | Difference (Mbps) | Improvement | 95% CI for difference (Mbps) | Holm-adjusted p-value |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 13.381 | 13.334 | -0.047 | -0.35% | [-0.112, 0.017] | 0.1127 |
| Mild | 2.447 | 2.915 | 0.468 | 19.14% | [0.008, 0.929] | 0.0947 |
| Moderate | 0.983 | 1.305 | 0.322 | 32.75% | [0.218, 0.426] | 0.0010 |
| Severe | 0.788 | 1.038 | 0.250 | 31.70% | [0.222, 0.278] | 1.61e-7 |
| Handover | 0.472 | 0.600 | 0.128 | 27.23% | [0.099, 0.158] | 0.0002 |

Welch's two-sample t-test was used to compare the mean goodput of stock and K20 for each network profile. Holm correction was applied to account for the five statistical comparisons. Statistical significance was assessed at the 0.05 level.

The results indicate that K20 achieved higher mean goodput under mild, moderate, severe, and handover conditions. The largest relative improvements were observed under moderate and severe conditions.

After Holm correction, the differences were statistically significant under moderate, severe, and handover conditions. The mild-profile improvement was not statistically significant after correction, and there was no statistically significant difference under baseline conditions.

The confidence intervals shown are the individual, unadjusted 95% Welch confidence intervals. The statistical tests are based on five repetitions per configuration and should therefore be interpreted as preliminary evidence.

These results belong to the new instrumented experiment matrix and are reported separately from the earlier performance results. TCP was not included in this new matrix, so this analysis does not provide a new TCP comparison.

## Offline Threshold Analysis and Dynamic Recovery

### Offline Packet-Gap and Spurious-Loss Analysis

Historical server-side qlogs from the `threshold_20` and `huge_threshold_100` datasets were analysed to examine packet reordering and spurious-loss indicators.

The analysis covered 13,228 declared packet-loss events. Of these, 12,204 were identified as spurious-loss indicators based on subsequent acknowledgements, giving an aggregate indicator rate of approximately 92.26%.

The analysis also examined the packet-number gap between a packet declared lost and the largest acknowledged packet at the time of the loss declaration. The observed gaps varied across network profiles and datasets. One negative-gap observation was retained in the validated dataset: `threshold_20`, severe profile, run 5, packet number 7. The available qlog information was insufficient to establish its exact cause.

### Packet-Threshold Trade-off

An offline analysis evaluated candidate packet thresholds K = 3, 5, 10, 20, 50 and 100 by replaying the observed acknowledgement timelines.

The results showed a trade-off. Larger thresholds reduced the number of spurious-loss indicators for which the candidate packet threshold would have been crossed before the observed late acknowledgement. However, they also increased the delay before packet-threshold detection for packets without an observed late acknowledgement. These packets are treated as a proxy for genuine losses, not as confirmed genuine losses.

For example, the pooled median positive crossing delays at K=20 were approximately 99 ms under moderate conditions and 130 ms under severe conditions. At K=50, these increased to approximately 307 ms and 396 ms, respectively.

K=20 was identified as a useful candidate for further evaluation, while K=50 and K=100 represented more aggressive threshold settings. These are offline counterfactual estimates and do not simulate the complete QUIC recovery process, including retransmissions, congestion control and changes to subsequent ACK timelines.

### Dynamic Recovery Experiments

Three dynamic recovery experiments were conducted using a 10 MB file under the moderate network profile. All three transfers completed successfully and passed SHA-256 checksum validation.

| Run | Download time (s) | Goodput (Mbps) | Adaptation events |
|---|---:|---:|---:|
| 1 | 88.17 | 0.951 | 461 |
| 2 | 81.71 | 1.027 | 458 |
| 3 | 82.95 | 1.011 | 490 |

The average goodput was approximately 0.996 Mbps, and the average completion time was approximately 84.28 seconds.

Across the three server-side qlogs, 1,409 `recovery:k_adapted` events were recorded. These include calls where the adaptive threshold remained unchanged and should not be interpreted as actual threshold increases. The observed actual increases were 65, 59 and 64 in runs 1, 2 and 3, respectively.

The available qlogs did not record every internal threshold-decay operation. Therefore, the complete adaptive threshold timeline could not be reconstructed.

### Performance Comparison of Static and Dynamic Configurations

The following comparison uses separate 10 MB transfer datasets under the moderate network profile.

| Configuration | Runs | Mean goodput (Mbps) | Sample SD (Mbps) | Mean completion time (s) |
|---|---:|---:|---:|---:|
| Stock, K20 dataset | 5 | 0.9924 | 0.0650 | 84.81 |
| K=20 | 5 | 1.2802 | 0.0727 | 65.70 |
| Stock, K100 dataset | 5 | 0.9784 | 0.0405 | 85.86 |
| K=100 | 5 | 1.3634 | 0.1666 | 62.25 |
| Dynamic | 3 | 0.9963 | 0.0401 | 84.28 |

All reported transfers passed SHA-256 validation.

K=100 achieved the highest mean goodput among these configurations, followed by K=20. However, K=100 also showed greater run-to-run variability. The dynamic configuration achieved mean goodput close to the two stock baselines in this three-run experiment.

These results are descriptive comparisons rather than a fully controlled statistical comparison because the configurations belong to separate experiment datasets and have different run counts.

Figure: `../analysis/final_goodput_comparison.png`

### Congestion-Window Analysis

Congestion-window behaviour during the dynamic experiments was examined using server-side `recovery:metrics_updated` qlog events.

| Metric | Run 1 | Run 2 | Run 3 |
|---|---:|---:|---:|
| CWND samples | 18,920 | 18,591 | 19,098 |
| Initial CWND (bytes) | 12,000 | 12,000 | 12,000 |
| Minimum CWND (bytes) | 2,400 | 2,400 | 2,400 |
| Maximum CWND (bytes) | 71,532 | 37,704 | 57,724 |
| Final CWND (bytes) | 15,140 | 23,047 | 19,948 |
| Observed decrease samples | 262 | 260 | 178 |

The congestion window varied considerably across the three runs. The decrease counts represent sample-to-sample decreases and do not necessarily correspond to distinct congestion events. The available measurements do not establish a causal relationship between adaptive threshold changes and congestion-window reductions.

Figures:
- `../analysis/dynamic_cwnd_over_time.png`
- `../analysis/dynamic_cwnd_summary.csv`

## Video Workload: QoE under Reordering

*Author: Pooja (with Amrutha for the testbed part).*

**Data:** the final video matrix: stock, k20 and `dynamic_undo`, 5 profiles, 5 runs each (75 runs), run by Amrutha in one session on commit `32ca59e`. Its `src/` is identical to the Phase 1 pin `a8d846c`, and every run's `run_info.json` records `"dirty": false`. The `undo` ablation (congestion undo only, K fixed at 3; 25 runs) was run later the same day on commit `0daf55f`, clean tree, whose `src/` differs from the pin only by the added `undo` mode (12 lines in `recovery.py`); it is a separate session from the other three variants. The earlier provisional video runs (stock and k20 of 2026-11-06 from a working tree with uncommitted changes, `dynamic` of 2026-11-10) are superseded and are not used in the tables below.

### 1. Why a video workload

The bulk-download results measure raw goodput. A video player reacts differently: it buffers ahead, adapts its bitrate, and
only the stalls and quality drops are visible to a viewer. We therefore replay the same network profiles with a DASH playback
simulator to see how reordering-induced loss detection errors turn into startup delay, stalls and lower quality.

### 2. Method

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

### 3. Results

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

### 4. Figures

* Figure 5 (`plots/video/plot5_qoe.png`): QoE per profile and variant (stock, k20, `dynamic_undo`, `undo`; contract weights). Caption: `dynamic_undo` has the highest QoE in mild, moderate and severe and the three variants are identical in baseline; at handover all three are negative and stock is highest under the contract formula, an effect of the switch penalty (see the sensitivity table).
* Figure 6 (`plots/video/plot6_bitrate.png`): average bitrate. Caption: `dynamic_undo` plays the highest bitrate on every impaired profile (2.80, 1.12, 0.77 and 0.42 Mbps against 1.49, 0.59, 0.57 and 0.29 for stock); all variants reach the same 4.68 Mbps on baseline.
* Figure 7 (`plots/video/plot7_stalls.png`): stalls per run. Caption: stalls are rare; stock stalls most in moderate (1.2 per run), k20 and `undo` most at handover (0.8 each), and `dynamic_undo` stalled once in its 25 runs.
* Figure 8 (`plots/video/plot8_timeline.png`): buffer level and bitrate over time for the median-QoE stock and `dynamic_undo` run of the moderate profile (stock run 1, `dynamic_undo` run 5). Caption: stock stalls once at about 9 s and then stays on the 0.5 Mbps rung for most of 12 to 52 s and 64 to 98 s; `dynamic_undo` holds 1 Mbps, climbs to 2.5 Mbps twice (about 49 to 57 s and 90 to 93 s), and both keep the buffer between about 6 and 11 s after the opening.

All figures come with CSV data and alt-text files. Error bars are 95% confidence intervals over the runs of a cell.

### 5. Interpretation

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

### 6. Limitations

* Playback is simulated: no decoding, audio ignored, one viewer, one connection.
* Synthetic content at constant bitrate; real video varies segment sizes, which changes throughput samples.
* The QoE weights are a modelling choice. The ranking is stable across the weight sets tried except at handover (see Section 3).
* Stalls are concentrated in the first segments and depend on the client's startup rule (one segment buffered, bitrate chosen from one sample). The 12 s buffer cap, startup rule and ABR parameters are identical for all variants and fixed before the final runs.
* 5 runs per cell: Holm-adjusted p-values are a rough guide, and the k20 result changed between the provisional and the final session.
* The video-run qlogs are held by Amrutha and are not in the repository, so the loss-mechanism numbers above can be reproduced only from her copy. The rule field shows which rule recorded a declaration, not why a packet was reordered.
* The `undo` ablation was run in a separate session on a commit that differs from the pin only by the added ablation mode; session-to-session variation is not controlled, and the split between undo and adaptive K rests on 5 runs per cell.
* The earlier `dynamic` matrix (2026-11-10, commit `82766da`, same `src/` as the pin) is kept under `video_provisional/` but is not part of the final comparison; its bitrate gain over stock was +5 to +13% (significant only in severe).

## Final Phase 1 Recovery-Variant Matrix: Dynamic Undo

### Scope and methodology

A separate final experiment matrix evaluated seven recovery variants at frozen source revision `a8d846cd48deeda588146bee145d4da74fadfa46` (`a8d846c`): stock, K5, K10, K20, K100, dynamic, and dynamic undo. Each variant was tested under baseline, mild, moderate, severe, and handover profiles, with five repetitions per combination, giving \(7 \times 5 \times 5 = 175\) runs. Each run transferred a 10 MiB file. Download integrity was checked using SHA-256, and server-side qlogs were retained.

This dataset is separate from the earlier three-run dynamic-only experiment and the earlier instrumented stock/K20 matrix. Their results are not pooled.

### Goodput results

| Network profile | Dynamic Undo mean goodput (Mbps) | Improvement over stock |
|---|---:|---:|
| Baseline | 13.3708 | 0.10% |
| Mild | 5.3402 | 142.78% |
| Moderate | 1.9408 | 107.08% |
| Severe | 1.2028 | 52.91% |
| Handover | 0.6948 | 81.13% |

The best-performing variant by mean goodput in each profile was:

| Network profile | Best-performing variant | Mean goodput (Mbps) |
|---|---|---:|
| Baseline | K10 | 13.3882 |
| Mild | Dynamic Undo | 5.3402 |
| Moderate | Dynamic Undo | 1.9408 |
| Severe | Dynamic Undo | 1.2028 |
| Handover | Dynamic Undo | 0.6948 |

Dynamic Undo achieved the highest mean goodput among the seven variants in all four impaired profiles. K10 achieved the highest mean under baseline conditions, where differences between configurations were small.

### Statistical analysis

Welch's two-sample t-tests compared each alternative variant with stock within each profile. Holm correction was applied separately within each profile across the six comparisons against stock.

| Profile | Welch p-value | Holm-adjusted p-value | Significant at 0.05? |
|---|---:|---:|---|
| Baseline | 0.138150 | 0.276301 | No |
| Mild | 0.000115 | 0.000690 | Yes |
| Moderate | 0.000069 | 0.000277 | Yes |
| Severe | 0.000053 | 0.000320 | Yes |
| Handover | 0.026163 | 0.156979 | No |

The improvements over stock were statistically significant after within-profile Holm correction under mild, moderate, and severe conditions. The handover improvement was not significant after correction, despite its higher observed mean goodput. The baseline difference was small and statistically insignificant. These tests compare each variant with stock; they do not establish that Dynamic Undo is statistically superior to every other variant. Each comparison uses five runs per group and should be interpreted accordingly.

### Recovery-event analysis

Server-side qlogs from the 25 Dynamic Undo runs were examined for `recovery:packet_lost`, `recovery:cwnd_restored`, and `recovery:undo_abandoned` events.

| Profile | Packet-loss events | CWND restorations | Undo abandonments |
|---|---:|---:|---:|
| Baseline | 0 | 0 | 0 |
| Mild | 3,724 | 128 | 47 |
| Moderate | 6,150 | 532 | 158 |
| Severe | 4,800 | 356 | 246 |
| Handover | 5,627 | 494 | 472 |
| **Total** | **20,301** | **1,510** | **923** |

All 923 observed undo-abandonment events were logged with reason `genuine_loss`. The implementation also supports abandonment for persistent congestion and excessive pending losses, but neither reason appeared in this dataset.

The implementation saves a congestion-control snapshot before processing eligible losses and tracks ACK-eliciting packets declared lost. When late acknowledgements remove all pending losses in an undo episode, the saved congestion-control state can be restored, provided the current congestion window has not already recovered to at least its pre-reduction value. The pacing rate is then recalculated. If any pending loss remains unacknowledged beyond twice the smoothed RTT, the episode is abandoned and the congestion reduction is retained. Persistent congestion and exceeding the configured pending-loss limit also trigger abandonment.

The magnitude of recorded congestion-window restorations was:

| Profile | Restorations | Mean absolute increase (bytes) | Median absolute increase (bytes) | Median relative increase |
|---|---:|---:|---:|---:|
| Mild | 128 | 41,000.9 | 35,812.0 | 110.8% |
| Moderate | 532 | 17,296.8 | 15,292.0 | 83.4% |
| Severe | 356 | 14,404.9 | 12,643.5 | 102.1% |
| Handover | 494 | 10,104.8 | 9,152.5 | 121.1% |

Moderate conditions produced the largest number of restorations and the highest restoration share among restoration and abandonment events. Handover produced the largest abandonment activity relative to packet-loss events.

| Profile | Restorations per 100 loss events | Abandonments per 100 loss events | Restoration share |
|---|---:|---:|---:|
| Mild | 3.44 | 1.26 | 73.14% |
| Moderate | 8.65 | 2.57 | 77.10% |
| Severe | 7.42 | 5.12 | 59.14% |
| Handover | 8.78 | 8.39 | 51.14% |

These are event-count ratios, not probabilities of successful recovery. Individual packet-loss events do not necessarily correspond one-to-one with undo episodes.

### Why Dynamic Undo works, and why it is safe

Raising the packet threshold alone has a ceiling. In the instrumented
stock/K20 matrix, K20 shifted most remaining losses to the time threshold:
under K20, time-rule losses accounted for 93% of losses at moderate and
85% at severe, compared with 13% under stock. Total losses fell by only
about 11–15%. This shows why increasing the packet threshold alone cannot
eliminate all premature loss declarations.

The threshold-only `dynamic` variant has a further limitation: it raises K
only after a late acknowledgement provides evidence of spurious loss. By
that point, the loss may already have reduced the congestion window.
Consistent with this, `dynamic` achieved lower mean goodput than K20 in
every impaired profile of the final matrix.

Dynamic Undo addresses the cost of spurious loss declarations. It saves
congestion-control state before eligible losses are reported to Cubic and
restores that state when every tracked loss in the episode is acknowledged
late. Because it tracks losses independently of the detection rule, it can
also undo reductions caused by time-threshold losses that a higher packet
threshold cannot prevent.

The rollback is conservative. If any pending loss remains unacknowledged
beyond twice the smoothed RTT, the episode is abandoned and the congestion
reduction is retained. Persistent congestion and exceeding the pending-loss
limit also trigger abandonment.

The abandonment counts are consistent with genuine losses continuing to
reduce the congestion window. A 10 MiB transfer represents approximately
8,700 packets. Using the configured random-loss rates gives the following
rough expected counts across five runs:

| Profile | Random loss rate | Expected genuine losses | Observed abandonments |
|---|---:|---:|---:|
| Mild | 0.1% | 44 | 47 |
| Moderate | 0.3% | 131 | 158 |
| Severe | 0.5% | 218 | 246 |
| Handover | 1.0% | 437 | 472 |

The observed counts are within approximately 8–21% of these rough
expectations. This is only an approximate consistency check: packet counts
are estimated from file size, and an abandoned episode can contain more
than one genuine loss. On the loss-free baseline profile, there were no
restorations and no abandonments. These observations are consistent with
Dynamic Undo retaining reductions for genuine losses while rolling back
reductions associated with spurious losses; they do not independently prove
the cause of each event. The design is described in `dynamic_design.md`.

### Exploratory correlation analysis

Per-run recovery-event counts and event rates were compared with goodput across the five runs in each profile. The relationships varied by profile. Restoration counts were positively correlated with goodput under mild and severe conditions but negatively correlated under moderate conditions. Abandonment counts were negatively correlated with goodput in all four impaired profiles.

Event rates normalized by download duration produced different correlations. However, goodput and event rates both contain download duration in their denominators, creating mathematical coupling that can influence the observed relationships. These correlations are exploratory and do not establish causation. With only five runs per profile, they should not be treated as strong statistical evidence.

### Dataset validation and tests

The final matrix contained all 175 expected records, exactly five runs for each of the 35 variant-profile combinations, no duplicate run keys, and no missing expected runs. All 175 downloaded files passed SHA-256 verification. The server-side qlogs were analysed and passed JSON parsing during the experiment; raw qlog files are not included in the repository because of their size.

The recovery tests also passed: 9 tests in `tests/test_dynamic_undo.py` (including 5 subtests), and 36 tests across `tests/test_recovery.py` and `tests/test_dynamic_recovery.py`, for 45 passing tests in total.

### Discussion

The final matrix provides evidence that Dynamic Undo can improve bulk-transfer goodput under several impaired network profiles. Its mean goodput was highest among the tested variants under mild, moderate, severe, and handover conditions. The improvements over stock were statistically significant after within-profile Holm correction under mild, moderate, and severe conditions, but not under handover.

The qlog evidence is consistent with the intended conditional rollback behaviour: congestion-control state was restored when all tracked losses in an undo episode were acknowledged late, while observed abandonment events retained the congestion reduction because the implementation classified the pending losses as genuine. Event counts alone do not prove that restorations caused the measured goodput improvements.

This final Dynamic Undo matrix is distinct from the earlier three-run dynamic-only experiment. The earlier experiment evaluated adaptive thresholding without the same rollback variant and remains a separate preliminary result.

## Bulk-Transfer Undo-Only Ablation

### Scope and methodology

A separate 25-run bulk-transfer ablation evaluated the congestion-state rollback mechanism without adaptive packet-threshold selection. The `undo` variant kept the packet threshold fixed at K = 3 (the stock threshold), enabled congestion-state rollback, and disabled adaptive K. It was tested under the baseline, mild, moderate, severe, and handover profiles, with five repetitions per profile. Each run transferred the same 10 MiB file used in the final recovery-variant matrix.

All 25 transfers completed successfully and passed SHA-256 verification. The ablation was conducted in a separate experiment session from the original 175-run matrix. Its results are therefore compared with the five stock runs per profile from the 175-run matrix as independent samples; the datasets are not treated as paired observations.

### Goodput results

| Profile | Stock mean (Mbps) | Stock SD | Undo mean (Mbps) | Undo SD | Improvement over stock |
|---|---:|---:|---:|---:|---:|
| Baseline | 13.3576 | 0.0124 | 13.3474 | 0.0248 | -0.08% |
| Mild | 2.1996 | 0.2161 | 4.0350 | 0.4662 | +83.44% |
| Moderate | 0.9372 | 0.0316 | 1.6960 | 0.2370 | +80.96% |
| Severe | 0.7866 | 0.0492 | 1.1954 | 0.1036 | +51.97% |
| Handover | 0.3836 | 0.2078 | 0.6294 | 0.0230 | +64.08% |

### Statistical analysis

Welch's two-sample, two-sided t-tests compared `undo` with stock separately within each profile. Because the ablation and original stock runs came from separate experiment sessions, independent-sample tests were used. Holm correction was applied across the five profile-level comparisons. Statistical significance was assessed at the 0.05 level.

| Profile | Welch p-value | Holm-adjusted p-value | Significant after correction? |
|---|---:|---:|---|
| Baseline | 0.443334 | 0.443334 | No |
| Mild | 0.000278 | 0.001320 | Yes |
| Moderate | 0.001825 | 0.005474 | Yes |
| Severe | 0.000264 | 0.001320 | Yes |
| Handover | 0.056833 | 0.113666 | No |

The undo-only variant achieved significantly higher mean goodput than stock under mild, moderate, and severe conditions after Holm correction. The observed handover improvement was 64.08%, but it did not reach statistical significance after correction. Baseline goodput was effectively unchanged. These results show that congestion-state rollback can provide a substantial goodput benefit without adaptive packet-threshold selection under the three impaired profiles where the difference was statistically significant.

### Interpretation and limitations

The ablation isolates the contribution of the rollback mechanism more directly than the combined `dynamic_undo` variant: K remains fixed at the stock value, while congestion-state rollback is enabled. The significant improvements under mild, moderate, and severe conditions support the conclusion that rollback itself contributes to the performance gains observed with `dynamic_undo`; adaptive K is not the only mechanism that can improve goodput.

The comparison has five repetitions per group and uses stock results from the separate 175-run session. Session-to-session variation is therefore a limitation, and the small sample size means the statistical results should be interpreted as experimental evidence rather than a guarantee of performance under other conditions. The handover result is particularly uncertain: its mean improvement is positive, but the difference is not statistically significant after correction. The raw run data and comparison table are stored separately under `experiments/results/phase1_undo_ablation_5runs/`; the original 175-run dataset is unchanged.

## Limitations

The final Dynamic Undo matrix contains five repetitions per variant-profile combination. Its statistical comparisons are pairwise against stock, with Holm correction applied within each profile; they do not establish statistical superiority over every alternative variant. The handover goodput improvement was not significant after correction. Event counts and event-count ratios are not counts or probabilities of unique recovery episodes, and exploratory correlations cannot establish causation. This matrix is separate from the earlier three-run dynamic-only experiment and the earlier instrumented stock/K20 matrix.

There are several limitations to consider when interpreting the results.

First, the new instrumented goodput experiments used five repetitions for each QUIC configuration and network profile. Although this provides an initial comparison, more repetitions would help provide a stronger understanding of performance variability.

Second, the experiments represent a limited set of network profiles and file-transfer conditions. The results may differ under other network conditions, file sizes or configurations.

Third, the TCP results were collected separately and have different numbers of runs in some profiles. Therefore, the TCP and QUIC comparisons should be interpreted with this difference in mind.

Fourth, the offline packet-threshold analysis replays observed ACK timelines and does not simulate the complete QUIC recovery process. Losses without observed late acknowledgements are treated as proxies rather than confirmed genuine losses.

Fifth, the threshold-only `dynamic` variant had a smaller mean goodput gain than static K20 in every impaired profile of the final matrix. Its gains over stock were 21.45% under mild, 7.32% under moderate, 6.20% under severe, and 27.32% under handover, compared with K20 gains of approximately 33.14%, 40.13%, 24.40%, and 47.40%, respectively. Its adaptation is reactive: K rises only after a late acknowledgement provides evidence of spurious loss, by which time the congestion window may already have been reduced. The earlier three-run dynamic-only experiment is superseded by the five-run-per-profile results in the final matrix. Although threshold adaptation and decay events are logged, K trajectories were not analysed in this report.

Sixth, CWND decreases observed in qlog samples do not independently establish their cause or demonstrate a causal relationship between adaptive threshold changes. The final 175-run matrix and the separate undo-only bulk-transfer ablation use five repetitions per variant-profile cell and report Welch tests with Holm correction; the small sample sizes and separate-session ablation comparison mean that these results should be treated as preliminary experimental evidence.

Finally, the video workload is a simulation: it does not perform video decoding or model audio, and it uses one viewer and one connection. The content uses synthetic constant-bitrate renditions, whereas real video may have variable segment sizes. The QoE weights are modelling choices; sensitivity analysis across seven alternative weight sets shows that the ranking is stable for mild, moderate and severe profiles, but depends on the weights under handover. Each video profile-variant cell contains five runs. Welch tests with Holm correction were performed, but the small sample size means the adjusted p-values should be treated as a rough guide. The stock, k20 and dynamic_undo runs share one clean-tree session at the Phase 1 source pin; the undo ablation was run in a separate clean-tree session on a commit differing only by the added undo mode. This session difference limits the strength of direct ablation comparisons. Video-run qlogs are held by Amrutha and are not in the repository, so the loss-mechanism analysis cannot be independently reproduced from the repository alone. The qlog rule field identifies which rule recorded a loss declaration; it does not establish why a packet was reordered.

## Conclusion

The final 175-run Dynamic Undo matrix provides a separate evaluation of the rollback variant. Dynamic Undo achieved the highest mean goodput among the seven tested variants in all four impaired profiles, with improvements over stock of 142.78% (mild), 107.08% (moderate), 52.91% (severe), and 81.13% (handover). After within-profile Holm correction, the improvements were statistically significant under mild, moderate, and severe conditions, but not under handover or baseline conditions. The qlog analysis recorded 1,510 congestion-window restorations and 923 undo abandonments across the 25 Dynamic Undo runs; all observed abandonments were attributed to genuine loss. These findings are distinct from the earlier three-run dynamic-only results and should be interpreted within the scope and limitations of the final matrix.

The earlier performance experiments showed that increasing the packet loss detection threshold to 20 improved average goodput and reduced completion time compared with the default configuration across the five network profiles. The new instrumented experiments also showed higher mean goodput for K20 under mild, moderate, severe and handover conditions, while baseline goodput remained almost unchanged. After Holm correction, the improvements were statistically significant under moderate, severe and handover conditions, but not under mild or baseline conditions.

The offline packet-gap and threshold analysis highlighted the trade-off between avoiding premature loss declarations and delaying packet-threshold detection. The new qlog analysis achieved 100% attribution coverage and showed differences in packet-based and time-based loss attribution between stock and K20.

The static K=20 and K=100 experiments showed higher mean goodput than their respective stock baselines in the moderate-profile datasets. In the final matrix, the threshold-only `dynamic` variant achieved higher mean goodput than stock in every impaired profile, with gains ranging from 6.20% to 27.32%, but remained below static K20. This is consistent with its reactive adaptation: the threshold is raised only after evidence of spurious loss arrives, potentially after the congestion window has already been reduced. Adding congestion-state rollback through Dynamic Undo produced the highest mean goodput among the tested variants in all four impaired profiles, while baseline goodput remained effectively unchanged.

The video workload extended the evaluation beyond bulk goodput to startup delay, playback stalls, delivered bitrate and a modelled QoE score. In the final four-variant video matrix, dynamic_undo achieved the highest mean bitrate on every impaired profile and significantly higher QoE than stock under mild and moderate conditions. Its QoE advantage over stock was not statistically significant under severe or handover conditions. Under the contract QoE formula, stock had a slightly higher mean handover QoE than dynamic_undo because of the quality-switch penalty. The ranking under handover changed across the alternative QoE weight sets, while the mild, moderate and severe rankings remained stable.

The video-only undo ablation, with K fixed at 3, shows that congestion undo alone provides most of the bitrate and QoE improvement under mild and moderate conditions. Adding adaptive K provides further bitrate gains, with the clearest statistically significant difference between undo and dynamic_undo occurring under moderate conditions. At handover, dynamic_undo has higher mean QoE than undo, although the difference is not statistically significant after correction. A separate 25-run bulk-transfer undo-only ablation, also with K fixed at 3, found statistically significant goodput improvements over stock under mild (+83.44%), moderate (+80.96%), and severe (+51.97%) conditions after Holm correction. The baseline difference was negligible, and the handover improvement (+64.08%) was not statistically significant after correction. This provides independent evidence that congestion-state rollback contributes to bulk-transfer gains without adaptive K. The bulk ablation was run in a separate session from the original 175-run stock matrix, so session-to-session variation remains a limitation.

TCP performed better than both QUIC configurations in the impaired profiles in the earlier comparison. Overall, the results suggest that modifying QUIC loss detection can improve performance under some impaired network conditions, and that these effects can also be reflected in video playback metrics. Further controlled experiments, additional repetitions and analysis of video-run qlogs are needed to establish the effectiveness and generality of these findings.
