import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

data = pd.DataFrame({
    "profile": ["Mild", "Moderate", "Severe"],
    "expected_genuine_losses": [44, 131, 218],
    "observed_abandonments": [47, 158, 246],
})

data["observed_to_expected_pct"] = (
    data["observed_abandonments"] /
    data["expected_genuine_losses"] * 100
).round(1)

out = "experiments/report/plots/final"

data.to_csv(f"{out}/F3_undo_abandonment_data.csv", index=False)

x = np.arange(len(data))
width = 0.34

fig, ax = plt.subplots(figsize=(9, 5.5))

bars1 = ax.bar(
    x - width / 2,
    data["expected_genuine_losses"],
    width,
    label="Expected genuine losses"
)

bars2 = ax.bar(
    x + width / 2,
    data["observed_abandonments"],
    width,
    label="Observed undo abandonments"
)

ax.set_title("Undo Abandonments vs Expected Genuine Losses")
ax.set_xlabel("Network profile")
ax.set_ylabel("Count across five runs")
ax.set_xticks(x)
ax.set_xticklabels(data["profile"])
ax.legend()
ax.grid(axis="y", alpha=0.25)

for bars in [bars1, bars2]:
    for bar in bars:
        height = bar.get_height()
        ax.annotate(
            f"{height:.0f}",
            (bar.get_x() + bar.get_width() / 2, height),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            fontsize=9
        )

for i, row in data.iterrows():
    ax.text(
        x[i],
        max(row["expected_genuine_losses"],
            row["observed_abandonments"]) + 17,
        f'{row["observed_to_expected_pct"]:.1f}%',
        ha="center",
        fontsize=9
    )

ax.text(
    0.5, -0.19,
    "Percentage labels show observed abandonments as a percentage of expected losses.",
    transform=ax.transAxes,
    ha="center",
    fontsize=8
)

plt.tight_layout()
fig.savefig(f"{out}/F3_undo_abandonment.png", dpi=200,
            bbox_inches="tight")
plt.close(fig)

with open(f"{out}/F3_undo_abandonment.alt.txt", "w") as f:
    f.write(
        "Grouped bar chart comparing approximate expected genuine losses "
        "with observed undo-abandonment events across five runs. "
        "Mild: 44 expected and 47 observed (106.8%). "
        "Moderate: 131 expected and 158 observed (120.6%). "
        "Severe: 218 expected and 246 observed (112.8%). "
        "Expected counts are rough estimates based on file size and "
        "configured random-loss rates. An abandoned episode can contain "
        "more than one genuine loss, so this is an approximate consistency "
        "check, not a one-to-one validation."
    )

print("F3 generated successfully.")
print(data.to_string(index=False))
