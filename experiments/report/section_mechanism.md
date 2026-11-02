# Loss Mechanism Analysis

**Author:** Person 3

> **PRELIMINARY:** The results below come from one 10 MB download per profile (`p3sample`, collected on 2026-10-22). Replace them with results from the complete experiment matrix (5 runs per cell) before finalizing the report. Fields marked `[X]` still need data.

## 1. The Cascade

QUIC loss detection (RFC 9002, Section 6.1.1) can declare a packet lost when a sufficiently newer packet has been acknowledged and the packet-number gap reaches the configured packet threshold, `kPacketThreshold` (3 in the current configuration).

On mobile paths, packet reordering can cause a packet to arrive late without being lost. The sender may then go through the following sequence:

1. Packets arrive out of order because of network effects such as carrier aggregation, PDCP processing, or handovers.
2. The sender receives an ACK for a newer packet while an older packet remains unacknowledged. If the packet-number gap reaches the threshold, the sender declares the older packet lost.
3. The congestion controller treats the loss declaration as a congestion signal and reduces the congestion window (`cwnd`).
4. An ACK for the supposedly lost packet arrives later. The loss is classified as **spurious**, meaning that the original packet was acknowledged after being declared lost.

This can cause an unnecessary congestion-window reduction when the loss declaration was caused by reordering rather than actual packet loss.

## 2. Packet Sequence Example

```text
Sender                                      Receiver
  | send pkt 1,2,3,4,5,6,7 --------------------> |
  |                                              | pkt 3 is delayed
  | <-------------------- ACKs for 1,2,4,5,6,7 -- |
  | largest acknowledged = 7                    |
  | packet 3 meets the packet-threshold condition|
  | pkt 3 declared LOST; congestion response     |
  | <-------------------- ACK including pkt 3 --- |
  | pkt 3 acknowledged after being declared lost |
  |                 SPURIOUS LOSS                |
```

The example illustrates the mechanism. The actual declaration depends on the packet-number gap and the recovery implementation's loss-detection rules.

## 3. What We Measured

**Definition:** A spurious loss is a packet declared lost at time \(L\) and subsequently acknowledged at time \(A\), where \(A > L\).

**Data source:** Sender-side (server) qlog, application packet-number space, for a 10 MB download over the emulated 15 Mbit/s link.

| Profile | Goodput (Mbps) | Declared lost | Spurious | Spurious rate | Median late-ACK delay |
|---|---:|---:|---:|---:|---:|
| Baseline | 13.34 | 0 | 0 | 0% | N/A |
| Mild | Not run yet | — | — | — | — |
| Moderate | 0.92 | 794 | 760 | 95.7% | [X] ms |
| Severe | 0.81 | 630 | 563 | 89.4% | [X] ms |
| Handover | Not run yet | — | — | — | — |

The median late-ACK delay should be obtained from the corresponding JSON summary in `experiments/analysis/sample_data/` after running `detect_spurious.py` with the `--summary` option.

**Limitations:** A declared loss may result from packet-threshold detection, time-threshold detection, or PTO-related recovery behavior. The data belonging to a declared-lost packet may already have been retransmitted in another packet. Therefore, a late ACK does not mean the data was delivered only once. Additionally, aioquic retains a bounded ACK history, so sufficiently late acknowledgements may no longer be observable.

## 4. Figures

### Figure 2: Congestion Window Over Time — Baseline vs Moderate

**File:** `plots/plot2_cwnd.png`

The preliminary figure compares the baseline and moderate profiles using one sample run per profile. For the final report, use the median-goodput run of the stock variant and record its run identifier.

In the baseline run, the congestion window grows rapidly during slow start, reaches approximately 290 KB within 0.5 seconds, and later grows to around 391 KB without declared losses. In the moderate run, the congestion window remains below approximately 35 KB and repeatedly falls to around 3–5 KB. These reductions coincide with clusters of declared losses, 760 of the 794 declared losses being classified as spurious.

Each panel uses its own time and congestion-window scale.

### Figure 4: Cumulative Acknowledged Packet Bytes — Baseline vs Severe

**File:** `plots/plot4_cumulative.png`

The preliminary baseline transfer finishes in approximately 6 seconds, while the severe-profile transfer takes approximately 103 seconds and progresses at a much lower rate.

The plotted quantity counts acknowledged QUIC packet bytes, including packet headers and retransmitted copies. It is not a measure of unique file-payload bytes delivered.

## 5. Interpretation (Preliminary)

- **Large throughput reduction:** Goodput falls from approximately 13.3 Mbps in the baseline run to 0.92 Mbps in the moderate run, a reduction of about 93%. The baseline run has no declared losses. This suggests that the observed throughput reduction is not explained simply by sustained link saturation.
- **High spurious-loss rate:** Approximately 95.7% of declared losses in the moderate run and 89.4% in the severe run were classified as spurious.
- **Random-loss consistency check:** The 34 moderate and 67 severe declared losses that were not classified as spurious can be compared with the configured netem loss rates of 0.3% and 0.5%. This is only a rough consistency check; it does not independently prove that these packets were genuinely lost.
- **Packet-threshold attribution:** The qlog does not directly identify which loss-detection rule caused each loss declaration. The high-threshold control experiment is needed to help isolate the effect of packet-threshold detection. Record the control-run goodput for each profile here: **[X]**.
- **Congestion-window reductions:** Number of congestion-window reductions following spurious loss declarations in the moderate run: **[X]**. Fill this using the verified analysis output.
- **Study limitations:** These observations come from one run per profile and only the application packet-number space. A single run is one sample of a stochastic network emulation, so the results must be validated against the complete experiment matrix.

## 6. Input for the Literature Comparison (Person 5)

Compare the observed mechanism with the explanations in Marx (2023) and Palmer (2024):

- Do the papers describe a similar relationship between packet reordering, spurious loss detection, congestion-window reduction, and throughput?
- Which aspects of the mechanism observed in our qlogs are consistent with their explanations?
- What evidence from our experiments supports or contradicts those explanations?

Complete this comparison using the relevant findings from the papers and the verified results from the full experiment matrix.
