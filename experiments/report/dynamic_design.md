# Dynamic Packet Threshold Algorithm Design

**Status:** `dynamic` and `dynamic_undo` implemented on main (commit a8d846c,
pinned as phase1).
Time-threshold extension not triggered (section 6). Official matrix on the
frozen pin pending (Reethika).

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

# dynamic_undo only (section 7): congestion state saved just before a
# loss cut the window, and the losses since then (pkt_num → loss time)
self._undo_snapshot: Optional[dict[str, Any]] = None
self._undo_pending: dict[int, float] = {}

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

Every packet number in `_recent_lost` is then checked against the ACK
ranges, in `_process_late_acks()`:

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
a declared-lost packet has already been removed from `sent_packets`.

`_process_late_acks()` is called from two places. Normally it runs after the
newly acknowledged packets and the RTT estimate are processed, just before
`_detect_loss()`, so a raised K applies to the same ACK. It also runs in the
early-return branch taken when an ACK acknowledges nothing new: an ACK whose
only new information is a late packet lands there, because that packet is no
longer in `sent_packets`. Without this second call (commit c89a756, found by
Shamili's tests) those late ACKs were silently ignored.

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
started again from K=3. Time-limited decay (commit b40f456) fixed this.
Decay steps are logged as `recovery:k_decayed` (section 8).

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
it ends.

In 3-run tests at moderate, K still fell back to 3 about 30 times per run
(once every 2 to 3 s). A slower decay (K_DECAY 0.97, about 85 clean RTTs from
40 to 3) did not reduce the resets or improve goodput, so 0.9 was kept. The
limit on threshold-only adaptation turned out not to be the decay rate but
the cost of each burst that is declared lost before K rises (section 7).

---

## 5. Gating

Every dynamic code path is gated on `self._dynamic_mode or
self._dynamic_undo_mode`. With `AIOQUIC_PACKET_THRESHOLD` unset or an
integer, both are False: `effective_k` equals the static threshold,
`_recent_lost` is never filled, and `_adapt_k` and decay never run, so
behaviour is identical to stock. The existing test suite passes unchanged.

---

## 6. Time Threshold Extension (not triggered)

The decision rule from Day 2: if the "time" rule and PTO together account for
more than half of spurious losses under stock at both moderate and severe,
adapt `K_TIME_THRESHOLD` as well.

Reethika's instrumented attribution (commit 60a3fc8, 5 runs per cell) shows
the condition is not met. Under stock, the packet rule dominates:

| Profile | Variant | Losses | packet | time | both | pto |
|---|---|---:|---:|---:|---:|---:|
| moderate | stock | 3,902 | 3,038 (78%) | 504 (13%) | 360 | 0 |
| moderate | k20 | 3,466 | 129 (4%) | 3,232 (93%) | 105 | 0 |
| severe | stock | 3,321 | 2,581 (78%) | 417 (13%) | 322 | 1 |
| severe | k20 | 2,823 | 358 (13%) | 2,406 (85%) | 59 | 0 |

The k20 rows matter more for the design than the rule itself. Once K is
high, almost every remaining loss is declared by the time threshold instead:
raising K moves losses to the other rule rather than removing them. Total
losses fall by only about 11 to 15%. This is why adapting the packet
threshold alone cannot match the gains from undoing spurious congestion
responses, and why `dynamic_undo` tracks losses from every rule (section 7).

---

## 7. dynamic_undo

### 7.1 Why

Threshold adaptation is reactive. K rises only after a late ACK proves a loss
spurious, and by then the burst that produced it has already been declared
lost and has cut the congestion window. With K falling back between bursts,
dynamic alone performed at stock level. In the same moderate session as the
numbers in 7.4, `dynamic` reached 0.938 Mbps against stock 0.958 and k20 1.324;
Shamili's independent 3-run test on another machine gave 0.996 Mbps for
dynamic. `dynamic_undo` removes the cost instead: it keeps the adaptive K
and also rolls back the window cut once the losses that caused it prove
spurious.

### 7.2 Algorithm

1. **Snapshot.** In `_detect_loss()`, in `dynamic_undo` mode and for the
   application-data space, the congestion controller's state is copied just
   before the losses are reported. The copy takes every scalar field
   (`congestion_window`, `ssthresh` and, for Cubic, `_W_max`, `_W_est`,
   `_cwnd_epoch`, `_t_epoch`, `K`, `_starting_congestion_avoidance`,
   `_congestion_recovery_start_time`), except those in
   `UNDO_EXCLUDED_FIELDS`: `bytes_in_flight`, which tracks packets actually
   outstanding, and the measurements `rtt` and `last_ack`.
2. **Open an episode.** After the losses are reported, the state is compared
   with the snapshot. If it changed, the window was cut and an undo episode
   opens: the snapshot is kept and every ack-eliciting lost packet is added
   to `_undo_pending` with its loss time. Losses while an episode is open are
   added to it whether or not they cut the window again, whatever rule
   declared them.
3. **Late ACKs.** `_process_late_acks()` removes each late-acknowledged
   packet from `_undo_pending`. When the set is empty, every loss in the
   episode was spurious: the snapshot is restored (unless the window has
   already grown past it), the pacer rate is updated and
   `recovery:cwnd_restored` is logged.
4. **Abandon.** At the start of each ACK, if any pending loss is older than
   2 × smoothed RTT without a late ACK, it is treated as genuine and the
   episode is dropped; the cut stands. Persistent congestion, or more than
   `MAX_UNDO_PENDING` (256) pending losses, also abandons the episode.
   `recovery:undo_abandoned` records the reason.

Restoring only when every loss in the episode proves spurious is the same
conservative rule as TCP's Eifel response (RFC 4015) and Linux's congestion
undo. A genuine loss in the episode always keeps the reduction, so the
sender never becomes more aggressive than its congestion controller would
be without the spurious losses.

### 7.3 Tests

`tests/test_dynamic_undo.py` (9 tests, Reno and Cubic): restore when all
losses are spurious; no restore on partial late ACKs; abandon on a genuine
loss, including a very late ACK afterwards; `bytes_in_flight` untouched by
a restore; restore logged; no snapshot in `dynamic`, integer or unset modes;
a second burst inside an open episode must also prove spurious; too many
pending losses abandon; decay logged. Two deliberate faults (skipping the
restore, and restoring `bytes_in_flight`) were each caught by the tests.

### 7.4 First results

Moderate profile, 10 MB, 3 runs per variant in one session (WSL laptop):

| Variant | Runs (Mbps) | Mean | vs stock |
|---|---|---:|---:|
| stock | 0.969, 0.984, 1.038 | 0.997 | |
| k20 | 1.263, 1.266, 1.320 | 1.283 | +29% |
| dynamic_undo | 2.054, 1.834, 1.761 | 1.883 | +89% |

The slowest `dynamic_undo` run was faster than the fastest k20 run. Each run
had 104 to 135 restores and 27 to 35 abandoned episodes. At the profile's
0.3% random loss, a 10 MB transfer (about 8,700 packets) is expected to lose
about 26 packets genuinely, which matches the abandoned count: real losses
keep their window reduction and only reordering is undone.

On the loss-free baseline profile (10 MB, 3 runs each), `dynamic_undo`
recorded no restores and reached 12.866, 12.912 and 12.713 Mbps (mean
12.830) against stock's 12.918 and 12.929 Mbps (−0.7%), within the 2%
target. A third stock run (10.270 Mbps) was a one-off slow start and is
excluded from that comparison; including it, the stock mean is 12.039.

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

### recovery:k_decayed

Emitted at each decay step (at most once per smoothed RTT), with `old_k` and
`new_k`. Together with `k_adapted`, this gives the full K timeline.

### recovery:cwnd_restored

Emitted when a `dynamic_undo` episode is restored, with `old_cwnd` (the cut
window) and `new_cwnd` (the restored one).

### recovery:undo_abandoned

Emitted when an episode is dropped, with `reason` ("genuine_loss",
"persistent_congestion" or "too_many_losses") and the number of losses still
pending.

### recovery:packet_lost

Carries `rule` ("packet", "time", "both", "pto" or "handshake"), `by_packet`
and `by_time` from the Day 1 rule-attribution patch, which is how losses
eligible for `_recent_lost` can be identified in the qlogs.

---

## 9. Open Questions

- Other profiles: severe and handover may differ, especially handover with
  1% genuine loss (more abandoned episodes).
- Official numbers: Reethika's matrix on the frozen pin, all variants in one
  session; the results in 7.4 come from a noisier WSL setup.
- Fairness: a paragraph in the report on why undo is safe (section 7.2).