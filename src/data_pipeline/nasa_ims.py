"""NASA IMS Bearing Run-to-Failure dataset loader and preprocessing pipeline.

Supports:
- NASA IMS 20 kHz vibration data (ASCII whitespace/tab delimited files).
- Timestamp parsing from filename: YYYY.MM.DD.HH.MM.SS.
- Multi-bearing channel extraction:
    * 4-channel setups (Sets 2 & 3: 1 radial accelerometer per bearing).
    * 8-channel setups (Set 1: 2 orthogonal accelerometers [x and y] per bearing).
- 1-second window framing (20,000 samples @ 20 kHz).
- Vibration feature extraction (time & frequency domain).
- Linear and Piecewise-linear Remaining Useful Life (RUL) in operating hours.
- Composite Health Index [1.0 -> 0.0] adhering to Member 3 telemetry contracts.
- Robust file handling: empty, truncated, or malformed snapshot detection and skipping.
- Synthetic fixture generation for offline pipeline verification when raw data is not present.
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import warnings
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


def resolve_ims_channel(
    n_channels: int,
    target_bearing: int = 1,
    axis: Optional[str] = None,
    channel_idx: Optional[int] = None,
) -> Tuple[int, str]:
    """Resolve 0-indexed channel number and bearing identifier label.

    NASA IMS Layout Specifications:
    - 4-Channel Sets (Test 2 & Test 3):
        One radial accelerometer per bearing housing.
        Channel 0 -> Bearing 1
        Channel 1 -> Bearing 2
        Channel 2 -> Bearing 3
        Channel 3 -> Bearing 4
    - 8-Channel Set (Test 1):
        Two orthogonal accelerometers (x-axis / horizontal and y-axis / vertical) per bearing housing.
        Bearing 1: Ch 0 (x), Ch 1 (y)
        Bearing 2: Ch 2 (x), Ch 3 (y)
        Bearing 3: Ch 4 (x), Ch 5 (y)
        Bearing 4: Ch 6 (x), Ch 7 (y)
        (Formula: ch = (target_bearing - 1) * 2 + (0 if axis=='x' else 1))

    Args:
        n_channels: Channel count of snapshot matrix (must be 4 or 8).
        target_bearing: Bearing index (1 to 4).
        axis: Vibration axis for 8-channel Set 1 ('x' or 'y'). Defaults to 'x'.
        channel_idx: Optional explicit 0-indexed channel override.

    Returns:
        Tuple of (channel_index, bearing_id_str).
    """
    if channel_idx is not None:
        if not (0 <= channel_idx < n_channels):
            raise ValueError(
                f"Explicit channel_idx {channel_idx} is out of bounds for {n_channels}-channel dataset."
            )
        if n_channels == 8:
            b_num = channel_idx // 2 + 1
            ax_suffix = "x" if channel_idx % 2 == 0 else "y"
            return channel_idx, f"Bearing_{b_num}_{ax_suffix}"
        return channel_idx, f"Bearing_{channel_idx + 1}"

    if not (1 <= target_bearing <= 4):
        raise ValueError(f"target_bearing must be between 1 and 4, got {target_bearing}.")

    if n_channels == 4:
        ch = target_bearing - 1
        return ch, f"Bearing_{target_bearing}"

    elif n_channels == 8:
        ax = (axis or "x").lower().strip()
        if ax in ("x", "horiz", "horizontal", "1", "ch1"):
            offset = 0
            ax_suffix = "x"
        elif ax in ("y", "vert", "vertical", "2", "ch2"):
            offset = 1
            ax_suffix = "y"
        else:
            raise ValueError(
                f"Invalid axis '{axis}' for 8-channel NASA IMS Set 1. Must be 'x' or 'y'."
            )
        ch = (target_bearing - 1) * 2 + offset
        return ch, f"Bearing_{target_bearing}_{ax_suffix}"

    else:
        raise ValueError(f"Unsupported channel count {n_channels}. Expected 4 or 8.")


def load_ims_snapshot_file(
    file_path: Union[str, Path],
    min_samples: int = 100,
) -> np.ndarray:
    """Load a single NASA IMS ASCII snapshot file with performance optimization and validation.

    Args:
        file_path: Path to the snapshot file.
        min_samples: Minimum required sample count to guard against truncated files.

    Returns:
        2D numpy array of shape (N_samples, N_channels), typically (20480, 4) or (20480, 8).
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"NASA IMS snapshot file not found: {path}")

    # Guard against 0-byte empty files
    if path.stat().st_size == 0:
        raise ValueError(f"NASA IMS snapshot file is empty (0 bytes): {path}")

    try:
        # High-performance C-engine tabular parsing for whitespace-delimited floats
        df = pd.read_csv(path, sep=r"\s+", header=None, engine="c", dtype=np.float64)
        data = df.to_numpy()
    except (pd.errors.EmptyDataError, ValueError) as exc:
        # Fallback to np.loadtxt or re-raise
        try:
            data = np.loadtxt(path)
        except Exception as exc2:
            raise ValueError(f"Failed to parse NASA IMS file {path}: {exc2}") from exc2
    except Exception as exc:
        raise ValueError(f"Failed to parse NASA IMS file {path}: {exc}") from exc

    if data.ndim == 1:
        data = data.reshape(-1, 1)

    if data.shape[0] < min_samples:
        raise ValueError(
            f"NASA IMS snapshot file {path} is truncated: found {data.shape[0]} rows "
            f"(minimum expected: {min_samples})."
        )

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
    axis: Optional[str] = None,
    channel_idx: Optional[int] = None,
    experiment_id: str = "NASA_IMS_Set2",
    max_rul_hours: Optional[float] = 100.0,
    healthy_fraction: float = 0.60,
    max_snapshots: Optional[int] = None,
    min_samples_per_snapshot: int = 100,
    min_valid_snapshots: int = 2,
    max_skipped_fraction: float = 0.20,
) -> pd.DataFrame:
    """Process an entire NASA IMS run-to-failure experiment folder into an RUL feature dataset.

    Args:
        data_dir: Path to folder containing timestamped snapshot files.
        target_bearing: Bearing number (1, 2, 3, or 4).
        axis: Vibration axis for 8-channel Set 1 ('x' or 'y').
        channel_idx: Optional direct 0-indexed channel override.
        experiment_id: Identifier for experiment tracking.
        max_rul_hours: Capped maximum RUL for piecewise linear target (in operating hours).
        healthy_fraction: Proportion of experiment duration considered healthy.
        max_snapshots: Optional limit on snapshots to process (useful for tests/quick runs).
        min_samples_per_snapshot: Minimum rows required for a valid snapshot.
        min_valid_snapshots: Minimum valid snapshots needed to construct an RUL timeline.
        max_skipped_fraction: Maximum allowable ratio of corrupted files before raising error.

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

    # Process files sequentially to maintain minimal memory footprint
    valid_entries: List[Tuple[datetime, Path, List[Dict[str, float]]]] = []
    skipped_files: List[Tuple[str, str]] = []
    resolved_ch: Optional[int] = None
    bearing_label: Optional[str] = None

    for ts, file_path in files:
        try:
            snapshot_data = load_ims_snapshot_file(
                file_path, min_samples=min_samples_per_snapshot
            )
            # Resolve channel on first valid snapshot
            if resolved_ch is None:
                resolved_ch, bearing_label = resolve_ims_channel(
                    n_channels=snapshot_data.shape[1],
                    target_bearing=target_bearing,
                    axis=axis,
                    channel_idx=channel_idx,
                )

            if resolved_ch >= snapshot_data.shape[1]:
                raise ValueError(
                    f"Resolved channel {resolved_ch} exceeds available channels "
                    f"({snapshot_data.shape[1]}) in {file_path.name}."
                )

            window_feats = process_ims_snapshot(snapshot_data, channel_idx=resolved_ch)
            valid_entries.append((ts, file_path, window_feats))

        except Exception as exc:
            warnings.warn(f"Skipping invalid NASA IMS snapshot {file_path.name}: {exc}")
            skipped_files.append((file_path.name, str(exc)))

    # Validate that sufficient valid snapshots remain
    if len(valid_entries) < min_valid_snapshots:
        raise ValueError(
            f"Insufficient valid snapshots ({len(valid_entries)} valid out of {len(files)} total). "
            f"At least {min_valid_snapshots} are required to construct an RUL degradation timeline. "
            f"Skipped {len(skipped_files)} files: {skipped_files[:3]}..."
        )

    skipped_fraction = len(skipped_files) / len(files)
    if len(files) >= 5 and skipped_fraction > max_skipped_fraction:
        raise ValueError(
            f"Excessive invalid snapshots: skipped {len(skipped_files)} of {len(files)} files "
            f"({skipped_fraction:.1%} > allowable {max_skipped_fraction:.1%}). "
            f"Dataset may be severely corrupted or incorrectly formatted."
        )

    t0 = valid_entries[0][0]
    t_end = valid_entries[-1][0]

    timeline_hours = [(ts - t0).total_seconds() / 3600.0 for ts, _, _ in valid_entries]
    total_life_hours = (t_end - t0).total_seconds() / 3600.0

    # Derive RUL targets across valid chronological snapshots
    linear_rul_series = compute_linear_rul(timeline_hours)
    piecewise_rul_series = compute_piecewise_rul(
        timeline_hours, max_rul=max_rul_hours, healthy_fraction=healthy_fraction
    )
    health_index_series = compute_health_index(timeline_hours)

    rows = []
    for s_idx, (ts, file_path, window_feats) in enumerate(valid_entries):
        elapsed_hr = timeline_hours[s_idx]
        lin_rul = linear_rul_series[s_idx]
        pw_rul = piecewise_rul_series[s_idx]
        hi = health_index_series[s_idx]

        for wf in window_feats:
            row = {
                "experiment_id": experiment_id,
                "bearing_id": bearing_label,
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
    df.attrs["skipped_files"] = skipped_files
    df.attrs["skipped_count"] = len(skipped_files)
    df.attrs["total_files"] = len(files)
    df.attrs["valid_count"] = len(valid_entries)
    return df


def generate_synthetic_ims_experiment(
    output_dir: Union[str, Path],
    n_snapshots: int = 20,
    n_channels: int = 4,
    samples_per_snapshot: int = 20480,
    target_channel: int = 0,
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

        # Simulate wear on target_channel: baseline Gaussian noise with exponential growth at end
        wear_factor = 1.0 + 0.05 * (i ** 2) / (n_snapshots ** 2) if i > n_snapshots // 2 else 1.0

        channels_data = []
        for ch in range(n_channels):
            base_noise = rng.normal(0, 0.05, size=samples_per_snapshot)
            if ch == target_channel:
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
