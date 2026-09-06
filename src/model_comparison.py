import pandas as pd

from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold, cross_validate
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, LabelEncoder


# ============================================================
# 1. LOAD DATA
# ============================================================

DATA_PATH = "data/processed/cwru_features.csv"

df = pd.read_csv(DATA_PATH)

print("Dataset shape:", df.shape)


# ============================================================
# 2. FEATURES
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

X = df[feature_columns]


# ============================================================
# 3. TARGET
# ============================================================

encoder = LabelEncoder()

y = encoder.fit_transform(df["label"])

print("\nClasses:")
print(encoder.classes_)


# ============================================================
# 4. GROUPS
# ============================================================
# Windows belonging to the same original CWRU file
# must stay together.

groups = df["file_id"]


# ============================================================
# 5. DEFINE MODELS
# ============================================================

models = {

    "Logistic Regression": Pipeline([
        ("scaler", StandardScaler()),
        (
            "classifier",
            LogisticRegression(
                max_iter=2000,
                random_state=42
            )
        )
    ]),

    "SVM": Pipeline([
        ("scaler", StandardScaler()),
        (
            "classifier",
            SVC(
                kernel="rbf",
                random_state=42
            )
        )
    ]),

    "Random Forest": RandomForestClassifier(
        n_estimators=200,
        random_state=42,
        class_weight="balanced"
    )
}


# ============================================================
# 6. FILE-LEVEL CROSS-VALIDATION
# ============================================================

cv = GroupKFold(n_splits=4)

scoring = {
    "accuracy": "accuracy",
    "precision": "precision_macro",
    "recall": "recall_macro",
    "f1": "f1_macro"
}


# ============================================================
# 7. TRAIN AND EVALUATE EACH MODEL
# ============================================================

results = []

print("\n========================================")
print("MODEL COMPARISON")
print("========================================")


for model_name, model in models.items():

    scores = cross_validate(
        model,
        X,
        y,
        groups=groups,
        cv=cv,
        scoring=scoring
    )

    accuracy = scores["test_accuracy"].mean()
    precision = scores["test_precision"].mean()
    recall = scores["test_recall"].mean()
    f1 = scores["test_f1"].mean()

    results.append({
        "model": model_name,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1
    })

    print(f"\n{model_name}")
    print("-" * 40)

    print(f"Accuracy : {accuracy:.4f}")
    print(f"Precision: {precision:.4f}")
    print(f"Recall   : {recall:.4f}")
    print(f"F1 Score : {f1:.4f}")


# ============================================================
# 8. SUMMARY
# ============================================================

results_df = pd.DataFrame(results)

print("\n========================================")
print("MODEL COMPARISON SUMMARY")
print("========================================")

print(
    results_df.to_string(index=False)
)