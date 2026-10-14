# Member 1 — Data & Signal Processing Pipeline Specification
## Datasets: CWRU, NASA IMS, XJTU-SY, Paderborn, MIMII
## Module: `src/data_pipeline`

---

## 1. System Overview

This document specifies the multi-dataset ingestion, digital signal processing (DSP), feature extraction, Remaining Useful Life (RUL) target construction, and acoustic anomaly pipelines implemented by **Member 1 (Data & Signal Processing)** for the *Edge-IoT Predictive Maintenance Platform for Industrial Motors*.

The pipeline is organized as a modular Python package in [`src/data_pipeline/`](file:///e:/Edge_IOT_Predictive_Maintenance/src/data_pipeline/):

```
src/data_pipeline/
├── __init__.py          # Public API exports for all datasets
├── features.py          # Unified 12/15 vibration feature extraction (pure NumPy/SciPy)
├── rul_targets.py       # Linear RUL, Piecewise RUL, and Health Index [1.0 -> 0.0]
├── nasa_ims.py          # NASA IMS 20 kHz ASCII loader & run-to-failure pipeline
├── xjtu_sy.py           # XJTU-SY 25.6 kHz 2-axis CSV loader & RUL pipeline
├── paderborn.py         # Paderborn 64 kHz multi-channel (vibration + phase current) pipeline
├── mimii.py             # MIMII 16 kHz acoustic audio WAV & log-Mel filterbank pipeline
└── splits.py            # Experiment-boundary protection & leakage-free group partitioning
```

---

## 2. Dataset Formats & Sampling Rates

| Dataset | Modality | Native Sampling Rate ($f_s$) | Primary Maintenance Task | File Format | Snapshot / Frame Cadence |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **CWRU** | 1-Axis Vibration (DE) | 12,000 Hz | Discrete Bearing Fault Classification | MATLAB `.mat` | Continuous runs |
| **NASA IMS** | 4-Channel Vibration | 20,000 Hz | Run-to-Failure Degradation & RUL | ASCII tab/space delimited | 20,480 samples every 10 min |
| **XJTU-SY** | 2-Axis Vibration (Horiz & Vert) | 25,600 Hz | Accelerated Fatigue Degradation & RUL | 2-column CSV | 32,768 samples every 1 min |
| **Paderborn** | Multi-Channel (Vibration + 2 Motor Phase Currents) | 64,000 Hz | Motor Current Signature Analysis & Bearing Fault Classification | MATLAB `.mat` | Continuous 64 kHz sync runs |
| **MIMII** | 8-Ch Acoustic Audio (Mic Array / Single Ch) | 16,000 Hz | Industrial Machine Acoustic Anomaly Detection | 16-bit PCM `.wav` | 10-second recordings (1s frames) |

---

## 3. Extracted Feature Definitions

### A. Vibration Features (CWRU, NASA IMS, XJTU-SY, Paderborn)
Every 1-second vibration window is processed into canonical time- and frequency-domain features:

| Feature Name | Domain | Formula / Description | Physical Interpretation |
| :--- | :--- | :--- | :--- |
| `rms` | Time | $\sqrt{\frac{1}{N}\sum x^2}$ | Overall vibration energy and load |
| `mean` | Time | $\frac{1}{N}\sum x$ | DC bias (near zero for AC accelerometers) |
| `std` | Time | $\sqrt{\frac{1}{N}\sum (x - \mu)^2}$ | Dynamic AC vibration spread |
| `peak` | Time | $\max \|x\|$ | Maximum absolute impact shock amplitude |
| `peak_to_peak` | Time | $\max(x) - \min(x)$ | Total dynamic range of waveform |
| `skewness` | Time | $\frac{m_3}{m_2^{3/2}}$ (Fisher-Pearson moment) | Asymmetry of impact pulses |
| `kurtosis` | Time | $\frac{m_4}{m_2^2} - 3.0$ (Fisher excess kurtosis) | Impulsiveness of bearing fault shocks (normal = 0) |
| `crest_factor` | Time | $\text{peak} / \text{rms}$ | Spikiness of shock pulses relative to energy |
| `shape_factor` | Time | $\text{rms} / \text{mean}(\|x\|)$ | Waveform shape evolution |
| `impulse_factor` | Time | $\text{peak} / \text{mean}(\|x\|)$ | Sensitivity to incipient bearing micro-impacts |
| `margin_factor` | Time | $\text{peak} / (\text{mean}(\sqrt{\|x\|}))^2$ | Robustness to mechanical shock loading |
| `dominant_frequency_hz` | Freq | $\arg\max_{f > 0} \|X(f)\|$ | Primary rotational or resonant frequency |
| `spectral_centroid_hz` | Freq | $\sum f \|X(f)\| / \sum \|X(f)\|$ | Center of mass of the vibration spectrum |
| `spectral_bandwidth_hz`| Freq | $\sqrt{\sum (f - f_c)^2 \|X(f)\| / \sum \|X(f)\|}$| Spectral spread across higher harmonics |
| `spectral_energy` | Freq | $\sum \|X(f)\|^2$ | Total frequency domain spectral power |

### B. Motor Current Signature Analysis (MCSA) Features (Paderborn)
Extracts phase current dynamics to detect electrical unbalance, broken rotor bars, and load modulation:
- `current_1_rms`, `current_1_mean`, `current_1_std`, `current_1_peak`, `current_1_crest_factor`.
- `current_1_dominant_frequency_hz`: fundamental supply frequency (~50 Hz).
- `current_1_spectral_energy`: total AC electrical current energy.
- `current_2_*`: matching metrics for phase 2.
- `current_phase_unbalance`: phase RMS disparity ratio $\frac{|I_1 - I_2|}{0.5(I_1 + I_2)}$.

### C. Acoustic Anomaly Features (MIMII)
Extracts audio-specific features without flattening sound into standard accelerometer vibration:
- `audio_rms`: root-mean-square sound pressure.
- `audio_peak`: peak acoustic amplitude.
- `audio_crest_factor`: sound spikiness.
- `zero_crossing_rate`: frequency of sign changes.
- `spectral_centroid_hz`: acoustic brightness.
- `spectral_bandwidth_hz`: acoustic dispersion.
- `spectral_flatness` (Wiener entropy): geometric mean divided by arithmetic mean of power spectrum ($0.0 \approx$ pure tone/whistle, $1.0 \approx$ white noise). Highly sensitive to squealing bearings and cavitation.
- `spectral_rolloff_hz`: frequency below which 85% of sound power is concentrated.
- `mel_band_00` to `mel_band_15`: 16 triangular log-Mel filterbank energies spanning 50 Hz to 8000 Hz.

---

## 4. RUL Target Formulations (NASA IMS & XJTU-SY)

For run-to-failure degradation tracking, targets are computed strictly along each individual bearing's timeline. **Failure time is never inferred from other bearings.**

1. **Exact Linear RUL (`rul_hours_linear` / `rul_minutes_linear`):**
   $$RUL(t) = \max(0.0, T_{\text{failure}} - t)$$
2. **Piecewise-Linear RUL (`rul_hours_piecewise` / canonical `rul_hours`):**
   $$RUL_{\text{piecewise}}(t) = \min(RUL(t), RUL_{\text{max}})$$
   Caps the target during the early healthy plateau, followed by linear degradation to 0 operating hours.
3. **Composite Health Index (`health_index`):**
   $$HI(t) = \text{clip}\left(\frac{RUL(t)}{T_{\text{failure}}}, 0.0, 1.0\right)$$
   Normalized continuous health state ($1.0 = \text{healthy}, 0.0 = \text{failed}$). Strictly complies with Member 3's `RecommendedTelemetryPayload` validation rule ($0.0 \le \text{health\_index} \le 1.0$).

---

## 5. Output Schemas for Member 2 & Member 3 Consumption

### A. NASA IMS Processed Dataset: `data/processed/nasa_ims_features.csv`
- **Identifier Columns:** `experiment_id`, `bearing_id`, `snapshot_id`, `timestamp`, `elapsed_hours`.
- **Feature Columns:** 12 canonical CWRU features + 3 extended degradation metrics.
- **Target Columns:** `health_index`, `rul_hours_linear`, `rul_hours_piecewise`, `rul_hours`.

### B. XJTU-SY Processed Dataset: `data/processed/xjtu_sy_features.csv`
- **Identifier Columns:** `experiment_id`, `operating_condition`, `bearing_id`, `snapshot_id`, `elapsed_minutes`, `elapsed_hours`, `split` (`train` / `test`).
- **Feature Columns:** Primary axis canonical 12 features, horizontal axis (`horiz_*`), vertical axis (`vert_*`).
- **Target Columns:** `health_index`, `rul_minutes_linear`, `rul_hours_linear`, `rul_hours_piecewise`, `rul_hours`.

### C. Paderborn Processed Dataset: `data/processed/paderborn_features.csv`
- **Identifier Columns:** `experiment_id`, `bearing_id`, `damage_type`, `operating_condition`, `window_id`, `timestamp_sec`, `split` (`train` / `test`).
- **Vibration Columns:** `vib_rms`, `vib_kurtosis`, `vib_spectral_energy`, etc., plus canonical un-prefixed aliases (`rms`, `kurtosis`, etc.) for direct CWRU model testing.
- **Motor Current Columns:** `current_1_rms`, `current_1_dominant_frequency_hz`, `current_2_rms`, `current_phase_unbalance`, etc.
- **Grouping Rule:** Split strictly by physical `bearing_id`. Windows of test bearings (e.g. `KA01`) never leak into train.

### D. MIMII Processed Dataset: `data/processed/mimii_features.csv`
- **Identifier Columns:** `machine_type`, `machine_id`, `snr_condition`, `condition` (`normal` / `anomaly`), `anomaly_label` (0 / 1), `recording_id`, `window_id`, `timestamp_sec`, `channel_id`, `split` (`train` / `test`).
- **Acoustic Columns:** `audio_rms`, `audio_peak`, `audio_crest_factor`, `zero_crossing_rate`, `spectral_centroid_hz`, `spectral_bandwidth_hz`, `spectral_flatness`, `spectral_rolloff_hz`.
- **Log-Mel Bands:** 16 filterbank features `mel_band_00` through `mel_band_15`.
- **Splitting Modalities:**
  - `split_mimii_by_recording()`: Unsupervised anomaly detection. Train contains ONLY normal recordings (70%); Test contains held-out normal (30%) + anomaly recordings (100%). Zero recording overlap!
  - `split_mimii_by_machine()`: Cross-machine domain generalization. Train on `id_00`, test on `id_02`.

---

## 6. How Member 2 Consumes These Datasets

### A. RUL Regression (NASA IMS / XJTU-SY)
```python
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error

df = pd.read_csv("data/processed/xjtu_sy_features.csv")
features = ["rms", "kurtosis", "crest_factor", "dominant_frequency_hz", "spectral_energy"]

train_df = df[df["split"] == "train"]
test_df = df[df["split"] == "test"]

model = RandomForestRegressor(n_estimators=100, random_state=42)
model.fit(train_df[features], train_df["rul_hours"])
preds = model.predict(test_df[features])
print("RUL MAE (hours):", mean_absolute_error(test_df["rul_hours"], preds))
```

### B. Multi-Modal Fault Classification (Paderborn)
```python
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report

df = pd.read_csv("data/processed/paderborn_features.csv")
multimodal_features = [
    "vib_rms", "vib_kurtosis", "vib_spectral_energy",
    "current_1_rms", "current_phase_unbalance", "current_1_dominant_frequency_hz"
]

train_df = df[df["split"] == "train"]
test_df = df[df["split"] == "test"]

clf = RandomForestClassifier(n_estimators=100, random_state=42)
clf.fit(train_df[multimodal_features], train_df["damage_type"])
preds = clf.predict(test_df[multimodal_features])
print(classification_report(test_df["damage_type"], preds))
```

### C. Unsupervised Acoustic Anomaly Detection (MIMII)
```python
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import roc_auc_score

df = pd.read_csv("data/processed/mimii_features.csv")
mel_features = [f"mel_band_{i:02d}" for i in range(16)] + ["spectral_flatness", "audio_rms"]

train_df = df[df["split"] == "train"]  # Normal sound only
test_df = df[df["split"] == "test"]    # Normal + Anomaly

# Fit Isolation Forest on normal baseline operating sound
detector = IsolationForest(contamination=0.1, random_state=42)
detector.fit(train_df[mel_features])

# Score anomaly
scores = -detector.decision_function(test_df[mel_features])
print("Acoustic Anomaly ROC-AUC:", roc_auc_score(test_df["anomaly_label"], scores))
```

---

## 7. Real Data Ingestion Guide

When real raw datasets are acquired, place them into:
- NASA IMS: `data/raw/NASA_IMS/<Set_folder>/` (timestamp files `YYYY.MM.DD.HH.MM.SS`).
- XJTU-SY: `data/raw/XJTU_SY/<Bearing_folder>/` (`1.csv`, `2.csv`, ...).
- Paderborn: `data/raw/Paderborn/` (`*.mat` files with 64 kHz vibration & currents).
- MIMII: `data/raw/MIMII/<machine_type>/<machine_id>/<snr>/normal|anomaly/*.wav`.

Executing the module processors directly:
```python
from data_pipeline import (
    process_ims_experiment,
    process_xjtu_bearing_experiment,
    process_paderborn_dataset,
    process_mimii_subset,
)

# Process Paderborn
df_pb = process_paderborn_dataset("data/raw/Paderborn", test_bearings=["KA01"])
df_pb.to_csv("data/processed/paderborn_features.csv", index=False)

# Process MIMII
df_mi = process_mimii_subset("data/raw/MIMII/pump", split_strategy="recording")
df_mi.to_csv("data/processed/mimii_features.csv", index=False)
```

---

## 8. Verification & Test Suite

All data pipelines are covered by automated unit tests in `tests/`:
- `tests/test_cwru_loader.py`: 6 tests (CWRU key selection, 98 vs 99 fix, Fisher kurtosis).
- `tests/test_rul_targets.py`: 5 tests (Linear RUL, Piecewise RUL, Health Index [1.0 -> 0.0]).
- `tests/test_nasa_ims.py`: 3 tests (NASA IMS timestamps, 20 kHz windowing, RUL generation).
- `tests/test_xjtu_sy.py`: 3 tests (XJTU-SY 2-axis CSV loading, experiment isolation).
- `tests/test_paderborn.py`: 5 tests (64 kHz multi-channel ingestion, MCSA features, bearing leakage checks).
- `tests/test_mimii.py`: 5 tests (16 kHz WAV loading, Log-Mel filterbanks, acoustic stats, unsupervised split).

Execute the full suite:
```powershell
.\.venv\Scripts\python.exe -m unittest tests/test_cwru_loader.py tests/test_rul_targets.py tests/test_nasa_ims.py tests/test_xjtu_sy.py tests/test_paderborn.py tests/test_mimii.py -v
```
**Total:** 27 unit tests, 100% passing.
