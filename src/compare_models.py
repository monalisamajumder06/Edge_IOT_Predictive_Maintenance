import joblib
import pandas as pd
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from data_loader import load_and_split_data

def evaluate_model(model, scaler, X_test, y_test):
    X_test_scaled = scaler.transform(X_test)
    y_pred = model.predict(X_test_scaled)
    
    return {
        "Accuracy": accuracy_score(y_test, y_pred),
        "Precision": precision_score(y_test, y_pred, average='macro'),
        "Recall": recall_score(y_test, y_pred, average='macro'),
        "F1": f1_score(y_test, y_pred, average='macro')
    }

def compare_models():
    print("Loading test data...")
    _, X_test, _, y_test = load_and_split_data()

    models_info = {
        "Logistic Regression": {
            "model_path": "models/logreg_model.pkl",
            "scaler_path": "models/logreg_scaler.pkl"
        },
        "SVM": {
            "model_path": "models/svm_model.pkl",
            "scaler_path": "models/svm_scaler.pkl"
        },
        "Random Forest": {
            "model_path": "models/random_forest.pkl",
            "scaler_path": "models/rf_scaler.pkl"
        }
    }

    results = []

    for model_name, paths in models_info.items():
        print(f"Evaluating {model_name}...")
        try:
            model = joblib.load(paths["model_path"])
            scaler = joblib.load(paths["scaler_path"])
            
            metrics = evaluate_model(model, scaler, X_test, y_test)
            metrics["Model"] = model_name
            results.append(metrics)
        except Exception as e:
            print(f"Error loading {model_name}: {e}")

    # Reorder columns
    df_results = pd.DataFrame(results)[["Model", "Accuracy", "Precision", "Recall", "F1"]]
    
    print("\n========================================================")
    print("MODEL COMPARISON RESULTS")
    print("========================================================")
    print(df_results.to_string(index=False))
    print("========================================================\n")

    output_path = "data/processed/model_comparison.csv"
    df_results.to_csv(output_path, index=False)
    print(f"Comparison saved to {output_path}")

if __name__ == "__main__":
    compare_models()
