# Congestion-only safety experiment

## Network profile

- No configured packet reordering
- No configured random packet loss
- 30 ms one-way delay
- 15 Mbit/s rate cap
- 30-packet queue

This is a congestion-only profile, not a loss-free profile.
Queue overflow can still cause packet drops.

## Experimental runs

- Stock: 5 runs
- Dynamic Undo: 5 runs
- All 10 downloads passed SHA-256 verification.

## Goodput

| Variant | Mean goodput |
|---|---:|
| Stock | 4.4182 Mbps |
| Dynamic Undo | 4.4516 Mbps |

Dynamic Undo had a descriptive mean-goodput increase of approximately
0.76%. This is not evidence of a statistically significant improvement.

## Server-side qlog verification

Exactly five large server qlogs per variant were inspected.

| Event/count | Stock | Dynamic Undo |
|---|---:|---:|
| cwnd_restored | 0 | 0 |
| undo_abandoned | 0 | 114 |
| undo_abandoned with reason=genuine_loss | 0 | 114 |

The 114 genuine_loss counts are the reason values associated with
the 114 undo_abandoned events. They are not additional standalone
events.

No congestion-window restoration occurred in either variant.
Dynamic Undo abandoned undo when genuine loss was detected.

## Interpretation and limitation

The results show that, in this tested congestion-only profile,
Dynamic Undo did not restore congestion state and abandoned undo
when genuine loss was detected. Queue overflow can cause packet
drops even though random loss was not configured.

These results describe this specific profile and do not establish
safety under every possible network condition.

Environment: Ubuntu WSL2.
