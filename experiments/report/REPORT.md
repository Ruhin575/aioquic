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

## Limitations

There are several limitations to consider when interpreting the results.

First, the new instrumented goodput experiments used five repetitions for each QUIC configuration and network profile. Although this provides an initial comparison, more repetitions would help provide a stronger understanding of performance variability.

Second, the experiments represent a limited set of network profiles and file-transfer conditions. The results may differ under other network conditions, file sizes, or configurations.

Third, the TCP results were collected separately and have different numbers of runs in some profiles. Therefore, the TCP and QUIC comparisons should be interpreted with this difference in mind.

Fourth, the offline packet-threshold analysis replays observed ACK timelines and does not simulate the complete QUIC recovery process. Losses without observed late acknowledgements are treated as proxies rather than confirmed genuine losses.

Fifth, the dynamic recovery evaluation consists of only three runs under the moderate network profile. The available qlogs do not expose the complete adaptive threshold and decay timeline. Therefore, the dynamic results are preliminary and do not establish a clear performance improvement over stock QUIC.

Finally, CWND decreases observed in qlog samples do not independently establish their cause or demonstrate a causal relationship with adaptive threshold changes. The earlier performance results were also not accompanied by statistical significance tests. The new instrumented goodput results use five repetitions and should be treated as preliminary.

## Conclusion

The earlier performance experiments showed that increasing the packet loss detection threshold to 20 improved average goodput and reduced completion time compared with the default configuration across the five network profiles. The new instrumented experiments also showed higher mean goodput for K20 under mild, moderate, severe and handover conditions, while baseline goodput remained almost unchanged. After Holm correction, the improvements were statistically significant under moderate, severe and handover conditions, but not under mild or baseline conditions.

The offline packet-gap and threshold analysis highlighted the trade-off between avoiding premature loss declarations and delaying packet-threshold detection. The new qlog analysis achieved 100% attribution coverage and showed differences in packet-based and time-based loss attribution between stock and K20.

The static K=20 and K=100 experiments showed higher mean goodput than their respective stock baselines in the moderate-profile datasets. However, the three-run dynamic recovery experiment did not demonstrate a clear goodput improvement over stock QUIC. Its congestion-window measurements showed considerable variation, but did not establish a causal relationship between threshold adaptation and congestion-window changes.

TCP performed better than both QUIC configurations in the impaired profiles in the earlier comparison. Overall, the results suggest that modifying QUIC loss detection can improve performance under some impaired network conditions, but further controlled experiments are needed to establish the effectiveness of dynamic recovery and the generality of these findings.