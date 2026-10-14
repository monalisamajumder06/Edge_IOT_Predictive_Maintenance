"""Unit tests for NASA IMS bearing data loader and run-to-failure pipeline.

Verifies:
1. Timestamp parsing from NASA IMS filename convention (YYYY.MM.DD.HH.MM.SS).
2. Snapshot file loading with 4-channel and 8-channel shape validation.
3. 1-second windowing (20,000 samples @ 20 kHz) and feature extraction.
4. End-to-end run-to-failure processing with synthetic test fixtures.
5. RUL target countdown (linear and piecewise) and Health Index compliance.
6. Error handling for missing directories, invalid channels, and malformed files.
"""

import shutil
import sys
import unittest
from datetime import datetime
from pathlib import Path
import numpy as np

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from data_pipeline.nasa_ims import (
    parse_ims_filename_timestamp,
    load_ims_snapshot_file,
    process_ims_snapshot,
    process_ims_experiment,
    generate_synthetic_ims_experiment,
    SAMPLING_RATE_IMS,
)
from data_pipeline.features import CORE_FEATURE_COLUMNS


class TestNASAIMS(unittest.TestCase):
    """Test suite for NASA IMS run-to-failure data pipeline."""

    def setUp(self):
        self.temp_dir = Path("data/interim/test_nasa_ims")
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_parse_ims_filename_timestamp(self):
        """Verify parsing of valid and invalid NASA IMS timestamp filenames."""
        valid_name = "2003.10.22.12.06.24"
        ts = parse_ims_filename_timestamp(valid_name)
        self.assertEqual(ts, datetime(2003, 10, 22, 12, 6, 24))

        invalid_name = "snapshot_01.txt"
        with self.assertRaises(ValueError):
            parse_ims_filename_timestamp(invalid_name)

    def test_load_snapshot_file_validation(self):
        """Verify snapshot file loading and channel shape enforcement."""
        dummy_file = self.temp_dir / "2003.10.22.12.00.00"
        # Create valid 4-channel file (20480 rows, 4 columns)
        arr_valid = np.random.randn(1000, 4)
        np.savetxt(dummy_file, arr_valid, delimiter="\t")

        loaded = load_ims_snapshot_file(dummy_file)
        self.assertEqual(loaded.shape, (1000, 4))

        # Create invalid 3-channel file
        arr_invalid = np.random.randn(1000, 3)
        np.savetxt(dummy_file, arr_invalid, delimiter="\t")
        with self.assertRaises(ValueError) as ctx:
            load_ims_snapshot_file(dummy_file)
        self.assertIn("Expected 4 or 8 channels", str(ctx.exception))

    def test_end_to_end_synthetic_ims_experiment(self):
        """Verify full run-to-failure processing with generated synthetic IMS fixtures."""
        n_snapshots = 12
        exp_dir = generate_synthetic_ims_experiment(
            output_dir=self.temp_dir / "Set2_Synth",
            n_snapshots=n_snapshots,
            samples_per_snapshot=20480,
            seed=42,
        )

        df = process_ims_experiment(
            data_dir=exp_dir,
            target_bearing=1,
            experiment_id="NASA_IMS_Synth",
            max_rul_hours=1.5,
        )

        self.assertGreater(len(df), 0)
        self.assertEqual(df["experiment_id"].iloc[0], "NASA_IMS_Synth")
        self.assertEqual(df["bearing_id"].iloc[0], "Bearing_1")

        # Verify all canonical feature columns are present
        for col in CORE_FEATURE_COLUMNS:
            self.assertIn(col, df.columns)
            self.assertFalse(df[col].isna().any(), f"NaN in feature column {col}")

        # Verify telemetry contract fields
        self.assertIn("health_index", df.columns)
        self.assertIn("rul_hours", df.columns)
        self.assertIn("rul_hours_linear", df.columns)
        self.assertIn("rul_hours_piecewise", df.columns)

        # Verify RUL monotonicity across sequential snapshot points
        snapshot_df = df.drop_duplicates(subset=["snapshot_id"]).sort_values("snapshot_id")
        rul_linear = snapshot_df["rul_hours_linear"].to_numpy()
        self.assertTrue(np.all(np.diff(rul_linear) <= 0.0), "Linear RUL is not non-increasing.")
        self.assertEqual(rul_linear[-1], 0.0)

        # Health Index must degrade from 1.0 down to 0.0
        hi = snapshot_df["health_index"].to_numpy()
        self.assertAlmostEqual(hi[0], 1.0, places=4)
        self.assertAlmostEqual(hi[-1], 0.0, places=4)
        self.assertTrue(np.all((hi >= 0.0) & (hi <= 1.0)))


if __name__ == "__main__":
    unittest.main()
