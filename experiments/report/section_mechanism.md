# Performance Analysis of QUIC under Packet Reordering

**Contributors:** Person 3 (Loss Mechanism Analysis); Pooja (Video Workload and QoE Analysis, with Amrutha for the testbed)

> **PRELIMINARY REPORT:** The loss-mechanism results currently include one 10 MB sample download per profile (`p3sample`, collected on 2026-10-22). The video section contains placeholders for results from the complete experiment matrix. Replace all preliminary values and `[X]` placeholders with verified results from the required real runs before finalizing this report. Files prefixed with `fake_` are test fixtures only and must never be treated as experimental results.

## 1. Introduction

Packet reordering can occur on mobile network paths because of mechanisms such as carrier aggregation, PDCP processing, and handovers. When a transport protocol interprets a delayed packet as lost, it may trigger congestion-control responses even though the packet eventually arrives. In QUIC, this can lead to spurious loss declarations and unnecessary congestion-window reductions.

Bulk-download experiments help characterize the transport-level effects of reordering through metrics such as goodput, declared losses, spurious losses, and congestion-window behaviour. However, raw goodput does not fully describe the impact on an application such as video streaming. A video player buffers content ahead of playback and adapts its selected bitrate according to measured download throughput. A reduction in throughput may therefore appear as lower video quality, increased startup delay, playback stalls, or some combination of these effects.

This study examines both levels:

1. **Transport-level behaviour:** how packet reordering interacts with QUIC loss detection and congestion control.
2. **Application-level behaviour:** how the resulting network performance affects video playback and Quality of Experience (QoE).

The central question is whether the transport-level effects observed in bulk transfers translate into measurable changes in video playback, and whether alternative QUIC configurations mitigate those effects.

## 2. QUIC Loss-Detection Mechanism

### 2.1 The loss-detection cascade

QUIC loss detection (RFC 9002, Section 6.1.1) can declare a packet lost when a sufficiently newer packet has been acknowledged and the packet-number gap reaches the configured packet threshold, `kPacketThreshold` (3 in the current configuration).

On mobile paths, packet reordering can cause a packet to arrive late without being lost. The sender may then go through the following sequence:

1. Packets arrive out of order because of network effects such as carrier aggregation, PDCP processing, or handovers.
2. The sender receives an ACK for a newer packet while an older packet remains unacknowledged. If the packet-number gap reaches the threshold, the sender declares the older packet lost.
3. The congestion controller treats the loss declaration as a congestion signal and reduces the congestion window (`cwnd`).
4. An ACK for the supposedly lost packet arrives later. The loss is classified as **spurious**, meaning that the original packet was acknowledged after being declared lost.

This can cause an unnecessary congestion-window reduction when the loss declaration was caused by reordering rather than actual packet loss.

### 2.2 Packet-sequence example

```text
Sender                                      Receiver
  | send pkt 1,2,3,4,5,6,7 --------------------> |
  |                                               | pkt 3 is delayed
  | <-------------------- ACKs for 1,2,4,5,6,7 -- |
  | largest acknowledged = 7                     |
  | packet 3 meets the packet-threshold condition |
  | pkt 3 declared LOST; congestion response      |
  | <-------------------- ACK including pkt 3 --- |
  | pkt 3 acknowledged after being declared lost |
  |                  SPURIOUS LOSS                |
```

The example illustrates the mechanism. The actual declaration depends on the packet-number gap and the recovery implementation's loss-detection rules.

### 2.3 Definition of spurious loss

A spurious loss is a packet declared lost at time \(L\) and subsequently acknowledged at time \(A\), where \(A > L\).

A declared loss may result from packet-threshold detection, time-threshold detection, or PTO-related recovery behaviour. The data belonging to a declared-lost packet may already have been retransmitted in another packet. Therefore, a late ACK does not mean the data was delivered only once. Additionally, aioquic retains a bounded ACK history, so sufficiently late acknowledgements may no longer be observable.

## 3. Experimental Methodology

### 3.1 Shared testbed and network profiles

The experiments use the same namespace topology, netem profiles, 15 Mbit/s link, and server as the bulk-transfer matrix. The network profiles are:

- Baseline
- Mild
- Moderate
- Severe
- Handover

The QUIC variants considered in the video workload are stock, K20, K100, and dynamic. The number of runs per cell is **[X]**. Client-side and server-side qlogs are retained for every run.

### 3.2 Bulk-download workload

The loss-mechanism analysis uses sender-side (server) qlogs from the application packet-number space for a 10 MB download over the emulated 15 Mbit/s link.

