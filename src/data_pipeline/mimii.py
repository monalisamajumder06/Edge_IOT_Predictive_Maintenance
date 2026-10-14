"""MIMII Industrial Machine Acoustic Anomaly Dataset loader and preprocessing pipeline.

Supports:
- Scoped acoustic anomaly detection pipeline (e.g. Industrial Pumps / Fans).
- Native 16 kHz 16-bit PCM WAV audio ingestion.
- Multi-channel microphone array support (default channel 0 / Mic 0).
- True acoustic domain feature extraction:
    * Acoustic energy & dynamics: audio_rms, audio_peak, audio_crest_factor, zero_crossing_rate.
    * Timbral & spectral profile: spectral_centroid_hz, spectral_bandwidth_hz,
      spectral_flatness (Wiener entropy), spectral_rolloff_hz.
    * Log-Mel Filterbank energies (16 bands, 50 Hz to 8000 Hz) using pure NumPy/SciPy.
- Metadata preservation: machine_type, machine_id, snr_condition, condition (normal/anomaly), anomaly_label (0/1).
- Leakage-proof splitting:
    * Machine-instance grouping (train on id_00, evaluate generalization on id_02).
    * Recording-level grouping (train on normal recordings, test on held-out normal & anomaly).
- Synthetic fixture generation for offline pipeline verification when raw multi-GB audio archives are absent.
"""

from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
import scipy.io.wavfile as wavfile
from sklearn.model_selection import GroupShuffleSplit

from .splits import verify_no_experiment_leakage


SAMPLING_RATE_MIMII = 16000.0  # 16 kHz


