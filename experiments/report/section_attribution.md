# Loss Rule Attribution Analysis

## 1. Objective

The objective of loss rule attribution is to identify which loss detection rule declared a QUIC packet lost. This helps distinguish packet-threshold-based loss detection from time-threshold-based loss detection and other mechanisms such as PTO.

The attribution analysis uses the sender-side (server) qlogs for download experiments.

## 2. Methodology

The analysis pipeline consists of the following steps:

1. Parse server-side qlogs using `experiments/analysis/parse_qlog.py`.
2. Extract packet loss events (`recovery:packet_lost`).
3. Preserve the attribution metadata associated with each event:
   - `rule`
   - `by_packet`
   - `by_time`
4. Run `experiments/analysis/analyze_rule_attribution.py` over the result directories.
5. Generate two outputs:
   - `attribution_summary.csv`: per-qlog loss and attribution statistics.
   - `attribution_events.csv`: event-level packet numbers, timestamps, and attribution metadata.

An event is considered attributed when its qlog contains usable rule metadata. Events without this metadata are recorded as `unavailable`, rather than being assigned an inferred rule.

## 3. Historical Dataset Results

The existing historical qlogs were analysed for two result directories.

| Dataset | Server qlogs processed | Total loss events | Attributed events | Unavailable events | Attribution coverage |
|---|---:|---:|---:|---:|---:|
| `huge_threshold_100` | 50 | 26,489 | 0 | 26,489 | 0% |
| `threshold_20` | 50 | 27,366 | 0 | 27,366 | 0% |
| **Total** | **100** | **53,855** | **0** | **53,855** | **0%** |

All 100 qlogs were processed successfully, with no parsing failures.

Some baseline runs contained no loss events. These runs have zero losses and therefore no applicable attribution coverage.

## 4. Interpretation and Limitation

The historical qlogs contain packet loss events, but their `recovery:packet_lost` event data does not include the fields `rule`, `by_packet`, or `by_time`.

Consequently, the analysis cannot determine which loss detection rule declared these packets lost. All historical loss events are therefore marked as `unavailable`.

This does not imply that packet-threshold, time-threshold, or PTO mechanisms were never triggered. It means that the available historical logs do not contain sufficient metadata to establish which mechanism declared each loss.

We do not infer the loss detection rule from packet numbers or event timestamps, since doing so would not provide reliable attribution.

## 5. Use of Historical Data

Although rule-wise attribution is unavailable, the historical qlogs can still be used for analyses supported by their recorded events, including:

- Packet loss counts.
- Packet-level loss behaviour.
- Spurious-loss analysis, where the required ACK information is available.
- Comparisons of loss behaviour across network profiles and experiment variants.

Rule-wise attribution is excluded from conclusions based on these historical qlogs.

## 6. Requirements for New Instrumented Experiments

New experiments must be generated using the instrumented aioquic implementation that records loss attribution metadata.

For each `recovery:packet_lost` event, the raw qlog should contain:

- `rule`: the rule responsible for declaring the packet lost.
- `by_packet`: packet-threshold attribution information, when applicable.
- `by_time`: time-threshold attribution information, when applicable.

The analysis pipeline should then be validated on newly generated qlogs by checking that:

1. The raw qlog contains the attribution fields.
2. `parse_qlog.py` preserves these fields.
3. `analyze_rule_attribution.py` reports the corresponding rule counts.
4. Attribution coverage is calculated from the events with available metadata.

Until these instrumented results are available, rule-wise attribution remains an open part of the analysis.
