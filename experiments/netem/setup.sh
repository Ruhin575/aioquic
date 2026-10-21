#!/usr/bin/env bash
# experiments/netem/setup.sh
#
# Apply one of the five fixed netem profiles to the router egress interfaces.
#   sudo ./setup.sh <profile> <DL_IF> <UL_IF> [ROUTER_NS]
# Profiles: baseline mild moderate severe handover
# ROUTER_NS: the network namespace that owns DL_IF and UL_IF. If omitted,
# both interfaces are expected to be in the root namespace. For the Day 0
# topology (ns-client <-> ns-router <-> ns-server) this is ns-router. You
# can also set the ROUTER_NS environment variable instead of passing the
# positional argument.
# Design notes:
#   - DL_IF is the router interface facing the client. The DOWNLINK profile
#     (delay, jitter, loss, reorder, rate cap) is applied here, because that
#     is where the server->client data stream is impaired.
#   - UL_IF is the router interface facing the server. Only a fixed one-way
#     delay (plus the same 15 Mbit cap, for link symmetry) is applied here,
#     so cross-profile differences come from the downlink alone and the ACK
#     path stays comparable across runs.
#   - The 15 Mbit cap is applied with netem's own `rate` option, which puts
#     impairment and shaping in one qdisc. The order is: netem decides which
#     packets to delay/drop/reorder, then releases them at 15 Mbit.

set -euo pipefail

if [ "$#" -lt 3 ] || [ "$#" -gt 4 ]; then
    echo "Usage: $0 <profile> <DL_IF> <UL_IF> [ROUTER_NS]" >&2
    echo "Profiles: baseline mild moderate severe handover" >&2
    exit 2
fi

PROFILE="$1"
DL_IF="$2"
UL_IF="$3"
ROUTER_NS="${4:-${ROUTER_NS:-}}"

RATE_CAP="15mbit"
UL_DELAY="30ms"        # fixed one-way uplink delay for every profile

# Build the ns-exec prefix. Empty array when ROUTER_NS is empty => root ns.
if [ -n "$ROUTER_NS" ]; then
    NS_EXEC=(ip netns exec "$ROUTER_NS")
    WHERE="ns=$ROUTER_NS"
else
    NS_EXEC=()
    WHERE="ns=root"
fi

# Fail fast if we don't have CAP_NET_ADMIN.
if ! tc -V >/dev/null 2>&1; then
    echo "tc (iproute2) not found" >&2
    exit 1
fi
if [ "$(id -u)" -ne 0 ]; then
    echo "This script needs root (CAP_NET_ADMIN). Re-run with sudo." >&2
    exit 1
fi

# Interfaces must exist in the chosen namespace.
for IF in "$DL_IF" "$UL_IF"; do
    if ! "${NS_EXEC[@]}" ip link show "$IF" >/dev/null 2>&1; then
        echo "Interface not found: $IF (${WHERE})" >&2
        echo "Hint: pass the router namespace as the 4th argument," \
             "e.g. ./setup.sh $PROFILE $DL_IF $UL_IF ns-router" >&2
        exit 1
    fi
done

# Clear any existing root qdiscs.
"${NS_EXEC[@]}" tc qdisc del dev "$DL_IF" root 2>/dev/null || true
"${NS_EXEC[@]}" tc qdisc del dev "$UL_IF" root 2>/dev/null || true

case "$PROFILE" in
    baseline)
        # Clean LTE: 30 ms +/- 5 ms, no impairments.
        DL_NETEM="delay 30ms 5ms distribution normal rate ${RATE_CAP}"
        ;;
    mild)
        # Good LTE: 40 ms +/- 10 ms, 0.1% independent loss, 5% reorder with 25% corr.
        DL_NETEM="delay 40ms 10ms distribution normal loss random 0.1% reorder 5% 25% rate ${RATE_CAP}"
        ;;
    moderate)
        # Typical LTE: 50 ms +/- 15 ms, 0.3% independent loss, 15% reorder with 50% corr.
        DL_NETEM="delay 50ms 15ms distribution normal loss random 0.3% reorder 15% 50% rate ${RATE_CAP}"
        ;;
    severe)
        # Cell edge: 70 ms +/- 25 ms, 0.5% independent loss, 25% reorder with 75% corr.
        DL_NETEM="delay 70ms 25ms distribution normal loss random 0.5% reorder 25% 75% rate ${RATE_CAP}"
        ;;
    handover)
        # Tower handover: 80 ms +/- 40 ms, 1% independent loss, 30% reorder with 80% corr.
        # Loss correlation parameter is deliberately omitted: tc-netem(8) marks it
        # deprecated ("bad behavior"), and in practice it causes drop probability
        # to collapse to zero at small p when correlation is high.
        DL_NETEM="delay 80ms 40ms distribution normal loss random 1% reorder 30% 80% rate ${RATE_CAP}"
        ;;
    *)
        echo "Unknown profile: $PROFILE" >&2
        echo "Profiles: baseline mild moderate severe handover" >&2
        exit 2
        ;;
esac

# Downlink: full profile.
# shellcheck disable=SC2086
"${NS_EXEC[@]}" tc qdisc add dev "$DL_IF" root handle 10: netem ${DL_NETEM}

# Uplink: fixed delay + same rate cap (no jitter/loss/reorder).
"${NS_EXEC[@]}" tc qdisc add dev "$UL_IF" root handle 10: netem delay "${UL_DELAY}" rate "${RATE_CAP}"

echo "Applied profile: ${PROFILE} (${WHERE}) "
echo "${DL_IF} (downlink, server -> client) "
"${NS_EXEC[@]}" tc qdisc show dev "$DL_IF"
echo "${UL_IF} (uplink, client -> server) "
"${NS_EXEC[@]}" tc qdisc show dev "$UL_IF"
