#!/usr/bin/env bash
set -Eeuo pipefail

# Person 1: create the isolated client-router-server topology.
# Run with sudo: sudo bash experiments/topology/create.sh

NAMESPACES=(ns-client ns-router ns-server)

# Refuse to interfere with an existing test setup.
for ns in "${NAMESPACES[@]}"; do
    if ip netns list | awk '{print $1}' | grep -Fxq "$ns"; then
        echo "STOP: namespace $ns already exists."
        exit 1
    fi
done

for iface in c0 rc0 rs0 s0; do
    if ip link show "$iface" >/dev/null 2>&1; then
        echo "STOP: interface $iface already exists on the host."
        exit 1
    fi
done

# If setup fails halfway through, remove only our named namespaces.
cleanup_on_error() {
    status=$?
    if [ "$status" -ne 0 ]; then
        echo "Setup failed; cleaning up namespaces created by this script."
        for ns in "${NAMESPACES[@]}"; do
            ip netns del "$ns" 2>/dev/null || true
        done
    fi
    exit "$status"
}
trap cleanup_on_error EXIT

ip netns add ns-client
ip netns add ns-router
ip netns add ns-server

# Link 1: client <-> router
ip link add c0 type veth peer name rc0
ip link set c0 netns ns-client
ip link set rc0 netns ns-router

# Link 2: router <-> server
ip link add rs0 type veth peer name s0
ip link set rs0 netns ns-router
ip link set s0 netns ns-server

# Configure client interface and default route.
ip -n ns-client link set lo up
ip -n ns-client link set c0 up
ip -n ns-client addr add 10.10.1.2/24 dev c0
ip -n ns-client route add default via 10.10.1.1

# Configure router interfaces and enable forwarding only here.
ip -n ns-router link set lo up
ip -n ns-router link set rc0 up
ip -n ns-router addr add 10.10.1.1/24 dev rc0
ip -n ns-router link set rs0 up
ip -n ns-router addr add 10.10.2.1/24 dev rs0
ip netns exec ns-router sysctl -w net.ipv4.ip_forward=1

# Configure server interface and default route.
ip -n ns-server link set lo up
ip -n ns-server link set s0 up
ip -n ns-server addr add 10.10.2.2/24 dev s0
ip -n ns-server route add default via 10.10.2.1

trap - EXIT

echo
echo "Topology created successfully."
echo "Client: 10.10.1.2"
echo "Router: 10.10.1.1 and 10.10.2.1"
echo "Server: 10.10.2.2"
echo "DL_IF=rc0"
echo "UL_IF=rs0"
