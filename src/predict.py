from pathlib import Path
import re
from scipy.io import loadmat
from scipy.stats import skew, kurtosis
import numpy as np
import pandas as pd
import joblib


def load_vibration_signal(file_path):
    """Load the Drive-End vibration signal from a CWRU .mat file.

    Selects the specific Drive-End variable associated with the file's numeric
    identifier (e.g. 'X099_DE_time' for '99.mat') to prevent loading stale
    variables present in multi-signal MAT files.
    """

    file_path = Path(file_path)
    data = loadmat(file_path)

    de_keys = [key for key in data.keys() if key.endswith("_DE_time")]

    if len(de_keys) == 0:
        raise ValueError(f"No Drive-End vibration signal found in {file_path}")

    # Extract numeric identifier from filename stem (e.g. '99' from '99.mat')
    match = re.search(r"(\d+)", file_path.stem)
    if match:
        file_num = int(match.group(1))
        matching_keys = [
            k for k in de_keys
            if re.search(rf"^X0*{file_num}_DE_time$", k)
        ]
        if len(matching_keys) == 1:
            return data[matching_keys[0]].flatten()
        elif len(matching_keys) > 1:
            raise ValueError(
                f"Ambiguous Drive-End signals matching file ID {file_num} in {file_path}: {matching_keys}"
            )

    # Fallback if filename has no numeric ID or if exactly one DE key exists
    if len(de_keys) == 1:
        return data[de_keys[0]].flatten()

    raise ValueError(
        f"Multiple Drive-End signals found in {file_path} ({de_keys}) "
        f"but none unambiguously matched file ID '{file_path.stem}'."
    )


def create_windows(signal, sampling_rate=12000):
    """Create 1-second windows with 50% overlap."""

    window_size = sampling_rate
    step_size = window_size // 2

    windows = []

    for start in range(0, len(signal) - window_size + 1, step_size):
        window = signal[start:start + window_size]
        windows.append(window)

    return np.array(windows)


def extract_features(window, sampling_rate=12000):
    """Extract features aligned with src/preprocessing.py (Fisher excess kurtosis)."""

    rms = np.sqrt(np.mean(window ** 2))

    mean = np.mean(window)

    std = np.std(window)

    peak = np.max(np.abs(window))

    peak_to_peak = np.ptp(window)

    skewness = float(skew(window))

    # Fisher excess kurtosis (normal distribution = 0.0), matching src/preprocessing.py
    kurt = float(kurtosis(window))

    crest_factor = peak / rms if rms != 0 else 0

    fft_values = np.fft.rfft(window)
    frequencies = np.fft.rfftfreq(
        len(window),
        1 / sampling_rate
    )

    magnitude = np.abs(fft_values)

    # Ignore DC component
    magnitude[0] = 0

    dominant_index = np.argmax(magnitude)

    dominant_frequency = frequencies[dominant_index]

    total_magnitude = np.sum(magnitude)

    if total_magnitude != 0:

        spectral_centroid = (
            np.sum(frequencies * magnitude) /
            total_magnitude
        )

        spectral_bandwidth = np.sqrt(
            np.sum(
                ((frequencies - spectral_centroid) ** 2)
                * magnitude
            )
            / total_magnitude
        )

    else:

        spectral_centroid = 0
        spectral_bandwidth = 0

    spectral_energy = np.sum(magnitude ** 2)

    return [
        rms,
        mean,
        std,
        peak,
        peak_to_peak,
        skewness,
        kurt,
        crest_factor,
        dominant_frequency,
        spectral_centroid,
        spectral_bandwidth,
        spectral_energy
    ]



if __name__ == "__main__":

    # --------------------------------------------------
    # Change this file when testing another CWRU file
    # --------------------------------------------------

    file_path = "data/raw/CWRU/132.mat"

    model_path = "models/random_forest.pkl"

    # Load trained model
    model = joblib.load(model_path)

    print("Model loaded successfully!")

    # Load vibration signal
    signal = load_vibration_signal(file_path)

    print("Signal samples:", len(signal))

    # Create windows
    windows = create_windows(signal)

    print("Number of windows:", len(windows))

    # Extract features
    feature_rows = []

    for window in windows:

        features = extract_features(window)

        feature_rows.append(features)

    feature_names = [
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

    X = pd.DataFrame(
        feature_rows,
        columns=feature_names
    )

    # Predict every window
    predictions = model.predict(X)

    # Count predictions
    prediction_counts = pd.Series(predictions).value_counts()

    final_prediction = prediction_counts.idxmax()

    confidence = (
        prediction_counts[final_prediction]
        / len(predictions)
    )

    print()
    print("========================================")
    print("BEARING CONDITION PREDICTION")
    print("========================================")

    print("Input file:", file_path)

    print("Predicted condition:", final_prediction)

    print(
        "Prediction confidence:",
        f"{confidence * 100:.2f}%"
    )

    print()
    print("Window predictions:")

    print(prediction_counts)

    print("========================================")