# Video Workload: QoE under Reordering

*Author: Pooja (with Amrutha for the testbed part). Fill every `[X]` from real runs only. The stubs (`fake_*.csv`) are never results.*

## 1. Why a video workload

The bulk-download results measure raw goodput. A video player reacts differently: it buffers ahead, adapts its bitrate, and
only the stalls and quality drops are visible to a viewer. We therefore replay the same network profiles with a DASH playback
simulator to see how reordering-induced loss detection errors turn into startup delay, stalls and lower quality.

## 2. Method

**Content.** One 2-minute test video, five renditions (0.25, 0.5, 1, 2.5 and 5 Mbps), 4 s segments, one manifest with
keyframe-aligned representations, encoded at constant bitrate so each rung's real bitrate matches its nominal value
(verified: [X: real bitrates from ffprobe or file sizes]). The ladder starts below 1 Mbps because stock QUIC reaches only
0.5 to 3 Mbps on the impaired profiles (bulk matrix, base commit 342b224).

**Client.** `stream_client.py`: one persistent HTTP/3 connection (aioquic, Cubic), sequential segment requests, throughput-based
bitrate adaptation (harmonic mean of the last 3 downloads x 0.8, first segment on the lowest rung), a 12 s playback buffer cap (the dash.js default `stableBufferTime`, its buffer target while not playing the top quality; fixed before the matrix and identical for all variants).
Playback is simulated in real time (no decoding, audio ignored). Startup delay runs from before the QUIC handshake until one
segment is buffered; a stall starts when the buffer reaches zero before the video is fully downloaded and ends when one segment is
buffered again.

**Metrics per run.** Startup delay, stall count, total stall time, average bitrate, number of quality switches, and
QoE = avg_bitrate_mbps - 0.3 x stalls - 0.05 x stall_seconds - 0.1 x quality_switches ([X: weights as finally chosen]).

**Testbed.** Same namespace topology, netem profiles, 15 Mbit link and server as the bulk matrix; variants stock, k20, k100 and
dynamic; [X] runs per cell; client and server qlogs kept for every run.

**Validation.** 21 offline tests cover the ABR rule, buffer and stall accounting and the manifest parser. Baseline trace
(no netem): startup [X] s, [X] stalls, top rung reached after [X] segments (target: under 3 s, none, top rungs).

## 3. Results

| Profile | Variant | Startup (s) | Stalls / run | Stall time (s) | Avg bitrate (Mbps) | Switches | QoE |
|---|---|---|---|---|---|---|---|
| baseline | stock | [X] | [X] | [X] | [X] | [X] | [X] |
| mild | stock | [X] | [X] | [X] | [X] | [X] | [X] |
| moderate | stock | [X] | [X] | [X] | [X] | [X] | [X] |
| severe | stock | [X] | [X] | [X] | [X] | [X] | [X] |
| handover | stock | [X] | [X] | [X] | [X] | [X] | [X] |
| (same rows for k20, k100 and dynamic) | | | | | | | |

## 4. Figures

* Figure 5 (`plot5_qoe.png`): QoE per profile and variant. Caption: [X]
* Figure 6 (`plot6_bitrate.png`): average bitrate. Caption: [X]
* Figure 7 (`plot7_stalls.png`): stalls per run. Caption: [X]
* Figure 8 (`plot8_timeline.png`): buffer level and bitrate over time for one stock and one k20 run of the same profile. Caption: [X]

All figures come with CSV data and alt-text files. Error bars are 95% confidence intervals over the runs of a cell.

## 5. Interpretation

* [How much of the goodput loss in the bulk matrix becomes lower bitrate versus stalls?]
* [Does k20 improve QoE where it improved goodput (+23 to +35% in bulk)? Does dynamic go further?]
* [Link to the mechanism: spurious-loss share of the video runs, from the server qlogs (`analyze_runs.py`).]
* [Which rule (packet, time, PTO) declares the losses in the video runs? From Reethika's attribution table.]

## 6. Limitations

* Playback is simulated: no decoding, audio ignored, one viewer, one connection.
* Synthetic content at constant bitrate; real video varies segment sizes, which changes throughput samples.
* The QoE weights are a modelling choice; conclusions should hold across reasonable weights ([X: sensitivity check]).
* [X] runs per cell; differences between close variants may not be significant (see the statistics pass).
