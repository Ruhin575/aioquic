from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

OUT = Path("experiments/report/plots/final")
OUT.mkdir(parents=True, exist_ok=True)

# Colour-blind-friendly palette; keep each variant's colour consistent.
COLORS = {
    "stock": "#0072B2",
    "k5": "#E69F00",
    "k10": "#56B4E9",
    "k20": "#009E73",
    "k100": "#D55E00",
    "dynamic": "#CC79A7",
    "dynamic_undo": "#332288",
    "undo": "#999999",
    "tcp": "#000000",
}

PROFILES = ["baseline", "mild", "moderate", "severe", "handover"]
VARIANTS = ["stock", "k5", "k10", "k20", "k100", "dynamic", "dynamic_undo"]

# 95% two-sided Student-t critical values for n=5 and n=8.
T_CRIT = {5: 2.776445, 8: 2.364624}

def summarize(df, group_columns, value_column):
    rows = []
    for keys, group in df.groupby(group_columns, sort=False):
        if not isinstance(keys, tuple):
            keys = (keys,)

        values = group[value_column].astype(float).to_numpy()
        n = len(values)
        mean = values.mean()
        sd = values.std(ddof=1) if n > 1 else 0.0
        critical = T_CRIT.get(n)

        if critical is None:
            raise ValueError(f"No t critical value configured for n={n}")

        ci = critical * sd / np.sqrt(n)

        row = dict(zip(group_columns, keys))
        row.update({
            "n": n,
            "mean": mean,
            "std_dev": sd,
            "ci95_low": mean - ci,
            "ci95_high": mean + ci,
            "ci95_half_width": ci,
        })
        rows.append(row)

    return pd.DataFrame(rows)


# ============================================================
# F1: Goodput comparison across 7 variants and 5 profiles
# ============================================================

path = Path("experiments/results/phase1_all_variants_final_5runs/transfers.csv")
df = pd.read_csv(path)

assert len(df) == 175, f"Expected 175 records, found {len(df)}"
assert set(df["variant"]) == set(VARIANTS)
assert set(df["profile"]) == set(PROFILES)
assert df["sha256_ok"].astype(str).str.lower().isin(["true", "1"]).all(), \
    "Some transfer checksums failed; inspect the CSV before plotting."

stats = summarize(df, ["profile", "variant"], "goodput_mbps")
stats.to_csv(OUT / "F1_goodput_data.csv", index=False)

fig, axes = plt.subplots(1, 5, figsize=(21, 5.8), sharey=True)

for ax, profile in zip(axes, PROFILES):
    subset = stats[stats["profile"] == profile].set_index("variant")
    x = np.arange(len(VARIANTS))

    means = [subset.loc[v, "mean"] for v in VARIANTS]
    errors = [subset.loc[v, "ci95_half_width"] for v in VARIANTS]

    bars = ax.bar(
        x, means,
        color=[COLORS[v] for v in VARIANTS],
        edgecolor="black",
        linewidth=0.5,
        width=0.72,
    )
    ax.errorbar(
        x, means, yerr=errors,
        fmt="none", ecolor="black",
        capsize=3, linewidth=1,
    )

    ax.set_title(profile.capitalize())
    ax.set_xticks(x)
    ax.set_xticklabels(
        ["Stock", "K5", "K10", "K20", "K100", "Dynamic", "Dynamic\nUndo"],
        rotation=45, ha="right",
    )
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)

axes[0].set_ylabel("Goodput (Mbit/s)")
fig.suptitle(
    "F1. Goodput across seven QUIC recovery variants",
    fontsize=15, y=1.02,
)
fig.text(
    0.5, -0.04,
    "Bars show mean goodput; error bars show 95% t-confidence intervals (n=5).",
    ha="center",
)
fig.tight_layout()
fig.savefig(OUT / "F1_goodput_comparison.png", dpi=220, bbox_inches="tight")
plt.close(fig)

(OUT / "F1_goodput_comparison.alt.txt").write_text(
    "Five-panel comparison of Stock, K5, K10, K20, K100, Dynamic and "
    "Dynamic Undo goodput across baseline, mild, moderate, severe and "
    "handover profiles. Each bar is the mean of five 10 MB runs; error "
    "bars show two-sided 95% Student-t confidence intervals."
)


# ============================================================
# F2: Loss-rule attribution, Stock vs K20, moderate and severe
# ============================================================

path = Path(
    "experiments/results/attribution_main/analysis_application/"
    "attribution_by_profile.csv"
)
df = pd.read_csv(path)

selected = df[
    df["variant"].isin(["stock", "k20"])
    & df["profile"].isin(["moderate", "severe"])
].copy()

categories = ["packet", "time", "both", "pto", "unavailable"]

rows = []
for _, row in selected.iterrows():
    total = int(row["total_lost"])
    for category in categories:
        count = int(row[category])
        percent = (100 * count / total) if total else 0.0
        rows.append({
            "variant": row["variant"],
            "profile": row["profile"],
            "rule": category,
            "count": count,
            "total_lost": total,
            "percentage": percent,
        })

f2 = pd.DataFrame(rows)
f2.to_csv(OUT / "F2_loss_attribution_data.csv", index=False)

rule_colors = {
    "packet": "#0072B2",
    "time": "#E69F00",
    "both": "#009E73",
    "pto": "#CC79A7",
    "unavailable": "#999999",
}

fig, axes = plt.subplots(1, 2, figsize=(11, 6), sharey=True)

