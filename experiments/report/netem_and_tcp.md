# Network emulation and TCP comparison

## Topology and traffic shaping

The topology is three Linux network namespaces: `ns-client`,
`ns-router`, `ns-server`, connected by two veth pairs. The router
forwards IPv4 between the two subnets. `experiments/topology/create.sh`
builds the namespaces and exports two environment variables:

- `DL_IF`: the router's egress interface toward the client. This is
  where the downlink (server to client) data stream leaves the router,
  so this is where we impair.
- `UL_IF`: the router's egress interface toward the server. The
  uplink carries ACKs and HTTP requests only.

`experiments/netem/setup.sh <profile> <DL_IF> <UL_IF> ns-router`
attaches a single `netem` qdisc per interface. On `DL_IF` it applies
the full profile (delay, jitter, loss, reorder) plus a 15 Mbit rate
cap via netem's own `rate` option. On `UL_IF` it applies only a fixed
30 ms one-way delay plus the same 15 Mbit cap. The asymmetry is
intentional:

1. Mobile uplinks are usually less lossy and less jittery than
   downlinks in the real paths this models.
2. Keeping the uplink identical across profiles means any observed
   difference in download time is attributable to downlink impairment
   alone, not to changes in ACK clocking.

### Profiles (configured values)

| Profile  | Delay | Jitter | Loss  | Reorder (prob / corr) | Rate cap | Use case       |
|----------|-------|--------|-------|-----------------------|----------|----------------|
| baseline | 30 ms | 5 ms   | 0 %   | 0 %  / n/a            | 15 Mbit  | Clean LTE      |
| mild     | 40 ms | 10 ms  | 0.1 % | 5 %  / 25 %           | 15 Mbit  | Good LTE       |
| moderate | 50 ms | 15 ms  | 0.3 % | 15 % / 50 %           | 15 Mbit  | Typical LTE    |
| severe   | 70 ms | 25 ms  | 0.5 % | 25 % / 75 %           | 15 Mbit  | Cell edge      |
| handover | 80 ms | 40 ms  | 1 %   | 30 % / 80 %           | 15 Mbit  | Tower handover |

### Configured vs measured

netem's `reorder N% M%` is a probability model, not an observed-rate
target: `N%` is the probability a packet is sent ahead of its queue
position, and `M%` is the correlation with the previous decision. A
packet marked for immediate send only becomes an out-of-order arrival
if a packet behind it in queue happens to leave with less remaining
delay. So the observed out-of-order rate depends on jitter, offered
rate and the rate cap. We measure what the client actually sees with
`verify.sh`, which runs a 2000-packet sequenced UDP probe through the
same qdiscs the main experiments use.

| Profile  | Downlink delay (RTT − 30 ms) | Jitter (ping mdev) | Loss (UDP) | Out-of-order (UDP) |
|----------|------------------------------|--------------------|------------|---------------------|
| baseline | 30.12 ms                     | 5.09 ms            | 0.000 %    | 0.000 %             |
| mild     | 41.69 ms                     | 10.34 ms           | 0.100 %    | 1.502 %             |
| moderate | 51.67 ms                     | 15.40 ms           | 0.250 %    | 6.667 %             |
| severe   | 74.99 ms                     | 23.35 ms           | 0.600 %    | 9.557 %             |
| handover | 96.18 ms                     | 36.08 ms           | 0.700 %    | 21.148 %            |

Delay is derived from the ping RTT (kernel-timestamped), minus the
fixed 30 ms uplink. Jitter is `ping -q` mdev. Loss and reorder are
from the 2000-packet sequenced UDP probe in `verify.sh`. Observed
reorder is lower than configured by design, as noted above. Loss uses
the uncorrelated model: `tc-netem(8)` marks the correlated-loss
parameter deprecated, and a pre-sweep diagnostic confirmed that at
small p the correlated model's Markov walk stays near its mean and
produces essentially zero drops over 2000 packets. Observed mean
delays for `severe` and `handover` run higher than their netem base
because at high jitter the time-ordered netem send queue blocks
packets with low sampled delay behind packets with very high sampled
delay; the `reorder` setting partially relaxes this.

## TCP baseline

The TCP baseline uses:

- A Python `http.server` HTTP/1.1 server (no TLS, `Connection: close`).
- `curl --http1.1` as the client.
- The same five profiles, 10 MB file, 5 runs per profile, plus the
  validation sweep (50 MB, baseline and severe, 3 runs).

