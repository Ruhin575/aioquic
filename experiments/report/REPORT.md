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

## Limitations

There are a few limitations to consider when interpreting the results.

First, the experiments used five repetitions for each QUIC configuration and network profile. Although this provides an initial comparison, more repetitions would help provide a stronger understanding of performance variability.

Second, the experiments represent a limited set of network profiles and file-transfer conditions. The results may differ under other network conditions, file sizes, or configurations.

Third, the TCP results were collected separately and have different numbers of runs in some profiles. Therefore, the TCP and QUIC comparisons should be interpreted with this difference in mind.

Finally, the measured improvements in average goodput and completion time do not by themselves establish statistical significance. The results show the behavior observed in these experiments, rather than guaranteeing the same performance in all mobile networks.

## Conclusion

In our experiments, increasing the loss detection threshold to 20 gave QUIC a higher average goodput and a shorter completion time than the default configuration in all five network profiles, with the biggest gains under mild and moderate impairment. At baseline there was almost no difference. TCP still performed better than both QUIC configurations in the impaired profiles. Spurious loss rates stayed high in all the impaired profiles, so the cause still needs a closer look at the logs.
````