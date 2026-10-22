#!/usr/bin/env bash
# experiments/analysis/collect_sample_qlogs.sh   (Person 3)
#
# Produces REAL qlogs by chaining P1's and P2's scripts:
#   topology (P1) -> netem profile (P2) -> run_transfer.py (P1) -> teardown.
# Runs one 10 MB download per profile with variant "p3sample".
#
# Run from the repository root, inside your activated virtualenv, on Linux/WSL2:
#     bash experiments/analysis/collect_sample_qlogs.sh
#     bash experiments/analysis/collect_sample_qlogs.sh baseline moderate
#     bash experiments/analysis/collect_sample_qlogs.sh --overwrite moderate   # replace existing sample data
#     P3_VARIANT=p3sample2 bash experiments/analysis/collect_sample_qlogs.sh moderate   # keep old data, new name
#
# Existing sample data is never deleted silently: if logs for the variant already exist the
# script stops and tells you the two ways to continue. Variant names must start with "p3sample"
# so analyze_runs.py keeps excluding them from final results.
#
# Safety properties:
#   * profile names are validated before anything is changed
#   * refuses to run if the ns-* namespaces already exist (will not destroy anyone's setup)
#   * netem support is tested inside a throw-away namespace, never on a host interface
#   * run_transfer.py normally appends to the team's experiments/results/transfers.csv.
#     This script runs it through run_sample_transfer.py, which redirects the result row to
#     experiments/analysis/sample_data/transfers_p3sample.csv, so the team CSV is never opened
#     or modified (nothing to back up or restore).
#   * cleanup (netem, namespaces) is installed before anything is modified
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

VALID_PROFILES="baseline mild moderate severe handover"
VARIANT="${P3_VARIANT:-p3sample}"
case "$VARIANT" in
    p3sample*) ;;
    *) echo "P3_VARIANT must start with 'p3sample' (got '$VARIANT') so samples stay out of final results." >&2; exit 2 ;;
esac
OVERWRITE=0
FILE="10MB.bin"
EXPECTED_SIZE=10485760
RUN=1
SAMPLE_OUT="experiments/analysis/sample_data/transfers_${VARIANT}.csv"

PROFILES=()
for ARG in "$@"; do
    if [ "$ARG" = "--overwrite" ]; then OVERWRITE=1; else PROFILES+=("$ARG"); fi
done
[ ${#PROFILES[@]} -eq 0 ] && PROFILES=(baseline moderate severe)
for P in "${PROFILES[@]}"; do
    case " $VALID_PROFILES " in
        *" $P "*) ;;
        *) echo "Unknown profile '$P'. Valid: $VALID_PROFILES" >&2; exit 2 ;;
    esac
done

# Refuse to destroy existing sample data unless explicitly told to (checked before any sudo/network change).
EXISTING=""
for D in experiments/transfer/server-qlog/$VARIANT experiments/transfer/client-qlog/$VARIANT \
         experiments/transfer/downloaded/$VARIANT "$SAMPLE_OUT"; do
    [ -e "$D" ] && EXISTING="$EXISTING $D"
done
if [ -n "$EXISTING" ] && [ "$OVERWRITE" = 0 ]; then
    echo "Existing '$VARIANT' sample data found:$EXISTING" >&2
    echo "Nothing was changed. Either:" >&2
    echo "  1) keep it and collect under a new name:  P3_VARIANT=${VARIANT}2 bash $0 ${PROFILES[*]}" >&2
    echo "  2) back it up, then replace it:  sudo cp -a experiments/transfer/server-qlog/$VARIANT ~/${VARIANT}-backup" >&2
    echo "     and rerun with:  bash $0 --overwrite ${PROFILES[*]}" >&2
    exit 3
fi

TOPOLOGY_UP=0
NETEM_APPLIED=0

cleanup() {
    set +e
    echo "== cleanup =="
    [ "$NETEM_APPLIED" = 1 ] && sudo bash experiments/netem/teardown.sh rc0 rs0 ns-router
    [ "$TOPOLOGY_UP" = 1 ] && sudo bash experiments/topology/destroy.sh
}

trap cleanup EXIT

echo "== 0. checks =="
sudo -v
for c in ip tc openssl; do
    command -v "$c" >/dev/null || { echo "'$c' not found (sudo apt install iproute2 openssl)"; exit 1; }
done
python -c "import aioquic" 2>/dev/null || { echo "aioquic not importable: activate the venv and run pip install -e '.[dev]'"; exit 1; }
# examples/http3_server.py and its default app (examples/demo.py) need extra packages
# that "pip install -e ." does not install.
for MOD in wsproto starlette jinja2 dnslib httpx; do
    python -c "import $MOD" 2>/dev/null || {
        echo "Python package '$MOD' is missing (needed by the aioquic examples)."
        echo "This script checked: $(command -v python)  ($(python --version 2>&1))"
        echo "Install into THAT python with:"
        echo "    python -m pip install wsproto starlette jinja2 dnslib httpx"
        echo "If the path above is not your project's .venv, run: source .venv/bin/activate  and retry."
        exit 1
    }
