# QUIC File Transfer Experiments

This directory contains the experiment setup for comparing HTTP/3 file transfers using `aioquic` under different packet-loss detection thresholds and network conditions.

## 1. Person 1 Implementation

The following components have been implemented:

- Created an isolated client-router-server network topology using Linux network namespaces.
- Added a runner to start the HTTP/3 server and client and perform file transfers.
- Added SHA-256 and file-size verification to check download integrity.
- Calculates download time and application goodput in Mbps.
- Added a configurable packet threshold using the `AIOQUIC_PACKET_THRESHOLD` environment variable.
- Preserved the default packet threshold of `3` when no override is provided.
- Increased client timing-log precision to six decimal places for more accurate measurements of short transfers.
- Records transfer measurements in a CSV file and generates client-side and server-side QUIC qlogs.
- Stores client and server qlogs separately for each variant, profile, and run.

The packet-threshold override affects packet-threshold-based loss detection. The existing time-based loss detection remains in place.

## 2. Directory Structure

- `topology/create.sh` — creates the client-router-server network topology.
- `topology/destroy.sh` — removes the experiment network namespaces.
- `transfer/run_transfer.py` — runs a file transfer and records its measurements.
- `transfer/www/` — contains test files such as `1MB.bin`, `10MB.bin`, and `50MB.bin`.
- `transfer/client-qlog/<variant>/<profile>/<run>/` — stores client-side QUIC logs for each experiment run.
- `transfer/server-qlog/<variant>/<profile>/<run>/` — stores server-side QUIC logs for each experiment run.
- `transfer/server.log` — contains server output.
- `results/transfers.csv` — stores transfer measurements.

Generated downloads, logs, certificates, and private keys should not be committed unless the team explicitly needs a particular artifact.

## 3. Environment Setup

Run commands from the repository root and activate the project's Python virtual environment.

If the development dependencies have not been installed, follow the installation instructions in the repository's main README.

Generate a local TLS certificate for the server IP address:

```bash
openssl req -x509 -newkey ec \
  -pkeyopt ec_paramgen_curve:prime256v1 \
  -nodes -days 14 \
  -subj "/CN=10.10.2.2" \
  -addext "subjectAltName=IP:10.10.2.2" \
  -keyout experiments/transfer/ns-key.pem \
  -out experiments/transfer/ns-cert.pem
```

These are local test credentials. Never commit private keys.

## 4. Create the Network Topology

Run:

```bash
sudo bash experiments/topology/create.sh
```

The script creates three network namespaces:

| Component | IP address |
|---|---|
| Client | `10.10.1.2` |
| Router interface facing the client | `10.10.1.1` |
| Router interface facing the server | `10.10.2.1` |
| Server | `10.10.2.2` |

The router forwards packets between the client and server subnets.

The script prints these interface names:

- `DL_IF=rc0`
- `UL_IF=rs0`

These names are printed by the script; they are not automatically exported into the calling shell.

Person 2 should use the appropriate interfaces when configuring network impairment profiles.

**Important:** The topology scripts require privileged network operations. Run them only in the intended Linux/WSL environment.

## 5. Run a File Transfer

### Stock packet threshold

```bash
python experiments/transfer/run_transfer.py \
  --file 1MB.bin \
  --variant stock \
  --profile baseline \
  --run 1
```

### Explicit packet-threshold override

```bash
python experiments/transfer/run_transfer.py \
  --file 1MB.bin \
  --variant huge-threshold \
  --profile baseline \
  --run 1 \
  --threshold 1000000
```

The variant names above are intended experiment labels. Confirm the final names and threshold values with the team before collecting final results.

To see all supported command-line options, run:

```bash
python experiments/transfer/run_transfer.py --help
```

The available options include `--file`, `--variant`, `--profile`, `--run`, and `--threshold`.

When `--threshold` is omitted, the default packet threshold is used. The runner configures Cubic congestion control for the client and server.

The `--profile` option labels the experiment in the CSV file. It does not configure network conditions by itself. Network impairment profiles must be configured separately.

## 6. Experiment Profiles and Variants

