import joblib
import pandas as pd

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix
)


# ============================================================
# 1. LOAD FEATURE DATASET
# ============================================================

DATA_PATH = "data/processed/cwru_features.csv"

df = pd.read_csv(DATA_PATH)

print("Dataset shape:", df.shape)


# ============================================================
# 2. TRAIN / TEST FILE SPLIT
# ============================================================
# IMPORTANT:
# We split by FILE, not by individual windows.
# This prevents windows from the same vibration recording
# appearing in both training and testing data.

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


print("\nTraining shape:", train_df.shape)
print("Testing shape:", test_df.shape)


# ============================================================
# 3. SELECT FEATURES
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


X_train = train_df[feature_columns]
y_train = train_df["label"]

X_test = test_df[feature_columns]
y_test = test_df["label"]


print("\nNumber of features:", len(feature_columns))

print("\nFeatures:")
for feature in feature_columns:
    print("-", feature)


# ============================================================
# 4. TRAIN RANDOM FOREST
# ============================================================

model = RandomForestClassifier(
    n_estimators=200,
    random_state=42
)

model.fit(X_train, y_train)


# ============================================================
# 5. PREDICTIONS
# ============================================================

y_pred = model.predict(X_test)


# ============================================================
# 6. EVALUATION
# ============================================================

accuracy = accuracy_score(y_test, y_pred)

print("\n========================================")
print("IMPROVED RANDOM FOREST RESULTS")
print("========================================")

print("\nAccuracy:", accuracy)

print("\nClassification Report:")
print(
    classification_report(
        y_test,
        y_pred
    )
)


# ============================================================
# 7. CONFUSION MATRIX
# ============================================================

cm = confusion_matrix(
    y_test,
    y_pred,
    labels=[
        "normal",
        "inner_race",
        "ball",
        "outer_race"
    ]
)

print("\nConfusion Matrix:")
print(cm)


# ============================================================
# 8. FEATURE IMPORTANCE
# ============================================================

importance = pd.DataFrame({
    "feature": feature_columns,
    "importance": model.feature_importances_
})

importance = importance.sort_values(
    by="importance",
    ascending=False
)

print("\n========================================")
print("FEATURE IMPORTANCE")
print("========================================")

print(importance.to_string(index=False))

# Save trained model
joblib.dump(model, "models/random_forest.pkl")

print("Random Forest model saved successfully!")