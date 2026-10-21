#!/usr/bin/env bash
set -Eeuo pipefail

# Person 1: remove the isolated client-router-server topology.
# Run with sudo: sudo bash experiments/topology/destroy.sh

NAMESPACES=(ns-client ns-router ns-server)

for ns in "${NAMESPACES[@]}"; do
    if ip netns list | awk '{print $1}' | grep -Fxq "$ns"; then
        echo "Removing namespace: $ns"
        ip netns del "$ns"
    else
        echo "Namespace $ns does not exist; skipping."
    fi
done

echo "Topology cleanup complete."
