import pandas as pd
import matplotlib.pyplot as plt

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay


# ============================================================
# 1. LOAD DATA
# ============================================================

DATA_PATH = "data/processed/cwru_features.csv"

df = pd.read_csv(DATA_PATH)


# ============================================================
# 2. DEFINE FEATURES
# ============================================================

feature_columns = [
    "rms",
    "mean",
    "std",
    "peak",
    "peak_to_peak",
    "skewness",
    "kurtosis",
    "crest_factor",
    "dominant_frequency_hz",
    "spectral_centroid_hz",
    "spectral_bandwidth_hz",
    "spectral_energy"
]


# ============================================================
# 3. SAME FILE-LEVEL SPLIT
# ============================================================

train_files = [
    97, 98, 100,
    105, 106, 108,
    118, 119, 121,
    130, 131, 133
]

test_files = [
    99,
    107,
    120,
    132
]


train_df = df[df["file_id"].isin(train_files)].copy()
test_df = df[df["file_id"].isin(test_files)].copy()


X_train = train_df[feature_columns]
y_train = train_df["label"]

X_test = test_df[feature_columns]
y_test = test_df["label"]


# ============================================================
# 4. TRAIN FINAL REVIEW-1 RANDOM FOREST
# ============================================================

model = RandomForestClassifier(
    n_estimators=200,
    random_state=42,
    class_weight="balanced"
)

model.fit(X_train, y_train)

y_pred = model.predict(X_test)


# ============================================================
# 5. CONFUSION MATRIX
# ============================================================

class_names = [
    "normal",
    "inner_race",
    "ball",
    "outer_race"
]

cm = confusion_matrix(
    y_test,
    y_pred,
    labels=class_names
)

display = ConfusionMatrixDisplay(
    confusion_matrix=cm,
    display_labels=class_names
)

display.plot()

plt.title("Random Forest Confusion Matrix")

plt.tight_layout()

plt.savefig(
    "data/processed/confusion_matrix.png",
    dpi=300
)

plt.show()


# ============================================================
# 6. FEATURE IMPORTANCE
# ============================================================

importance = pd.DataFrame({
    "feature": feature_columns,
    "importance": model.feature_importances_
})

importance = importance.sort_values(
    "importance",
    ascending=True
)


plt.figure(figsize=(10, 7))

plt.barh(
    importance["feature"],
    importance["importance"]
)

plt.xlabel("Importance")
plt.ylabel("Feature")

plt.title(
    "Random Forest Feature Importance"
)

plt.tight_layout()

plt.savefig(
    "data/processed/feature_importance.png",
    dpi=300
)

plt.show()


# ============================================================
# 7. CONFIRM OUTPUTS
# ============================================================

print("\nEvaluation plots created successfully!")

print(
    "Saved:",
    "data/processed/confusion_matrix.png"
)

print(
    "Saved:",
    "data/processed/feature_importance.png"
)