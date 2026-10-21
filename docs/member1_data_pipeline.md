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
├── nasa_ims.py          # NASA IMS 20 kHz ASCII loader & run-to-failure pipeline (4-Ch & 8-Ch)
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
| **NASA IMS** | 4-Ch / 8-Ch Vibration | 20,000 Hz | Run-to-Failure Degradation & RUL | ASCII tab/space delimited | 20,480 samples every 10 or 5 min |
| **XJTU-SY** | 2-Axis Vibration (Horiz & Vert) | 25,600 Hz | Accelerated Fatigue Degradation & RUL | 2-column CSV | 32,768 samples every 1 min |
| **Paderborn** | Multi-Channel (Vibration + 2 Motor Phase Currents) | 64,000 Hz | Motor Current Signature Analysis & Bearing Fault Classification | MATLAB `.mat` | Continuous 64 kHz sync runs |
| **MIMII** | 8-Ch Acoustic Audio (Mic Array / Single Ch) | 16,000 Hz | Industrial Machine Acoustic Anomaly Detection | 16-bit PCM `.wav` | 10-second recordings (1s frames) |

---

## 3. NASA IMS Run-to-Failure Specification & Channel Layout

### A. Supported Raw Folder Structure
NASA IMS files must be uncompressed into an experiment directory:
```
data/raw/NASA_IMS/<Set_folder>/
├── 2004.02.12.10.32.39
├── 2004.02.12.10.42.39
└── ...
```
- **File Naming:** Strictly timestamped `YYYY.MM.DD.HH.MM.SS`. Non-matching files (e.g. `.DS_Store`, READMEs) are filtered out automatically.
- **File Format:** Pure ASCII whitespace- or tab-delimited floating-point arrays without headers.
- **Snapshots:** 20,480 samples recorded at 20,000 Hz (1.024 seconds recording per snapshot).

### B. Explicit Channel Mapping & Layouts
According to the official NASA / IMS Center documentation:

#### 1. 4-Channel Configuration (Test 2 & Test 3)
One radial PCB 353B33 accelerometer per bearing:
| Bearing Number | Channel Index (0-based) | File Column | Default Label | Verified Fault Outcome |
| :---: | :---: | :---: | :---: | :--- |
| **Bearing 1** | `0` | Column 1 | `Bearing_1` | Outer race failure in Test 2 |
| **Bearing 2** | `1` | Column 2 | `Bearing_2` | Undamaged (survived) |
| **Bearing 3** | `2` | Column 3 | `Bearing_3` | Outer race failure in Test 3 |
| **Bearing 4** | `3` | Column 4 | `Bearing_4` | Undamaged (survived) |

*Mapping formula:* `channel_idx = target_bearing - 1`.

#### 2. 8-Channel Configuration (Test 1)
Two orthogonal accelerometers per bearing housing (X-axis = horizontal, Y-axis = vertical):
| Bearing Number | Axis | Channel Index (0-based) | File Column | Default Label | Verified Fault Outcome |
| :---: | :---: | :---: | :---: | :---: | :--- |
| **Bearing 1** | X | `0` | Column 1 | `Bearing_1_x` | Undamaged |
| **Bearing 1** | Y | `1` | Column 2 | `Bearing_1_y` | Undamaged |
| **Bearing 2** | X | `2` | Column 3 | `Bearing_2_x` | Undamaged |
| **Bearing 2** | Y | `3` | Column 4 | `Bearing_2_y` | Undamaged |
| **Bearing 3** | X | `4` | Column 5 | `Bearing_3_x` | Inner race defect in Test 1 |
| **Bearing 3** | Y | `5` | Column 6 | `Bearing_3_y` | Inner race defect in Test 1 |
| **Bearing 4** | X | `6` | Column 7 | `Bearing_4_x` | Roller element defect in Test 1 |
| **Bearing 4** | Y | `7` | Column 8 | `Bearing_4_y` | Roller element defect in Test 1 |

*Mapping formula:* `channel_idx = (target_bearing - 1) * 2 + (0 if axis == 'x' else 1)`.

### C. Sampling & Framing Assumptions
- **Sampling Frequency ($f_s$):** 20,000 Hz.
- **Window Size:** 1 second ($20,000$ samples @ 20 kHz).
- **Framing Step:** If snapshot has 20,480 samples, 1 primary window (`window_id = 0`) is extracted starting at sample 0.

