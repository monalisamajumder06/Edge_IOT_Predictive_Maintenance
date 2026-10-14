"""Paderborn University Bearing Dataset loader and preprocessing pipeline.

Supports:
- Paderborn bearing test rig signals (MATLAB .mat format).
- Multi-channel ingestion: 64 kHz vibration acceleration and 2-phase motor currents.
- Multi-channel feature extraction:
    * Vibration: Canonical 12/15 time & frequency features (RMS, kurtosis, spectral energy, etc.).
    * Motor Phase Current: MCSA features (RMS, peak, crest factor, spectral energy, phase unbalance).
- Sensor/channel identity preservation (vib_*, current_1_*, current_2_*).
- Leakage-proof experiment-level / bearing-level dataset splitting.
- Synthetic fixture generation for offline validation when raw data is not locally present.
"""

from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
import scipy.io as sio

from .features import extract_vibration_features, FEATURE_COLUMNS
from .splits import split_experiments_by_bearing, verify_no_experiment_leakage


SAMPLING_RATE_PADERBORN = 64000.0  # 64 kHz


def extract_current_features(
    current_1: np.ndarray,
    current_2: Optional[np.ndarray] = None,
    sampling_rate: float = SAMPLING_RATE_PADERBORN,
) -> Dict[str, float]:
    """Extract Motor Current Signature Analysis (MCSA) features from phase currents.

    Args:
        current_1: 1D array of motor phase 1 current (Amperes).
        current_2: Optional 1D array of motor phase 2 current (Amperes).
        sampling_rate: Sampling frequency in Hz (default 64,000 Hz).

    Returns:
        Dictionary of statistical and frequency-domain current features.
    """
    if len(current_1) == 0:
        raise ValueError("Cannot extract current features from an empty array.")

    # Guard against NaN/inf
    if np.isnan(current_1).any() or np.isinf(current_1).any():
        current_1 = np.nan_to_num(current_1, nan=0.0, posinf=0.0, neginf=0.0)

    c1_mean = float(np.mean(current_1))
    c1_std = float(np.std(current_1))
    c1_rms = float(np.sqrt(np.mean(current_1 ** 2)))
    c1_peak = float(np.max(np.abs(current_1)))
    c1_crest = (c1_peak / c1_rms) if c1_rms > 1e-12 else 0.0

    # FFT for current harmonics (fundamental supply frequency ~50 Hz)
    fft_1 = np.fft.rfft(current_1)
    freqs = np.fft.rfftfreq(len(current_1), d=1.0 / sampling_rate)
    mag_1 = np.abs(fft_1)
    if len(mag_1) > 0:
        mag_1[0] = 0.0  # Zero DC component

    c1_dom_idx = int(np.argmax(mag_1)) if len(mag_1) > 0 else 0
    c1_dom_freq = float(freqs[c1_dom_idx]) if len(freqs) > 0 else 0.0
    c1_spectral_energy = float(np.sum(mag_1 ** 2))

    features: Dict[str, float] = {
        "current_1_rms": c1_rms,
        "current_1_mean": c1_mean,
        "current_1_std": c1_std,
        "current_1_peak": c1_peak,
        "current_1_crest_factor": c1_crest,
        "current_1_dominant_frequency_hz": c1_dom_freq,
        "current_1_spectral_energy": c1_spectral_energy,
        # Canonical aliases for general current metrics
        "current_rms": c1_rms,
        "current_peak": c1_peak,
    }

    if current_2 is not None and len(current_2) > 0:
        if np.isnan(current_2).any() or np.isinf(current_2).any():
            current_2 = np.nan_to_num(current_2, nan=0.0, posinf=0.0, neginf=0.0)

        c2_mean = float(np.mean(current_2))
        c2_std = float(np.std(current_2))
        c2_rms = float(np.sqrt(np.mean(current_2 ** 2)))
        c2_peak = float(np.max(np.abs(current_2)))
        c2_crest = (c2_peak / c2_rms) if c2_rms > 1e-12 else 0.0

        fft_2 = np.fft.rfft(current_2)
        mag_2 = np.abs(fft_2)
        if len(mag_2) > 0:
            mag_2[0] = 0.0
        c2_dom_idx = int(np.argmax(mag_2)) if len(mag_2) > 0 else 0
        c2_dom_freq = float(freqs[c2_dom_idx]) if len(freqs) > 0 else 0.0
        c2_spectral_energy = float(np.sum(mag_2 ** 2))

        # Phase unbalance ratio
        avg_rms = 0.5 * (c1_rms + c2_rms)
        phase_unbalance = (abs(c1_rms - c2_rms) / avg_rms) if avg_rms > 1e-12 else 0.0

        features.update({
            "current_2_rms": c2_rms,
            "current_2_mean": c2_mean,
            "current_2_std": c2_std,
            "current_2_peak": c2_peak,
            "current_2_crest_factor": c2_crest,
            "current_2_dominant_frequency_hz": c2_dom_freq,
            "current_2_spectral_energy": c2_spectral_energy,
            "current_phase_unbalance": phase_unbalance,
        })

    return features


