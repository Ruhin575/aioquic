# Qlog Analysis

This directory contains tools to parse QUIC qlogs, detect spurious losses, calculate summary statistics, and generate plots for analyzing loss mechanisms under different network conditions.

## Requirements

Run commands from the repository root. Activate the project's Python environment and install the required dependencies:

```bash
python -m pip install -e ".[dev]"
python -m pip install pandas matplotlib wsproto starlette jinja2 dnslib httpx
```

## 1. Collect Sample Qlogs

Collect qlogs for the baseline, moderate, and severe network profiles:

```bash
bash experiments/analysis/collect_sample_qlogs.sh baseline moderate severe
```

The collected qlogs are stored under:

```text
experiments/transfer/server-qlog/p3sample/
```

The corresponding sample transfer results are written to:

```text
experiments/analysis/sample_data/transfers_p3sample.csv
```

## 2. Parse Qlogs and Detect Spurious Losses

Parse the qlogs and calculate spurious-loss statistics for each profile:

```bash
D=experiments/transfer/server-qlog/p3sample
O=experiments/analysis/sample_data
for p in baseline moderate severe; do
  python experiments/analysis/parse_qlog.py \
    --input "$D/$p/1" \
    --output "$O/$p.csv"
  python experiments/analysis/detect_spurious.py \
    --input "$O/$p.csv" \
    --output "$O/${p}_spurious.csv" \
    --summary "$O/$p.json"
done
```

This produces parsed CSV files, spurious-loss CSV files, and JSON summaries for each profile.

## 3. Generate Mechanism Plots

### Plot 2: Congestion window versus time

Compare baseline and moderate conditions, with declared-loss and spurious-loss markers.

```bash
python experiments/analysis/plot_mechanism.py cwnd \
  --panel baseline="$O/baseline.csv" \
  --panel moderate="$O/moderate.csv" \
  --out experiments/analysis/plots
```

### Plot 4: Cumulative bytes versus time

Compare baseline and severe conditions.

```bash
python experiments/analysis/plot_mechanism.py cumulative \
  --series baseline="$O/baseline.csv" \
  --series severe="$O/severe.csv" \
  --out experiments/analysis/plots
```

Sample plots are written to `experiments/analysis/plots/`. The final figures used in the report belong in `experiments/report/plots/`.

## 4. Reference Results from the First Real Sample Run

The following results were obtained from one run per profile and can be used as a reference when checking the analysis pipeline.

| Profile  |   Goodput | Packets sent | Declared lost | Spurious | Spurious rate |
| -------- | --------: | -----------: | ------------: | -------: | ------------: |
| Baseline | 13.3 Mbps |       10,226 |             0 |        0 |            0% |
| Moderate | 0.92 Mbps |       12,367 |           794 |      760 |         95.7% |
| Severe   | 0.81 Mbps |       11,915 |           630 |      563 |         89.4% |

These values are from a single real sample run per profile and are provided for pipeline validation only. Results may vary between runs because network emulation is stochastic. They should not be treated as final experimental conclusions; use the complete experiment matrix for the final analysis.

## 5. Analyze the Complete Experiment Results

After the complete experiment matrix is available, run the batch analysis:

```bash
python experiments/analysis/analyze_run.py
```

Check the reported numbers of selected, analyzed, and skipped runs. Investigate missing qlogs or invalid runs before using the summary as final evidence.

To generate median-run plots for the stock variant under moderate conditions:

```bash
python experiments/analysis/plot_mechanism.py median-run \
  --results experiments/results/transfers.csv \
  --variant stock \
  --profile moderate
```

Use the appropriate median runs to generate the final plots under `experiments/report/plots/`, then update `experiments/report/section_mechanism.md` with the verified results and interpretation.

## Outputs

- **Parsed data:** CSV files containing packet events and available congestion-control and RTT metrics.
- **Spurious-loss analysis:** CSV files and JSON summaries.
- **Mechanism plots:** Congestion window versus time and cumulative bytes versus time.
- **Findings:** `QLOG_FINDINGS.md`.
- **Report:** `experiments/report/section_mechanism.md`.