The bulk-transfer analysis records:

- Goodput
- Number of packets declared lost
- Number and rate of spurious losses
- Median delay between loss declaration and late acknowledgement
- Congestion-window behaviour
- Cumulative acknowledged QUIC packet bytes

The packet-byte metric includes QUIC packet headers and retransmitted copies. It is not a measure of unique file-payload bytes delivered.

### 3.3 Video content and workload

The video workload uses one 2-minute test video with five renditions: 0.25, 0.5, 1, 2.5, and 5 Mbps. Each rendition is divided into 4-second segments, with one manifest containing keyframe-aligned representations. The content is encoded at constant bitrate so that each rendition's measured bitrate matches its nominal value. Verify the real bitrates using ffprobe or file sizes and record them here: **[X: verified real bitrates]**.

The bitrate ladder starts below 1 Mbps because stock QUIC reaches only approximately 0.5 to 3 Mbps on the impaired profiles in the bulk matrix (base commit `342b224`). This provides lower representations that the player can select when throughput is constrained.

### 3.4 Video client and playback simulation

The video client, `stream_client.py`, uses one persistent HTTP/3 connection (aioquic, Cubic) and requests segments sequentially.

The client uses throughput-based bitrate adaptation:

- It computes the harmonic mean of the last three segment-download throughput samples.
- It applies a safety factor of 0.8.
- The first segment is requested at the lowest bitrate rung.

The playback buffer has a maximum capacity of **12 seconds**. This value is based on the dash.js `stableBufferTime` setting and is fixed before the experiment matrix so that all variants use the same buffer cap. Confirm that this is the final agreed value before running the complete matrix.

Playback is simulated in real time. Video decoding is not performed and audio is ignored.

- **Startup delay:** measured from before the QUIC handshake until one segment has been buffered.
- **Stall start:** occurs when the playback buffer reaches zero before the video has finished downloading.
- **Stall end:** occurs when one segment has been buffered again.

### 3.5 Video metrics and QoE

The video workload records the following metrics per run:

- Startup delay
- Stall count
- Total stall time
- Average bitrate
- Number of quality switches
- QoE score

The proposed QoE model is:

\[
\mathrm{QoE}
=
\mathrm{avg\_bitrate\_mbps}
- 0.3 \times \mathrm{stalls}
- 0.05 \times \mathrm{stall\_seconds}
- 0.1 \times \mathrm{quality\_switches}
\]

The final weights must be confirmed and recorded here: **[X: final QoE weights]**. Since the weights are a modelling choice, include a sensitivity check to determine whether the conclusions hold across reasonable alternative weights.

### 3.6 Validation

The video implementation has 21 offline tests covering the ABR rule, buffer and stall accounting, and manifest parser. Record the final test result and any changes made before the experiment matrix: **[X: validation result]**.

For the baseline trace without netem, record:

- Startup delay: **[X] s**
- Number of stalls: **[X]**
- Number of segments until the top rung is reached: **[X]**

The baseline target is startup below 3 seconds, no stalls, and selection of the top bitrate rungs.

## 4. Bulk-Transfer Results: Loss Mechanism Analysis

### 4.1 Preliminary measurements

**Data source:** Sender-side (server) qlog, application packet-number space, for a 10 MB download over the emulated 15 Mbit/s link.

The values below are preliminary and come from one sample download per profile (`p3sample`, collected on 2026-10-22). Replace them with results from the complete experiment matrix (5 runs per cell) before finalizing the report.

| Profile | Goodput (Mbps) | Declared lost | Spurious | Spurious rate | Median late-ACK delay |
|---|---:|---:|---:|---:|---:|
| Baseline | 13.34 | 0 | 0 | 0% | N/A |
| Mild | Not run yet | — | — | — | — |
| Moderate | 0.92 | 794 | 760 | 95.7% | [X] ms |
| Severe | 0.81 | 630 | 563 | 89.4% | [X] ms |
| Handover | Not run yet | — | — | — | — |

The median late-ACK delay should be obtained from the corresponding JSON summary in `experiments/analysis/sample_data/` after running `detect_spurious.py` with the `--summary` option.

### 4.2 Congestion-window behaviour

**Figure 2: Congestion Window Over Time — Baseline vs Moderate**

**File:** `plots/plot2_cwnd.png`

The preliminary figure compares the baseline and moderate profiles using one sample run per profile. For the final report, use the median-goodput run of the stock variant and record its run identifier.