done
command -v python >/dev/null && echo "using python: $(command -v python)"

for NS in ns-client ns-router ns-server; do
    if ip netns list | awk '{print $1}' | grep -Fxq "$NS"; then
        echo "Namespace $NS already exists (a leftover, or a teammate's experiment). Not touching it."
        echo "If it is a leftover, run: sudo bash experiments/topology/destroy.sh"
        exit 1
    fi
done

# netem test in a throw-away namespace (does not touch any host interface)
sudo ip netns add p3-netem-check
if ! sudo ip netns exec p3-netem-check tc qdisc add dev lo root netem delay 1ms; then
    sudo ip netns del p3-netem-check
    echo "Could not attach netem inside a test namespace. Likely the sch_netem kernel module is missing."
    echo "Try: sudo modprobe sch_netem   (on WSL2 the default kernel often lacks it: use an Ubuntu VM)"
    exit 1
fi
sudo ip netns del p3-netem-check

echo "== 1. test file (deterministic, seed 42) =="
mkdir -p experiments/transfer/www
TF="experiments/transfer/www/$FILE"
if [ -f "$TF" ]; then
    SIZE=$(stat -c %s "$TF")
    if [ "$SIZE" -ne "$EXPECTED_SIZE" ]; then
        echo "$TF exists but is $SIZE bytes, expected $EXPECTED_SIZE. Delete it or fix it, then rerun."
        exit 1
    fi
else
    python - <<'PY'
import random
open("experiments/transfer/www/10MB.bin", "wb").write(random.Random(42).randbytes(10 * 1024 * 1024))
PY
fi
ls -l "$TF"

echo "== 2. TLS certificate (from P1's README) =="
CERT=experiments/transfer/ns-cert.pem
if [ -f "$CERT" ]; then
    openssl x509 -checkend 0 -noout -in "$CERT" >/dev/null || { echo "$CERT has expired: delete it and the key, then rerun."; exit 1; }
else
    openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 14 \
        -subj "/CN=10.10.2.2" -addext "subjectAltName=IP:10.10.2.2" \
        -keyout experiments/transfer/ns-key.pem -out "$CERT"
fi

echo "== 3. clear old $VARIANT logs and sample results (only reached with --overwrite or no existing data) =="
mkdir -p "$(dirname "$SAMPLE_OUT")"
rm -f "$SAMPLE_OUT"
sudo rm -rf experiments/transfer/server-qlog/$VARIANT experiments/transfer/client-qlog/$VARIANT \
            experiments/transfer/downloaded/$VARIANT

echo "== 4. topology =="
sudo bash experiments/topology/create.sh
TOPOLOGY_UP=1

for P in "${PROFILES[@]}"; do
    echo "== 5. profile: $P =="
    sudo bash experiments/netem/setup.sh "$P" rc0 rs0 ns-router
    NETEM_APPLIED=1
    if ! python experiments/analysis/run_sample_transfer.py --file "$FILE" --variant "$VARIANT" --profile "$P" --run "$RUN" \
            --results-file "$SAMPLE_OUT"; then
        echo "ERROR: run_transfer.py failed. Last lines of experiments/transfer/server.log:" >&2
        tail -n 15 experiments/transfer/server.log >&2 || true
        exit 1
    fi
    QDIR="experiments/transfer/server-qlog/$VARIANT/$P/$RUN"
    if ! ls "$QDIR"/*.qlog >/dev/null 2>&1; then
        echo "ERROR: transfer finished but no server qlog found in $QDIR" >&2
        echo "aioquic writes the server qlog only when the server connection fully closes. If P1's" >&2
        echo "run_transfer.py stops the server immediately, apply: git apply experiments/analysis/p1_wait_for_server_qlog.patch" >&2
        exit 1
    fi
    sudo bash experiments/netem/teardown.sh rc0 rs0 ns-router
    NETEM_APPLIED=0
done

echo
echo "== done. server qlogs (the sender's logs, the ones to analyse): =="
find "experiments/transfer/server-qlog/$VARIANT" -name "*.qlog" -exec ls -l {} \;
echo "sample results: $SAMPLE_OUT   (the team's transfers.csv was not touched)"
echo
echo "Next: python experiments/analysis/parse_qlog.py --input experiments/transfer/server-qlog/$VARIANT/moderate/1 --output /tmp/moderate.csv"