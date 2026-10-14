"""Unit tests for Paderborn University bearing dataset loader and feature pipeline.

Verifies:
1. Loading 64 kHz multi-channel signals (vibration + 2-phase motor currents) from MAT files.
2. Motor Current Signature Analysis (MCSA) feature extraction & phase unbalance calculation.
3. 64 kHz 1-second windowing, channel identity preservation (vib_*, current_1_*, current_2_*).
4. Canonical feature alias projection for Member 2 classification model compatibility.
5. Strict bearing-level grouped splitting with zero window leakage.
6. Error handling for missing files, empty arrays, or malformed MAT structures.
"""

from pathlib import Path
import shutil
import sys
import unittest
import numpy as np
import scipy.io as sio

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from data_pipeline.paderborn import (
    load_paderborn_mat,
    extract_current_features,
    process_paderborn_signals,
    process_paderborn_experiment,
    process_paderborn_dataset,
    generate_synthetic_paderborn_experiment,
    SAMPLING_RATE_PADERBORN,
)
from data_pipeline.features import CORE_FEATURE_COLUMNS
from data_pipeline.splits import verify_no_experiment_leakage


class TestPaderbornPipeline(unittest.TestCase):
    """Test suite for Paderborn multi-channel bearing pipeline."""

    def setUp(self):
        self.temp_dir = Path("data/interim/test_paderborn")
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_load_paderborn_mat_and_metadata(self):
        """Verify loading 64 kHz MAT files with vibration and 2-phase currents."""
        mat_path = generate_synthetic_paderborn_experiment(
            output_dir=self.temp_dir,
            filename="N15_M07_F10_K001_1.mat",
            bearing_id="K001",
            damage_type="healthy",
            duration_sec=1.5,
            sampling_rate=SAMPLING_RATE_PADERBORN,
        )

        loaded = load_paderborn_mat(mat_path)
        self.assertIn("vibration", loaded)
        self.assertIn("current_1", loaded)
        self.assertIn("current_2", loaded)

        vib = loaded["vibration"]
        cur1 = loaded["current_1"]
        cur2 = loaded["current_2"]

        expected_samples = int(1.5 * SAMPLING_RATE_PADERBORN)
        self.assertEqual(len(vib), expected_samples)
        self.assertEqual(len(cur1), expected_samples)
        self.assertIsNotNone(cur2)
        self.assertEqual(len(cur2), expected_samples)
        self.assertEqual(loaded["metadata"]["bearing_id"], "K001")
        self.assertEqual(loaded["metadata"]["damage_type"], "healthy")

    def test_current_feature_extraction_and_phase_unbalance(self):
        """Verify MCSA features and phase unbalance calculation."""
        fs = SAMPLING_RATE_PADERBORN
        duration = 1.0
        n_samples = int(duration * fs)
        t = np.arange(n_samples) / fs

        # Balanced 50 Hz 2-phase current (3.0 A RMS)
        i1 = 3.0 * np.sqrt(2) * np.sin(2 * np.pi * 50.0 * t)
        i2 = 3.0 * np.sqrt(2) * np.sin(2 * np.pi * 50.0 * t - 2 * np.pi / 3)

        feats_balanced = extract_current_features(i1, i2, sampling_rate=fs)
        self.assertAlmostEqual(feats_balanced["current_1_rms"], 3.0, places=2)
        self.assertAlmostEqual(feats_balanced["current_2_rms"], 3.0, places=2)
        self.assertAlmostEqual(feats_balanced["current_1_dominant_frequency_hz"], 50.0, delta=2.0)
        self.assertAlmostEqual(feats_balanced["current_phase_unbalance"], 0.0, places=2)

        # Unbalanced phase currents (i1 = 3.0 A RMS, i2 = 2.0 A RMS)
        i2_unbal = 2.0 * np.sqrt(2) * np.sin(2 * np.pi * 50.0 * t - 2 * np.pi / 3)
        feats_unbalanced = extract_current_features(i1, i2_unbal, sampling_rate=fs)
        self.assertGreater(feats_unbalanced["current_phase_unbalance"], 0.3)

    def test_multichannel_windowing_and_feature_columns(self):
        """Verify 64 kHz windowing (64000 samples @ 64 kHz) and channel identity preservation."""
        fs = SAMPLING_RATE_PADERBORN
        duration = 2.0  # 2 seconds = 128,000 samples
        n_samples = int(duration * fs)

        vib = np.random.randn(n_samples)
        cur1 = np.sin(2 * np.pi * 50 * np.arange(n_samples) / fs)
        cur2 = np.cos(2 * np.pi * 50 * np.arange(n_samples) / fs)

        windows = process_paderborn_signals(
            vib, cur1, cur2,
            sampling_rate=fs,
            window_size=64000,
            step_size=32000,  # 50% overlap -> 3 windows (starts at 0, 32000, 64000)
        )

        self.assertEqual(len(windows), 3)

        first_win = windows[0]
        # Check vibration channel identity
        self.assertIn("vib_rms", first_win)
        self.assertIn("vib_kurtosis", first_win)
        self.assertIn("vib_spectral_energy", first_win)

        # Check current channel identity
        self.assertIn("current_1_rms", first_win)
        self.assertIn("current_2_rms", first_win)
        self.assertIn("current_phase_unbalance", first_win)

        # Check canonical feature projection for Member 2
        for col in CORE_FEATURE_COLUMNS:
            self.assertIn(col, first_win, f"Missing canonical feature alias: {col}")
            self.assertEqual(first_win[col], first_win[f"vib_{col}"])

    def test_bearing_leakage_free_splitting(self):
        """Verify multi-bearing dataset processing guarantees zero bearing leakage."""
        bearings = [("K001", "healthy"), ("K002", "healthy"), ("KA01", "outer_race"), ("KI01", "inner_race")]

        for b_id, d_type in bearings:
            generate_synthetic_paderborn_experiment(
                output_dir=self.temp_dir,
                filename=f"N15_M07_F10_{b_id}_1.mat",
                bearing_id=b_id,
                damage_type=d_type,
                duration_sec=2.0,
            )

        df = process_paderborn_dataset(
            self.temp_dir,
            test_bearings=["KA01"],  # Hold out outer race bearing KA01 for test
        )

        self.assertIn("split", df.columns)
        train_df = df[df["split"] == "train"]
        test_df = df[df["split"] == "test"]

        # Assert no leakage
        self.assertTrue(verify_no_experiment_leakage(train_df, test_df, group_col="bearing_id"))

        # Assert KA01 windows are exclusively in test
        self.assertSetEqual(set(test_df["bearing_id"].unique()), {"KA01"})
        self.assertNotIn("KA01", train_df["bearing_id"].unique())

    def test_error_handling(self):
        """Verify error handling on missing file and empty arrays."""
        with self.assertRaises(FileNotFoundError):
            load_paderborn_mat(self.temp_dir / "non_existent.mat")

        with self.assertRaises(ValueError):
            extract_current_features(np.array([]))


if __name__ == "__main__":
    unittest.main()