In the baseline run, the congestion window grows rapidly during slow start, reaches approximately 290 KB within 0.5 seconds, and later grows to around 391 KB without declared losses. In the moderate run, the congestion window remains below approximately 35 KB and repeatedly falls to around 3–5 KB. These reductions coincide with clusters of declared losses, 760 of the 794 declared losses being classified as spurious.

Each panel uses its own time and congestion-window scale.

### 4.3 Cumulative acknowledged packet bytes

**Figure 4: Cumulative Acknowledged Packet Bytes — Baseline vs Severe**

**File:** `plots/plot4_cumulative.png`

The preliminary baseline transfer finishes in approximately 6 seconds, while the severe-profile transfer takes approximately 103 seconds and progresses at a much lower rate.

The plotted quantity counts acknowledged QUIC packet bytes, including packet headers and retransmitted copies. It is not a measure of unique file-payload bytes delivered.

### 4.4 Preliminary interpretation

- **Large throughput reduction:** Goodput falls from approximately 13.3 Mbps in the baseline run to 0.92 Mbps in the moderate run, a reduction of about 93%. The baseline run has no declared losses. This suggests that the observed throughput reduction is not explained simply by sustained link saturation.
- **High spurious-loss rate:** Approximately 95.7% of declared losses in the moderate run and 89.4% in the severe run were classified as spurious.
- **Random-loss consistency check:** The 34 moderate and 67 severe declared losses that were not classified as spurious can be compared with the configured netem loss rates of 0.3% and 0.5%. This is only a rough consistency check; it does not independently prove that these packets were genuinely lost.
- **Packet-threshold attribution:** The qlog does not directly identify which loss-detection rule caused each loss declaration. The high-threshold control experiment is needed to help isolate the effect of packet-threshold detection. Record the control-run goodput for each profile here: **[X]**.
- **Congestion-window reductions:** Number of congestion-window reductions following spurious loss declarations in the moderate run: **[X]**. Fill this using the verified analysis output.
- **Study limitations:** These observations come from one run per profile and only the application packet-number space. A single run is one sample of a stochastic network emulation, so the results must be validated against the complete experiment matrix.

## 5. Video Results: QoE under Reordering

### 5.1 Results table

Populate the following table using real runs only. Do not use `fake_video_results.csv` or other fake data as experimental results.

| Profile | Variant | Startup (s) | Stalls / run | Stall time (s) | Avg bitrate (Mbps) | Switches | QoE |
|---|---|---:|---:|---:|---:|---:|---:|
| Baseline | Stock | [X] | [X] | [X] | [X] | [X] | [X] |
| Mild | Stock | [X] | [X] | [X] | [X] | [X] | [X] |
| Moderate | Stock | [X] | [X] | [X] | [X] | [X] | [X] |
| Severe | Stock | [X] | [X] | [X] | [X] | [X] | [X] |
| Handover | Stock | [X] | [X] | [X] | [X] | [X] | [X] |
| Baseline | K20 | [X] | [X] | [X] | [X] | [X] | [X] |
| Mild | K20 | [X] | [X] | [X] | [X] | [X] | [X] |
| Moderate | K20 | [X] | [X] | [X] | [X] | [X] | [X] |
| Severe | K20 | [X] | [X] | [X] | [X] | [X] | [X] |
| Handover | K20 | [X] | [X] | [X] | [X] | [X] | [X] |
| Baseline | K100 | [X] | [X] | [X] | [X] | [X] | [X] |
| Mild | K100 | [X] | [X] | [X] | [X] | [X] | [X] |
| Moderate | K100 | [X] | [X] | [X] | [X] | [X] | [X] |
| Severe | K100 | [X] | [X] | [X] | [X] | [X] | [X] |
| Handover | K100 | [X] | [X] | [X] | [X] | [X] | [X] |
| Baseline | Dynamic | [X] | [X] | [X] | [X] | [X] | [X] |
| Mild | Dynamic | [X] | [X] | [X] | [X] | [X] | [X] |
| Moderate | Dynamic | [X] | [X] | [X] | [X] | [X] | [X] |
| Severe | Dynamic | [X] | [X] | [X] | [X] | [X] | [X] |
| Handover | Dynamic | [X] | [X] | [X] | [X] | [X] | [X] |

Report the number of runs per cell and the aggregation method used. Error bars in the figures should represent 95% confidence intervals over the runs in each cell.

### 5.2 QoE and bitrate figures

- **Figure 5 — QoE per profile and variant:** `plot5_qoe.png`. Caption: **[X]**
- **Figure 6 — Average bitrate:** `plot6_bitrate.png`. Caption: **[X]**
- **Figure 7 — Stalls per run:** `plot7_stalls.png`. Caption: **[X]**
- **Figure 8 — Playback timeline:** `plot8_timeline.png`. Show buffer level and bitrate over time for one stock run and one K20 run under the same profile. Caption: **[X]**