for ax, profile in zip(axes, ["moderate", "severe"]):
    subset = selected[selected["profile"] == profile].set_index("variant")
    x = np.arange(2)
    bottoms = np.zeros(2)

    for rule in categories:
        values = []
        for variant in ["stock", "k20"]:
            total = int(subset.loc[variant, "total_lost"])
            count = int(subset.loc[variant, rule])
            values.append(100 * count / total if total else 0.0)

        ax.bar(
            x, values, bottom=bottoms,
            label=rule.capitalize(),
            color=rule_colors[rule],
            edgecolor="white",
            linewidth=0.5,
        )
        bottoms += np.array(values)

    ax.set_title(profile.capitalize())
    ax.set_xticks(x)
    ax.set_xticklabels(["Stock", "K20"])
    ax.set_ylim(0, 100)
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)

axes[0].set_ylabel("Share of loss declarations (%)")
fig.suptitle("F2. Loss-rule attribution: Stock vs K20", fontsize=15)
axes[1].legend(title="Attribution", bbox_to_anchor=(1.02, 1), loc="upper left")
fig.text(
    0.5, 0.02,
    "Percentages are calculated within each variant/profile; "
    "the 'both' category means both packet and time criteria applied.",
    ha="center", fontsize=9,
)
fig.tight_layout(rect=[0, 0.07, 0.85, 0.93])
fig.savefig(OUT / "F2_loss_rule_attribution.png", dpi=220, bbox_inches="tight")
plt.close(fig)

(OUT / "F2_loss_rule_attribution.alt.txt").write_text(
    "Two 100% stacked bar charts compare Stock and K20 loss-rule attribution "
    "under moderate and severe profiles. Segments show packet-threshold, "
    "time-threshold, both, PTO and unavailable attribution as percentages "
    "of each variant's total loss declarations. Counts and percentages are "
    "provided in F2_loss_attribution_data.csv."
)


# ============================================================
# F4: QUIC vs TCP, using 10 MB transfers only
# ============================================================

quic_path = Path(
    "experiments/results/phase1_all_variants_final_5runs/transfers.csv"
)
tcp_path = Path("experiments/results/tcp.csv")

quic = pd.read_csv(quic_path)
tcp = pd.read_csv(tcp_path)

quic = quic[quic["variant"].isin(["stock", "k20", "dynamic_undo"])].copy()

# QUIC file_size is stored as bytes; TCP file_size is stored as text.
quic["file_size_bytes"] = pd.to_numeric(quic["file_size"])
quic = quic[quic["file_size_bytes"] == 10485760]

tcp = tcp[tcp["file_size"].astype(str).str.upper() == "10MB"].copy()

quic["goodput_mbps"] = pd.to_numeric(quic["goodput_mbps"])
tcp["goodput_mbps"] = pd.to_numeric(tcp["goodput_mbps"])

combined = pd.concat([
    quic[["variant", "profile", "run", "goodput_mbps"]],
    tcp[["variant", "profile", "run", "goodput_mbps"]],
], ignore_index=True)

assert set(combined["variant"]) == {"stock", "k20", "dynamic_undo", "tcp"}

f4_stats = summarize(combined, ["profile", "variant"], "goodput_mbps")
f4_stats.to_csv(OUT / "F4_quic_tcp_data.csv", index=False)

fig, ax = plt.subplots(figsize=(12, 6.5))

variants_f4 = ["stock", "k20", "dynamic_undo", "tcp"]
x = np.arange(len(PROFILES))
width = 0.19
offsets = np.linspace(-1.5 * width, 1.5 * width, len(variants_f4))

for variant, offset in zip(variants_f4, offsets):
    subset = f4_stats[f4_stats["variant"] == variant].set_index("profile")
    means = [subset.loc[p, "mean"] for p in PROFILES]
    errors = [subset.loc[p, "ci95_half_width"] for p in PROFILES]

    ax.bar(
        x + offset, means, width,
        yerr=errors, capsize=3,
        label=variant.replace("_", " ").upper(),
        color=COLORS[variant],
        edgecolor="black",
        linewidth=0.5,
    )

ax.set_xticks(x)
ax.set_xticklabels([p.capitalize() for p in PROFILES])
ax.set_ylabel("Goodput (Mbit/s)")
ax.set_title("F4. QUIC recovery variants compared with Linux TCP")
ax.grid(axis="y", alpha=0.25)
ax.set_axisbelow(True)
ax.legend(title="Transport / variant")
fig.text(
    0.5, 0.01,
    "Only 10 MB transfers are included. Bars show means; error bars show "
    "95% Student-t confidence intervals. Five runs per group.",
    ha="center", fontsize=9,
)
fig.tight_layout(rect=[0, 0.05, 1, 1])
fig.savefig(OUT / "F4_quic_vs_tcp.png", dpi=220, bbox_inches="tight")
plt.close(fig)

(OUT / "F4_quic_vs_tcp.alt.txt").write_text(
    "Grouped bar chart comparing Stock QUIC, K20 QUIC, Dynamic Undo QUIC "
    "and Linux TCP across baseline, mild, moderate, severe and handover "
    "profiles. Only 10 MB transfers are included, with five runs per "
    "variant/profile. Error bars show 95% Student-t confidence intervals."
)

print("\nGenerated F1, F2 and F4:")
for path in sorted(OUT.iterdir()):
    if path.is_file():
        print(f"{path} ({path.stat().st_size:,} bytes)")
