"""Data and Signal Processing Pipeline for Edge IoT Predictive Maintenance.

Member 1 — Core Package.
Provides multi-dataset ingestion, feature extraction, windowing, and RUL target generation.
"""

from .features import (
    extract_vibration_features,
    calculate_time_features,
    calculate_frequency_features,
    FEATURE_COLUMNS,
    CORE_FEATURE_COLUMNS,
    EXTENDED_FEATURE_COLUMNS,
)
from .rul_targets import (
    compute_linear_rul,
    compute_piecewise_rul,
    compute_health_index,
)
from .nasa_ims import (
    process_ims_experiment,
    load_ims_snapshot_file,
    parse_ims_filename_timestamp,
    generate_synthetic_ims_experiment,
    resolve_ims_channel,
)
from .xjtu_sy import (
    process_xjtu_bearing_experiment,
    process_xjtu_dataset,
    load_xjtu_snapshot_file,
    generate_synthetic_xjtu_experiment,
)
from .splits import (
    split_experiments_by_bearing,
    verify_no_experiment_leakage,
)
from .paderborn import (
    SAMPLING_RATE_PADERBORN,
    load_paderborn_mat,
    extract_current_features,
    process_paderborn_signals,
    process_paderborn_experiment,
    process_paderborn_dataset,
    generate_synthetic_paderborn_experiment,
)
from .mimii import (
    SAMPLING_RATE_MIMII,
    hz_to_mel,
    mel_to_hz,
    compute_mel_filterbank,
    extract_audio_features,
    load_mimii_wav,
    parse_mimii_path_metadata,
    process_mimii_recording,
    split_mimii_by_machine,
    split_mimii_by_recording,
    process_mimii_subset,
    generate_synthetic_mimii_subset,
)

__all__ = [
    "extract_vibration_features",
    "calculate_time_features",
    "calculate_frequency_features",
    "FEATURE_COLUMNS",
    "CORE_FEATURE_COLUMNS",
    "EXTENDED_FEATURE_COLUMNS",
    "compute_linear_rul",
    "compute_piecewise_rul",
    "compute_health_index",
    "process_ims_experiment",
    "load_ims_snapshot_file",
    "parse_ims_filename_timestamp",
    "generate_synthetic_ims_experiment",
    "resolve_ims_channel",
    "process_xjtu_bearing_experiment",
    "process_xjtu_dataset",
    "load_xjtu_snapshot_file",
    "generate_synthetic_xjtu_experiment",
    "split_experiments_by_bearing",
    "verify_no_experiment_leakage",
    "SAMPLING_RATE_PADERBORN",
    "load_paderborn_mat",
    "extract_current_features",
    "process_paderborn_signals",
    "process_paderborn_experiment",
    "process_paderborn_dataset",
    "generate_synthetic_paderborn_experiment",
    "SAMPLING_RATE_MIMII",
    "hz_to_mel",
    "mel_to_hz",
    "compute_mel_filterbank",
    "extract_audio_features",
    "load_mimii_wav",
    "parse_mimii_path_metadata",
    "process_mimii_recording",
    "split_mimii_by_machine",
    "split_mimii_by_recording",
    "process_mimii_subset",
    "generate_synthetic_mimii_subset",
]