All figures should be accompanied by their CSV data and alt-text files.

### 5.3 Video interpretation

Use the verified experiment matrix to address the following questions:

1. **Goodput-to-QoE impact:** How much of the goodput reduction observed in the bulk matrix appears as lower video bitrate, and how much appears as playback stalls?
2. **Variant comparison:** Does K20 improve QoE in the profiles where it improved goodput (reported as +23% to +35% in the bulk results)? Does dynamic go further? Include K100 in the comparison.
3. **Loss mechanism in video runs:** What fraction of declared losses in the video runs are spurious, based on server qlogs analysed using `analyze_runs.py`?
4. **Loss-rule attribution:** Which rule—packet threshold, time threshold, or PTO-related recovery—declares the losses in the video runs? Use Reethika's attribution table.
5. **Buffer behaviour:** How do bitrate adaptation and the playback buffer interact under each profile? Distinguish a quality reduction from an actual playback stall.

Do not infer causation from a correlation alone. Support explanations with the corresponding run-level measurements and qlog evidence.

## 6. Cross-Workload Discussion

This section connects the transport-level results in Section 4 with the application-level results in Section 5.

### 6.1 From goodput to video quality

Compare bulk goodput with average video bitrate for the same network profile and QUIC variant. Determine whether a reduction in available throughput primarily causes the player to select a lower representation, or whether it also causes the playback buffer to empty and produce stalls.

A lower average video bitrate does not necessarily imply playback interruption: a player may preserve continuous playback by selecting a lower representation. Conversely, a shortfall in segment-download throughput can cause stalls if the playback buffer is depleted before the next segment is available.

### 6.2 Do transport improvements translate into QoE improvements?

Compare stock, K20, K100, and dynamic using both transport-level and video-level metrics. Determine whether improvements in goodput are accompanied by:

- Higher average video bitrate
- Lower startup delay
- Fewer stalls or less total stall time
- Fewer or more frequent quality switches
- Higher QoE

An improvement in one metric does not guarantee improvement in every other metric. Discuss any trade-offs observed in the data.

### 6.3 Loss behaviour during video streaming

Use the server qlogs from the video runs to calculate the spurious-loss share and relate it to bitrate adaptation and playback behaviour. Where possible, connect the observed losses to the loss-rule attribution results. State clearly when the available evidence cannot distinguish packet-threshold, time-threshold, and PTO-related loss declarations.

## 7. Literature Comparison

Compare the observed mechanism with the explanations in Marx (2023) and Palmer (2024).

Address the following questions:

- Do the papers describe a similar relationship between packet reordering, spurious loss detection, congestion-window reduction, and throughput?
- Which aspects of the mechanism observed in the qlogs are consistent with their explanations?
- What evidence from the bulk-transfer and video experiments supports or contradicts those explanations?

Complete this comparison using the relevant findings from the papers and the verified results from the full experiment matrix. Avoid claiming that the experiments establish more than the measured evidence supports.

## 8. Limitations

### 8.1 Transport-level analysis

- A declared loss may result from packet-threshold detection, time-threshold detection, or PTO-related recovery behaviour.
- The data belonging to a declared-lost packet may already have been retransmitted in another packet. A late ACK therefore does not imply that the data was delivered only once.
- aioquic retains a bounded ACK history, so sufficiently late acknowledgements may no longer be observable.
- The preliminary observations come from one run per profile and only the application packet-number space. The complete experiment matrix is required to assess variability.

### 8.2 Video workload

- Playback is simulated: no video decoding is performed, audio is ignored, and the experiment represents one viewer using one connection.
- The content is synthetic and encoded at constant bitrate. Real video has variable segment sizes, which can change throughput samples and adaptation behaviour.
- The QoE weights are a modelling choice. Conclusions should be checked across reasonable alternative weights: **[X: sensitivity-check result]**.
- The final number of runs per cell is **[X]**. Differences between close variants may not be statistically significant; report the results of the statistical analysis.
- The buffer cap and all other client parameters must remain fixed across variants and profiles for a fair comparison.

## 9. Conclusion

**[X: Complete this section after the full experiment matrix has been analysed.]**

Summarize the principal transport-level findings, the effect of packet reordering on loss detection and congestion control, and the extent to which those effects translate into video QoE degradation. State which QUIC variants perform better under which network profiles, identify relevant trade-offs, and distinguish statistically supported findings from observations that remain inconclusive.
