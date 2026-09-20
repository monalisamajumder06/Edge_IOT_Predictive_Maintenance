import joblib
import pandas as pd
import matplotlib.pyplot as plt

from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay, classification_report
from data_loader import load_and_split_data, get_feature_columns

def plot_confusion_matrices():
    print("Loading data...")
    _, X_test, _, y_test = load_and_split_data()
    feature_columns = get_feature_columns()

    class_names = [
        "normal",
        "inner_race",
        "ball",
        "outer_race"
    ]

    models_info = {
        "Logistic Regression": {
            "model_path": "models/logreg_model.pkl",
            "scaler_path": "models/logreg_scaler.pkl",
            "cm_output": "data/processed/cm_logreg.png"
        },
        "SVM": {
            "model_path": "models/svm_model.pkl",
            "scaler_path": "models/svm_scaler.pkl",
            "cm_output": "data/processed/cm_svm.png"
        },
        "Random Forest": {
            "model_path": "models/random_forest.pkl",
            "scaler_path": "models/rf_scaler.pkl",
            "cm_output": "data/processed/cm_rf.png"
        }
    }

    # ============================================================
    # CONFUSION MATRICES & CLASSIFICATION REPORTS
    # ============================================================

    for model_name, paths in models_info.items():
        try:
            model = joblib.load(paths["model_path"])
            scaler = joblib.load(paths["scaler_path"])
            
            X_test_scaled = scaler.transform(X_test)
            y_pred = model.predict(X_test_scaled)

            print(f"\n========================================")
            print(f"{model_name.upper()} CLASSIFICATION REPORT")
            print(f"========================================")
            print(classification_report(y_test, y_pred, labels=class_names))

            cm = confusion_matrix(y_test, y_pred, labels=class_names)
            display = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=class_names)
            
            plt.figure(figsize=(8, 6))
            display.plot(cmap="Blues", values_format="d")
            plt.title(f"{model_name} Confusion Matrix")
            plt.tight_layout()
            
            plt.savefig(paths["cm_output"], dpi=300)
            plt.close('all') # close to avoid overlapping plots
            print(f"Saved {model_name} Confusion Matrix to: {paths['cm_output']}")

            # Special case: Feature Importance for Random Forest
            if model_name == "Random Forest":
                plot_rf_feature_importance(model, feature_columns)

        except Exception as e:
            print(f"Could not process {model_name}: {e}")

def plot_rf_feature_importance(model, feature_columns):
    importance = pd.DataFrame({
        "feature": feature_columns,
        "importance": model.feature_importances_
    }).sort_values("importance", ascending=True)

    plt.figure(figsize=(10, 7))
    plt.barh(importance["feature"], importance["importance"])
    plt.xlabel("Importance")
    plt.ylabel("Feature")
    plt.title("Random Forest Feature Importance")
    plt.tight_layout()
    
    output_path = "data/processed/feature_importance.png"
    plt.savefig(output_path, dpi=300)
    plt.close()
    print(f"Saved Random Forest Feature Importance to: {output_path}")

if __name__ == "__main__":
    plot_confusion_matrices()
    print("\nEvaluation plotting complete!")