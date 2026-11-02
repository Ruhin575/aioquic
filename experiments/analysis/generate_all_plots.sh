#!/usr/bin/env bash
# experiments/analysis/generate_all_plots.sh   (Person 5)
#
# One command: select main-matrix QUIC runs -> parse qlogs -> detect spurious losses
# -> compute metrics -> Plots 1-4.   Strict: stops with a clear message if data is missing.
#
#   bash experiments/analysis/generate_all_plots.sh --check   # validate inputs only
#   bash experiments/analysis/generate_all_plots.sh           # full pipeline
#
# Environment overrides: QUIC_CSV TCP_CSV OUT_DIR WORK_DIR QLOG_ROOT EXPECTED_RUNS ALLOW_PARTIAL=1
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

QUIC_CSV="${QUIC_CSV:-experiments/results/transfers.csv}"
TCP_CSV="${TCP_CSV:-experiments/results/tcp.csv}"
OUT_DIR="${OUT_DIR:-experiments/report/plots}"
WORK_DIR="${WORK_DIR:-experiments/analysis/work_main}"
QLOG_ROOT="${QLOG_ROOT:-experiments/results}"
EXPECTED_RUNS="${EXPECTED_RUNS:-5}"
ALLOW_PARTIAL="${ALLOW_PARTIAL:-0}"
A=experiments/analysis

MODE="${1:-}"
if [[ -n "$MODE" && "$MODE" != "--check" ]]; then
    echo "Usage: bash $A/generate_all_plots.sh [--check]" >&2
    exit 2
fi

for f in "$QUIC_CSV" "$TCP_CSV" "$A/parse_qlog.py" "$A/detect_spurious.py" \
         "$A/compute_metrics.py" "$A/plot_results.py" "$A/plot_mechanism.py"; do
    [[ -f "$f" ]] || { echo "ERROR: required file not found: $f" >&2; exit 2; }
done
python -c 'import pandas, matplotlib' >/dev/null 2>&1 \
    || { echo "ERROR: pandas and matplotlib must be installed in the active Python environment." >&2; exit 2; }

echo "QUIC results: $QUIC_CSV"
echo "TCP results:  $TCP_CSV"
echo "Qlog root:    $QLOG_ROOT"
echo "Work dir:     $WORK_DIR   (main-matrix analysis only)"
echo "Output dir:   $OUT_DIR"
mkdir -p "$WORK_DIR"

# ---- 1. select successful 10 MB stock / huge-threshold runs and locate server qlogs ----
python - "$QUIC_CSV" "$WORK_DIR" "$QLOG_ROOT" "$EXPECTED_RUNS" "$ALLOW_PARTIAL" <<'PY'
import sys
from pathlib import Path
import pandas as pd

csv_path, work_dir, qlog_root = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
expected, allow_partial = int(sys.argv[4]), sys.argv[5] == "1"
VARIANTS = ["stock", "huge-threshold"]
PROFILES = ["baseline", "mild", "moderate", "severe", "handover"]

df = pd.read_csv(csv_path, dtype=str)
df.columns = [c.strip() for c in df.columns]
required = {"variant", "profile", "file_size", "run", "sha256_ok", "qlog_path", "goodput_mbps"}
missing = required - set(df.columns)
if missing:
    raise SystemExit(f"ERROR: {csv_path} is missing columns: {sorted(missing)}")

def size_bytes(value):
    text = str(value).strip().upper()
    try:
        if text.endswith("MB"):
            return int(float(text[:-2]) * 1_000_000)
        return int(float(text))
    except ValueError:
        return None

df["_size"] = df["file_size"].map(size_bytes)
sel = df[
    df["variant"].isin(VARIANTS)
    & df["profile"].isin(PROFILES)
    & df["sha256_ok"].str.strip().str.lower().isin(["true", "1", "yes"])
    & df["_size"].isin([10_000_000, 10_485_760])      # "10MB" label or 10 MiB in bytes
].copy()

if sel.empty:
    print("ERROR: no successful 10 MB stock/huge-threshold runs found in", csv_path)
    print("The CSV probably holds only smoke tests. Obtain the main-matrix results; nothing was generated.")
    raise SystemExit(3)

dups = sel[sel.duplicated(["variant", "profile", "run"], keep=False)]
if not dups.empty:
    print("ERROR: duplicate (variant, profile, run) rows; resolve them first:")
    print(dups[["variant", "profile", "run"]].drop_duplicates().to_string(index=False))
    raise SystemExit(4)

counts = sel.groupby(["variant", "profile"]).size()
problems = []
print(f"Selected successful 10 MB QUIC runs (expected {expected} per cell):")
for v in VARIANTS:
    for p in PROFILES:
        n = int(counts.get((v, p), 0))
        print(f"  {v:15} {p:10} runs={n}")
        if n != expected:
            problems.append(f"{v}/{p}: {n}")
if problems and not allow_partial:
    print("ERROR: incomplete matrix -> " + ", ".join(problems))
    print("Get the missing runs, or set ALLOW_PARTIAL=1 to proceed knowingly (results will be partial).")
    raise SystemExit(3)

def find_server_dir(row):
    qp = Path(str(row["qlog_path"]).strip())
    cands = []
    if "client-qlog" in qp.parts:                       # older layout: .../client-qlog/...
        cands.append(Path(*["server-qlog" if x == "client-qlog" else x for x in qp.parts]))
    else:                                               # current layout: qlog_path is the run dir
        cands.append(qp / "server-qlog")
    cands.append(qlog_root / row["variant"] / row["profile"] / f"run_{row['run']}" / "server-qlog")
    for c in cands:
        if c.is_dir() and any(c.glob("*.qlog")):
            return str(c), cands
    return None, cands

