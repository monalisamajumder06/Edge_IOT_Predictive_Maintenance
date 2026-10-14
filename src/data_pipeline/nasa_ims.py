"""NASA IMS Bearing Run-to-Failure dataset loader and preprocessing pipeline.

Supports:
- NASA IMS 20 kHz vibration data (ASCII whitespace/tab delimited files).
- Timestamp parsing from filename: YYYY.MM.DD.HH.MM.SS.
- Multi-bearing channel extraction (Set 1 with 8 channels, Sets 2 & 3 with 4 channels).
- 1-second window framing (20,000 samples @ 20 kHz).
- Vibration feature extraction (time & frequency domain).
- Linear and Piecewise-linear Remaining Useful Life (RUL) in operating hours.
- Composite Health Index [1.0 -> 0.0] adhering to Member 3 telemetry contracts.
- Synthetic fixture generation for offline pipeline verification when raw data is not present.
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd

from .features import extract_vibration_features, FEATURE_COLUMNS
from .rul_targets import compute_linear_rul, compute_piecewise_rul, compute_health_index


SAMPLING_RATE_IMS = 20000.0  # 20 kHz


def parse_ims_filename_timestamp(filename: str) -> datetime:
    """Parse timestamp from NASA IMS filename (format: YYYY.MM.DD.HH.MM.SS)."""
    clean_name = Path(filename).name
    try:
        return datetime.strptime(clean_name, "%Y.%m.%d.%H.%M.%S")
    except ValueError as exc:
        raise ValueError(
            f"Filename '{clean_name}' does not match expected NASA IMS timestamp "
            f"format 'YYYY.MM.DD.HH.MM.SS'."
        ) from exc


def load_ims_snapshot_file(file_path: Union[str, Path]) -> np.ndarray:
    """Load a single NASA IMS ASCII snapshot file.

    Returns:
        2D numpy array of shape (N_samples, N_channels), typically (20480, 4) or (20480, 8).
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"NASA IMS snapshot file not found: {path}")

    try:
        data = np.loadtxt(path)
    except Exception as exc:
        raise ValueError(f"Failed to parse NASA IMS file {path}: {exc}") from exc

    if data.ndim == 1:
        data = data.reshape(-1, 1)

    if data.shape[1] not in (4, 8):
        raise ValueError(
            f"Expected 4 or 8 channels in NASA IMS file {path}, but found {data.shape[1]} channels."
        )

    return data


def process_ims_snapshot(
    snapshot_data: np.ndarray,
    channel_idx: int,
    sampling_rate: float = SAMPLING_RATE_IMS,
    window_size: int = 20000,
) -> List[Dict[str, float]]:
    """Slice a snapshot channel into 1-second windows and extract vibration features."""
    signal = snapshot_data[:, channel_idx]
    n_samples = len(signal)

    if n_samples < window_size:
        # If recording is slightly shorter than window_size, use entire signal
        feature_dict = extract_vibration_features(signal, sampling_rate=sampling_rate)
        return [{"window_id": 0, **feature_dict}]

    # 1-second non-overlapping or 50% overlap windows within snapshot
    step_size = window_size // 2 if n_samples >= window_size + (window_size // 2) else window_size
    windows_features = []

    for w_idx, start in enumerate(range(0, n_samples - window_size + 1, step_size)):
        window = signal[start : start + window_size]
        features = extract_vibration_features(window, sampling_rate=sampling_rate)
        windows_features.append({"window_id": w_idx, **features})

    return windows_features


