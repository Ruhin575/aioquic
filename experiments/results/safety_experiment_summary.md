# Congestion-only safety experiment

Profile:
- No packet reordering
- No random packet loss
- 30 ms one-way delay
- 15 Mbit/s rate cap
- Queue limit: 30

Variants and runs:
- Stock: 5 runs
- Dynamic Undo: 5 runs
- All 10 downloads passed SHA-256 verification.

Mean goodput:
- Stock: 4.4182 Mbps
- Dynamic Undo: 4.4516 Mbps
- Descriptive difference: +0.76%

Qlog verification:
- Stock: 14 qlog files inspected
- Dynamic Undo: 10 qlog files inspected
- cwnd_restored events: 0
- undo_abandoned events: 0
- genuine_loss events: 0

Interpretation:
No genuine-loss, restoration or abandonment events were observed in
this loss-free, reordering-free profile. This supports the expected
no-unnecessary-undo behavior under this tested condition; it does not
establish safety under every possible network condition.

Environment: Ubuntu WSL2.
