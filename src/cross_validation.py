import pandas as pd
import numpy as np

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupKFold, cross_validate
from sklearn.preprocessing import LabelEncoder
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer


# --------------------------------------------------
# 1. Load feature dataset
# --------------------------------------------------

DATA_PATH = "data/processed/cwru_features.csv"

df = pd.read_csv(DATA_PATH)

print("Dataset shape:", df.shape)


# --------------------------------------------------
# 2. Define features, labels and groups
# --------------------------------------------------

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
    "spectral_energy",
]

X = df[feature_columns]
y = df["label"]

# file_id identifies the original CWRU recording.
# We use it as the grouping variable so that windows
# from the same recording never appear in both train
# and validation sets.

groups = df["file_id"]


# --------------------------------------------------
# 3. Encode class labels
# --------------------------------------------------

label_encoder = LabelEncoder()
y_encoded = label_encoder.fit_transform(y)

print("\nClasses:")
print(label_encoder.classes_)


# --------------------------------------------------
# 4. Create Random Forest pipeline
# --------------------------------------------------

model = Pipeline([
    ("imputer", SimpleImputer(strategy="median")),
    (
        "classifier",
        RandomForestClassifier(
            n_estimators=200,
            random_state=42,
            class_weight="balanced"
        )
    )
])


# --------------------------------------------------
# 5. File-level cross-validation
# --------------------------------------------------

cv = GroupKFold(n_splits=4)

scoring = {
    "accuracy": "accuracy",
    "precision": "precision_macro",
    "recall": "recall_macro",
    "f1": "f1_macro"
}

results = cross_validate(
    model,
    X,
    y_encoded,
    groups=groups,
    cv=cv,
    scoring=scoring
)


# --------------------------------------------------
# 6. Display results for every fold
# --------------------------------------------------

print("\n========================================")
print("FILE-LEVEL CROSS-VALIDATION RESULTS")
print("========================================")

for i in range(4):
    print(f"\nFold {i + 1}")
    print(f"Accuracy : {results['test_accuracy'][i]:.4f}")
    print(f"Precision: {results['test_precision'][i]:.4f}")
    print(f"Recall   : {results['test_recall'][i]:.4f}")
    print(f"F1 Score : {results['test_f1'][i]:.4f}")


# --------------------------------------------------
# 7. Calculate average performance
# --------------------------------------------------

print("\n========================================")
print("AVERAGE CROSS-VALIDATION PERFORMANCE")
print("========================================")

print(
    f"Accuracy : "
    f"{results['test_accuracy'].mean():.4f} "
    f"+/- {results['test_accuracy'].std():.4f}"
)

print(
    f"Precision: "
    f"{results['test_precision'].mean():.4f} "
    f"+/- {results['test_precision'].std():.4f}"
)

print(
    f"Recall   : "
    f"{results['test_recall'].mean():.4f} "
    f"+/- {results['test_recall'].std():.4f}"
)

print(
    f"F1 Score : "
    f"{results['test_f1'].mean():.4f} "
    f"+/- {results['test_f1'].std():.4f}"
)