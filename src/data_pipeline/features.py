"""Vibration signal feature extraction module.

Provides unified time-domain and frequency-domain feature extraction
conforming to the project's feature specifications across CWRU, NASA IMS,
and XJTU-SY datasets.
"""

from typing import Dict, List, Optional
import numpy as np
from scipy.stats import skew, kurtosis

# Canonical 12 CWRU features + 3 run-to-failure degradation metrics
CORE_FEATURE_COLUMNS: List[str] = [
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
    "spectral_energy",
]

EXTENDED_FEATURE_COLUMNS: List[str] = CORE_FEATURE_COLUMNS + [
    "shape_factor",
    "impulse_factor",
    "margin_factor",
]

FEATURE_COLUMNS = CORE_FEATURE_COLUMNS


def calculate_time_features(window: np.ndarray) -> Dict[str, float]:
    """Extract statistical time-domain features from a 1D vibration array."""
    if len(window) == 0:
        raise ValueError("Cannot calculate features from an empty window.")

    # Guard against NaN/inf in raw signal
    if np.isnan(window).any() or np.isinf(window).any():
        window = np.nan_to_num(window, nan=0.0, posinf=0.0, neginf=0.0)

    mean = float(np.mean(window))
    std = float(np.std(window))
    rms = float(np.sqrt(np.mean(window ** 2)))
    peak = float(np.max(np.abs(window)))
    peak_to_peak = float(np.ptp(window))

    # Fisher-Pearson standardized skewness
    skewness = float(skew(window)) if std > 1e-12 else 0.0

    # Fisher's excess kurtosis (normal distribution = 0.0)
    kurt = float(kurtosis(window, fisher=True)) if std > 1e-12 else 0.0

    crest_factor = (peak / rms) if rms > 1e-12 else 0.0

    mean_abs = float(np.mean(np.abs(window)))
    mean_sqrt = float(np.mean(np.sqrt(np.abs(window))))

    shape_factor = (rms / mean_abs) if mean_abs > 1e-12 else 0.0
    impulse_factor = (peak / mean_abs) if mean_abs > 1e-12 else 0.0
    margin_factor = (peak / (mean_sqrt ** 2)) if mean_sqrt > 1e-12 else 0.0

    return {
        "rms": rms,
        "mean": mean,
        "std": std,
        "peak": peak,
        "peak_to_peak": peak_to_peak,
        "skewness": skewness,
        "kurtosis": kurt,
        "crest_factor": crest_factor,
        "shape_factor": shape_factor,
        "impulse_factor": impulse_factor,
        "margin_factor": margin_factor,
    }


def calculate_frequency_features(
    window: np.ndarray, sampling_rate: float = 12000.0
) -> Dict[str, float]:
    """Extract frequency-domain features using real Fast Fourier Transform (rfft)."""
    if len(window) == 0:
        raise ValueError("Cannot calculate frequency features from an empty window.")

    fft_values = np.fft.rfft(window)
    frequencies = np.fft.rfftfreq(len(window), d=1.0 / sampling_rate)

    magnitude = np.abs(fft_values)

    # Suppress DC component (0 Hz) to isolate vibration harmonics
    if len(magnitude) > 0:
        magnitude[0] = 0.0

    dominant_index = int(np.argmax(magnitude)) if len(magnitude) > 0 else 0
    dominant_frequency = float(frequencies[dominant_index]) if len(frequencies) > 0 else 0.0

    magnitude_sum = float(np.sum(magnitude))

    if magnitude_sum > 1e-12:
        spectral_centroid = float(np.sum(frequencies * magnitude) / magnitude_sum)
        spectral_bandwidth = float(
            np.sqrt(np.sum(((frequencies - spectral_centroid) ** 2) * magnitude) / magnitude_sum)
        )
    else:
        spectral_centroid = 0.0
        spectral_bandwidth = 0.0

    spectral_energy = float(np.sum(magnitude ** 2))

    return {
        "dominant_frequency_hz": dominant_frequency,
        "spectral_centroid_hz": spectral_centroid,
        "spectral_bandwidth_hz": spectral_bandwidth,
        "spectral_energy": spectral_energy,
    }


def extract_vibration_features(
    window: np.ndarray,
    sampling_rate: float = 12000.0,
    include_extended: bool = False,
) -> Dict[str, float]:
    """Extract all time- and frequency-domain vibration features for a single window."""
    time_feats = calculate_time_features(window)
    freq_feats = calculate_frequency_features(window, sampling_rate=sampling_rate)

    features = {}
    features.update(time_feats)
    features.update(freq_feats)

    if not include_extended:
        # Retain canonical 12 CWRU columns
        return {k: features[k] for k in CORE_FEATURE_COLUMNS}

    return {k: features[k] for k in EXTENDED_FEATURE_COLUMNS}