def hz_to_mel(hz: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
    """Convert frequency from Hertz to Mel scale."""
    return 2595.0 * np.log10(1.0 + hz / 700.0)


def mel_to_hz(mel: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
    """Convert frequency from Mel scale to Hertz."""
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)


def compute_mel_filterbank(
    sr: float = SAMPLING_RATE_MIMII,
    n_fft: int = 1024,
    n_mels: int = 16,
    f_min: float = 50.0,
    f_max: float = 8000.0,
) -> np.ndarray:
    """Construct a triangular Mel filterbank matrix in pure NumPy.

    Args:
        sr: Sampling rate in Hz.
        n_fft: FFT window length.
        n_mels: Number of Mel filter bands.
        f_min: Lowest frequency in Hz.
        f_max: Highest frequency in Hz.

    Returns:
        Array of shape (n_mels, n_fft // 2 + 1) containing filterbank weights.
    """
    f_nyquist = sr / 2.0
    f_max = min(f_max, f_nyquist)

    mel_min = hz_to_mel(f_min)
    mel_max = hz_to_mel(f_max)
    mel_points = np.linspace(mel_min, mel_max, n_mels + 2)
    hz_points = mel_to_hz(mel_points)

    # Convert Hz points to FFT bin numbers
    n_bins = n_fft // 2 + 1
    fft_freqs = np.linspace(0.0, f_nyquist, n_bins)
    bin_indices = np.floor((n_fft + 1) * hz_points / sr).astype(int)
    bin_indices = np.clip(bin_indices, 0, n_bins - 1)

    fbank = np.zeros((n_mels, n_bins), dtype=float)
    for m in range(1, n_mels + 1):
        f_m_minus = bin_indices[m - 1]
        f_m = bin_indices[m]
        f_m_plus = bin_indices[m + 1]

        # Left triangular slope
        if f_m > f_m_minus:
            fbank[m - 1, f_m_minus:f_m] = (
                np.arange(f_m_minus, f_m) - f_m_minus
            ) / (f_m - f_m_minus)
        # Right triangular slope
        if f_m_plus > f_m:
            fbank[m - 1, f_m:f_m_plus] = (
                f_m_plus - np.arange(f_m, f_m_plus)
            ) / (f_m_plus - f_m)

    return fbank


def extract_audio_features(
    signal: np.ndarray,
    sampling_rate: float = SAMPLING_RATE_MIMII,
    n_fft: int = 1024,
    hop_length: int = 512,
    n_mels: int = 16,
) -> Dict[str, float]:
    """Extract acoustic features including time-domain stats, spectral shapes, and log-Mel energies.

    Args:
        signal: 1D normalized float array [-1.0, 1.0].
        sampling_rate: Sampling frequency (default 16 kHz).
        n_fft: Frame length for STFT analysis.
        hop_length: Hop length between frames.
        n_mels: Number of log-Mel filterbank bands.

    Returns:
        Dictionary of acoustic features.
    """
    if len(signal) == 0:
        raise ValueError("Cannot extract acoustic features from empty audio signal.")

    # Guard against NaN/inf
    if np.isnan(signal).any() or np.isinf(signal).any():
        signal = np.nan_to_num(signal, nan=0.0, posinf=0.0, neginf=0.0)

    # 1. Time-Domain Acoustic Features
    rms = float(np.sqrt(np.mean(signal ** 2)))
    peak = float(np.max(np.abs(signal)))
    crest_factor = (peak / rms) if rms > 1e-12 else 0.0

    # Zero crossing rate (normalized by sample count)
    zcr = float(np.mean(np.abs(np.diff(np.signbit(signal)))))

    # 2. Window-Level Spectral Analysis
    fft_vals = np.fft.rfft(signal)
    freqs = np.fft.rfftfreq(len(signal), d=1.0 / sampling_rate)
    mag_spec = np.abs(fft_vals)
    power_spec = mag_spec ** 2
    if len(power_spec) > 0:
        power_spec[0] = 0.0  # Suppress DC

    tot_power = float(np.sum(power_spec))

    # Spectral Centroid & Bandwidth
    if tot_power > 1e-12:
        centroid = float(np.sum(freqs * power_spec) / tot_power)
        bandwidth = float(np.sqrt(np.sum(((freqs - centroid) ** 2) * power_spec) / tot_power))
    else:
        centroid = 0.0
        bandwidth = 0.0

    # Spectral Flatness (Wiener entropy = geometric_mean / arithmetic_mean)
    # Evaluated across all non-DC spectral bins with numerical floor epsilon
    eps = 1e-12
    non_dc_power = power_spec[1:] if len(power_spec) > 1 else power_spec
    if len(non_dc_power) > 0 and tot_power > 1e-12:
        log_mean = float(np.mean(np.log(non_dc_power + eps)))
        geom_mean = float(np.exp(log_mean))
        arith_mean = float(np.mean(non_dc_power))
        spectral_flatness = float(geom_mean / (arith_mean + eps))
        spectral_flatness = min(1.0, max(0.0, spectral_flatness))
    else:
        spectral_flatness = 0.0

    # Spectral Rolloff (Frequency below which 85% of power is concentrated)
    if tot_power > 1e-12:
        cum_power = np.cumsum(power_spec)
        rolloff_idx = int(np.searchsorted(cum_power, 0.85 * tot_power))
        rolloff_idx = min(rolloff_idx, len(freqs) - 1)
        spectral_rolloff = float(freqs[rolloff_idx])
    else:
        spectral_rolloff = 0.0

    features: Dict[str, float] = {
        "audio_rms": rms,
        "audio_peak": peak,
        "audio_crest_factor": crest_factor,
        "zero_crossing_rate": zcr,
        "spectral_centroid_hz": centroid,
        "spectral_bandwidth_hz": bandwidth,
        "spectral_flatness": spectral_flatness,
        "spectral_rolloff_hz": spectral_rolloff,
    }

    # 3. Log-Mel Filterbank Energies
    # Slice signal into STFT frames using Hann window
    fbank = compute_mel_filterbank(sr=sampling_rate, n_fft=n_fft, n_mels=n_mels)
    hann = np.hanning(n_fft)

    frame_powers = []
    if len(signal) >= n_fft:
        for f_start in range(0, len(signal) - n_fft + 1, hop_length):
            frame = signal[f_start : f_start + n_fft] * hann
            f_mag = np.abs(np.fft.rfft(frame)) ** 2
            frame_powers.append(f_mag)
        mean_frame_power = np.mean(frame_powers, axis=0)
    else:
        # Pad short signal
        padded = np.pad(signal, (0, n_fft - len(signal)), mode="constant") * hann
        mean_frame_power = np.abs(np.fft.rfft(padded)) ** 2

    mel_energies = np.dot(fbank, mean_frame_power)
    log_mel = np.log(mel_energies + 1e-12)

    for m_idx in range(n_mels):
        features[f"mel_band_{m_idx:02d}"] = float(log_mel[m_idx])

    return features


def load_mimii_wav(
    file_path: Union[str, Path],
    channel: int = 0,
) -> np.ndarray:
    """Load a 16 kHz 16-bit PCM WAV file and return a normalized float32 1D array.

    Args:
        file_path: Path to the WAV file.
        channel: Microphone channel to select (0-indexed, default 0).

    Returns:
        1D numpy array with audio normalized to [-1.0, 1.0].
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"MIMII audio file not found: {path}")

    try:
        sr, audio_data = wavfile.read(path)
    except Exception as exc:
        raise ValueError(f"Failed to read WAV file {path}: {exc}") from exc

    if sr != int(SAMPLING_RATE_MIMII):
        raise ValueError(
            f"Expected {int(SAMPLING_RATE_MIMII)} Hz sampling rate for MIMII audio, "
            f"got {sr} Hz in {path}."
        )

    # Normalize int16 or int32 to [-1.0, 1.0]
    if audio_data.dtype == np.int16:
        float_data = audio_data.astype(np.float32) / 32768.0
    elif audio_data.dtype == np.int32:
        float_data = audio_data.astype(np.float32) / 2147483648.0
    elif np.issubdtype(audio_data.dtype, np.floating):
        float_data = audio_data.astype(np.float32)
    else:
        float_data = audio_data.astype(np.float32)

    if float_data.ndim > 1:
        # Multi-channel WAV (e.g. 8-channel microphone array)
        if channel >= float_data.shape[1]:
            raise ValueError(
                f"Requested channel {channel}, but audio has only {float_data.shape[1]} channels."
            )
        return float_data[:, channel]

    return float_data


def parse_mimii_path_metadata(file_path: Union[str, Path]) -> Dict[str, Any]:
    """Parse machine type, machine ID, SNR, condition, and recording ID from path."""
    path = Path(file_path).resolve()
    parts = path.parts
    filename = path.stem

    # Default metadata
    meta: Dict[str, Any] = {
        "machine_type": "pump",
        "machine_id": "id_00",
        "snr_condition": "0_dB",
        "condition": "normal",
        "anomaly_label": 0,
        "recording_id": filename,
    }

    for part in parts:
        p_lower = part.lower()
        if p_lower in ("pump", "fan", "valve", "slider"):
            meta["machine_type"] = p_lower
        elif re.match(r"^id_\d{2}$", p_lower):
            meta["machine_id"] = p_lower
        elif re.match(r"^-?\d+(_)?db$", p_lower):
            meta["snr_condition"] = p_lower
        elif p_lower in ("normal", "healthy"):
            meta["condition"] = "normal"
            meta["anomaly_label"] = 0
        elif p_lower in ("anomaly", "abnormal", "fault"):
            meta["condition"] = "anomaly"
            meta["anomaly_label"] = 1

    # Form globally unique recording_id to avoid collision across conditions/machines
    meta["recording_id"] = f"{meta['machine_id']}_{meta['condition']}_{filename}"

    return meta


def process_mimii_recording(
    file_path: Union[str, Path],
    channel: int = 0,
    window_sec: float = 1.0,
    step_sec: float = 1.0,
    sampling_rate: float = SAMPLING_RATE_MIMII,
) -> List[Dict[str, Any]]:
    """Process a single MIMII WAV recording into windowed acoustic feature records."""
    audio = load_mimii_wav(file_path, channel=channel)
    meta = parse_mimii_path_metadata(file_path)

    window_size = int(window_sec * sampling_rate)
    step_size = int(step_sec * sampling_rate)

    n_samples = len(audio)
    if n_samples == 0:
        raise ValueError(f"Empty audio signal in {file_path}")

    # Fallback if audio shorter than window
    if n_samples < window_size:
        feats = extract_audio_features(audio, sampling_rate=sampling_rate)
        record = {
            **meta,
            "window_id": 0,
            "timestamp_sec": 0.0,
            "channel_id": channel,
            **feats,
        }
        return [record]

    records = []
    for w_idx, start in enumerate(range(0, n_samples - window_size + 1, step_size)):
        chunk = audio[start : start + window_size]
        feats = extract_audio_features(chunk, sampling_rate=sampling_rate)
        record = {
            **meta,
            "window_id": w_idx,
            "timestamp_sec": round(start / sampling_rate, 4),
            "channel_id": channel,
            **feats,
        }
        records.append(record)

    return records


def split_mimii_by_machine(
    df: pd.DataFrame,
    test_machines: Optional[List[str]] = None,
    test_size: float = 0.5,
    random_state: int = 42,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Split MIMII dataset strictly by machine_id to evaluate domain generalization."""
    if "machine_id" not in df.columns:
        raise KeyError("Column 'machine_id' not found in DataFrame.")

    unique_machines = df["machine_id"].unique().tolist()
    if len(unique_machines) < 2:
        raise ValueError(
            f"Cannot split by machine_id with fewer than 2 distinct machines. Found: {unique_machines}"
        )

    if test_machines is not None:
        test_set = set(test_machines)
        train_df = df[~df["machine_id"].isin(test_set)].copy()
        test_df = df[df["machine_id"].isin(test_set)].copy()
    else:
        gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=random_state)
        train_idx, test_idx = next(gss.split(df, groups=df["machine_id"]))
        train_df = df.iloc[train_idx].copy()
        test_df = df.iloc[test_idx].copy()

    verify_no_experiment_leakage(train_df, test_df, group_col="machine_id")

    train_df["split"] = "train"
    test_df["split"] = "test"
    return train_df, test_df


