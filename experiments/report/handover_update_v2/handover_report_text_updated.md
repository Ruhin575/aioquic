### Updated handover results (additional runs 6–10)

The original 175-run matrix was supplemented with five additional handover runs each for Stock, K20, and Dynamic Undo. The combined dataset therefore contains 190 observations: the original 175 runs plus 15 additional handover runs. For the handover profile, Stock, K20, and Dynamic Undo each have n=10; the other four variants retain n=5.

- `dynamic` (n=5): mean goodput 0.4884 Mbps (95% t CI 0.4556–0.5212); all checksums passed.
- `dynamic_undo` (n=10): mean goodput 0.6843 Mbps (95% t CI 0.6519–0.7167); all checksums passed.
- `k10` (n=5): mean goodput 0.5762 Mbps (95% t CI 0.5421–0.6103); all checksums passed.
- `k100` (n=5): mean goodput 0.5940 Mbps (95% t CI 0.5515–0.6365); all checksums passed.
- `k20` (n=10): mean goodput 0.5848 Mbps (95% t CI 0.5644–0.6052); all checksums passed.
- `k5` (n=5): mean goodput 0.5242 Mbps (95% t CI 0.4959–0.5525); all checksums passed.
- `stock` (n=10): mean goodput 0.4300 Mbps (95% t CI 0.3245–0.5355); all checksums passed.

Pairwise Welch tests compare each variant with Stock, with Holm correction across the six comparisons within the handover profile. See `handover_welch_holm_vs_stock.csv` for p-values, adjusted p-values, and 95% confidence intervals for mean differences.

Stock handover run 4 remains included in the primary analysis: its goodput is 0.012 Mbps and its download time is 6817.246 s, despite a successful checksum. The run is retained pending inspection of the exact server qlog from the original final-matrix experiment. Qlogs from recovery-test, threshold-20, or huge-threshold experiments are not substitutes.