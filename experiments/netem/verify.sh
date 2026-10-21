#!/usr/bin/env bash
# Apply a profile and measure what the client actually sees. Produces:
#   sudo ./verify.sh <profile> <DL_IF> <UL_IF>
# Environment overrides: 
#   ROUTER_NS  (default ns-router)   # where DL_IF and UL_IF live
#   CLIENT_NS  (default ns-client)
#   SERVER_NS  (default ns-server)
#   CLIENT_IF  (default veth-c)      # client-side veth inside ns-client
#   CLIENT_IP  (default 10.0.1.1)    # IP of client inside ns-client
#   SERVER_IP  (default 10.0.2.2)    # IP of server inside ns-server
#   PORT       (default 55000)
#   COUNT      (default 2000)        # UDP probe packets
#   INTERVAL   (default 0.005)       # seconds between probe packets
#   OUT_DIR    (default ./verify-out)

set -euo pipefail

if [ "$#" -ne 3 ]; then
    echo "Usage: $0 <profile> <DL_IF> <UL_IF>" >&2
    exit 2
fi

PROFILE="$1"
DL_IF="$2"
UL_IF="$3"

ROUTER_NS="${ROUTER_NS:-ns-router}"
CLIENT_NS="${CLIENT_NS:-ns-client}"
SERVER_NS="${SERVER_NS:-ns-server}"
CLIENT_IF="${CLIENT_IF:-veth-c}"
CLIENT_IP="${CLIENT_IP:-10.0.1.1}"
SERVER_IP="${SERVER_IP:-10.0.2.2}"
PORT="${PORT:-55000}"
COUNT="${COUNT:-2000}"
INTERVAL="${INTERVAL:-0.005}"
OUT_DIR="${OUT_DIR:-./verify-out}"

HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$OUT_DIR"
PCAP="$OUT_DIR/${PROFILE}.pcap"
CSV="$OUT_DIR/${PROFILE}.csv"

if [ "$(id -u)" -ne 0 ]; then
    echo "This script needs root. Re-run with sudo." >&2
    exit 1
fi

"$HERE/setup.sh" "$PROFILE" "$DL_IF" "$UL_IF" "$ROUTER_NS"

echo
echo "Verifying profile: $PROFILE "

# Ping - delay and jitter sanity check. RTT is uplink + downlink one-way.
echo
echo "ping (300 packets, 20 ms apart) "
ip netns exec "$CLIENT_NS" ping -c 300 -i 0.02 -q "$SERVER_IP" | tail -4 || true

# UDP probe with pcap on the client side.
echo
echo "--- UDP probe (${COUNT} packets, ${INTERVAL}s interval) ---"

# tcpdump on the client-side interface. -U flushes per packet, -s 0 captures full.
ip netns exec "$CLIENT_NS" tcpdump -i "$CLIENT_IF" -U -s 0 \
    -w "$PCAP" "udp and port $PORT" >/dev/null 2>&1 &
TPID=$!
sleep 0.5

# Receiver in the client ns.
ip netns exec "$CLIENT_NS" python3 "$HERE/udp_probe.py" receiver \
    "$PORT" "$CSV" --duration "$(python3 -c "print(${COUNT}*${INTERVAL}+5)")" &
RPID=$!
sleep 0.3

# Sender in the server ns, aimed at the CLIENT's IP.
ip netns exec "$SERVER_NS" python3 "$HERE/udp_probe.py" sender \
    "$CLIENT_IP" "$PORT" --count "$COUNT" --interval "$INTERVAL"

# Let in-flight packets drain through netem's delay queue. For moderate
# that's 50 ms +/- 15 ms; for handover it can approach 120 ms. 3 s is
# generous and keeps verify.sh deterministic.
sleep 3

# Receiver writes rows incrementally and handles SIGTERM cleanly, so a
# kill here is safe. We then wait so the final flush completes.
kill "$RPID" 2>/dev/null || true
wait "$RPID" 2>/dev/null || true
kill "$TPID" 2>/dev/null || true
wait "$TPID" 2>/dev/null || true

# Analysis.
python3 "$HERE/analyze_probe.py" "$CSV" "$PROFILE"

echo
echo "pcap : $PCAP"
echo "csv  : $CSV"
echo
echo "Compare observed values to the configured values in profiles.md."
