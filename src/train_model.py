import joblib
import pandas as pd

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    classification_report,
    confusion_matrix
)
from sklearn.preprocessing import StandardScaler
from data_loader import load_and_split_data, get_feature_columns

def train_and_evaluate_rf():
    print("Loading data...")
    X_train, X_test, y_train, y_test = load_and_split_data()
    feature_columns = get_feature_columns()

    print("Scaling features...")
    # Using the same scaling logic for fairness in model comparison
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # ============================================================
    # TRAIN RANDOM FOREST
    # ============================================================
    print("Training Random Forest...")
    model = RandomForestClassifier(
        n_estimators=200,
        random_state=42
    )
    model.fit(X_train_scaled, y_train)

    # ============================================================
    # PREDICTIONS & EVALUATION
    # ============================================================
    y_pred = model.predict(X_test_scaled)

    accuracy = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred, average='macro')
    recall = recall_score(y_test, y_pred, average='macro')
    f1 = f1_score(y_test, y_pred, average='macro')

    print("\n========================================")
    print("RANDOM FOREST RESULTS")
    print("========================================")
    print(f"Accuracy:  {accuracy:.4f}")
    print(f"Precision: {precision:.4f}")
    print(f"Recall:    {recall:.4f}")
    print(f"F1-score:  {f1:.4f}")

    print("\nClassification Report:")
    print(classification_report(y_test, y_pred))

    # ============================================================
    # CONFUSION MATRIX
    # ============================================================
    cm = confusion_matrix(
        y_test,
        y_pred,
        labels=["normal", "inner_race", "ball", "outer_race"]
    )
    print("\nConfusion Matrix:")
    print(cm)

    # ============================================================
    # FEATURE IMPORTANCE
    # ============================================================
    importance = pd.DataFrame({
        "feature": feature_columns,
        "importance": model.feature_importances_
    }).sort_values(by="importance", ascending=False)

    print("\n========================================")
    print("FEATURE IMPORTANCE")
    print("========================================")
    print(importance.to_string(index=False))

    # Save trained model and scaler
    model_path = "models/random_forest.pkl"
    scaler_path = "models/rf_scaler.pkl"
    joblib.dump(model, model_path)
    joblib.dump(scaler, scaler_path)

    print(f"\nModel saved to {model_path}")
    print(f"Scaler saved to {scaler_path}")

if __name__ == "__main__":
    train_and_evaluate_rf()