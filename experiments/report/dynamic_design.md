# Dynamic Packet Threshold Algorithm Design

## 1. Motivation

The static packet threshold K=3 (RFC 9002 default) causes spurious loss
declarations when reordering gaps exceed 3. A higher static K (e.g. K=20)
reduces spurious losses but delays genuine loss detection. The dynamic
algorithm raises K when spurious losses are observed and decays it back
toward 3 during clean RTTs, so it pays the cost of a high K only while
reordering is actually happening.

---

## 2. Mode Selection and State Variables

`AIOQUIC_PACKET_THRESHOLD` is parsed once in `QuicPacketRecovery.__init__()`
into `self._threshold_mode`, which is "static", "dynamic" or "dynamic_undo".
Unset or an integer gives "static". The dynamic state is always defined, so
no code path depends on which branch the parse took:

```python
self._dynamic_mode = self._threshold_mode == "dynamic"
self._dynamic_undo_mode = self._threshold_mode == "dynamic_undo"
self._k_adaptive: float = float(K_PACKET_THRESHOLD)    # starts at 3.0

# pkt_num → (loss_time, sent_time, gap_at_declaration)
self._recent_lost: dict[int, tuple[float, float, int]] = {}

# dynamic_undo only (not yet used, see section 7)
self._saved_cwnd: Optional[int] = None
self._saved_ssthresh: Optional[int] = None

# set when K is raised; consulted and cleared once per RTT window
self._k_adapted_this_round: bool = False
# start of the current RTT window for decay (section 3.5)
self._k_last_decay_time: float = 0.0
```

`K_PACKET_THRESHOLD` remains 3 (unchanged from RFC 9002).

---

## 3. Algorithm

### 3.1 Effective threshold

In `_detect_loss()`, the packet-threshold rule uses:

```python
effective_k = (
    int(self._k_adaptive)
    if (self._dynamic_mode or self._dynamic_undo_mode)
    else self._packet_threshold
)
packet_threshold = space.largest_acked_packet - effective_k
```

### 3.2 On packet declared lost

A loss is recorded in `_recent_lost` only when all of these hold: a dynamic
mode is active, the packet is in the application-data (1-RTT) space, and its
rule is "packet" (the packet threshold fired and the time threshold did not;
"both" is excluded). These losses come from `_detect_loss()`, which always
reports a congestion event.

```python
gap = space.largest_acked_packet - packet_number   # gap at declaration time
self._recent_lost[packet_number] = (now, packet.sent_time, gap)
```

The gap is stored at declaration time, not recomputed at ACK time: by then
`largest_acked` has moved on and the gap would overstate the K that was
needed.

`_recent_lost` is capped at 64 entries. When full, the entry with the
smallest packet number (oldest in sequence) is evicted.

Time-threshold, PTO and handshake losses are not recorded. Dynamic K governs
only packet-threshold detection, so only packet-threshold spurious losses
should move it.

### 3.3 On ACK received

At the top of `on_ack_received()`, in dynamic modes, entries older than
2 × smoothed_rtt are dropped:

```python
self._expire_recent_lost(now)
```

After the newly acknowledged packets and the RTT estimate are processed, and
just before `_detect_loss()`, every packet number in `_recent_lost` is checked
against the ACK ranges:

```python
for pn in list(self._recent_lost):
    for r in ack_rangeset:
        if r.start <= pn < r.stop:
            _, _, gap = self._recent_lost.pop(pn)
            self._adapt_k(gap)
            break
```

A late ACK for a packet in `_recent_lost` means the packet was delivered, so
its loss declaration was spurious. The raw ACK ranges must be checked because
a declared-lost packet has already been removed from `sent_packets`. Placing
the check before `_detect_loss()` means a raised K applies to the same ACK.

### 3.4 `_adapt_k(gap)`

```python
old_k = self._k_adaptive
self._k_adaptive = min(max(self._k_adaptive, float(gap + 1)), float(K_MAX))
self._k_adapted_this_round = True
# log recovery:k_adapted (section 8)
```

`gap + 1` is the smallest K that would have avoided this spurious loss. K
never decreases here, only in decay.

### 3.5 Decay

Decay runs at most once per smoothed RTT of elapsed time, checked in the
branch of `on_ack_received()` that updates the RTT estimate:

```python
if now - self._k_last_decay_time >= self._rtt_smoothed:
    if not self._k_adapted_this_round and self._k_adaptive > K_PACKET_THRESHOLD:
        self._k_adaptive = max(self._k_adaptive * K_DECAY, float(K_PACKET_THRESHOLD))
    self._k_adapted_this_round = False
    self._k_last_decay_time = now
```

The flag collects any K increase during the current RTT window. K relaxes
only after a full RTT with no spurious loss detected.

An earlier version (commit 0179440) decayed on every RTT sample. aioquic
takes an RTT sample on most ACKs, several per round trip, so that version
drained K from 22 to 3 in well under a second and every reordering burst
started again from K=3. In a moderate-profile test (10 MB, one run each),
dynamic with per-sample decay reached 0.961 Mbps against 0.945 Mbps for
stock. With time-limited decay (commit b40f456) it reached 1.171 Mbps
(+24%), and packet-rule losses fell from 680 (stock) to 474.

---

## 4. Constants (from Shamili's Day 2 gap analysis, commit 8779d49)

### K_MAX = 40

