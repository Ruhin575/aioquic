import json
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt

runs = {
    "Run 1": Path(
        "experiments/results/dynamic_test/dynamic/moderate/run_1/server-qlog/1697c31d2f4d0eb0.qlog"
    ),
    "Run 2": Path(
        "experiments/results/dynamic_test/dynamic/moderate/run_2/server-qlog/fec37c5cd9fca745.qlog"
    ),
    "Run 3": Path(
        "experiments/results/dynamic_test/dynamic/moderate/run_3/server-qlog/66d5c7dd4fcbc15b.qlog"
    ),
}

out = Path("experiments/report/plots/final")
out.mkdir(parents=True, exist_ok=True)

all_increases = []
summary = []

for run_name, path in runs.items():
    data = json.loads(path.read_text())

    events = [
        event
        for trace in data.get("traces", [])
        for event in trace.get("events", [])
    ]

    if not events:
        raise ValueError(f"No events found in {path}")

    start_time = min(event["time"] for event in events)

    adapted = [
        event for event in events
        if event.get("name") == "recovery:k_adapted"
    ]

    decayed = [
        event for event in events
        if event.get("name") == "recovery:k_decayed"
    ]

    increases = []

    for event in adapted:
        values = event.get("data", {})
        old_k = values.get("old_k")
        new_k = values.get("new_k")

        if old_k is None or new_k is None:
            continue

        if float(new_k) > float(old_k):
            increases.append({
                "run": run_name,
                "time_s": (event["time"] - start_time) / 1000,
                "old_k": float(old_k),
                "new_k": float(new_k),
                "gap": values.get("gap"),
            })

    all_increases.extend(increases)

    summary.append({
        "run": run_name,
        "k_adapted_events": len(adapted),
        "actual_k_increases": len(increases),
        "k_decayed_events": len(decayed),
    })

timeline = pd.DataFrame(all_increases)
summary_df = pd.DataFrame(summary)

timeline.to_csv(out / "F6_adaptive_k_timeline.csv", index=False)
summary_df.to_csv(out / "F6_adaptive_k_summary.csv", index=False)

fig, axes = plt.subplots(3, 1, figsize=(10, 10), sharex=False)

for ax, run_name in zip(axes, runs.keys()):
    run_data = timeline[timeline["run"] == run_name].copy()
    run_data = run_data.sort_values("time_s")

    if run_data.empty:
        ax.set_title(f"{run_name}: no recorded K increases")
        continue

    # Initial K is 3. Each event updates K to its observed new_k.
    times = [0.0] + run_data["time_s"].tolist()
    values = [3.0] + run_data["new_k"].tolist()

    ax.step(times, values, where="post")
    ax.scatter(
        run_data["time_s"],
        run_data["new_k"],
        s=12,
        label="Observed K increase"
    )

    ax.set_title(
        f"{run_name}: {len(run_data)} actual K increases"
    )
    ax.set_ylabel("Adaptive K")
    ax.grid(alpha=0.25)

axes[-1].set_xlabel("Time since first qlog event (seconds)")

fig.suptitle(
    "Adaptive Packet Threshold K Over Time\n"
    "Preliminary Dynamic Experiment — Moderate Profile",
    fontsize=13
)

fig.text(
    0.5, 0.01,
    "Only recorded K increases are shown. No k_decayed events "
    "were present in the three available qlogs.",
    ha="center",
    fontsize=9
)

plt.tight_layout(rect=[0, 0.04, 1, 0.94])
fig.savefig(out / "F6_adaptive_k_over_time.png",
            dpi=200, bbox_inches="tight")
plt.close(fig)

with open(out / "F6_adaptive_k_over_time.alt.txt", "w") as f:
    f.write(
        "Three-panel step chart showing observed adaptive packet threshold "
        "K increases over time for three preliminary Dynamic experiments "
        "under the moderate network profile. Each run starts at K=3. "
        "The qlogs contain 461, 458 and 490 k_adapted events respectively, "
        "but only 65, 59 and 64 actual increases. No k_decayed events were "
        "recorded. The chart therefore shows observed increases only and "
        "does not represent a complete K trajectory or unlogged decay."
    )

print("F6 generated successfully.")
print("\nEvent summary:")
print(summary_df.to_string(index=False))
print("\nTotal actual increases:", len(timeline))
print("\nGenerated files:")
for name in [
    "F6_adaptive_k_over_time.png",
    "F6_adaptive_k_timeline.csv",
    "F6_adaptive_k_summary.csv",
    "F6_adaptive_k_over_time.alt.txt",
]:
    print(out / name)
