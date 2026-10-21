# Network emulation profiles

Five profiles span clean LTE to tower handover. All values below are the
**configured** inputs to netem on the downlink. Uplink carries only a fixed
30 ms one-way delay plus the 15 Mbit cap, so cross-profile differences are
attributable to the downlink alone.

| Profile  | One-way delay | Jitter | Loss (independent) | Reorder (prob / corr) | Rate cap | Use case          |
|----------|---------------|--------|--------------------|-----------------------|----------|-------------------|
| baseline | 30 ms         | 5 ms   | 0 %                | 0 % / n/a             | 15 Mbit  | Clean LTE         |
| mild     | 40 ms         | 10 ms  | 0.1 %              | 5 % / 25 %            | 15 Mbit  | Good LTE          |
| moderate | 50 ms         | 15 ms  | 0.3 %              | 15 % / 50 %           | 15 Mbit  | Typical LTE       |
| severe   | 70 ms         | 25 ms  | 0.5 %              | 25 % / 75 %           | 15 Mbit  | Cell edge         |
| handover | 80 ms         | 40 ms  | 1 %                | 30 % / 80 %           | 15 Mbit  | Tower handover    |

Jitter uses a normal distribution (`distribution normal`), as is standard for
netem when modelling radio-link delay variation.

Loss is applied with `loss random P` (independent per-packet Bernoulli). The
correlated-loss syntax `loss P C%` is deliberately avoided: `tc-netem(8)`
marks the correlation parameter deprecated due to "noticed bad behavior",
and we verified empirically that at small p and high correlation the
Markov walk underlying the correlated model stays near its mean and
produces essentially zero drops over sample sizes in the thousands.
Reorder uses correlation because its underlying model is independent of
loss and empirically works as advertised.

## Why configured != observed

`netem reorder N% M%` is a **probability model**, not a target observed rate:

- `N%` is the probability that any given packet is sent immediately (ahead of
  the current delay queue), making it a candidate for arriving before packets
  queued ahead of it.
- `M%` is the correlation to the previous reorder decision, which clumps
  reordering events.

A packet marked for immediate send only *becomes* an out-of-order arrival
if a packet behind it in queue happens to be scheduled with less remaining
delay. So the observed out-of-order rate depends on jitter, offered rate,
and the rate cap, not only on `N%`. The same caveat applies to `loss N% M%`
when `M% > 0`, because losses then arrive in bursts rather than independently.

Report the **measured** values from `verify.sh` and keep the configured
values as the recipe used to produce them.

## Measured values (fill in from verify.sh)

| Profile  | Delay (RTT / 2) | Jitter | Loss | Reorder |
|----------|-----------------|--------|------|---------|
| baseline |                 |        |      |         |
| mild     |                 |        |      |         |
| moderate |                 |        |      |         |
| severe   |                 |        |      |         |
| handover |                 |        |      |         |