def load_paderborn_mat(file_path: Union[str, Path]) -> Dict[str, Union[np.ndarray, Dict]]:
    """Load signals and metadata from a Paderborn MATLAB (.mat) file.

    Supports both direct key format and Paderborn test rig struct format.

    Returns:
        Dictionary with:
            - 'vibration': 1D np.ndarray
            - 'current_1': 1D np.ndarray
            - 'current_2': Optional 1D np.ndarray
            - 'metadata': dict of bearing_id, damage_type, etc.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Paderborn file not found: {path}")

    try:
        mat_dict = sio.loadmat(path)
    except Exception as exc:
        raise ValueError(f"Failed to load Paderborn MAT file {path}: {exc}") from exc

    # Filter out MATLAB dunder keys
    data_keys = [k for k in mat_dict.keys() if not k.startswith("__")]
    if not data_keys:
        raise ValueError(f"No valid data variables found in {path}.")

    vibration: Optional[np.ndarray] = None
    current_1: Optional[np.ndarray] = None
    current_2: Optional[np.ndarray] = None
    meta: Dict[str, Union[str, float]] = {}

    # Case 1: Direct keys in mat file
    lower_map = {k.lower(): k for k in data_keys}

    # Search for vibration
    for cand in ["vibration", "vib", "acc", "vibration_1", "vibration_radial", "vibration_signal"]:
        if cand in lower_map:
            arr = np.squeeze(mat_dict[lower_map[cand]])
            if arr.ndim == 1 and len(arr) > 0:
                vibration = arr.astype(float)
                break

    # Search for current 1
    for cand in ["current_1", "current_phase_1", "phase_current_1", "current_a", "current"]:
        if cand in lower_map:
            arr = np.squeeze(mat_dict[lower_map[cand]])
            if arr.ndim == 1 and len(arr) > 0:
                current_1 = arr.astype(float)
                break

    # Search for current 2
    for cand in ["current_2", "current_phase_2", "phase_current_2", "current_b"]:
        if cand in lower_map:
            arr = np.squeeze(mat_dict[lower_map[cand]])
            if arr.ndim == 1 and len(arr) > 0:
                current_2 = arr.astype(float)
                break

    # Case 2: Structured Paderborn format (nested struct named after experiment or Y array)
    if vibration is None:
        for k in data_keys:
            val = mat_dict[k]
            # Check if this object has struct fields like 'Y' or signal arrays
            if hasattr(val, "dtype") and val.dtype.names:
                names = val.dtype.names
                if "Y" in names:
                    # Typical Paderborn structure: struct.Y contains measurement channels
                    y_struct = val["Y"][0, 0]
                    # Inspect fields inside Y
                    if hasattr(y_struct, "dtype") and y_struct.dtype.names:
                        for sub_field in y_struct.dtype.names:
                            field_lower = sub_field.lower()
                            data_arr = np.squeeze(y_struct[sub_field])
                            if data_arr.ndim == 1:
                                if "vib" in field_lower or "acc" in field_lower:
                                    vibration = data_arr.astype(float)
                                elif "cur" in field_lower and current_1 is None:
                                    current_1 = data_arr.astype(float)
                                elif "cur" in field_lower and current_2 is None:
                                    current_2 = data_arr.astype(float)
                # Check for direct named fields inside struct
                for field in names:
                    field_lower = field.lower()
                    data_arr = np.squeeze(val[field][0, 0])
                    if data_arr.ndim == 1 and len(data_arr) > 0:
                        if "vib" in field_lower or "acc" in field_lower:
                            vibration = data_arr.astype(float)
                        elif "cur" in field_lower:
                            if "2" in field_lower or "b" in field_lower:
                                current_2 = data_arr.astype(float)
                            elif current_1 is None:
                                current_1 = data_arr.astype(float)

    # Fallback: if vibration still not found, check any 1D/2D arrays
    if vibration is None:
        for k in data_keys:
            arr = np.squeeze(mat_dict[k])
            if isinstance(arr, np.ndarray) and arr.ndim == 1 and len(arr) > 100:
                vibration = arr.astype(float)
                break
            elif isinstance(arr, np.ndarray) and arr.ndim == 2:
                # E.g., multiple columns
                if arr.shape[1] >= 2:
                    vibration = arr[:, 0].astype(float)
                    current_1 = arr[:, 1].astype(float)
                    if arr.shape[1] >= 3:
                        current_2 = arr[:, 2].astype(float)
                    break

    if vibration is None:
        raise ValueError(
            f"Could not identify vibration signal in Paderborn file {path}. "
            f"Available variables: {data_keys}"
        )

    # Default dummy current if current_1 missing to maintain downstream contract
    if current_1 is None:
        current_1 = np.zeros_like(vibration)

    # Extract metadata fields if present
    for k in ["bearing_id", "damage_type", "damage_method", "operating_condition"]:
        if k in mat_dict:
            meta[k] = str(mat_dict[k]).strip("[]'\" ")

    return {
        "vibration": vibration,
        "current_1": current_1,
        "current_2": current_2,
        "metadata": meta,
    }


def process_paderborn_signals(
    vibration: np.ndarray,
    current_1: np.ndarray,
    current_2: Optional[np.ndarray] = None,
    sampling_rate: float = SAMPLING_RATE_PADERBORN,
    window_size: int = 64000,  # 1-second @ 64 kHz
    step_size: int = 32000,    # 50% overlap
) -> List[Dict[str, float]]:
    """Segment multi-channel Paderborn signals into 1-second windows and extract features."""
    n_samples = min(len(vibration), len(current_1))
    if current_2 is not None and len(current_2) > 0:
        n_samples = min(n_samples, len(current_2))

    if n_samples == 0:
        raise ValueError("Cannot process empty signal arrays.")

    # Single-window fallback if total duration < 1 second
    if n_samples < window_size:
        vib_feats = extract_vibration_features(vibration[:n_samples], sampling_rate=sampling_rate)
        cur2_slice = current_2[:n_samples] if current_2 is not None else None
        cur_feats = extract_current_features(current_1[:n_samples], cur2_slice, sampling_rate=sampling_rate)

        row: Dict[str, float] = {"window_id": 0, "timestamp_sec": 0.0}
        for k, v in vib_feats.items():
            row[f"vib_{k}"] = v
            # Expose canonical unprefixed features for Member 2 model compatibility
            if k in FEATURE_COLUMNS:
                row[k] = v
        row.update(cur_feats)
        return [row]

    windows: List[Dict[str, float]] = []
    for w_idx, start in enumerate(range(0, n_samples - window_size + 1, step_size)):
        vib_win = vibration[start : start + window_size]
        cur1_win = current_1[start : start + window_size]
        cur2_win = current_2[start : start + window_size] if current_2 is not None else None

        vib_feats = extract_vibration_features(vib_win, sampling_rate=sampling_rate)
        cur_feats = extract_current_features(cur1_win, cur2_win, sampling_rate=sampling_rate)

        row = {
            "window_id": w_idx,
            "timestamp_sec": round(start / sampling_rate, 4),
        }
        for k, v in vib_feats.items():
            row[f"vib_{k}"] = v
            # Expose canonical unprefixed features
            if k in FEATURE_COLUMNS:
                row[k] = v
        row.update(cur_feats)
        windows.append(row)

    return windows


def infer_paderborn_metadata_from_filename(filename: str) -> Dict[str, str]:
    """Infer bearing ID and damage condition from standard Paderborn file naming."""
    name = Path(filename).stem
    # Standard Paderborn bearing codes:
    # K001 - K006: Healthy / Undamaged
    # KA01, KA03, KA05, etc.: Artificial outer ring damage
    # KI01, KI03, KI05, etc.: Artificial inner ring damage
    # KB23, KB24, KB27: Accelerated lifetime fatigue damage
    meta = {
        "experiment_id": name,
        "bearing_id": name,
        "damage_type": "unknown",
        "damage_category": "unknown",
    }

    upper_name = name.upper()

    # Match bearing code
    match = re.search(r"(K[A-Z0-9]{3,4})", upper_name)
    if match:
        code = match.group(1)
        meta["bearing_id"] = code
        if code.startswith("K0"):
            meta["damage_type"] = "healthy"
            meta["damage_category"] = "undamaged"
        elif code.startswith("KA"):
            meta["damage_type"] = "outer_race"
            meta["damage_category"] = "artificial_outer"
        elif code.startswith("KI"):
            meta["damage_type"] = "inner_race"
            meta["damage_category"] = "artificial_inner"
        elif code.startswith("KB"):
            meta["damage_type"] = "fatigue_damage"
            meta["damage_category"] = "accelerated_runin"

    if "HEALTHY" in upper_name or "NORMAL" in upper_name:
        meta["damage_type"] = "healthy"
        meta["damage_category"] = "undamaged"
    elif "OUTER" in upper_name:
        meta["damage_type"] = "outer_race"
        meta["damage_category"] = "artificial_outer"
    elif "INNER" in upper_name:
        meta["damage_type"] = "inner_race"
        meta["damage_category"] = "artificial_inner"

    return meta


def process_paderborn_experiment(
    file_path: Union[str, Path],
    bearing_id: Optional[str] = None,
    damage_type: Optional[str] = None,
    operating_condition: Optional[str] = None,
    sampling_rate: float = SAMPLING_RATE_PADERBORN,
    window_size: int = 64000,
    step_size: int = 32000,
) -> pd.DataFrame:
    """Process a single Paderborn experiment file into a feature DataFrame."""
    path = Path(file_path)
    loaded = load_paderborn_mat(path)

    vibration = loaded["vibration"]
    current_1 = loaded["current_1"]
    current_2 = loaded["current_2"]
    file_meta = loaded.get("metadata", {})

    inferred = infer_paderborn_metadata_from_filename(path.name)

    b_id = bearing_id or file_meta.get("bearing_id") or inferred["bearing_id"]
    d_type = damage_type or file_meta.get("damage_type") or inferred["damage_type"]
    op_cond = operating_condition or file_meta.get("operating_condition") or "N15_M07_F10"

    windows = process_paderborn_signals(
        vibration=vibration,
        current_1=current_1,
        current_2=current_2,
        sampling_rate=sampling_rate,
        window_size=window_size,
        step_size=step_size,
    )

    rows = []
    for w in windows:
        row = {
            "experiment_id": inferred["experiment_id"],
            "bearing_id": str(b_id),
            "damage_type": str(d_type),
            "operating_condition": str(op_cond),
            **w,
        }
        rows.append(row)

    return pd.DataFrame(rows)


def process_paderborn_dataset(
    directory_path: Union[str, Path],
    test_bearings: Optional[List[str]] = None,
    test_size: float = 0.33,
    random_state: int = 42,
) -> pd.DataFrame:
    """Batch process a directory of Paderborn MAT files with leakage-free group splitting.

    Guarantees that all windows from the same bearing_id reside exclusively in
    either the train or test partition.
    """
    dir_path = Path(directory_path)
    if not dir_path.is_dir():
        raise FileNotFoundError(f"Paderborn dataset directory not found: {dir_path}")

    mat_files = sorted(dir_path.glob("*.mat"))
    if not mat_files:
        raise ValueError(f"No .mat files found in {dir_path}.")

    dfs = [process_paderborn_experiment(f) for f in mat_files]
    full_df = pd.concat(dfs, ignore_index=True)

    # Perform leakage-free splitting by bearing_id if multiple bearings present
    unique_bearings = full_df["bearing_id"].unique().tolist()
    if len(unique_bearings) >= 2:
        train_df, test_df = split_experiments_by_bearing(
            full_df,
            group_col="bearing_id",
            test_groups=test_bearings,
            test_size=test_size,
            random_state=random_state,
        )
        return pd.concat([train_df, test_df], ignore_index=True)
    else:
        full_df["split"] = "train"
        return full_df


def generate_synthetic_paderborn_experiment(
    output_dir: Union[str, Path],
    filename: str,
    bearing_id: str,
    damage_type: str = "healthy",
    duration_sec: float = 2.0,
    sampling_rate: float = SAMPLING_RATE_PADERBORN,
    seed: int = 42,
) -> Path:
    """Generate realistic synthetic 64 kHz vibration and 2-phase motor currents in MAT format.

    Simulates:
    - 64 kHz radial vibration with 25 Hz rotational fundamental + harmonic resonances.
    - Bearing fault impacts (BPFO at 85 Hz, BPFI at 135 Hz) depending on damage_type.
    - 64 kHz 2-phase motor currents (50 Hz fundamental + 150 Hz harmonic + fault sidebands).
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    file_path = out_path / filename

    rng = np.random.default_rng(seed)
    n_samples = int(duration_sec * sampling_rate)
    t = np.arange(n_samples) / sampling_rate

    # 1. Synthesize 64 kHz Vibration Signal
    # Motor rotation carrier (25 Hz = 1500 RPM)
    rotation_carrier = 0.05 * np.sin(2 * np.pi * 25.0 * t) + 0.02 * np.sin(2 * np.pi * 50.0 * t)
    # Background mechanical vibration noise
    vib_noise = rng.normal(0, 0.03, size=n_samples)
    vibration = rotation_carrier + vib_noise

    if damage_type == "outer_race":
        # BPFO = ~85 Hz impact train
        bpfo = 85.0
        impact_train = np.zeros(n_samples)
        pulse_indices = np.arange(0, n_samples, int(sampling_rate / bpfo))
        for p_idx in pulse_indices:
            decay_len = min(400, n_samples - p_idx)
            decay_env = np.exp(-np.linspace(0, 5, decay_len))
            resonance = np.sin(2 * np.pi * 3200 * t[:decay_len])
            impact_train[p_idx : p_idx + decay_len] += 0.25 * decay_env * resonance
        vibration += impact_train

    elif damage_type == "inner_race":
        # BPFI = ~135 Hz impact train amplitude modulated by 25 Hz rotation
        bpfi = 135.0
        impact_train = np.zeros(n_samples)
        pulse_indices = np.arange(0, n_samples, int(sampling_rate / bpfi))
        for p_idx in pulse_indices:
            decay_len = min(400, n_samples - p_idx)
            decay_env = np.exp(-np.linspace(0, 5, decay_len))
            resonance = np.sin(2 * np.pi * 4500 * t[:decay_len])
            mod = 1.0 + 0.8 * np.sin(2 * np.pi * 25.0 * t[p_idx])
            impact_train[p_idx : p_idx + decay_len] += 0.3 * mod * decay_env * resonance
        vibration += impact_train

    elif damage_type == "fatigue_damage":
        # Run-in fatigue wear: broadband elevated vibration + irregular impact shocks
        wear_noise = rng.normal(0, 0.15, size=n_samples)
        vibration += wear_noise

    # 2. Synthesize 64 kHz 2-Phase Motor Currents (50 Hz fundamental + 3rd harmonic)
    current_amp = 3.5  # Amperes
    phase_offset = 2.0 * np.pi / 3.0  # 120 degrees electrical phase shift

    # Phase 1
    current_1 = (
        current_amp * np.sin(2 * np.pi * 50.0 * t)
        + 0.15 * np.sin(2 * np.pi * 150.0 * t)
        + rng.normal(0, 0.02, size=n_samples)
    )
    # Phase 2
    current_2 = (
        current_amp * np.sin(2 * np.pi * 50.0 * t - phase_offset)
        + 0.15 * np.sin(2 * np.pi * 150.0 * t - phase_offset)
        + rng.normal(0, 0.02, size=n_samples)
    )

    # In damaged condition, add characteristic load modulation sidebands
    if damage_type != "healthy":
        sideband_mod = 0.08 * np.sin(2 * np.pi * 25.0 * t)
        current_1 += sideband_mod * current_amp * np.sin(2 * np.pi * 50.0 * t)
        current_2 += sideband_mod * current_amp * np.sin(2 * np.pi * 50.0 * t - phase_offset)

    mat_payload = {
        "vibration": vibration,
        "current_1": current_1,
        "current_2": current_2,
        "bearing_id": bearing_id,
        "damage_type": damage_type,
        "sampling_rate": sampling_rate,
    }

    sio.savemat(file_path, mat_payload)
    return file_path
