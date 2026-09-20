# Edge-IoT Predictive Maintenance

## Overview
This project aims to build a robust Predictive Maintenance (PdM) system for industrial motors and bearings. By analyzing vibration data, the system detects mechanical faults early, preventing catastrophic machine failures and minimizing unscheduled downtime. 

The ultimate goal is to deploy an end-to-end Edge-IoT pipeline: collecting data from sensors, running localized inference on Edge microcontrollers (TinyML), and transmitting health diagnostics to an IoT dashboard for monitoring. 

**Note:** The project is actively under development in stages. The current repository contains the **Machine Learning Fault Classification Baseline**, which operates on the CWRU dataset.

## Problem Statement
Industrial bearings undergo continuous stress, making them highly susceptible to progressive degradation. Traditional maintenance strategies (run-to-failure or routine-based) are either dangerous or highly inefficient. Predictive maintenance utilizes machine learning to recognize anomalous vibration signatures and classify specific defect types (e.g., inner race, outer race, or ball faults) well before a failure occurs.

## Current System Pipeline
The currently implemented pipeline processes offline vibration datasets, extracts features, and performs machine learning classification.

```text
Raw CWRU Vibration Data
        ↓
Signal Segmentation (1-sec windows, 50% overlap)
        ↓
Feature Extraction (Time & Frequency Domain)
        ↓
Leakage-safe Train/Test Split (Experiment-level)
        ↓
ML Fault Classification (LogReg, SVM, RF)
        ↓
Evaluation (Accuracy, Precision, Recall, F1, Confusion Matrices)
```

## Dataset
The current implementation utilizes the **Case Western Reserve University (CWRU) Bearing Dataset**. 
- **Raw Data:** `.mat` files containing Drive-End vibration signals.
- **Classes:** Normal, Inner Race Fault, Outer Race Fault, Ball Fault.

## Extracted Features
The feature engineering pipeline (`src/preprocessing.py`) extracts the following metrics from each signal window:
*   **Time-Domain:** RMS, Mean, Standard Deviation, Peak, Peak-to-Peak, Skewness, Kurtosis, Crest Factor.
*   **Frequency-Domain (FFT):** Dominant Frequency, Spectral Centroid, Spectral Bandwidth, Spectral Energy.

## Current ML Models
We have established three classification baselines for benchmarking:
1.  **Logistic Regression:** A linear baseline.
2.  **Support Vector Machine (SVM):** Utilizing an RBF kernel for non-linear boundary detection.
3.  **Random Forest:** An ensemble decision-tree classifier.

Data leakage is strictly prevented by splitting the dataset at the **experiment/file level** rather than randomizing individual windows. This ensures models generalize to entirely unseen vibration recordings.

## Project Structure
```text
Edge_IOT_Predictive_Maintenance/
├── data/
│   ├── raw/CWRU/               # Raw .mat CWRU files (User provided)
│   └── processed/              # Generated cwru_features.csv, plots, status files
├── models/                     # Saved .pkl models and scalers
├── src/
│   ├── preprocessing.py        # Signal segmentation and feature extraction
│   ├── data_loader.py          # Leakage-safe dataset splitting
│   ├── train_logreg.py         # Logistic Regression baseline training
│   ├── train_svm.py            # SVM baseline training
│   ├── train_model.py          # Random Forest baseline training
│   ├── compare_models.py       # Multi-model evaluation and comparison
│   ├── plot_results.py         # Confusion matrix and feature importance visualization
│   └── predict.py              # Inference script for classifying a raw .mat file
└── README.md                   # Project documentation
```

## Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/monalisamajumder06/Edge_IOT_Predictive_Maintenance.git
   cd Edge_IOT_Predictive_Maintenance
   ```
2. Ensure you have Python 3.8+ installed. Install the required dependencies:
   ```bash
   pip install pandas numpy scipy scikit-learn matplotlib joblib
   ```
3. Place the raw CWRU `.mat` files into `data/raw/CWRU/`.

## Usage
Run the pipeline sequentially using the following commands from the root directory:

1. **Extract Features:**
   ```bash
   python src/preprocessing.py
   ```
2. **Train Baseline Models:**
   ```bash
   python src/train_logreg.py
   python src/train_svm.py
   python src/train_model.py
   ```
3. **Compare Models & Evaluate:**
   ```bash
   python src/compare_models.py
   python src/plot_results.py
   ```
4. **Run Inference on a new file:**
   ```bash
   python src/predict.py
   ```

## Current Status & Roadmap

### ✅ Implemented
*   CWRU signal preprocessing and feature extraction.
*   Leakage-safe train/test infrastructure.
*   Fault classification baselines (Logistic Regression, SVM, Random Forest).
*   Model evaluation and performance comparison.
*   Single-file prediction pipeline.

### ⏳ Planned (Future Work)
*   **Remaining Useful Life (RUL):** Prediction of exact time-to-failure (Pending integration of a suitable degradation dataset).
*   **Advanced Architectures:** 1D Depthwise-Separable CNN, Shared backbone for joint Fault/RUL prediction.
*   **Edge Optimization:** INT8 Quantization, TinyML model conversion.
*   **Hardware Deployment:** Flashing to edge hardware (e.g., ESP32, STM32, Raspberry Pi).
*   **IoT & Backend:** Real-time sensor streaming via MQTT, FastAPI backend, InfluxDB time-series storage.
*   **Monitoring:** Live health dashboard via Grafana or Node-RED.

## Technical Stack
*   **Language:** Python
*   **Data Processing:** Pandas, NumPy, SciPy
*   **Machine Learning:** Scikit-Learn
*   **Visualization:** Matplotlib
