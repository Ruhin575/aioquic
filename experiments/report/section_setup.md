# Experimental Setup

## 1. Code Version

All experiments run aioquic from our fork (github.com/Ruhin575/aioquic) at a
pinned commit recorded in `experiments/BASE_COMMIT.txt`:

| Pin | Commit | Contents |
|---|---|---|
| phase0 | 342b224 | Stock aioquic with the `AIOQUIC_PACKET_THRESHOLD` override (static K) |
| phase1 | a8d846c | Adds loss-rule attribution, adaptive K (`dynamic`) and congestion undo (`dynamic_undo`) |

The Phase 1 matrix is run from the phase1 pin. With
`AIOQUIC_PACKET_THRESHOLD` unset, the phase1 code behaves identically to
stock aioquic: every addition is gated on the variable (see
`dynamic_design.md`, section 5), and the upstream test suite passes
unchanged.

## 2. Testbed Topology

The testbed is three Linux network namespaces on one host, connected by two
veth pairs (`experiments/topology/create.sh`):

```
ns-client                 ns-router                     ns-server
10.10.1.2  c0 ───── rc0  10.10.1.1 │ 10.10.2.1  rs0 ───── s0  10.10.2.2
                     (downlink netem)   (uplink netem)
```

The router forwards between the two /24 subnets (`net.ipv4.ip_forward=1`).
All impairment is applied by `tc netem` inside `ns-router`:

- `rc0` (towards the client) carries the **downlink**, server to client, which
  is where the data flows and where reordering is applied.
- `rs0` (towards the server) carries the **uplink**, client to server, which
  carries the client's ACKs.

Because both the client and server run in namespaces on the same kernel, the
only path impairments are the ones netem adds.

## 3. Network Profiles

`experiments/netem/setup.sh` defines five profiles modelled on LTE
conditions. Every profile caps both directions at 15 Mbit/s (netem `rate`)
and uses netem's default queue limit of 1000 packets. The uplink always has
a fixed 30 ms delay and no other impairment. The downlink varies:

| Profile | Models | Delay (normal dist.) | Loss | Reorder (correlation) |
|---|---|---|---:|---:|
| baseline | Clean LTE | 30 ms ± 5 ms | 0% | 0% |
| mild | Good LTE | 40 ms ± 10 ms | 0.1% | 5% (25%) |
| moderate | Typical LTE | 50 ms ± 15 ms | 0.3% | 15% (50%) |
| severe | Cell edge | 70 ms ± 25 ms | 0.5% | 25% (75%) |
| handover | Tower handover | 80 ms ± 40 ms | 1% | 30% (80%) |

Loss is independent random loss (`loss random`). Loss correlation is
deliberately not used for handover: tc-netem marks it deprecated, and at high
correlation it can drive the drop probability to zero.

With netem's `reorder P% C%`, a fraction P of packets (with correlation C to
the previous decision) is sent immediately, while the rest wait for the
configured delay. Combined with the delay jitter, this lets later packets
overtake earlier ones by many positions, which is the reordering the packet
threshold reacts to. Base round-trip time without jitter is 30 ms on the
uplink plus the profile's downlink delay, for example 60 ms on baseline and
80 ms on moderate.

## 4. Transfer Workload

Each run is one HTTP/3 download over aioquic's example server and client
(`examples/http3_server.py`, `examples/http3_client.py`):

- Server: `10.10.2.2:4433` in `ns-server`, self-signed P-256 certificate for
  `IP:10.10.2.2`, serving fixed files of random bytes.
- Client: in `ns-client`, trusting that certificate.
- Congestion control: **Cubic** on both endpoints.
- File sizes: 1 MB, 10 MB and 50 MB (`experiments/transfer/www/`). The
  results in this report use 10 MB unless stated otherwise.
- Both endpoints write qlog traces (`client-qlog/`, `server-qlog/`). The
  server qlog is the one analysed, since the server is the data sender whose
  loss recovery is under test.

`experiments/run_experiment.py` applies the netem profile, runs one transfer
with `experiments/transfer/run_transfer.py`, and tears the profile down
again, so every run starts from a fresh connection and an empty queue.
Results are stored under `<output>/<variant>/<profile>/run_<N>/`.

