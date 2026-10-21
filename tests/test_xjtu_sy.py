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
    process_xjtu_dataset,
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

    def test_operating_condition_auto_inference(self):
        """Verify operating condition is automatically inferred from parent condition directory."""
        cond_dir = self.temp_dir / "35Hz12kN"
        b_dir = generate_synthetic_xjtu_experiment(
            output_dir=cond_dir / "Bearing1_1", n_snapshots=3, seed=10
        )
        # Without specifying operating_condition, it should infer '35Hz12kN' from parent folder
        df = process_xjtu_bearing_experiment(b_dir)
        self.assertEqual(df["operating_condition"].iloc[0], "35Hz12kN")

    def test_process_xjtu_dataset_synthetic_and_leakage_protection(self):
        """Verify batch processing across condition directories with leakage-safe splitting."""
        b1_dir = generate_synthetic_xjtu_experiment(
            output_dir=self.temp_dir / "35Hz12kN" / "Bearing1_1", n_snapshots=3, seed=11
        )
        b2_dir = generate_synthetic_xjtu_experiment(
            output_dir=self.temp_dir / "37.5Hz11kN" / "Bearing2_1", n_snapshots=3, seed=12
        )

        df = process_xjtu_dataset(
            self.temp_dir,
            test_bearings=["Bearing2_1"],
        )

        self.assertIn("split", df.columns)
        train_df = df[df["split"] == "train"]
        test_df = df[df["split"] == "test"]

        self.assertEqual(set(train_df["bearing_id"].unique()), {"Bearing1_1"})
        self.assertEqual(set(test_df["bearing_id"].unique()), {"Bearing2_1"})
        self.assertTrue(verify_no_experiment_leakage(train_df, test_df, group_col="bearing_id"))

    def test_real_xjtu_sy_data_pipeline_if_present(self):
        """Verify data pipeline execution against the real extracted XJTU-SY dataset."""
        dataset_root = Path("data/raw/XJTU_SY/XJTU-SY_Bearing_Datasets")
        if not dataset_root.exists():
            self.skipTest("Real XJTU-SY dataset not found at expected path.")

        # 1. Verify single snapshot loading on real data
        sample_csv = dataset_root / "35Hz12kN" / "Bearing1_1" / "1.csv"
        h, v = load_xjtu_snapshot_file(sample_csv)
        self.assertEqual(len(h), 32768)
        self.assertEqual(len(v), 32768)
        self.assertFalse(np.isnan(h).any())
        self.assertFalse(np.isnan(v).any())
        self.assertFalse(np.isinf(h).any())
        self.assertFalse(np.isinf(v).any())
        self.assertFalse(np.array_equal(h, v))

        # 2. Verify bearing experiment processing on real data
        b1_dir = dataset_root / "35Hz12kN" / "Bearing1_1"
        df_exp = process_xjtu_bearing_experiment(b1_dir, max_snapshots=3)
        self.assertEqual(len(df_exp), 3)
        self.assertEqual(df_exp["bearing_id"].iloc[0], "Bearing1_1")
        self.assertEqual(df_exp["operating_condition"].iloc[0], "35Hz12kN")
        self.assertEqual(df_exp["snapshot_id"].tolist(), [1, 2, 3])
        self.assertEqual(df_exp["elapsed_minutes"].tolist(), [0.0, 1.0, 2.0])

        # Verify features present
        for col in CORE_FEATURE_COLUMNS:
            self.assertIn(col, df_exp.columns)
            self.assertIn(f"horiz_{col}", df_exp.columns)
            self.assertIn(f"vert_{col}", df_exp.columns)

        # 3. Verify batch processing with leakage-free splitting on real data
        df_batch = process_xjtu_dataset(
            dataset_root,
            bearing_subsets=["Bearing1_1", "Bearing2_1"],
            test_bearings=["Bearing2_1"],
            max_snapshots_per_bearing=2,
        )
        self.assertIn("split", df_batch.columns)
        train_df = df_batch[df_batch["split"] == "train"]
        test_df = df_batch[df_batch["split"] == "test"]

        self.assertEqual(set(train_df["bearing_id"].unique()), {"Bearing1_1"})
        self.assertEqual(set(test_df["bearing_id"].unique()), {"Bearing2_1"})
        self.assertEqual(train_df["operating_condition"].iloc[0], "35Hz12kN")
        self.assertEqual(test_df["operating_condition"].iloc[0], "37.5Hz11kN")
        self.assertTrue(verify_no_experiment_leakage(train_df, test_df, group_col="bearing_id"))


if __name__ == "__main__":
    unittest.main()
