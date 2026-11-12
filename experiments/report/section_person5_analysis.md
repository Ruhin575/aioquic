# Experiment Orchestration, Statistical Analysis and Results

## 1. Overview

This section presents the experiment orchestration and analysis performed to evaluate QUIC recovery behaviour under packet reordering and impaired network conditions.

The analysis consists of four parts:

1. Offline analysis of packet gaps and spurious loss indicators.
2. Evaluation of packet-threshold trade-offs.
3. Performance evaluation of the dynamic recovery implementation.
4. Congestion-window behaviour across repeated dynamic experiments.

## 2. Offline Packet-Gap Analysis

Historical server-side qlogs from the `threshold_20` and `huge_threshold_100` datasets were analysed.

The analysis covered 13,228 declared packet-loss events. Of these, 12,204 were identified as spurious-loss indicators using subsequent acknowledgements.

The aggregate spurious-loss indicator rate was approximately 92.26%.

The analysis also examined the packet-number gap between a declared-lost packet and the largest acknowledged packet at the time of loss declaration.

The results showed that packet reordering can produce substantial packet-number gaps. The observed gap ranges varied across network profiles and datasets.

One negative-gap observation was retained in the validated dataset rather than discarded. It was identified in `threshold_20`, severe profile, run 5, for packet number 7. The available qlog information was insufficient to establish the exact reason for this observation.

## 3. Packet-Threshold Trade-off Analysis

An offline analysis was performed to evaluate candidate packet thresholds K = 3, 5, 10, 20, 50 and 100.

For each candidate K, the observed acknowledgement timeline was replayed to determine when the packet-threshold condition would have been crossed.

Since the historical data does not provide definitive ground truth for genuine packet loss, losses without an observed late acknowledgement were treated as a proxy rather than confirmed genuine losses.

The analysis revealed a trade-off:

- Larger K values increased the number of spurious-loss indicators for which the candidate packet threshold would not have been crossed before the observed late acknowledgement.
- Larger K values also increased the delay before the packet-threshold condition was crossed for the no-observed-late-ACK proxy packets.

For example, the pooled median positive crossing delays increased substantially as K increased. At K=20, the median delays were approximately 99 ms for moderate conditions and 130 ms for severe conditions. At K=50, they increased to approximately 307 ms and 396 ms, respectively.

The run-to-run analysis also showed variability in the results. K=20 provided a useful candidate for further evaluation, while K=50 and K=100 represented more aggressive threshold settings.

These measurements are offline counterfactual estimates. They do not simulate the complete QUIC recovery process, including retransmissions, congestion control and changes to subsequent ACK timelines.

## 4. Dynamic Recovery Experiments

Three dynamic recovery experiments were conducted using a 10 MB file under the moderate network profile.

All three transfers completed successfully, and their SHA-256 checksums passed.

| Run | Download time (s) | Goodput (Mbps) | Adaptation events |
|---|---:|---:|---:|
| 1 | 88.17 | 0.951 | 461 |
| 2 | 81.71 | 1.027 | 458 |
| 3 | 82.95 | 1.011 | 490 |

The average goodput across the three runs was approximately 0.996 Mbps, and the average completion time was approximately 84.28 seconds.

Across the three server-side qlogs, 1,409 `recovery:k_adapted` events were recorded.

These events include calls where the adaptive threshold remained unchanged. Therefore, they should not be interpreted as 1,409 actual threshold increases.

The observed actual increases were 65, 59 and 64 in runs 1, 2 and 3, respectively.

The qlogs did not record every internal threshold-decay operation. Consequently, the complete adaptive threshold timeline could not be reconstructed from the available logs.

## 5. Performance Comparison

The performance comparison used 10 MB transfers under the moderate network profile.

| Configuration | Runs | Mean goodput (Mbps) | Sample SD (Mbps) | Mean completion time (s) |
|---|---:|---:|---:|---:|
| Stock, K20 dataset | 5 | 0.9924 | 0.0650 | 84.81 |
| K=20 | 5 | 1.2802 | 0.0727 | 65.70 |
| Stock, K100 dataset | 5 | 0.9784 | 0.0405 | 85.86 |
| K=100 | 5 | 1.3634 | 0.1666 | 62.25 |
| Dynamic | 3 | 0.9963 | 0.0401 | 84.28 |

All reported transfers passed SHA-256 validation.

K=100 achieved the highest mean goodput in the collected results, followed by K=20. However, K=100 also showed greater run-to-run variability.

The dynamic configuration achieved mean goodput close to the two stock baselines in this three-run experiment.

The stock baselines belong to separate experiment datasets, and the dynamic experiment used a different run count. Therefore, these results are descriptive comparisons rather than a fully controlled statistical comparison.

Figure: `final_goodput_comparison.png`

## 6. Congestion-Window Analysis

The congestion-window behaviour of the dynamic configuration was examined using server-side `recovery:metrics_updated` qlog events.

The analysis extracted congestion-window values and timestamps from all three dynamic runs.

| Metric | Run 1 | Run 2 | Run 3 |
|---|---:|---:|---:|
| CWND samples | 18,920 | 18,591 | 19,098 |
| Initial CWND (bytes) | 12,000 | 12,000 | 12,000 |
| Minimum CWND (bytes) | 2,400 | 2,400 | 2,400 |
| Maximum CWND (bytes) | 71,532 | 37,704 | 57,724 |
| Final CWND (bytes) | 15,140 | 23,047 | 19,948 |
| Observed decrease samples | 262 | 260 | 178 |

The results show that the congestion window varied considerably during the dynamic experiments.

The number of observed CWND decreases differed between runs. These are sample-to-sample decreases and do not necessarily represent distinct congestion events.

The available measurements do not establish a causal relationship between adaptive threshold changes and congestion-window reductions.

Figures:
- `dynamic_cwnd_over_time.png`
- `dynamic_cwnd_summary.csv`

## 7. Limitations

The following limitations must be considered:

1. Historical qlogs do not contain sufficient loss-rule attribution metadata for determining whether individual losses were caused by packet-threshold detection, time-threshold detection or PTO.
2. The offline threshold analysis uses observed ACK timelines and does not simulate the complete QUIC recovery process.
3. Losses without observed late acknowledgements are proxies and cannot be treated as confirmed genuine losses.
4. The dynamic experiment consists of only three runs under the moderate profile.
5. The dynamic qlogs do not expose the complete adaptive threshold and decay timeline.
6. CWND decreases observed in qlog samples do not independently establish their cause.
7. The K=20, K=100 and dynamic performance results have different experimental groupings and run counts.

## 8. Conclusion

The offline analysis demonstrated a substantial presence of spurious-loss indicators in the historical packet traces and highlighted the trade-off between avoiding premature loss declarations and delaying packet-threshold detection.

The static threshold experiments showed higher mean goodput for K=20 and K=100 than their respective stock baselines in the moderate-profile dataset.

The three dynamic experiments successfully demonstrated the operation of the adaptive recovery configuration, including repeated threshold-adaptation events and measurable congestion-window variation.

However, the dynamic configuration did not demonstrate a clear goodput improvement over stock QUIC in the available three-run comparison.

Further controlled experiments, complete threshold-decay instrumentation and loss-rule attribution are needed before making stronger conclusions about the effectiveness of dynamic recovery.