def split_mimii_by_recording(
    df: pd.DataFrame,
    test_size: float = 0.3,
    random_state: int = 42,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Partition MIMII recordings for unsupervised anomaly detection without window leakage.

    In unsupervised acoustic anomaly detection:
    - Train set: Contains ONLY normal recordings (e.g. 70% of normal recordings).
    - Test set: Contains held-out normal recordings (30%) + ALL anomalous recordings.
    - Zero window leakage: All windows from any recording_id belong strictly to either train or test.
    """
    if "recording_id" not in df.columns:
        raise KeyError("Column 'recording_id' not found in DataFrame.")
    if "anomaly_label" not in df.columns:
        raise KeyError("Column 'anomaly_label' not found in DataFrame.")

    normal_df = df[df["anomaly_label"] == 0].copy()
    anomaly_df = df[df["anomaly_label"] == 1].copy()

    normal_recordings = normal_df["recording_id"].unique().tolist()
    if len(normal_recordings) < 2:
        raise ValueError("At least 2 normal recordings required for recording-level split.")

    gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=random_state)
    train_idx, test_idx = next(gss.split(normal_df, groups=normal_df["recording_id"]))

    train_normal = normal_df.iloc[train_idx].copy()
    test_normal = normal_df.iloc[test_idx].copy()

    train_df = train_normal
    test_df = pd.concat([test_normal, anomaly_df], ignore_index=True)

    # Verification: train and test share zero recording_ids
    verify_no_experiment_leakage(train_df, test_df, group_col="recording_id")

    train_df["split"] = "train"
    test_df["split"] = "test"
    return train_df, test_df


def process_mimii_subset(
    root_dir: Union[str, Path],
    split_strategy: str = "recording",  # 'recording' or 'machine'
    test_size: float = 0.33,
    random_state: int = 42,
) -> pd.DataFrame:
    """Batch process a MIMII directory tree and apply leakage-free splitting."""
    path = Path(root_dir)
    if not path.is_dir():
        raise FileNotFoundError(f"MIMII directory not found: {path}")

    wav_files = sorted(path.rglob("*.wav"))
    if not wav_files:
        raise ValueError(f"No .wav files found under {path}")

    all_records = []
    for wf in wav_files:
        records = process_mimii_recording(wf)
        all_records.extend(records)

    full_df = pd.DataFrame(all_records)

    if split_strategy == "machine":
        unique_machines = full_df["machine_id"].unique().tolist()
        if len(unique_machines) >= 2:
            train_df, test_df = split_mimii_by_machine(
                full_df, test_size=test_size, random_state=random_state
            )
            return pd.concat([train_df, test_df], ignore_index=True)
    elif split_strategy == "recording":
        normal_recs = full_df[full_df["anomaly_label"] == 0]["recording_id"].unique()
        if len(normal_recs) >= 2:
            train_df, test_df = split_mimii_by_recording(
                full_df, test_size=test_size, random_state=random_state
            )
            return pd.concat([train_df, test_df], ignore_index=True)

    full_df["split"] = "train"
    return full_df


def generate_synthetic_mimii_subset(
    output_dir: Union[str, Path],
    machine_type: str = "pump",
    machine_ids: Tuple[str, ...] = ("id_00", "id_02"),
    snr: str = "0_dB",
    n_normal_per_machine: int = 3,
    n_anomaly_per_machine: int = 2,
    duration_sec: float = 3.0,
    seed: int = 42,
) -> Path:
    """Generate realistic synthetic 16 kHz 16-bit PCM WAV audio files in standard MIMII layout.

    Layout:
        <output_dir>/<machine_type>/<machine_id>/<snr>/normal/*.wav
        <output_dir>/<machine_type>/<machine_id>/<snr>/anomaly/*.wav

    Synthesizes:
    - Normal pump: 60 Hz fundamental electrical hum + 120/180/240 Hz harmonics + pink fluid noise.
    - Anomaly pump: Cavitation bursts + high-frequency squeal (2.5 kHz to 4.5 kHz) + elevated flatness.
    """
    out_path = Path(output_dir)
    rng = np.random.default_rng(seed)

    n_samples = int(duration_sec * SAMPLING_RATE_MIMII)
    t = np.arange(n_samples) / SAMPLING_RATE_MIMII

    for m_id in machine_ids:
        # Base machine specific rotational frequency (e.g. 58-62 Hz)
        base_f = 60.0 + (int(m_id[-2:]) * 1.5)

        # Normal directory
        norm_dir = out_path / machine_type / m_id / snr / "normal"
        norm_dir.mkdir(parents=True, exist_ok=True)

        for n_idx in range(n_normal_per_machine):
            # Motor hum
            hum = (
                0.20 * np.sin(2 * np.pi * base_f * t)
                + 0.08 * np.sin(2 * np.pi * (2 * base_f) * t)
                + 0.04 * np.sin(2 * np.pi * (3 * base_f) * t)
            )
            # Ambient fluid flow noise
            flow_noise = rng.normal(0, 0.04, size=n_samples)
            normal_audio = hum + flow_noise

            # Normalize to 16-bit PCM range
            max_val = np.max(np.abs(normal_audio)) + 1e-6
            normal_audio = (normal_audio / max_val * 0.7)  # Headroom
            audio_int16 = (normal_audio * 32767.0).astype(np.int16)

            wav_path = norm_dir / f"{n_idx:08d}.wav"
            wavfile.write(wav_path, int(SAMPLING_RATE_MIMII), audio_int16)

        # Anomaly directory
        anom_dir = out_path / machine_type / m_id / snr / "anomaly"
        anom_dir.mkdir(parents=True, exist_ok=True)

        for a_idx in range(n_anomaly_per_machine):
            # Motor hum with cavitation bursts and squeal
            hum = (
                0.22 * np.sin(2 * np.pi * base_f * t)
                + 0.09 * np.sin(2 * np.pi * (2 * base_f) * t)
            )
            flow_noise = rng.normal(0, 0.08, size=n_samples)

            # High frequency metallic squeal (3200 Hz)
            squeal = 0.18 * np.sin(2 * np.pi * 3200.0 * t)

            # Intermittent cavitation shocks
            cavitation = np.zeros(n_samples)
            burst_times = np.arange(0, n_samples, int(SAMPLING_RATE_MIMII * 0.25))
            for b in burst_times:
                blen = min(200, n_samples - b)
                cavitation[b : b + blen] += rng.normal(0, 0.35, size=blen)

            anom_audio = hum + flow_noise + squeal + cavitation
            max_val = np.max(np.abs(anom_audio)) + 1e-6
            anom_audio = (anom_audio / max_val * 0.85)
            audio_int16 = (anom_audio * 32767.0).astype(np.int16)

            wav_path = anom_dir / f"{a_idx:08d}.wav"
            wavfile.write(wav_path, int(SAMPLING_RATE_MIMII), audio_int16)

    return out_path
