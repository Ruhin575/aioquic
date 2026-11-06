#!/usr/bin/env bash
# experiments/video/local_smoke_test.sh [extra stream_client args...]
#
# End-to-end test on THIS machine, no namespaces and no sudo: starts the aioquic example server on 127.0.0.1
# serving experiments/video/content_local/, runs stream_client.py against it, then parse_video_results.py.
# On loopback the link is very fast, so expect: no stalls, startup well under 3 s, bitrate climbing to the top rung.
# (Stalls and rung changes under impairment are tested by the offline unit tests and, later, on the real topology.)
#
# Run from anywhere, inside the environment where aioquic and its example dependencies are installed:
#     bash experiments/video/make_video_content.sh        # Amrutha's builder, 2-minute video
#     bash experiments/video/local_smoke_test.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
CONTENT="$HERE/content"
[ -f "$CONTENT/manifest.mpd" ] || CONTENT="$HERE/content_local"
WORK="$(mktemp -d)"
[ -f "$CONTENT/manifest.mpd" ] || { echo "No video content: run  bash experiments/video/make_video_content.sh  (Amrutha, about 40 s) first"; exit 1; }

openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 2 \
    -subj "/CN=127.0.0.1" -addext "subjectAltName=IP:127.0.0.1" \
    -keyout "$WORK/key.pem" -out "$WORK/cert.pem" 2>/dev/null

mkdir -p "$WORK/server-qlog"      # aioquic refuses a qlog directory that does not exist
STATIC_ROOT="$CONTENT" python "$ROOT/examples/http3_server.py" --host 127.0.0.1 --port 4433 \
    --certificate "$WORK/cert.pem" --private-key "$WORK/key.pem" \
    --quic-log "$WORK/server-qlog" --congestion-control-algorithm cubic > "$WORK/server.log" 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true' EXIT
for _ in $(seq 1 50); do grep -q "Listening\|Starting server" "$WORK/server.log" 2>/dev/null && break; sleep 0.2; done
sleep 1

python "$HERE/stream_client.py" --url https://127.0.0.1:4433/manifest.mpd --ca-certs "$WORK/cert.pem" \
    --run-id smoke__loopback__1 --segments-out "$WORK/run/segments.csv" --qlog-dir "$WORK/client-qlog" "$@"
echo
python "$HERE/parse_video_results.py" "$WORK/run" --output "$WORK/video_results.csv"
cat "$WORK/video_results.csv"
echo "(work files kept in $WORK)"