def process_ims_experiment(
    data_dir: Union[str, Path],
    target_bearing: int = 1,
    experiment_id: str = "NASA_IMS_Set2",
    max_rul_hours: Optional[float] = 100.0,
    healthy_fraction: float = 0.60,
    max_snapshots: Optional[int] = None,
) -> pd.DataFrame:
    """Process an entire NASA IMS run-to-failure experiment folder into an RUL feature dataset.

    Args:
        data_dir: Path to folder containing timestamped snapshot files.
        target_bearing: Bearing number (1, 2, 3, or 4).
        experiment_id: Identifier for experiment tracking.
        max_rul_hours: Capped maximum RUL for piecewise linear target (in operating hours).
        healthy_fraction: Proportion of experiment duration considered healthy.
        max_snapshots: Optional limit on snapshots to process (useful for tests/quick runs).

    Returns:
        DataFrame containing window features, timestamps, linear RUL (hours),
        piecewise RUL (hours), and continuous Health Index [1.0 -> 0.0].
    """
    path = Path(data_dir)
    if not path.is_dir():
        raise FileNotFoundError(f"NASA IMS experiment directory not found: {path}")

    # Discover and sort snapshot files strictly by timestamp
    files = []
    for f in path.iterdir():
        if f.is_file():
            try:
                ts = parse_ims_filename_timestamp(f.name)
                files.append((ts, f))
            except ValueError:
                continue

    if len(files) == 0:
        raise ValueError(
            f"No valid NASA IMS timestamp files (YYYY.MM.DD.HH.MM.SS) found in {path}"
        )

    files.sort(key=lambda x: x[0])

    if max_snapshots is not None and max_snapshots > 0:
        files = files[:max_snapshots]

    t0 = files[0][0]
    t_end = files[-1][0]

    # Calculate timeline in operating hours strictly for this bearing's run-to-failure
    timeline_hours = [(ts - t0).total_seconds() / 3600.0 for ts, _ in files]
    total_life_hours = (t_end - t0).total_seconds() / 3600.0

    # Derive RUL targets across snapshots
    linear_rul_series = compute_linear_rul(timeline_hours)
    piecewise_rul_series = compute_piecewise_rul(
        timeline_hours, max_rul=max_rul_hours, healthy_fraction=healthy_fraction
    )
    health_index_series = compute_health_index(timeline_hours)

    # Channel mapping (1-indexed bearing -> 0-indexed column)
    ch_idx = target_bearing - 1

    rows = []
    for s_idx, (ts, file_path) in enumerate(files):
        snapshot_data = load_ims_snapshot_file(file_path)
        if ch_idx >= snapshot_data.shape[1]:
            raise ValueError(
                f"Bearing {target_bearing} maps to channel {ch_idx}, but file has only "
                f"{snapshot_data.shape[1]} channels."
            )

        window_feats = process_ims_snapshot(snapshot_data, channel_idx=ch_idx)

        elapsed_hr = timeline_hours[s_idx]
        lin_rul = linear_rul_series[s_idx]
        pw_rul = piecewise_rul_series[s_idx]
        hi = health_index_series[s_idx]

        for wf in window_feats:
            row = {
                "experiment_id": experiment_id,
                "bearing_id": f"Bearing_{target_bearing}",
                "snapshot_id": s_idx,
                "timestamp": ts.isoformat(),
                "elapsed_hours": round(elapsed_hr, 4),
                **wf,
                "health_index": round(float(hi), 4),
                "rul_hours_linear": round(float(lin_rul), 4),
                "rul_hours_piecewise": round(float(pw_rul), 4),
                # Canonical contract field matching Member 3 Telemetry schema
                "rul_hours": round(float(pw_rul), 4),
            }
            rows.append(row)

    df = pd.DataFrame(rows)
    return df


def generate_synthetic_ims_experiment(
    output_dir: Union[str, Path],
    n_snapshots: int = 20,
    n_channels: int = 4,
    samples_per_snapshot: int = 20480,
    seed: int = 42,
) -> Path:
    """Generate synthetic NASA IMS test snapshots simulating progressive bearing wear.

    Used for automated unit testing and pipeline verification when the raw 10 GB
    NASA IMS archive is not downloaded locally.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    # Base start: 2003-10-22 12:00:00, snapshot every 10 minutes
    start_time = datetime(2003, 10, 22, 12, 0, 0)

    for i in range(n_snapshots):
        cur_time = datetime.fromtimestamp(start_time.timestamp() + i * 600)
        filename = cur_time.strftime("%Y.%m.%d.%H.%M.%S")
        file_path = out_path / filename

        # Simulate wear on channel 0 (Bearing 1): baseline Gaussian noise with exponential growth at end
        wear_factor = 1.0 + 0.05 * (i ** 2) / (n_snapshots ** 2) if i > n_snapshots // 2 else 1.0

        channels_data = []
        for ch in range(n_channels):
            base_noise = rng.normal(0, 0.05, size=samples_per_snapshot)
            if ch == 0:
                # Add bearing fault pulse harmonics that intensify over time
                pulse = 0.02 * wear_factor * np.sin(2 * np.pi * 120 * np.arange(samples_per_snapshot) / SAMPLING_RATE_IMS)
                sig = (base_noise + pulse) * wear_factor
            else:
                sig = base_noise
            channels_data.append(sig)

        data_matrix = np.column_stack(channels_data)
        # Format as ASCII whitespace delimited with 6 decimal places
        np.savetxt(file_path, data_matrix, fmt="%.6f", delimiter="\t")

    return out_path