### D. RUL Target Formulations & Failure-Point Assumptions
- **Failure Point ($T_{\text{failure}}$):** The timestamp of the final valid snapshot in the experiment ($t_{\text{end}}$) is taken as the physical failure point for the designated failed bearing.
- **Linear RUL:** $RUL(t) = \max(0.0, T_{\text{failure}} - t)$ in operating hours.
- **Piecewise Linear RUL:** $RUL_{\text{piecewise}}(t) = \min(RUL(t), RUL_{\text{max}})$, capping early healthy operating hours (default first 60% of test or capped at $100.0$ hours) before decaying linearly to 0.0 operating hours at catastrophic failure.
- **Health Index:** Continuous metric $HI(t) = \text{clip}((T_{\text{failure}} - t) / T_{\text{failure}}, 0.0, 1.0)$ ($1.0 = \text{healthy}, 0.0 = \text{failed}$), strictly complying with Member 3's `RecommendedTelemetryPayload` schema in [`schemas/telemetry.py`](file:///e:/Edge_IOT_Predictive_Maintenance/schemas/telemetry.py).

### E. Limitations & Failure Mode Ground Truth
- Non-failed bearings in the same test rig (e.g. Bearings 2, 3, and 4 in Set 2) did not experience catastrophic failure. They should **not** be assigned zero-hour failure targets unless evaluating survival classification.
- In Set 1, dual-axis sensors provide complementary directional signals. Users can select either the `x` or `y` axis, or extract both sequentially.

---

## 4. Extracted Feature Definitions

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
- `current_1_rms`, `current_1_mean`, `current_1_std`, `current_1_peak`, `current_1_crest_factor`.
- `current_1_dominant_frequency_hz`: fundamental supply frequency (~50 Hz).
- `current_1_spectral_energy`: total AC electrical current energy.
- `current_2_*`: matching metrics for phase 2.
- `current_phase_unbalance`: phase RMS disparity ratio $\frac{|I_1 - I_2|}{0.5(I_1 + I_2)}$.

### C. Acoustic Anomaly Features (MIMII)
- `audio_rms`: root-mean-square sound pressure.
- `audio_peak`: peak acoustic amplitude.
- `audio_crest_factor`: sound spikiness.
- `zero_crossing_rate`: frequency of sign changes.
- `spectral_centroid_hz`: acoustic brightness.
- `spectral_bandwidth_hz`: acoustic dispersion.
- `spectral_flatness` (Wiener entropy): geometric mean divided by arithmetic mean of power spectrum ($0.0 \approx$ pure tone / squeal, $1.0 \approx$ white noise). Highly sensitive to squealing bearings and cavitation.
- `spectral_rolloff_hz`: frequency below which 85% of sound power is concentrated.
- `mel_band_00` to `mel_band_15`: 16 triangular log-Mel filterbank energies spanning 50 Hz to 8000 Hz.

---

## 5. Output Schemas for Member 2 & Member 3 Consumption

### A. NASA IMS Processed Dataset: `data/processed/nasa_ims_features.csv`
- **Identifier Columns:** `experiment_id`, `bearing_id`, `snapshot_id`, `timestamp`, `elapsed_hours`, `window_id`.
- **Feature Columns:** 12 canonical CWRU features (`rms`, `std`, `kurtosis`, `spectral_energy`, etc.).
- **Target Columns:** `health_index`, `rul_hours_linear`, `rul_hours_piecewise`, `rul_hours`.

### B. XJTU-SY Processed Dataset: `data/processed/xjtu_sy_features.csv`
- **Identifier Columns:** `experiment_id`, `operating_condition`, `bearing_id`, `snapshot_id`, `elapsed_minutes`, `elapsed_hours`, `split` (`train` / `test`).
- **Feature Columns:** Primary axis canonical 12 features, horizontal axis (`horiz_*`), vertical axis (`vert_*`).
- **Target Columns:** `health_index`, `rul_minutes_linear`, `rul_hours_linear`, `rul_hours_piecewise`, `rul_hours`.

### C. Paderborn Processed Dataset: `data/processed/paderborn_features.csv`
- **Identifier Columns:** `experiment_id`, `bearing_id`, `damage_type`, `operating_condition`, `window_id`, `timestamp_sec`, `split` (`train` / `test`).
- **Vibration Columns:** `vib_rms`, `vib_kurtosis`, `vib_spectral_energy`, etc., plus canonical un-prefixed aliases (`rms`, `kurtosis`, etc.).
- **Motor Current Columns:** `current_1_rms`, `current_1_dominant_frequency_hz`, `current_2_rms`, `current_phase_unbalance`, etc.

### D. MIMII Processed Dataset: `data/processed/mimii_features.csv`
- **Identifier Columns:** `machine_type`, `machine_id`, `snr_condition`, `condition` (`normal` / `anomaly`), `anomaly_label` (0 / 1), `recording_id`, `window_id`, `timestamp_sec`, `channel_id`, `split` (`train` / `test`).
- **Acoustic Columns:** `audio_rms`, `audio_peak`, `audio_crest_factor`, `zero_crossing_rate`, `spectral_centroid_hz`, `spectral_bandwidth_hz`, `spectral_flatness`, `spectral_rolloff_hz`.
- **Log-Mel Bands:** 16 filterbank features `mel_band_00` through `mel_band_15`.

