# Loss Mechanism Analysis

*Author: Pooja. Section 3 and the gap analysis use the Phase 0 bulk matrix (`experiments/results/threshold_20`, 5 runs per cell, 10 MB download, 15 Mbit link, Cubic, base commit 342b224). Nothing in this section waits for other people's data; the only open items are the literature comparison (Section 7) and the dynamic variants' results, which are the team's dynamic analysis (final bulk results: `dynamic_undo` is +143% mild, +107% moderate, +53% severe and +81% handover goodput over stock, `dynamic` alone +21%, +7%, +6% and +27%; `phase1_all_variants_final_5runs`).*

## 1. The cascade

QUIC loss detection (RFC 9002, Section 6.1.1) declares a packet lost when a packet sent later has been acknowledged and the unacknowledged packet is at least `kPacketThreshold` (3) packet numbers older. On mobile paths, reordering can make a packet arrive late without it being lost. The sender then goes through four steps:

1. Packets arrive out of order (carrier aggregation, PDCP, handovers).
2. The sender sees an ACK for a newer packet while an older one is still missing, and declares the older packet lost.
3. The congestion controller treats this as a congestion signal and reduces cwnd (Cubic multiplicatively decreases it).
4. The "lost" packet's ACK arrives shortly after. The loss was **spurious**, and the rate cut was unnecessary.

## 2. Packet sequence example

```
Sender                                   Receiver
  | send pkt 1,2,3,4,5,6,7 ------------>  |
  |                                       |  pkt 3 delayed in the network
  |  <---------- ACK 1,2,4,5,6,7 -------  |
  |  largest acked = 7, 7 - 3 = 4 >= 3:   |
  |  pkt 3 declared LOST, cwnd cut        |
  |  <---------- ACK 1-7 (3 arrives) ---  |
  |  pkt 3 acked AFTER being declared     |
  |  lost -> SPURIOUS LOSS                |
```

## 3. What we measured (bulk matrix, mean of 5 runs)

Definition: a spurious loss is a packet number declared lost at time L and first seen in an ACK at a later time A > L (sender-side server qlog, application packet-number space).

| Profile | Goodput stock (Mbps) | Goodput k20 (Mbps) | Gain | Declared lost, stock | Spurious, stock | Declared lost, k20 | Spurious, k20 |
|---|---|---|---|---|---|---|---|
| baseline | 13.36 | 13.35 | 0% | 0 | n/a | 0 | n/a |
| mild | 2.39 | 3.00 | +26% | 492 | 91.9% | 414 | 86.4% |
| moderate | 0.99 | 1.28 | +29% | 781 | 95.0% | 703 | 94.0% |
| severe | 0.75 | 1.02 | +35% | 708 | 91.2% | 582 | 89.5% |
| handover | 0.48 | 0.59 | +23% | 943 | 87.8% | 850 | 85.9% |

