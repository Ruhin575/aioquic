# Qlog Findings

## 1. Experiment Context

- **aioquic base:** Upstream 1.7.0 with P1's commit `ae11a4f` (packet-threshold environment variable).
- **Analyzed side:** Server qlog. During a download, the server is the sender.
- **Collection date:** 2026-10-22.
- **Sample variant:** `p3sample`.
- **Workload:** One 10 MB download per profile.

## 2. Real Qlogs Examined

| Profile  | Qlog file                                               |         Size |
| -------- | ------------------------------------------------------- | -----------: |
| Baseline | `server-qlog/p3sample/baseline/1/54b8608fa256ebd1.qlog` |  8,785,071 B |
| Moderate | `server-qlog/p3sample/moderate/1/3f16d66dec13fada.qlog` | 12,545,559 B |
| Severe   | `server-qlog/p3sample/severe/1/cb36633815316d14.qlog`   | 11,775,851 B |

The paths above are relative to `experiments/transfer/`.

**Evidence labels**

- **Verified:** Checked against the real sample qlogs listed above.
- **Source:** Inferred from or confirmed by inspecting aioquic source code, but not independently verified in the real qlogs.
- **To verify:** Requires further inspection or testing.

## 3. Qlog Format and Event Findings

|  # | Question                                    | Finding                                                                                                                                                                                                                       | Status        |
| -: | ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------- |
|  1 | File format                                 | JSON using qlog version `0.3`. Each connection produces a file named `<ODCID>.qlog`. All three files parsed without skipped-event warnings, and each run folder contained exactly one qlog.                                   | **Verified**  |
|  2 | Event structure                             | Events use dictionaries with `name`, `time` and `data` fields.                                                                                                                                                                | **Verified**  |
|  3 | Timestamp behavior                          | Event timestamps are interpreted as absolute wall-clock milliseconds. The moderate qlog spans approximately 92 seconds, consistent with the reported 91.5-second download duration.                                           | **Verified**  |
|  4 | `packet_sent`                               | Relevant fields include `header.packet_number`, `header.packet_type` and `raw.length`. The baseline contains 10,226 application-space packets and 10,228 packet rows in total, with two additional initial/handshake packets. | **Verified**  |
|  5 | `packet_lost`                               | The event data contains `type` and `packet_number`. The sample counts are 794 declared losses for moderate, 630 for severe and zero for baseline.                                                                             | **Verified**  |
|  6 | ACK range boundaries                        | Baseline sent and acknowledged row counts match at 10,228 each. This is consistent with inclusive ACK ranges `[start, end]`.                                                                                                  | **Verified**  |
|  7 | Late ACKs for declared-lost packets         | Later ACK frames expose packets previously declared lost. Moderate: 760 of 794 declared losses were later ACKed. Severe: 563 of 630.                                                                                          | **Verified**  |
|  8 | `metrics_updated`                           | Numeric `cwnd` and `bytes_in_flight` values are present. The sample contains 13,479 baseline, 19,206 moderate and 18,024 severe metric rows. The `cwnd` data was used for plotting.                                           | **Verified**  |
|  9 | `ssthresh` and RTT fields                   | These fields have not yet been fully inspected in the real qlogs.                                                                                                                                                             | **To verify** |
| 10 | Which side provides congestion-window data? | The server qlog represents the sender during a download and provides the congestion-window metrics used in the analysis.                                                                                                      | **Verified**  |
| 11 | Packet-number spaces                        | Multiple packet-number spaces are present. The parser maps 0-RTT and 1-RTT packets to `application`, and the analysis uses the application space.                                                                             | **Verified**  |

## 4. Sample Loss Results

| Profile  | Declared lost | Spurious | Not classified as spurious | Configured netem loss | Rough expected loss count |
| -------- | ------------: | -------: | -------------------------: | --------------------: | ------------------------: |
| Moderate |           794 |      760 |                         34 |                  0.3% |                  About 37 |
| Severe   |           630 |      563 |                         67 |                  0.5% |                  About 60 |

The rough expected counts are based on the configured loss percentage applied to approximately 12,300 moderate-profile packets and 11,900 severe-profile packets.

This is an informal consistency check, not an exact test. Network loss can affect retransmissions as well as original transmissions, so the expected count need not equal the number of declared losses that were not classified as spurious.

## 5. How Spurious Loss Is Defined

A packet is classified as a spurious loss when:

1. It is declared lost at time (L).
2. A later ACK acknowledges that same packet at time (A), where (A > L).

The detector uses this definition to count spurious losses and calculate summary statistics.

A later ACK does not necessarily mean the receiver obtained the data only once. The sender may already have retransmitted the data in a different packet.

## 6. Important Caveats

1. **Loss-detection mechanism:** `recovery:packet_lost` can represent losses detected through PTO-related retransmission behavior, time-threshold detection or packet-threshold detection. The qlog event does not directly identify which rule caused each declaration. Therefore, “declared lost” refers to a packet declared lost by the recovery logic, regardless of the specific rule. The high-threshold control run is intended to help isolate the packet-threshold effect.

2. **Bounded ACK history:** aioquic retains a bounded number of ACK ranges. A sufficiently late ACK might no longer be observable. Failure to observe a later ACK does not prove that the loss was genuine.

3. **Retransmissions:** A packet can be declared lost and subsequently acknowledged even after its data has been retransmitted in a different packet. Spurious-loss classification concerns the original packet's loss declaration, not whether the data was delivered exactly once.

4. **Client and server qlog paths:** P1's `transfers.csv` records the client qlog path. The corresponding server qlog is stored in the matching `server-qlog/` directory. The analysis workflow must resolve the corresponding server-side path correctly.

5. **Server qlog availability:** aioquic writes the server qlog when the connection has fully closed. The transfer runner must wait for the qlog to become available before attempting to analyze it. The provided `p1_wait_for_server_qlog.patch` addresses this issue if the equivalent fix has not already been applied.

6. **Sample size:** These checks use one run per profile. They validate the analysis approach and provide reference values, but they do not establish final results across repeated runs.

## 7. Remaining Work

- Inspect `ssthresh` and the RTT fields in real qlogs.
- Validate the parser and spurious-loss detector across repeated runs from the complete experiment matrix.
- Check whether the observed loss behavior remains consistent across profiles.
- Use the verified final results and plots when completing `experiments/report/section_mechanism.md`.