A run counts only if the downloaded file's SHA-256 matches the source
and its size matches what the client reported. Every result in this report
passed both checks.

## 5. Variants

The packet threshold is selected per run through `AIOQUIC_PACKET_THRESHOLD`,
which the runner sets on both endpoints:

| Variant | `AIOQUIC_PACKET_THRESHOLD` | Behaviour |
|---|---|---|
| stock | unset | RFC 9002: K = 3, time threshold 9/8 × RTT |
| k5, k10, k20, k100 | 5, 10, 20, 100 | Static packet threshold K |
| dynamic | `dynamic` | Adaptive K from late ACKs, K_MAX = 40, decay 0.9 per clean RTT |
| dynamic_undo | `dynamic_undo` | As dynamic, plus restoring the congestion state when every loss in an episode proves spurious |

Only the packet threshold changes. The time threshold (9/8 × RTT), PTO and
Cubic are stock in every variant. `dynamic_design.md` describes the two
dynamic variants.

## 6. Metrics

**Goodput** is the application-level download rate:

  goodput = (file size in bytes × 8) / download time

The download time is the client-reported time from sending the GET request to
receiving the last byte of the response, so it includes the handshake RTTs
and the whole transfer. Goodput is reported in Mbit/s.

**RTT** is aioquic's RFC 9002 estimate, taken from the server qlog
(`recovery:metrics_updated`). The latest RTT is the time from sending the
largest newly acknowledged ack-eliciting packet to receiving its ACK, minus
the peer's ACK delay (capped at max_ack_delay = 25 ms) when that leaves it
above min_rtt. The smoothed RTT is updated as

  smoothed_rtt = 7/8 · smoothed_rtt + 1/8 · latest_rtt

The time threshold, the dynamic decay window ("one clean RTT") and the
undo expiry (2 × smoothed_rtt) all use these values.

**Loss attribution** comes from the `recovery:packet_lost` events, which
carry the rule that declared each loss ("packet", "time", "both", "pto" or
"handshake"). **Spurious losses** are declared-lost packets that are
acknowledged later. **Undo activity** is counted from
`recovery:cwnd_restored` and `recovery:undo_abandoned`.

## 7. Machines

Two machines were used, and results from them are never mixed in one
comparison.

**Official matrix (report numbers).** Run by Reethika on native Linux,
with all variants of a profile in the same session and 5 runs per cell:

- CPU: 13th Gen Intel Core i7-1365U, 12 logical cores
- RAM: 14 GiB
- OS / kernel: Ubuntu 26.04.1 LTS, Linux 7.0.0-42-generic
- Python: 3.14.4

Baseline goodput on this machine varies by about 0.15% across runs
(13.373–13.392 Mbit/s for stock).

**Development and tuning.** Ruhin's laptop, used for the same-session
comparisons that guided the design (dynamic_design.md, sections 3.5 and 7.4):

- CPU: Intel Core Ultra 5 125H, 18 logical cores
- RAM: 7.5 GiB available to WSL
- OS / kernel: Ubuntu 24.04.5 LTS on WSL2, kernel 6.6.87.2-microsoft-standard-WSL2
- Python: 3.12.3

Baseline goodput on WSL varies much more (10.3–12.9 Mbit/s for stock), so
these runs are used only for relative comparisons within one session, never
as report figures. The two machines also differ in kernel and Python version,
which is another reason results are compared only within a machine.

## 8. Reproducing a Run

```bash
git checkout a8d846c
python -m venv .venv && source .venv/bin/activate
pip install -e . wsproto starlette jinja2 pandas
mkdir -p experiments/transfer/www
head -c 10M /dev/urandom > experiments/transfer/www/10MB.bin
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes \
  -days 14 -subj "/CN=10.10.2.2" -addext "subjectAltName=IP:10.10.2.2" \
  -keyout experiments/transfer/ns-key.pem -out experiments/transfer/ns-cert.pem
sudo bash experiments/topology/create.sh
python experiments/run_experiment.py --variant dynamic_undo \
  --profile moderate --file 10MB.bin --run 1 --output-dir results/example/
```

The namespaces have to be recreated after a reboot (or a WSL restart).
