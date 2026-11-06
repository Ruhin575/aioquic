
#!/usr/bin/env python3

"""Plot QUIC spurious-loss packet-number gap distributions."""

from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parent

INPUT = ROOT / "gap_distribution_validated.csv"
OUTPUT = ROOT / "plots"

DATASETS = ["threshold_20", "threshold_100"]
PROFILES = ["moderate", "severe"]
CANDIDATE_K = [3, 5, 10, 20, 50, 100]


def load_data():
    df = pd.read_csv(INPUT)

    # Keep only spurious losses with valid, non-negative gaps.
    df = df[
        (df["spurious"].astype(str).str.lower() == "true")
        & (df["gap"] >= 0)
    ].copy()

    return df


def plot_histograms(df):
    for profile in PROFILES:

        plt.figure(figsize=(10, 6))

        profile_data = df[df["profile"] == profile]

        max_gap = int(profile_data["gap"].max())
        bins = range(0, max_gap + 6, 5)

        for dataset in DATASETS:
            values = profile_data.loc[
                profile_data["dataset"] == dataset, "gap"
            ]

            plt.hist(
                values,
                bins=bins,
                density=True,
                alpha=0.5,
                label=dataset,
            )

        plt.xlabel("Packet-number gap")
        plt.ylabel("Probability density")
        plt.title(f"Spurious-loss Gap Distribution: {profile.title()}")
        plt.legend()
        plt.grid(axis="y", alpha=0.3)
        plt.tight_layout()

        path = OUTPUT / f"gap_histogram_{profile}.png"
        plt.savefig(path, dpi=300)
        plt.close()

        print("Saved:", path)


def plot_cumulative_curves(df):
    for profile in PROFILES:

        plt.figure(figsize=(10, 6))

        profile_data = df[df["profile"] == profile]

        for dataset in DATASETS:

            values = sorted(
                profile_data.loc[
                    profile_data["dataset"] == dataset, "gap"
                ].tolist()
            )

            if not values:
                continue

            # At each x, calculate percentage with gap strictly below x.
            x_values = sorted(set(values))
            y_values = [
                100 * sum(gap < x for gap in values) / len(values)
                for x in x_values
            ]

            plt.step(
                x_values,
                y_values,
                where="post",
                label=dataset,
            )

            # Mark the requested candidate thresholds.
            for k in CANDIDATE_K:
                percentage = (
                    100 * sum(gap < k for gap in values) / len(values)
                )
                plt.scatter(k, percentage, s=25)

        plt.xlabel("Candidate packet threshold K")
        plt.ylabel("Spurious losses with gap < K (%)")
        plt.title(f"Cumulative Gap Distribution: {profile.title()}")
        plt.xticks(CANDIDATE_K)
        plt.ylim(0, 105)
        plt.legend()
        plt.grid(alpha=0.3)
        plt.tight_layout()

        path = OUTPUT / f"gap_cumulative_{profile}.png"
        plt.savefig(path, dpi=300)
        plt.close()

        print("Saved:", path)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)

    df = load_data()

    print("Valid spurious-loss records:", len(df))

    plot_histograms(df)
    plot_cumulative_curves(df)

    print("\nPlot generation complete.")


if __name__ == "__main__":
    main()
