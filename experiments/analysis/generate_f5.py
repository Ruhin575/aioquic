#!/usr/bin/env python3
"""Generate F5 from run-1 server qlogs in experiments/results/shamili_moderate_final."""
import json, csv, re
from pathlib import Path
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "experiments" / "results" / "shamili_moderate_final"
OUT = ROOT / "experiments" / "report" / "plots" / "final"
OUT.mkdir(parents=True, exist_ok=True)

variants = [("stock", "Stock QUIC"), ("k20", "K20"), ("dynamic_undo", "Dynamic Undo")]
data, summary = {}, []
for variant, title in variants:
    qlogs = list((BASE / variant / "moderate" / "run_1" / "server-qlog").glob("*.qlog"))
    if len(qlogs) != 1:
        raise RuntimeError(f"Expected one server qlog for {variant} run 1; found {len(qlogs)}")
    qlog = json.loads(qlogs[0].read_text())
    events = qlog["traces"][0]["events"]
    metrics = [e for e in events if e.get("name") == "recovery:metrics_updated" and "cwnd" in e.get("data", {})]
    restores = [e for e in events if e.get("name") == "recovery:cwnd_restored"]
    if not metrics:
        raise RuntimeError(f"No CWND samples found in {qlogs[0]}")
    t0 = metrics[0]["time"]
    times = [(e["time"] - t0) / 1000 for e in metrics]
    cwnd = [e["data"]["cwnd"] for e in metrics]
    restore_times = [(e["time"] - t0) / 1000 for e in restores]
    data[variant] = (times, cwnd, restore_times)
    summary.append([variant, 1, qlogs[0].name, len(metrics), len(restores), round(max(times), 3)])

fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
for ax, (variant, title) in zip(axes, variants):
    times, cwnd, restores = data[variant]
    ax.plot(times, [v / 1024 for v in cwnd], linewidth=0.8, label="Congestion window")
    for i, t in enumerate(restores):
        ax.axvline(t, linestyle="--", linewidth=0.7, alpha=0.55,
                   label="CWND restored" if i == 0 else None)
    ax.set_title(title); ax.set_ylabel("CWND (KiB)")
    ax.grid(True, alpha=0.25)
    if restores: ax.legend(loc="upper right")
axes[-1].set_xlabel("Time from first CWND sample (seconds)")
fig.suptitle("Congestion Window over Time — Moderate Profile (Run 1)", y=0.995)
fig.tight_layout()
fig.savefig(OUT / "F5_cwnd_over_time.png", dpi=180, bbox_inches="tight")
plt.close(fig)

with (OUT / "F5_cwnd_timeline.csv").open("w", newline="") as f:
    w = csv.writer(f); w.writerow(["variant", "run", "time_s", "cwnd_bytes", "event"])
    for variant, (times, cwnd, restores) in data.items():
        for t, c in zip(times, cwnd): w.writerow([variant, 1, f"{t:.6f}", c, "metrics_updated"])
        for t in restores: w.writerow([variant, 1, f"{t:.6f}", "", "cwnd_restored"])
with (OUT / "F5_cwnd_summary.csv").open("w", newline="") as f:
    w = csv.writer(f); w.writerow(["variant", "run", "qlog_file", "cwnd_samples", "cwnd_restored_events", "duration_s"]); w.writerows(summary)
(OUT / "F5_cwnd_over_time.alt.txt").write_text(
    "Three-panel line chart of server-side congestion-window (CWND) samples over time "
    "for Stock QUIC, K20, and Dynamic Undo under the moderate network profile. "
    "Each panel uses run 1 from the final moderate-profile qlogs. Dashed vertical lines "
    "mark recovery:cwnd_restored events. CWND values are shown in KiB. This is a "
    "representative single-run trace, not an average across five repetitions.\\n"
)
print("Generated F5 outputs in", OUT)
print("Summary:", summary)
