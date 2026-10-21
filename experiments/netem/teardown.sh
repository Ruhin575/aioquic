#!/usr/bin/env bash
# experiments/netem/teardown.sh
#
# Remove any root qdisc from the two router interfaces. Safe to run even if
# no qdisc is attached.
#
# Usage:
#   sudo ./teardown.sh <DL_IF> <UL_IF> [ROUTER_NS]

set -euo pipefail

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
    echo "Usage: $0 <DL_IF> <UL_IF> [ROUTER_NS]" >&2
    exit 2
fi

DL_IF="$1"
UL_IF="$2"
ROUTER_NS="${3:-${ROUTER_NS:-}}"

if [ "$(id -u)" -ne 0 ]; then
    echo "This script needs root. Re-run with sudo." >&2
    exit 1
fi

if [ -n "$ROUTER_NS" ]; then
    NS_EXEC=(ip netns exec "$ROUTER_NS")
    WHERE="ns=$ROUTER_NS"
else
    NS_EXEC=()
    WHERE="ns=root"
fi

"${NS_EXEC[@]}" tc qdisc del dev "$DL_IF" root 2>/dev/null || true
"${NS_EXEC[@]}" tc qdisc del dev "$UL_IF" root 2>/dev/null || true

echo "Teardown complete (${WHERE})."
echo "--- ${DL_IF} ---"
"${NS_EXEC[@]}" tc qdisc show dev "$DL_IF" || true
echo "--- ${UL_IF} ---"
"${NS_EXEC[@]}" tc qdisc show dev "$UL_IF" || true