dirs, bad = [], []
for _, row in sel.iterrows():
    d, cands = find_server_dir(row)
    dirs.append(d)
    if d is None:
        bad.append((row["variant"], row["profile"], row["run"], cands[-1]))
if bad:
    print(f"ERROR: {len(bad)} selected run(s) have no server qlog:")
    for v, p, r, c in bad[:10]:
        print(f"  {v}/{p}/run {r}: expected e.g. {c}")
    if len(bad) > 10:
        print(f"  ... and {len(bad) - 10} more")
    print("Get the server-qlog folders (layout <variant>/<profile>/run_N/server-qlog) and set QLOG_ROOT if needed.")
    raise SystemExit(5)

sel["server_dir"] = dirs
sel["run_num"] = pd.to_numeric(sel["run"], errors="coerce")
sel = sel.sort_values(["variant", "profile", "run_num"])
work_dir.mkdir(parents=True, exist_ok=True)
sel[["variant", "profile", "run", "server_dir"]].to_csv(work_dir / "selected_runs.tsv", sep="\t", index=False)
out = sel.drop(columns=["_size", "run_num"]).copy()
out.insert(out.columns.get_loc("file_size"), "file_size_raw", out["file_size"])
out["file_size"] = "10MB"                               # normalised label used downstream
out.to_csv(work_dir / "selected_quic.csv", index=False)
print(f"Wrote {work_dir / 'selected_runs.tsv'} and {work_dir / 'selected_quic.csv'} ({len(out)} runs)")
PY

if [[ "$MODE" == "--check" ]]; then
    echo "Validation passed. No analysis or plots were generated."
    exit 0
fi

# ---- 2. per run: parse -> detect spurious -> metrics ----
mkdir -p "$WORK_DIR/parsed" "$WORK_DIR/spurious" "$WORK_DIR/metrics" "$OUT_DIR"
n=0
while IFS=$'\t' read -r variant profile run server_dir; do
    tag="${variant}__${profile}__${run}"
    echo "== $tag"
    python "$A/parse_qlog.py" --input "$server_dir" --output "$WORK_DIR/parsed/$tag.csv"
    python "$A/detect_spurious.py" --input "$WORK_DIR/parsed/$tag.csv" --output "$WORK_DIR/spurious/$tag.csv"
    python "$A/compute_metrics.py" --input "$WORK_DIR/parsed/$tag.csv" --spurious "$WORK_DIR/spurious/$tag.csv" \
        --transfers "$WORK_DIR/selected_quic.csv" --variant "$variant" --profile "$profile" --run "$run" \
        --output "$WORK_DIR/metrics/$tag.csv" > /dev/null
    n=$((n + 1))
done < <(tail -n +2 "$WORK_DIR/selected_runs.tsv")
echo "Processed $n runs."

# ---- 3. merge exactly the selected runs' metrics (stale files in WORK_DIR cannot leak in) ----
python - "$WORK_DIR" <<'PY'
import sys
from pathlib import Path
import pandas as pd
work = Path(sys.argv[1])
runs = pd.read_csv(work / "selected_runs.tsv", sep="\t", dtype=str)
frames = []
for r in runs.itertuples():
    f = work / "metrics" / f"{r.variant}__{r.profile}__{r.run}.csv"
    if not f.is_file():
        raise SystemExit(f"ERROR: missing metrics file {f}")
    frames.append(pd.read_csv(f))
out = pd.concat(frames, ignore_index=True)
if "file_size" not in out.columns:
    out["file_size"] = "10MB"
out.to_csv(work / "all_runs_metrics.csv", index=False)
print(f"Wrote {work / 'all_runs_metrics.csv'} ({len(out)} runs)")
PY

# ---- 4. Plots 1 and 3 ----
python "$A/plot_results.py" goodput --transfers "$WORK_DIR/selected_quic.csv" --tcp "$TCP_CSV" --out "$OUT_DIR"
python "$A/plot_results.py" spurious --metrics "$WORK_DIR/all_runs_metrics.csv" --out "$OUT_DIR"

# ---- 5. Plots 2 and 4 (median-goodput stock run per profile, 10 MB runs only) ----
median_run() {   # $1=variant $2=profile -> prints the run number
    local out run
    out="$(python "$A/plot_mechanism.py" median-run --results "$WORK_DIR/selected_quic.csv" --variant "$1" --profile "$2")"
    run="$(printf '%s\n' "$out" | sed -n 's/^Median run: run=\([^ ]*\) .*/\1/p')"
    [[ -n "$run" ]] || { echo "ERROR: could not read the median run for $1/$2: $out" >&2; exit 7; }
    echo "$run"
}
parsed_for() {   # $1=profile -> path of the parsed CSV of the median stock run
    local run f
    run="$(median_run stock "$1")"
    f="$WORK_DIR/parsed/stock__$1__${run}.csv"
    [[ -f "$f" ]] || { echo "ERROR: expected parsed file not found: $f" >&2; exit 7; }
    echo "median stock $1 run = $run" >&2
    echo "$f"
}
P_BASE="$(parsed_for baseline)"
P_MOD="$(parsed_for moderate)"
P_SEV="$(parsed_for severe)"
python "$A/plot_mechanism.py" cwnd --panel "baseline=$P_BASE" --panel "moderate=$P_MOD" --out "$OUT_DIR"
python "$A/plot_mechanism.py" cumulative --series "baseline=$P_BASE" --series "severe=$P_SEV" --out "$OUT_DIR"

echo
echo "Done. Plot files in $OUT_DIR:"
ls -1 "$OUT_DIR"/plot1_* "$OUT_DIR"/plot2_* "$OUT_DIR"/plot3_* "$OUT_DIR"/plot4_*
