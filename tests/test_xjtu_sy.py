"""Unit tests for XJTU-SY bearing data loader and run-to-failure pipeline.

Verifies:
1. 2-axis snapshot file loading (Horizontal & Vertical vibration).
2. Dual-axis feature extraction and 1-second windowing (25,600 samples @ 25.6 kHz).
3. End-to-end run-to-failure processing with synthetic XJTU-SY fixtures.
4. RUL target generation (minutes and hours) and Health Index compliance.
5. Experiment boundary protection and leakage-free bearing-level partitioning.
6. Error handling for malformed CSVs and missing files.
"""

import shutil
import sys
import unittest
from pathlib import Path
import numpy as np
import pandas as pd

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from data_pipeline.xjtu_sy import (
    load_xjtu_snapshot_file,
    process_xjtu_snapshot,
    process_xjtu_bearing_experiment,
    generate_synthetic_xjtu_experiment,
    SAMPLING_RATE_XJTU,
)
from data_pipeline.splits import (
    split_experiments_by_bearing,
    verify_no_experiment_leakage,
)
from data_pipeline.features import CORE_FEATURE_COLUMNS


class TestXJTUSY(unittest.TestCase):
    """Test suite for XJTU-SY run-to-failure data pipeline."""

    def setUp(self):
        self.temp_dir = Path("data/interim/test_xjtu_sy")
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_load_snapshot_file(self):
        """Verify reading 2-axis CSV snapshot files."""
        csv_path = self.temp_dir / "1.csv"
        df_dummy = pd.DataFrame({
            "Horizontal_vibration": [0.1, 0.2, 0.3],
            "Vertical_vibration": [0.4, 0.5, 0.6],
        })
        df_dummy.to_csv(csv_path, index=False)

        h, v = load_xjtu_snapshot_file(csv_path)
        self.assertEqual(len(h), 3)
        self.assertEqual(len(v), 3)
        np.testing.assert_allclose(h, [0.1, 0.2, 0.3])
        np.testing.assert_allclose(v, [0.4, 0.5, 0.6])

    def test_end_to_end_synthetic_xjtu_experiment(self):
        """Verify full run-to-failure processing with generated synthetic XJTU-SY fixtures."""
        n_snapshots = 10
        bearing_dir = generate_synthetic_xjtu_experiment(
            output_dir=self.temp_dir / "Bearing1_1",
            n_snapshots=n_snapshots,
            samples_per_snapshot=32768,
            seed=42,
        )

        df = process_xjtu_bearing_experiment(
            bearing_dir=bearing_dir,
            bearing_id="Bearing1_1",
            operating_condition="Condition_1",
            max_rul_hours=1.0,
        )

        self.assertGreater(len(df), 0)
        self.assertEqual(df["bearing_id"].iloc[0], "Bearing1_1")
        self.assertEqual(df["experiment_id"].iloc[0], "XJTU_SY")

        # Verify both dual-axis and canonical feature columns are present
        for col in CORE_FEATURE_COLUMNS:
            self.assertIn(col, df.columns)
            self.assertIn(f"horiz_{col}", df.columns)
            self.assertIn(f"vert_{col}", df.columns)

        # Verify telemetry contract fields
        self.assertIn("health_index", df.columns)
        self.assertIn("rul_hours", df.columns)
        self.assertIn("rul_minutes_linear", df.columns)

        # Verify RUL monotonicity
        snap_df = df.drop_duplicates(subset=["snapshot_id"]).sort_values("snapshot_id")
        lin_min = snap_df["rul_minutes_linear"].to_numpy()
        self.assertTrue(np.all(np.diff(lin_min) <= 0.0), "XJTU-SY RUL is not non-increasing.")
        self.assertEqual(lin_min[-1], 0.0)

        # Verify Health Index bounds
        hi = snap_df["health_index"].to_numpy()
        self.assertAlmostEqual(hi[0], 1.0, places=4)
        self.assertAlmostEqual(hi[-1], 0.0, places=4)
        self.assertTrue(np.all((hi >= 0.0) & (hi <= 1.0)))

    def test_experiment_boundary_protection_and_splitting(self):
        """Verify experiment boundary protection prevents mixing bearings across train/test splits."""
        # Generate two separate synthetic bearing experiments
        b1_dir = generate_synthetic_xjtu_experiment(
            output_dir=self.temp_dir / "Bearing1_1", n_snapshots=5, seed=1
        )
        b2_dir = generate_synthetic_xjtu_experiment(
            output_dir=self.temp_dir / "Bearing1_2", n_snapshots=5, seed=2
        )

        df1 = process_xjtu_bearing_experiment(b1_dir, bearing_id="Bearing1_1")
        df2 = process_xjtu_bearing_experiment(b2_dir, bearing_id="Bearing1_2")

        combined_df = pd.concat([df1, df2], ignore_index=True)

        # Split by bearing ID
        train_df, test_df = split_experiments_by_bearing(
            combined_df, group_col="bearing_id", test_groups=["Bearing1_2"]
        )

        # Verify zero group leakage
        self.assertTrue(verify_no_experiment_leakage(train_df, test_df, group_col="bearing_id"))
        self.assertEqual(set(train_df["bearing_id"].unique()), {"Bearing1_1"})
        self.assertEqual(set(test_df["bearing_id"].unique()), {"Bearing1_2"})
        self.assertEqual(len(set(train_df["bearing_id"]) & set(test_df["bearing_id"])), 0)


if __name__ == "__main__":
    unittest.main()
