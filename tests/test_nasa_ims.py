"""Unit tests for NASA IMS bearing data loader and run-to-failure pipeline.

Verifies:
1. Timestamp parsing from NASA IMS filename convention (YYYY.MM.DD.HH.MM.SS).
2. Snapshot file loading with 4-channel and 8-channel shape validation.
3. 1-second windowing (20,000 samples @ 20 kHz) and feature extraction.
4. End-to-end run-to-failure processing with synthetic test fixtures.
5. 4-channel explicit bearing-to-channel mapping (Sets 2 & 3).
6. 8-channel Set 1 orthogonal dual-axis mapping (x and y channels per bearing).
7. Strict chronological ordering and elapsed-time calculations.
8. Robust skipping and reporting of empty, corrupt, and truncated snapshots.
9. Error enforcement for insufficient valid snapshots or excessive invalid fraction.
"""

from datetime import datetime
from pathlib import Path
import shutil
import sys
import unittest
import numpy as np

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from data_pipeline.nasa_ims import (
    parse_ims_filename_timestamp,
    resolve_ims_channel,
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
        # Create valid 4-channel file (1000 rows, 4 columns)
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

    def test_four_channel_explicit_bearing_mapping(self):
        """Verify explicit 4-channel mapping (Bearing 1->Ch 0, Bearing 4->Ch 3)."""
        self.assertEqual(resolve_ims_channel(4, target_bearing=1), (0, "Bearing_1"))
        self.assertEqual(resolve_ims_channel(4, target_bearing=2), (1, "Bearing_2"))
        self.assertEqual(resolve_ims_channel(4, target_bearing=3), (2, "Bearing_3"))
        self.assertEqual(resolve_ims_channel(4, target_bearing=4), (3, "Bearing_4"))

        # Channel override
        self.assertEqual(resolve_ims_channel(4, channel_idx=2), (2, "Bearing_3"))

        # Out of bounds bearing
        with self.assertRaises(ValueError):
            resolve_ims_channel(4, target_bearing=5)

    def test_eight_channel_set1_mapping(self):
        """Verify 8-channel Set 1 orthogonal dual-axis mapping (x and y per bearing)."""
        # Bearing 1: x -> Ch 0, y -> Ch 1
        self.assertEqual(resolve_ims_channel(8, target_bearing=1, axis="x"), (0, "Bearing_1_x"))
        self.assertEqual(resolve_ims_channel(8, target_bearing=1, axis="y"), (1, "Bearing_1_y"))

        # Bearing 2: x -> Ch 2, y -> Ch 3
        self.assertEqual(resolve_ims_channel(8, target_bearing=2, axis="x"), (2, "Bearing_2_x"))
        self.assertEqual(resolve_ims_channel(8, target_bearing=2, axis="y"), (3, "Bearing_2_y"))

        # Bearing 3 (inner race defect): x -> Ch 4, y -> Ch 5
        self.assertEqual(resolve_ims_channel(8, target_bearing=3, axis="x"), (4, "Bearing_3_x"))
        self.assertEqual(resolve_ims_channel(8, target_bearing=3, axis="y"), (5, "Bearing_3_y"))

        # Bearing 4 (roller defect): x -> Ch 6, y -> Ch 7
        self.assertEqual(resolve_ims_channel(8, target_bearing=4, axis="x"), (6, "Bearing_4_x"))
        self.assertEqual(resolve_ims_channel(8, target_bearing=4, axis="y"), (7, "Bearing_4_y"))

        # Direct channel_idx override
        self.assertEqual(resolve_ims_channel(8, channel_idx=5), (5, "Bearing_3_y"))

        # Invalid axis raises error
        with self.assertRaises(ValueError):
            resolve_ims_channel(8, target_bearing=2, axis="z")

    def test_end_to_end_eight_channel_set1_experiment(self):
        """Verify end-to-end processing of 8-channel Set 1 fixture."""
        exp_dir = generate_synthetic_ims_experiment(
            output_dir=self.temp_dir / "Set1_Synth",
            n_snapshots=8,
            n_channels=8,
            samples_per_snapshot=20480,
            target_channel=4,  # Bearing 3 x-axis
            seed=42,
        )

        df = process_ims_experiment(
            data_dir=exp_dir,
            target_bearing=3,
            axis="x",
            experiment_id="NASA_IMS_Set1_B3x",
        )

        self.assertGreater(len(df), 0)
        self.assertEqual(df["bearing_id"].iloc[0], "Bearing_3_x")
        self.assertEqual(df["experiment_id"].iloc[0], "NASA_IMS_Set1_B3x")
        self.assertIn("spectral_energy", df.columns)

    def test_chronological_ordering(self):
        """Verify that snapshot files out of order in filesystem are strictly sorted."""
        exp_dir = self.temp_dir / "Unordered_Exp"
        exp_dir.mkdir(parents=True, exist_ok=True)

        # Write files out of order: 14:00, 12:00, 13:00
        timestamps = ["2003.10.22.14.00.00", "2003.10.22.12.00.00", "2003.10.22.13.00.00"]
        for ts_str in timestamps:
            data = np.random.randn(1000, 4)
            np.savetxt(exp_dir / ts_str, data, delimiter="\t")

        df = process_ims_experiment(data_dir=exp_dir, target_bearing=1)

        unique_snapshots = df.drop_duplicates("snapshot_id")
        elapsed_list = unique_snapshots["elapsed_hours"].tolist()
        # Expect strictly increasing: 0.0, 1.0, 2.0
        self.assertEqual(elapsed_list, [0.0, 1.0, 2.0])
        self.assertEqual(
            unique_snapshots["timestamp"].tolist(),
            ["2003-10-22T12:00:00", "2003-10-22T13:00:00", "2003-10-22T14:00:00"],
        )

    def test_corrupt_empty_and_truncated_snapshot_skipping(self):
        """Verify robust detection and skipping of empty, malformed, and truncated files."""
        exp_dir = self.temp_dir / "Corrupt_Exp"
        exp_dir.mkdir(parents=True, exist_ok=True)

        # Create 5 valid files
        for i in range(5):
            ts = f"2003.10.22.12.{i*10:02d}.00"
            data = np.random.randn(1000, 4)
            np.savetxt(exp_dir / ts, data, delimiter="\t")

        # 1. Empty file (0 bytes)
        empty_file = exp_dir / "2003.10.22.12.05.00"
        empty_file.touch()

        # 2. Corrupted text file (non-numeric garbage)
        corrupt_file = exp_dir / "2003.10.22.12.15.00"
        with open(corrupt_file, "w") as f:
            f.write("CORRUPT HEADER\nNOT A FLOAT\n")

        # 3. Truncated file (only 5 rows instead of minimum 100)
        trunc_file = exp_dir / "2003.10.22.12.25.00"
        np.savetxt(trunc_file, np.random.randn(5, 4), delimiter="\t")

        # Process experiment with skipping enabled
        df = process_ims_experiment(
            data_dir=exp_dir,
            target_bearing=1,
            min_samples_per_snapshot=100,
            max_skipped_fraction=0.50,  # 3 of 8 is 37.5%
        )

        # Assert valid files processed
        self.assertEqual(df.attrs["valid_count"], 5)
        self.assertEqual(df.attrs["skipped_count"], 3)
        skipped_names = [f[0] for f in df.attrs["skipped_files"]]
        self.assertIn("2003.10.22.12.05.00", skipped_names)
        self.assertIn("2003.10.22.12.15.00", skipped_names)
        self.assertIn("2003.10.22.12.25.00", skipped_names)

    def test_insufficient_valid_snapshots_error(self):
        """Verify that experiment with fewer than 2 valid snapshots raises ValueError."""
        exp_dir = self.temp_dir / "Insufficient_Exp"
        exp_dir.mkdir(parents=True, exist_ok=True)

        # Only 1 valid file
        np.savetxt(exp_dir / "2003.10.22.12.00.00", np.random.randn(1000, 4), delimiter="\t")
        # 1 empty file
        (exp_dir / "2003.10.22.12.10.00").touch()

        with self.assertRaises(ValueError) as ctx:
            process_ims_experiment(data_dir=exp_dir, target_bearing=1, min_valid_snapshots=2)
        self.assertIn("Insufficient valid snapshots", str(ctx.exception))

    def test_excessive_invalid_snapshots_error(self):
        """Verify that excessive skipped fraction (> allowable limit) aborts pipeline."""
        exp_dir = self.temp_dir / "Excessive_Skipped_Exp"
        exp_dir.mkdir(parents=True, exist_ok=True)

        # 2 valid files, 5 empty files -> 5/7 = 71.4% corrupt > 20%
        for i in range(2):
            np.savetxt(exp_dir / f"2003.10.22.12.{i:02d}.00", np.random.randn(1000, 4), delimiter="\t")
        for i in range(2, 7):
            (exp_dir / f"2003.10.22.12.{i:02d}.00").touch()

        with self.assertRaises(ValueError) as ctx:
            process_ims_experiment(
                data_dir=exp_dir,
                target_bearing=1,
                min_valid_snapshots=2,
                max_skipped_fraction=0.20,
            )
        self.assertIn("Excessive invalid snapshots", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
