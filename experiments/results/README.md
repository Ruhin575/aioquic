# Experiment Results

This directory stores the results of QUIC and TCP experiments.

## Directory structure

Each QUIC experiment run is stored using the following structure:

    <output>/<variant>/<profile>/run_<N>/
        client-qlog/
        server-qlog/
        download/

For example:

    experiments/results/
        stock/
            moderate/
                run_1/
                run_2/
        k20/
            severe/
                run_1/

## Variants

| Variant | Description |
|---|---|
| stock | Original aioquic loss detection |
| k5 | Packet threshold K = 5 |
| k10 | Packet threshold K = 10 |
| k20 | Packet threshold K = 20 |
| k100 | Packet threshold K = 100 |
| dynamic | Dynamically adjusted packet threshold |
| dynamic_undo | Dynamic threshold with undo mechanism |

The dynamic variants are included in the experiment design, but should not be used for real experiments until their implementation is complete.

## CSV schema

Each experiment result is recorded with these columns:

| Column | Description |
|---|---|
| variant | Loss-detection variant |
| profile | Network emulation profile |
| file_size | Transferred file |
| run | Run number |
| download_time_s | Download duration in seconds |
| goodput_mbps | Application goodput in Mbps |
| sha256_ok | Whether the downloaded file matches the original |
| qlog_path | Path to the corresponding qlog |

## Network profiles

The experiment matrix uses these profiles:

- baseline
- mild
- moderate
- severe
- handover

## Notes

- Keep results from different experiment stages in separate output directories.
- Do not overwrite historical result CSV files.
- A run is considered successful only when the transfer completes and the downloaded file passes SHA-256 verification.
- Synthetic results must be kept separate from actual experiment measurements.
