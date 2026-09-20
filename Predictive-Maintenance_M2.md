# Member 2: Review 1 Progress Report

## Summary Statement
Using the processed CWRU features produced by Member 1, Member 2 established leakage-safe fault-classification baselines using Logistic Regression, SVM and Random Forest, compared their performance using Accuracy, Precision, Recall and F1-score, generated confusion matrices, and established a basic RUL baseline if the required degradation dataset was ready.

## Current Completion Status
*   **CWRU Fault Classification**: Completed
*   **Leakage-safe Split (`src/data_loader.py`)**: Completed
*   **Logistic Regression Baseline (`src/train_logreg.py`)**: Completed
*   **SVM Baseline (`src/train_svm.py`)**: Completed
*   **Random Forest Baseline (`src/train_model.py`)**: Completed
*   **Classification Metrics (Accuracy/Precision/Recall/F1)**: Implemented
*   **Model Comparison (`src/compare_models.py`)**: Implemented
*   **Confusion Matrices (`src/plot_results.py`)**: Implemented

## Pending / Missing Artifacts
*   **RUL Baseline**: PENDING because no suitable degradation dataset is currently available in the repository.

## Future Work (Not in Review 1)
The following components belong to later stages or other team members and have not been implemented:
*   1D Depthwise-Separable CNN / Shared backbone / Multi-task learning
*   TinyML / INT8 quantization / Edge deployment (ESP32, STM32, Raspberry Pi)
*   Hardware metrics (RAM, Flash, Latency)
*   IoT integration (MQTT, Real-time sensor streaming, FastAPI, InfluxDB, Grafana, Node-RED, Dashboard)

## Validation Note
Code structure and integration were statically validated. Full runtime execution should be performed in the active Python environment where the required dependencies (pandas, scikit-learn, matplotlib) are installed.