---

## 6. How Member 2 Consumes These Datasets

### A. RUL Regression (NASA IMS / XJTU-SY)
```python
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error

df = pd.read_csv("data/processed/nasa_ims_features.csv")
features = [
    "rms", "mean", "std", "peak", "peak_to_peak", "skewness",
    "kurtosis", "crest_factor", "dominant_frequency_hz",
    "spectral_centroid_hz", "spectral_bandwidth_hz", "spectral_energy"
]

# Split early degradation vs late degradation or train across bearings
split_idx = int(len(df) * 0.70)
train_df, test_df = df.iloc[:split_idx], df.iloc[split_idx:]

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

---

## 7. Real Data Ingestion & Execution Guide

When real raw datasets are acquired, extract them into:
- NASA IMS: `data/raw/NASA_IMS/<Set_folder>/` (e.g. `data/raw/NASA_IMS/2nd_test/`).
- XJTU-SY: `data/raw/XJTU_SY/XJTU-SY_Bearing_Datasets/<Condition_folder>/<Bearing_folder>/` (`35Hz12kN/Bearing1_1/1.csv`, `37.5Hz11kN/Bearing2_1/1.csv`, `40Hz10kN/Bearing3_1/1.csv`, etc.).
- Paderborn: `data/raw/Paderborn/` (`*.mat` files with 64 kHz vibration & currents).
- MIMII: `data/raw/MIMII/<machine_type>/<machine_id>/<snr>/normal|anomaly/*.wav`.

Executing real-data ingestion:
```python
from data_pipeline import (
    process_ims_experiment,
    process_xjtu_bearing_experiment,
    process_xjtu_dataset,
    process_paderborn_dataset,
    process_mimii_subset,
)

# Process NASA IMS Set 2 Bearing 1 (Outer Race Failure)
df_ims = process_ims_experiment(
    data_dir="data/raw/NASA_IMS/2nd_test",
    target_bearing=1,
    experiment_id="NASA_IMS_Set2_B1",
)
df_ims.to_csv("data/processed/nasa_ims_features.csv", index=False)

# Process NASA IMS Set 1 Bearing 3 X-Axis (Inner Race Defect)
df_ims_set1 = process_ims_experiment(
    data_dir="data/raw/NASA_IMS/1st_test",
    target_bearing=3,
    axis="x",
    experiment_id="NASA_IMS_Set1_B3x",
)

# Process individual XJTU-SY Bearing experiment (with auto-inferred operating condition)
df_xjtu_b1 = process_xjtu_bearing_experiment(
    bearing_dir="data/raw/XJTU_SY/XJTU-SY_Bearing_Datasets/35Hz12kN/Bearing1_1",
)

# Batch process full XJTU-SY dataset with leakage-free train/test partition
df_xjtu = process_xjtu_dataset(
    dataset_root="data/raw/XJTU_SY/XJTU-SY_Bearing_Datasets",
    test_bearings=["Bearing1_5", "Bearing2_5", "Bearing3_5"],
)
df_xjtu.to_csv("data/processed/xjtu_sy_features.csv", index=False)
```

---

## 8. Verification & Test Suite

All data pipelines are covered by automated unit tests in `tests/`:
- `tests/test_cwru_loader.py`: 6 tests (CWRU key selection, 98 vs 99 fix, Fisher kurtosis).
- `tests/test_rul_targets.py`: 5 tests (Linear RUL, Piecewise RUL, Health Index [1.0 -> 0.0]).
- `tests/test_nasa_ims.py`: 10 tests (4-channel & 8-channel layouts, chronological sorting, corrupt snapshot handling, skipped-file reporting).
- `tests/test_xjtu_sy.py`: 6 tests (XJTU-SY 2-axis CSV loading, experiment isolation, condition auto-inference, batch dataset processing, real data validation).
- `tests/test_paderborn.py`: 5 tests (64 kHz multi-channel ingestion, MCSA features, bearing leakage checks).
- `tests/test_mimii.py`: 5 tests (16 kHz WAV loading, Log-Mel filterbanks, acoustic stats, unsupervised split).

Execute the full suite:
```powershell
.\.venv\Scripts\python.exe -m unittest tests/test_cwru_loader.py tests/test_rul_targets.py tests/test_nasa_ims.py tests/test_xjtu_sy.py tests/test_paderborn.py tests/test_mimii.py -v
```
**Total:** 44 unit tests, 100% passing.
