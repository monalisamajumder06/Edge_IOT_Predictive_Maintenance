from scipy.io import loadmat
import numpy as np
import pandas as pd
import joblib


def load_vibration_signal(file_path):
    """Load the Drive-End vibration signal from a CWRU .mat file."""

    data = loadmat(file_path)

    de_keys = [key for key in data.keys() if key.endswith("_DE_time")]

    # Some CWRU files contain multiple Drive-End signals.
    # Use the first available signal for prediction.
    if len(de_keys) == 0:
        raise ValueError("No Drive-End vibration signal found.")

    signal = data[de_keys[0]].flatten()

    return signal


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

    rms = np.sqrt(np.mean(window ** 2))

    mean = np.mean(window)

    std = np.std(window)

    peak = np.max(np.abs(window))

    peak_to_peak = np.ptp(window)

    skewness = (
        np.mean((window - mean) ** 3) /
        (std ** 3)
        if std != 0 else 0
    )

    kurtosis = (
        np.mean((window - mean) ** 4) /
        (std ** 4)
        if std != 0 else 0
    )

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
        kurtosis,
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