A second set with a packet threshold of 100 gives the same picture (moderate 1.36 Mbps, severe 0.95 Mbps), so the effect is capped, not simply limited by a too-small threshold. TCP on the same profiles reaches 5.3 Mbps at moderate (P2's baseline).

**Median late-ACK delay** (time between a packet being declared lost and the ACK that shows it arrived; pooled over the 5 runs, `detect_spurious.py`): stock 26 ms (mild), 26 ms (moderate), 39 ms (severe), 51 ms (handover); k20 9, 10, 17 and 28 ms. With k20 the remaining spurious declarations are wrong by only about 10 to 30 ms, which is consistent with the time rule being the one that fires.

**Congestion-window reductions** (`analyze_runs.py`, `cwnd_decrease_events`: number of times the logged cwnd decreases, per run, mean of 5 runs):

| Profile | Declared losses, stock | cwnd decreases, stock | Declared losses, k20 | cwnd decreases, k20 |
|---|---|---|---|---|
| mild | 492 | 35 | 414 | 34 |
| moderate | 781 | 112 | 703 | 109 |
| severe | 708 | 124 | 582 | 102 |
| handover | 943 | 210 | 850 | 190 |

There are many more declared losses than cwnd decreases because the controller reduces at most once per recovery period. k20 lowers declared losses by 10 to 18% but cuts the window almost as often (3% fewer on moderate, 18% fewer on severe), so most of its goodput gain is not explained by fewer cuts alone.

Limitations: "declared lost" means removed as lost by any recovery rule (packet threshold, time threshold or PTO); the data of a packet declared lost may already have been retransmitted, so a late ACK does not prove the receiver got the data only once; aioquic keeps a bounded number of ACK ranges, so a very old late ACK may be invisible.

## 4. Which rule declares the losses

At the moment a loss is declared we reconstruct the gap = (largest acknowledged packet number) - (lost packet number) from the ACK frames (`loss_gap_by_rule.py`). The packet rule can only fire when the gap reaches the threshold.

| Profile | Stock: gap >= 3 | Stock: median gap | k20: gap >= 20 | k20: median gap |
|---|---|---|---|---|
| mild | 95.7% | 14 | 50.4% | 17 |
| moderate | 87.4% | 7 | 10.1% | 8 |
| severe | 86.6% | 6 | 11.8% | 9 |
| handover | 81.9% | 5 | 5.7% | 6 |

With a threshold of 100, essentially none of the declared losses (about 8% in mild) reach a gap of 100. So most losses that remain after raising the threshold have a typical gap of only 6 to 9 packets: the packet rule cannot have declared them, and the time threshold or the PTO must have. The qlog does not say which, and some stock losses with gap >= 3 may also have been declared by the time rule. This is why a rule-attribution field is being added to `recovery.py`.

**Rule attribution from the instrumented build** (Reethika, `experiments/results/attribution_main`; 50 runs: stock and k20, 5 profiles, 5 runs each; every one of the 26,786 loss events carries a rule, coverage 100%). Counts are summed over the 5 runs; the rule categories are mutually exclusive:

| Variant | Profile | Declared losses | Packet only | Time only | Both | PTO |
|---|---|---|---|---|---|---|
| stock | mild | 2095 | 91.2% | 4.9% | 3.9% | 0.00% |
| stock | moderate | 3902 | 77.9% | 12.9% | 9.2% | 0.00% |
| stock | severe | 3321 | 77.7% | 12.6% | 9.7% | 0.03% |
| stock | handover | 4496 | 67.7% | 19.1% | 13.1% | 0.04% |
| k20 | mild | 2477 | 52.3% | 44.3% | 3.4% | 0.00% |
| k20 | moderate | 3466 | 3.7% | 93.2% | 3.0% | 0.00% |
| k20 | severe | 2823 | 12.7% | 85.2% | 2.1% | 0.00% |
| k20 | handover | 4206 | 3.4% | 95.4% | 1.2% | 0.02% |

* **Stock:** the packet rule declares most losses (68 to 91%), as the cascade in Section 1 predicts.
* **k20:** the time rule declares 93% (moderate), 85% (severe) and 95% (handover) of the losses; only mild stays mixed (52% packet, 44% time). PTO is negligible everywhere (at most 2 events).
* **Agreement with the gap analysis above.** The share of k20 losses that the packet rule could have declared (packet only plus both) is 56% mild, 7% moderate, 15% severe and 5% handover, against 50%, 10%, 12% and 6% from the independent gap reconstruction on the earlier run set. The two methods agree within a few points. The instrumented rerun also reproduces the declared-loss counts (stock moderate 780 per run against 781; the largest difference, severe, is 6%).
* Caution (as in `section_attribution.md`): this shows which rule recorded the declaration, not that the declarations are wrong. What shows they are wrong is the spurious share, which stays at 86 to 94% under k20.

**Goodput with Holm-corrected tests on the instrumented set** (Reethika's Welch tests, adjusted across the 5 profiles): k20 over stock is +32.8% moderate, +31.7% severe and +27.2% handover (all significant after correction), +19.1% mild (raw p = 0.047, adjusted p = 0.095, not significant after correction) and no difference at baseline.

## 5. Figures

**Figure 2: cwnd over time, baseline vs moderate** (`plots/figure2_cwnd_median_runs.png`). Median-goodput stock run of each profile from the Phase 0 matrix (`threshold_20`): baseline run 3 (13.36 Mbps) and moderate run 2 (0.95 Mbps), picked with `plot_mechanism.py median-run`. Each panel has its own scales. Caption: baseline grows in slow start to about 340 KB within half a second, then keeps growing slowly to 434 KB with no declared losses. Moderate reaches about 240 KB in its first 0.7 s, is cut at its first declared losses and then stays in a sawtooth below about 40 KB for the remaining 90 s; 847 of its 883 declared losses (95.9%) are spurious (green triangles), and the window drops at nearly every cluster of them. (The 240 KB in the panel title is the start-up peak, not the steady-state window.)

**Figure 4: cumulative acknowledged packet bytes, baseline vs severe** (`plots/figure4_cumulative_median_runs.png`). Median-goodput stock runs: baseline run 3 and severe run 4 (0.76 Mbps). This counts whole acknowledged packets (headers and retransmissions included), not unique file payload. Caption: the baseline run delivers 10.8 MB of acknowledged packet bytes in 6.4 s; the severe run needs 110 s for 11.6 MB, about 17 times longer.

The earlier `plot2_cwnd.png` and `plot4_cumulative.png` in the same folder come from the Phase 0 pipeline and use different runs; these two figures replace them in this section.

## 6. Interpretation

* Goodput falls from 13.4 Mbps (baseline) to 0.99 Mbps (moderate), about 93% lower, while the link is only about 7% utilised and baseline has no declared losses. The path is not congested; the sender is reacting to losses that did not happen.
* 86 to 95% of declared losses are spurious in every impaired profile (stock 88 to 95%, k20 86 to 94%).
* The few genuine losses (about 34 moderate, 67 severe in the first sample run) match the configured netem loss (0.3% and 0.5%), which supports the detector. They also trigger cwnd cuts, so reordering is not the only cause of cuts.
* Raising the packet threshold to 20 or 100 gives only +23 to +35% goodput and reduces declared losses by only about 10 to 18%. Packet-threshold tuning alone does not close the gap to TCP, and the attribution table now shows why: once the packet threshold is raised, the time rule declares 85 to 95% of the remaining losses on moderate, severe and handover (PTO is negligible). The dynamic packet threshold only adapts the packet rule, so on its own it behaves like k20 at best, and the final bulk matrix confirms it: `dynamic` gains +21% (mild), +7% (moderate), +6% (severe) and +27% (handover) over stock, against +33%, +40%, +24% and +47% for k20. What changes the result is the congestion undo: `dynamic_undo` reaches +143%, +107%, +53% and +81%, with no difference on baseline (`experiments/results/phase1_all_variants_final_5runs/transfers.csv`, 5 runs per cell, means).
* Limitations: simulated reordering from netem; one bulk size; one packet-number space analysed (application); medians of a stochastic emulation.

## 7. Input for the literature comparison (for P5)

* [Marx 2023 and Palmer 2024: does our mechanism match their explanation? Note that our data shows a second rule, the time threshold, declaring most of the remaining losses once the packet threshold is raised.]
