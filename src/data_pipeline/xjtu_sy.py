"""XJTU-SY Bearing Run-to-Failure dataset loader and preprocessing pipeline.

Supports:
- XJTU-SY accelerated life test vibration data (CSV format, 2-axis: Horizontal & Vertical).
- Sampling rate: 25.6 kHz (32,768 samples per 1.28s snapshot recorded every 1 minute).
- 1-second window framing (25,600 samples @ 25.6 kHz) with 50% overlap.
- Dual-axis feature extraction (Horizontal & Vertical vibration).
- Linear and Piecewise-linear Remaining Useful Life (RUL) in operating hours and minutes.
- Composite Health Index [1.0 -> 0.0] adhering to Member 3 telemetry contracts.
- Leakage-proof experiment-boundary protection: strictly isolates individual bearing life runs.
- Synthetic fixture generation for offline pipeline verification when raw data is not present.
"""

from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd

from .features import extract_vibration_features, FEATURE_COLUMNS
from .rul_targets import compute_linear_rul, compute_piecewise_rul, compute_health_index


SAMPLING_RATE_XJTU = 25600.0  # 25.6 kHz
SNAPSHOT_INTERVAL_MINUTES = 1.0  # 1 snapshot recorded every 1 minute


def load_xjtu_snapshot_file(file_path: Union[str, Path]) -> Tuple[np.ndarray, np.ndarray]:
    """Load a single XJTU-SY CSV snapshot containing Horizontal and Vertical vibration.

    Returns:
        Tuple of (horizontal_signal, vertical_signal) 1D numpy arrays.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"XJTU-SY snapshot file not found: {path}")

    # Read CSV, handling files with or without header
    try:
        # Check header
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            first_line = f.readline().strip()

        has_header = any(c.isalpha() for c in first_line)
        skiprows = 1 if has_header else 0

        df = pd.read_csv(path, skiprows=skiprows, header=None)
    except Exception as exc:
        raise ValueError(f"Failed to parse XJTU-SY CSV file {path}: {exc}") from exc

    if df.shape[1] < 2:
        raise ValueError(
            f"Expected at least 2 channels (Horizontal, Vertical) in {path}, found {df.shape[1]}."
        )

    horiz = df.iloc[:, 0].to_numpy(dtype=float)
    vert = df.iloc[:, 1].to_numpy(dtype=float)
    return horiz, vert


def process_xjtu_snapshot(
    horiz_signal: np.ndarray,
    vert_signal: np.ndarray,
    sampling_rate: float = SAMPLING_RATE_XJTU,
    window_size: int = 25600,  # 1 second @ 25.6 kHz
) -> List[Dict[str, float]]:
    """Slice 2-axis snapshot into 1-second windows and extract features."""
    n_samples = min(len(horiz_signal), len(vert_signal))

    if n_samples < window_size:
        h_feats = extract_vibration_features(horiz_signal, sampling_rate=sampling_rate)
        v_feats = extract_vibration_features(vert_signal, sampling_rate=sampling_rate)
        combined = {f"horiz_{k}": v for k, v in h_feats.items()}
        combined.update({f"vert_{k}": v for k, v in v_feats.items()})
        # Map primary horizontal features to canonical names for model compatibility
        combined.update({k: h_feats[k] for k in FEATURE_COLUMNS})
        return [{"window_id": 0, **combined}]

    step_size = window_size // 2 if n_samples >= window_size + (window_size // 2) else window_size
    windows_features = []

    for w_idx, start in enumerate(range(0, n_samples - window_size + 1, step_size)):
        h_win = horiz_signal[start : start + window_size]
        v_win = vert_signal[start : start + window_size]

        h_feats = extract_vibration_features(h_win, sampling_rate=sampling_rate)
        v_feats = extract_vibration_features(v_win, sampling_rate=sampling_rate)

        combined = {"window_id": w_idx}
        # Add channel-specific features
        for k, v in h_feats.items():
            combined[f"horiz_{k}"] = v
        for k, v in v_feats.items():
            combined[f"vert_{k}"] = v
        # Canonical feature aliases for standard 12-feature ML ingestion
        for k in FEATURE_COLUMNS:
            combined[k] = h_feats[k]

        windows_features.append(combined)

    return windows_features


def process_xjtu_bearing_experiment(
    bearing_dir: Union[str, Path],
    bearing_id: Optional[str] = None,
    operating_condition: str = "Condition_1",
    max_rul_hours: Optional[float] = 2.0,
    healthy_fraction: float = 0.60,
    max_snapshots: Optional[int] = None,
) -> pd.DataFrame:
    """Process all snapshot files for an individual XJTU-SY bearing run-to-failure run.

    Args:
        bearing_dir: Directory containing sequential snapshot CSVs (1.csv, 2.csv, ...).
        bearing_id: Unique bearing identifier (e.g. 'Bearing1_1'). If None, inferred from folder name.
        operating_condition: Operating condition tag.
        max_rul_hours: Capped maximum RUL for piecewise linear target (in hours).
        healthy_fraction: Proportion of experiment duration considered healthy.
        max_snapshots: Optional limit on snapshots to process.

    Returns:
        DataFrame containing window features, timeline (minutes and hours),
        linear RUL, piecewise RUL, and continuous Health Index.
    """
    path = Path(bearing_dir)
    if not path.is_dir():
        raise FileNotFoundError(f"XJTU-SY bearing directory not found: {path}")

    b_id = bearing_id or path.name

    # Discover and sort snapshot CSVs numerically by index
    csv_files = []
    for f in path.glob("*.csv"):
        m = re.search(r"(\d+)", f.stem)
        if m:
            csv_files.append((int(m.group(1)), f))

    if len(csv_files) == 0:
        raise ValueError(f"No numeric CSV snapshot files found in {path}")

    csv_files.sort(key=lambda x: x[0])

    if max_snapshots is not None and max_snapshots > 0:
        csv_files = csv_files[:max_snapshots]

    n_snapshots = len(csv_files)
    # Timeline in operating minutes (1 snapshot every 1 minute)
    timeline_minutes = [float(idx - 1) * SNAPSHOT_INTERVAL_MINUTES for idx, _ in csv_files]
    timeline_hours = [m / 60.0 for m in timeline_minutes]

    # Calculate RUL targets strictly for this individual bearing's timeline
    linear_rul_hours = compute_linear_rul(timeline_hours)
    linear_rul_minutes = compute_linear_rul(timeline_minutes)
    piecewise_rul_hours = compute_piecewise_rul(
        timeline_hours, max_rul=max_rul_hours, healthy_fraction=healthy_fraction
    )
    health_index_series = compute_health_index(timeline_hours)

    rows = []
    for s_pos, (snap_idx, file_path) in enumerate(csv_files):
        horiz, vert = load_xjtu_snapshot_file(file_path)
        windows = process_xjtu_snapshot(horiz, vert)

        el_min = timeline_minutes[s_pos]
        el_hr = timeline_hours[s_pos]
        lin_hr = linear_rul_hours[s_pos]
        lin_min = linear_rul_minutes[s_pos]
        pw_hr = piecewise_rul_hours[s_pos]
        hi = health_index_series[s_pos]

        for w_dict in windows:
            row = {
                "experiment_id": "XJTU_SY",
                "operating_condition": operating_condition,
                "bearing_id": b_id,
                "snapshot_id": snap_idx,
                "elapsed_minutes": round(el_min, 2),
                "elapsed_hours": round(el_hr, 4),
                **w_dict,
                "health_index": round(float(hi), 4),
                "rul_minutes_linear": round(float(lin_min), 2),
                "rul_hours_linear": round(float(lin_hr), 4),
                "rul_hours_piecewise": round(float(pw_hr), 4),
                # Canonical contract field matching Member 3 Telemetry schema
                "rul_hours": round(float(pw_hr), 4),
            }
            rows.append(row)

    df = pd.DataFrame(rows)
    return df


def generate_synthetic_xjtu_experiment(
    output_dir: Union[str, Path],
    n_snapshots: int = 15,
    samples_per_snapshot: int = 32768,
    seed: int = 42,
) -> Path:
    """Generate synthetic XJTU-SY CSV test snapshots simulating accelerated bearing fatigue.

    Used for automated unit testing and pipeline verification when the raw
    XJTU-SY dataset is not present in local storage.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    for i in range(1, n_snapshots + 1):
        file_path = out_path / f"{i}.csv"

        # Simulate accelerated degradation: amplitude increases markedly in last 30% of life
        wear = 1.0 + 0.1 * ((i / n_snapshots) ** 3) * 10.0 if i > n_snapshots * 0.7 else 1.0

        t = np.arange(samples_per_snapshot) / SAMPLING_RATE_XJTU
        horiz_base = rng.normal(0, 0.08, size=samples_per_snapshot)
        vert_base = rng.normal(0, 0.08, size=samples_per_snapshot)

        # Fault impact frequencies: 108 Hz ball pass frequency
        horiz_fault = 0.03 * wear * np.sin(2 * np.pi * 108 * t)
        vert_fault = 0.02 * wear * np.cos(2 * np.pi * 108 * t)

        horiz = (horiz_base + horiz_fault) * wear
        vert = (vert_base + vert_fault) * wear

        df = pd.DataFrame({
            "Horizontal_vibration": np.round(horiz, 6),
            "Vertical_vibration": np.round(vert, 6),
        })
        df.to_csv(file_path, index=False)

    return out_path