Use the agreed profile labels consistently:

- `baseline`
- `mild`
- `moderate`
- `severe`
- `handover`

Person 2 is responsible for configuring and documenting the network impairment parameters corresponding to these profiles.

The intended variant labels are:

- `stock` — uses the default packet threshold.
- `huge-threshold` — uses an explicitly configured packet threshold.

Coordinate with the team before changing these labels or selecting the final threshold values.

## 7. Results and CSV Format

Each successful transfer appends a row to `results/transfers.csv`.

The agreed CSV schema is:

```text
variant,profile,file_size,run,download_time_s,goodput_mbps,sha256_ok,qlog_path
```

Column descriptions:

| Column | Meaning |
|---|---|
| `variant` | Packet-threshold configuration being tested |
| `profile` | Network condition used for the run |
| `file_size` | Downloaded file size in bytes |
| `run` | Repetition number |
| `download_time_s` | Measured download duration in seconds |
| `goodput_mbps` | Application goodput in Mbps |
| `sha256_ok` | Whether the downloaded file matches the original file |
| `qlog_path` | Client qlog directory for the run |

The server qlogs are stored in the matching `transfer/server-qlog/<variant>/<profile>/<run>/` directory. Client and server qlogs for the same connection share a connection ID, which can be used to match them.

Use the CSV results and qlogs together when analyzing performance.

The runner and server share a port and log locations. Run transfers sequentially unless the scripts have been updated to isolate concurrent runs.

Keep repeated runs and the associated qlogs so that the team can compare variants and analyze packet-loss behavior.

## 8. Reproducibility Checklist

Before collecting final measurements:

1. Record the exact base repository commit and the final code commit.
2. Document how the test files were generated, including a fixed seed if one was used.
3. Use the same test files and transfer procedure across variants.
4. Keep the congestion-control algorithm consistent.
5. Verify that the configured packet threshold is actually applied to packet-loss detection.
6. Confirm that `sha256_ok` is true for every accepted transfer.
7. Record the network profile parameters used for each run.
8. Record actual baseline `ping` and `iperf3` measurements when available.
9. Preserve client and server qlogs for the corresponding run.
10. Repeat each experiment sufficiently to support a meaningful comparison.

Do not treat preliminary smoke-test measurements as final comparative results.

## 9. Team Handoff

### Person 1 — Topology and Transfer Runner

Implemented components include:

- Network namespace creation and cleanup.
- HTTP/3 server and client transfer orchestration.
- Configurable packet-threshold support.
- Download integrity verification.
- Download timing and goodput calculation.
- CSV result recording and QUIC qlog collection.
- Per-run organization of client and server qlogs.

### Person 2 — Network Impairment

Configure the network profiles using the interfaces printed by `topology/create.sh`.

Document the actual delay, loss, reordering, bandwidth, or other parameters used for each profile. The profile labels alone do not apply network impairments.

### Person 3 — Results and Qlog Analysis

Use the recorded CSV measurements and QUIC qlogs to compare transfer behavior across variants and network profiles.

Match client and server qlogs using their connection IDs, and ensure that the logs correspond to the correct variant, profile, and run.

### Other Team Members

Coordinate the final experiment labels, threshold values, test-file sizes, run counts, and measurement procedure before collecting the complete dataset.

The transfer runner already starts and stops the HTTP/3 server for each transfer. Coordinate with anyone integrating the experiment workflow to avoid duplicating this orchestration.

## 10. Cleanup

After all experiments have finished and no transfer is running, remove the network namespaces:

```bash
sudo bash experiments/topology/destroy.sh
```

This removes the experiment namespaces. Preserve the CSV results and qlogs required for analysis before cleaning up generated artifacts.

## 11. Important Notes

- Do not commit private keys or other secrets.
- Do not mix preliminary smoke-test runs with final experimental measurements without clearly identifying them.
- Keep the CSV header consistent with the agreed schema.
- Keep variant and profile labels consistent across all runs.
- Record actual measurements and configuration values rather than estimating them.
- Check that each result has a valid integrity check and the corresponding qlogs before using it for analysis.
