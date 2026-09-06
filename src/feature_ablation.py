import pandas as pd

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupKFold, cross_validate
from sklearn.preprocessing import LabelEncoder


# ============================================================
# 1. LOAD DATA
# ============================================================

DATA_PATH = "data/processed/cwru_features.csv"

df = pd.read_csv(DATA_PATH)

print("Dataset shape:", df.shape)


# ============================================================
# 2. DEFINE FEATURE GROUPS
# ============================================================

time_features = [
    "rms",
    "mean",
    "std",
    "peak",
    "peak_to_peak",
    "skewness",
    "kurtosis",
    "crest_factor"
]

frequency_features = [
    "dominant_frequency_hz",
    "spectral_centroid_hz",
    "spectral_bandwidth_hz",
    "spectral_energy"
]

all_features = time_features + frequency_features


# ============================================================
# 3. PREPARE TARGET AND GROUPS
# ============================================================

label_encoder = LabelEncoder()

y = label_encoder.fit_transform(df["label"])

# Original CWRU file ID.
# This ensures windows from the same recording stay together.
groups = df["file_id"]


# ============================================================
# 4. DEFINE EXPERIMENTS
# ============================================================

experiments = {
    "RMS only": [
        "rms"
    ],

    "Time-domain features": time_features,

    "Frequency-domain features": frequency_features,

    "All features": all_features
}


# ============================================================
# 5. FILE-LEVEL CROSS-VALIDATION
# ============================================================

cv = GroupKFold(n_splits=4)


print("\n========================================")
print("FEATURE ABLATION EXPERIMENT")
print("========================================")


results = []


for experiment_name, feature_list in experiments.items():

    X = df[feature_list]

    model = RandomForestClassifier(
        n_estimators=200,
        random_state=42,
        class_weight="balanced"
    )

    scores = cross_validate(
        model,
        X,
        y,
        groups=groups,
        cv=cv,
        scoring=[
            "accuracy",
            "precision_macro",
            "recall_macro",
            "f1_macro"
        ]
    )

    accuracy = scores["test_accuracy"].mean()
    precision = scores["test_precision_macro"].mean()
    recall = scores["test_recall_macro"].mean()
    f1 = scores["test_f1_macro"].mean()

    results.append({
        "experiment": experiment_name,
        "number_of_features": len(feature_list),
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1
    })

    print(f"\n{experiment_name}")
    print("-" * 40)

    print("Features:", len(feature_list))
    print(f"Accuracy : {accuracy:.4f}")
    print(f"Precision: {precision:.4f}")
    print(f"Recall   : {recall:.4f}")
    print(f"F1 Score : {f1:.4f}")


# ============================================================
# 6. SUMMARY TABLE
# ============================================================

results_df = pd.DataFrame(results)

print("\n========================================")
print("ABLATION SUMMARY")
print("========================================")

print(
    results_df.to_string(index=False)
)