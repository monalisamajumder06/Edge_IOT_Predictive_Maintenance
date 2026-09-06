import pandas as pd
import matplotlib.pyplot as plt


FEATURE_PATH = "data/processed/cwru_features.csv"

# Load feature dataset
df = pd.read_csv(FEATURE_PATH)

# Plot RMS vs dominant frequency
plt.figure(figsize=(10, 6))

for label in df["label"].unique():
    subset = df[df["label"] == label]

    plt.scatter(
        subset["dominant_frequency_hz"],
        subset["rms"],
        label=label,
        alpha=0.7
    )

plt.xlabel("Dominant Frequency (Hz)")
plt.ylabel("RMS")
plt.title("CWRU Bearing Conditions: Feature Space")
plt.legend()
plt.grid(True)

plt.tight_layout()

# Save the plot
output_path = "data/processed/feature_space.png"
plt.savefig(output_path, dpi=300)

plt.show()

print("Feature-space plot saved to:", output_path)