from scipy.io import loadmat
from scipy.stats import skew, kurtosis
import numpy as np
import pandas as pd
from pathlib import Path


# ============================================================
# 1. LOAD VIBRATION SIGNAL
# ============================================================

def load_vibration_signal(file_path):
    """Load the Drive-End vibration signal from a CWRU .mat file."""

    data = loadmat(file_path)

    de_keys = [
        key for key in data.keys()
        if key.endswith("_DE_time")
    ]

    if len(de_keys) == 0:
        raise ValueError(
            f"No Drive-End vibration signal found in {file_path}"
        )

    # Some CWRU files contain more than one DE signal.
    # We use the first valid Drive-End signal.
    signal = data[de_keys[0]].flatten()

    return signal


# ============================================================
# 2. CREATE WINDOWS
# ============================================================

def create_windows(signal, sampling_rate=12000):
    """Create 1-second windows with 50% overlap."""

    window_size = sampling_rate
    step_size = window_size // 2

    windows = []

    for start in range(
        0,
        len(signal) - window_size + 1,
        step_size
    ):
        window = signal[start:start + window_size]
        windows.append(window)

    return np.array(windows)


# ============================================================
# 3. TIME-DOMAIN FEATURES
# ============================================================

def calculate_time_features(window):
    """Extract statistical features from the vibration signal."""

    rms = np.sqrt(np.mean(window ** 2))

    mean = np.mean(window)

    std = np.std(window)

    peak = np.max(np.abs(window))

    peak_to_peak = np.ptp(window)

    skewness = skew(window)

    kurt = kurtosis(window)

    # Avoid division by zero
    if rms != 0:
        crest_factor = peak / rms
    else:
        crest_factor = 0

    return {
        "rms": rms,
        "mean": mean,
        "std": std,
        "peak": peak,
        "peak_to_peak": peak_to_peak,
        "skewness": skewness,
        "kurtosis": kurt,
        "crest_factor": crest_factor
    }


# ============================================================
# 4. FREQUENCY-DOMAIN FEATURES
# ============================================================

def calculate_frequency_features(
    window,
    sampling_rate=12000
):
    """Extract frequency-domain features using FFT."""

    fft_values = np.fft.rfft(window)

    frequencies = np.fft.rfftfreq(
        len(window),
        1 / sampling_rate
    )

    magnitude = np.abs(fft_values)

    # Ignore DC component
    magnitude[0] = 0

    # --------------------------------------------------------
    # Dominant frequency
    # --------------------------------------------------------

    dominant_index = np.argmax(magnitude)

    dominant_frequency = frequencies[dominant_index]

    # --------------------------------------------------------
    # Spectral centroid
    # --------------------------------------------------------

    magnitude_sum = np.sum(magnitude)

    if magnitude_sum != 0:
        spectral_centroid = (
            np.sum(frequencies * magnitude)
            / magnitude_sum
        )
    else:
        spectral_centroid = 0

    # --------------------------------------------------------
    # Spectral bandwidth
    # --------------------------------------------------------

    if magnitude_sum != 0:
        spectral_bandwidth = np.sqrt(
            np.sum(
                ((frequencies - spectral_centroid) ** 2)
                * magnitude
            )
            / magnitude_sum
        )
    else:
        spectral_bandwidth = 0

    # --------------------------------------------------------
    # Spectral energy
    # --------------------------------------------------------

    spectral_energy = np.sum(magnitude ** 2)

    return {
        "dominant_frequency_hz": dominant_frequency,
        "spectral_centroid_hz": spectral_centroid,
        "spectral_bandwidth_hz": spectral_bandwidth,
        "spectral_energy": spectral_energy
    }


# ============================================================
# 5. EXTRACT ALL FEATURES FROM ONE WINDOW
# ============================================================

def extract_features(window, sampling_rate=12000):

    time_features = calculate_time_features(window)

    frequency_features = calculate_frequency_features(
        window,
        sampling_rate
    )

    features = {}

    features.update(time_features)
    features.update(frequency_features)

    return features


# ============================================================
# 6. DATASET CONFIGURATION
# ============================================================

DATA_DIR = Path("data/raw/CWRU")

OUTPUT_PATH = Path(
    "data/processed/cwru_features.csv"
)


# Files we have selected for the project
FILE_LABELS = {

    # Normal
    97: "normal",
    98: "normal",
    99: "normal",
    100: "normal",

    # Inner race
    105: "inner_race",
    106: "inner_race",
    107: "inner_race",
    108: "inner_race",

    # Ball
    118: "ball",
    119: "ball",
    120: "ball",
    121: "ball",

    # Outer race
    130: "outer_race",
    131: "outer_race",
    132: "outer_race",
    133: "outer_race"
}


# ============================================================
# 7. MAIN PIPELINE
# ============================================================

if __name__ == "__main__":

    rows = []

    for file_id, label in FILE_LABELS.items():

        file_path = DATA_DIR / f"{file_id}.mat"

        if not file_path.exists():
            print(f"Skipping missing file: {file_id}.mat")
            continue

        print(
            f"Processing {file_id}.mat -> {label}"
        )

        signal = load_vibration_signal(file_path)

        windows = create_windows(signal)

        for window_number, window in enumerate(windows):

            features = extract_features(window)

            row = {
                "file_id": file_id,
                "window": window_number,
                **features,
                "label": label
            }

            rows.append(row)

    # --------------------------------------------------------
    # Create feature dataset
    # --------------------------------------------------------

    features_df = pd.DataFrame(rows)

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    features_df.to_csv(
        OUTPUT_PATH,
        index=False
    )

    # --------------------------------------------------------
    # Display results
    # --------------------------------------------------------

    print("\nFeature dataset created successfully!")

    print(
        "Dataset shape:",
        features_df.shape
    )

    print(
        "\nColumns:"
    )

    print(
        list(features_df.columns)
    )

    print(
        "\nClass distribution:"
    )

    print(
        features_df["label"].value_counts()
    )

    print(
        "\nFirst five rows:"
    )

    print(
        features_df.head()
    )