Both endpoints run inside their respective namespaces via `ip netns
exec`. The CSV it writes uses the contract schema (`variant, profile,
file_size, run, download_time_s, goodput_mbps, sha256_ok, qlog_path`,
with `qlog_path = "n/a"` for TCP).

### Why kernel TCP is informative

Linux's TCP uses RACK-TLP (`net.ipv4.tcp_recovery = 1` by default),
which is a time-based, reordering-tolerant loss detector. A packet is
flagged as lost only once an ACK has been seen for another packet sent
at least a reordering window after it, and that window grows when
reordering is observed. This is the opposite end of the design space
from aioquic's packet-count threshold, which flags a packet as lost
after `K_PACKET_THRESHOLD` later packets have been ACKed.

### What TCP comparison does and does not tell us

The point of a TCP baseline is **not** to claim that TCP is intrinsically
better than QUIC under reordering. The TCP baseline run differs from the
aioquic run in at least four ways:

1. Protocol: TCP vs QUIC. Different ACK format, different RTT
   estimation, different congestion-control feedback loop.
2. Implementation: hand-tuned C in the kernel vs Python in user space.
3. Language runtime: no GC on the datapath vs Python's interpreter and
   GC on the datapath.
4. Loss detection algorithm: RACK-TLP vs aioquic's packet-count
   threshold (and later, our packet-count-off control).

The "huge-threshold control" (the `--packet-threshold` variant)
isolates factor 4: comparing stock aioquic vs huge-threshold aioquic
keeps the implementation, language and protocol constant, so any
difference under reordering is attributable to the loss-detection
rule. The TCP baseline is included so a reader can see the ceiling a
reordering-tolerant loss detector reaches on the same path, with the
understanding that factors 1 to 3 also move.

### TCP baseline results

Main stage: 25 runs (5 profiles × 5 reps) on the 10 MB file.
Validation stage: 6 runs (baseline, severe × 3 reps) on the 50 MB file.
Every run passed its SHA-256 check.

| Profile  | Runs | Mean time (s) | σ (s) | Mean goodput (Mbit/s) | σ (Mbit/s) | % of 15 Mbit cap |
|----------|------|---------------|-------|------------------------|------------|-------------------|
| baseline | 5    | 6.15          | 0.06  | 13.65                  | 0.13       | 91.0 %            |
| mild     | 5    | 7.88          | 1.52  | 10.95                  | 1.98       | 73.0 %            |
| moderate | 5    | 17.47         | 6.59  | 5.27                   | 1.65       | 35.1 %            |
| severe   | 5    | 29.63         | 3.08  | 2.86                   | 0.32       | 19.0 %            |
| handover | 5    | 59.77         | 7.84  | 1.42                   | 0.21       | 9.5 %             |

50 MB validation runs:

| Profile  | Mean time (s) | Mean goodput (Mbit/s) | % of cap |
|----------|---------------|------------------------|----------|
| baseline | 29.50         | 14.22                  | 94.8 %   |
| severe   | 179.79        | 2.34                   | 15.6 %   |

Three features of this table are worth calling out:

1. Goodput falls roughly ten-fold from baseline to handover, which is
   TCP RACK responding to combined loss and reorder. RACK keeps
   working across the whole profile set, but the price of its
   reordering-tolerant window grows with the severity of the path.
2. The 50 MB baseline reaches 94.8 % of the 15 Mbit cap vs 91.0 % for
   the 10 MB baseline. The gap is slow-start overhead being
   amortised over the longer transfer rather than any change in
   steady-state behaviour.
3. Variance (σ of goodput) peaks on the mild and moderate profiles.
   On baseline the path is deterministic; on severe and handover the
   stack is almost always in reduced-cwnd recovery, so runs average
   out. The high-variance middle regime is where one reorder cluster
   per run can swing total time by a factor of two, and it is the
   regime where the qlog mechanism plots should give the clearest
   cascade from reorder → spurious loss declaration → unnecessary
   cwnd cut.

The TCP numbers are a ceiling, not a prediction for QUIC: TCP uses
RACK-TLP (kernel, C) while aioquic uses a packet-count threshold
(user-space, Python). The gap in Plot 1 between QUIC and TCP is
expected to shrink dramatically once the huge-threshold control is
compared against stock QUIC, because that comparison isolates the
loss-detection algorithm alone.