Spurious-loss gap distribution (gap_distribution_validated.csv):

| Profile | Spurious losses | Median | p90 | p95 | p99 | Max |
|---|---:|---:|---:|---:|---:|---:|
| Moderate | 6546 | 8 | 20 | 30 | 87 | 127 |
| Severe | 5658 | 9 | 20 | 28 | 58 | 82 |

Coverage (share of spurious gaps ≤ K) against cost (median genuine-loss
detection delay, recovery_tradeoff_summary_corrected.csv):

| K | Coverage moderate | Coverage severe | Delay moderate | Delay severe |
|---:|---:|---:|---:|---:|
| 20 | 91.0% | 90.1% | ≈ 99 ms | ≈ 130 ms |
| 30 | 95.2% | 95.8% | | |
| 40 | 96.4% | 97.4% | | |
| 50 | 97.3% | 98.3% | ≈ 307 ms | ≈ 396 ms |
| 100 | | | ≈ 615 ms | ≈ 814 ms |

(Delay was measured only at the K values in Shamili's sweep: 3, 5, 10, 20,
50 and 100.)

The knee is between K=20 and K=30. Above 40, each further step buys about 1
percentage point of coverage while genuine-loss delay keeps rising roughly
linearly. K=40 sits just past the p95 gap in both profiles. Since K reaches
the ceiling only during reordering and decays afterwards, the ceiling bounds
the worst case rather than setting the operating point. In the moderate test
run, the first confirmed spurious loss already had a gap of at least 39, so
K went straight from 3 to 40.

### K_DECAY = 0.9 per clean RTT

From K=40, K returns to the stock threshold of 3 after
ln(3/40) / ln(0.9) ≈ 25 clean RTTs. The base path RTT is about 60 ms (30 ms
each way, before jitter), and queueing under load makes the smoothed RTT
larger, so this takes a few seconds: long enough to stay protected through
bursty reordering, short enough to restore fast genuine-loss detection after
it ends. In the moderate test run K still fell back to 3 before 22 of the
451 confirmed spurious losses. If Day 5 runs show bursts arriving after such
resets cost goodput, the Day 6 option is a slower decay (e.g. 0.95); if K
stays high too long on clean paths, the fallback is 0.8 (about 11 RTTs).

---

## 5. Gating

Every dynamic code path is gated on `self._dynamic_mode or
self._dynamic_undo_mode`. With `AIOQUIC_PACKET_THRESHOLD` unset or an
integer, both are False: `effective_k` equals the static threshold,
`_recent_lost` is never filled, and `_adapt_k` and decay never run, so
behaviour is identical to stock. The existing test suite passes unchanged.

---

## 6. Time Threshold Extension (conditional)

After Reethika's Day 3 attribution table: if the "time" rule and PTO together
account for more than half of spurious losses at both moderate and severe,
extend the design to adapt `K_TIME_THRESHOLD` using the same late-ACK
evidence, with a separate cap on how far it may grow. This would be
implemented on Day 4, or in the Day 6 tuning pass if the table arrives late.

If the condition is not met, the adaptive packet threshold alone is the final
design. The evidence so far points this way:

- Shamili's Day 2 data: at K=3, about 90% of spurious losses had the packet
  threshold crossed before the late ACK (recovery_tradeoff_summary_corrected.csv).
- Instrumented stock run, moderate, 10 MB (one run): of 887 declared losses,
  680 packet, 117 time, 87 both, 2 PTO, 2 handshake. Time + PTO is 13.4% of
  all declared losses, so it cannot reach half of the spurious ones.
- Dynamic run, same profile: raising K shifts some detection to the time rule
  (time-rule losses 117 → 178), but time + PTO is still about 26% of declared
  losses.

Reethika's attribution table needs reruns on the pinned commit (moderate and
severe) before this is final; the Phase 0 qlogs carry no rule metadata.

---

## 7. dynamic_undo Extension (optional, Day 5 checkpoint decides)

Save congestion state just before `_on_packets_lost()` reports a loss to the
congestion controller:

```python
self._saved_cwnd = self._cc.congestion_window
self._saved_ssthresh = self._cc.ssthresh
```

When a spurious loss is confirmed in `_adapt_k()`, restore them. The
congestion controller interface (congestion/base.py) has no restore method,
so this needs either a small `restore_state()` added to the base class or
direct assignment of `congestion_window` and `ssthresh`, plus a pacer rate
update. Gated on `AIOQUIC_PACKET_THRESHOLD=dynamic_undo`.

Decision at the Day 5 checkpoint, based on whether dynamic alone meets the
targets (baseline goodput within 2% of stock, and a clear gain over stock on
moderate and severe).

---

## 8. qlog Events

### recovery:k_adapted

Emitted in `_adapt_k()` each time a spurious loss is confirmed, including
when K does not change because the gap is already covered:

```json
{
  "old_k": 3.0,
  "new_k": 40.0,
  "gap": 45,
  "mode": "dynamic"
}
```

Decay steps are not logged separately. A `k_adapted` event whose `old_k` is
below the previous event's `new_k` shows that decay ran in between.

### recovery:packet_lost

Carries `rule` ("packet", "time", "both", "pto" or "handshake"), `by_packet`
and `by_time` from the Day 1 rule-attribution patch, which is how losses
eligible for `_recent_lost` can be identified in the qlogs.
