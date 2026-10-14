"""Unit tests for CWRU data loading and variable selection logic.

Verifies:
1. File 98.mat loads 'X098_DE_time' correctly.
2. File 99.mat selects 'X099_DE_time' and NOT the stale 'X098_DE_time' variable.
3. The raw signals of 98 and 99 are distinct arrays with different lengths.
4. All 16 selected project files load their intended Drive-End signals without error.
5. Error handling for missing or ambiguous Drive-End variables.
6. Feature formula alignment between preprocessing.py and predict.py (Fisher excess kurtosis).
"""

import sys
import unittest
from pathlib import Path
import numpy as np
from scipy.io import loadmat, savemat

# Ensure src/ is importable
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from preprocessing import (
    load_vibration_signal,
    create_windows,
    extract_features as extract_features_prep,
    FILE_LABELS,
)
import predict


class TestCWRULoader(unittest.TestCase):
    """Test suite for CWRU data loading and variable selection."""

    def setUp(self):
        self.raw_cwru_dir = Path("data/raw/CWRU")

    def test_98_mat_loads_correct_signal(self):
        """Verify 98.mat loads X098_DE_time correctly."""
        file_path = self.raw_cwru_dir / "98.mat"
        if not file_path.exists():
            self.skipTest("98.mat not found in data/raw/CWRU")

        raw_mat = loadmat(file_path)
        self.assertIn("X098_DE_time", raw_mat)

        sig = load_vibration_signal(file_path)
        expected = raw_mat["X098_DE_time"].flatten()
        np.testing.assert_array_equal(sig, expected)
        self.assertEqual(len(sig), 483903)

    def test_99_mat_loads_x099_not_x098(self):
        """Verify 99.mat selects X099_DE_time, NOT stale X098_DE_time."""
        file_path = self.raw_cwru_dir / "99.mat"
        if not file_path.exists():
            self.skipTest("99.mat not found in data/raw/CWRU")

        raw_mat = loadmat(file_path)
        # Verify the raw file indeed contains both variables
        self.assertIn("X098_DE_time", raw_mat)
        self.assertIn("X099_DE_time", raw_mat)

        sig99 = load_vibration_signal(file_path)
        expected_99 = raw_mat["X099_DE_time"].flatten()
        stale_98 = raw_mat["X098_DE_time"].flatten()

        # Must match X099_DE_time exactly
        np.testing.assert_array_equal(sig99, expected_99)
        self.assertEqual(len(sig99), 485063)

        # Must NOT match X098_DE_time
        self.assertFalse(np.array_equal(sig99, stale_98))

        # Must NOT equal signal loaded from 98.mat
        sig98 = load_vibration_signal(self.raw_cwru_dir / "98.mat")
        self.assertFalse(np.array_equal(sig99, sig98))
        self.assertNotEqual(len(sig99), len(sig98))

    def test_all_16_project_files_load_intended_signals(self):
        """Verify all 16 files used in the classification project load valid DE signals."""
        for file_id, label in FILE_LABELS.items():
            file_path = self.raw_cwru_dir / f"{file_id}.mat"
            if not file_path.exists():
                continue
            sig = load_vibration_signal(file_path)
            self.assertIsInstance(sig, np.ndarray)
            self.assertGreater(len(sig), 12000, f"Signal in {file_id}.mat too short")
            self.assertFalse(np.isnan(sig).any(), f"NaN values in {file_id}.mat")

    def test_missing_de_key_raises_error(self):
        """Verify that a MAT file without any _DE_time key raises a ValueError."""
        temp_mat_path = Path("data/interim/test_no_de.mat")
        temp_mat_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            savemat(temp_mat_path, {"X100_FE_time": np.zeros((100, 1))})
            with self.assertRaises(ValueError) as ctx:
                load_vibration_signal(temp_mat_path)
            self.assertIn("No Drive-End vibration signal found", str(ctx.exception))
        finally:
            if temp_mat_path.exists():
                temp_mat_path.unlink()

    def test_ambiguous_de_keys_raises_error(self):
        """Verify that multiple DE keys that do not match the file number raise ValueError."""
        temp_mat_path = Path("data/interim/test_500.mat")
        temp_mat_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            savemat(temp_mat_path, {
                "X101_DE_time": np.zeros((100, 1)),
                "X102_DE_time": np.ones((100, 1))
            })
            with self.assertRaises(ValueError) as ctx:
                load_vibration_signal(temp_mat_path)
            self.assertIn("none unambiguously matched", str(ctx.exception))
        finally:
            if temp_mat_path.exists():
                temp_mat_path.unlink()

    def test_feature_formula_alignment_preprocessing_and_predict(self):
        """Verify that predict.py and preprocessing.py extract identical features (Fisher kurtosis)."""
        np.random.seed(42)
        test_window = np.random.randn(12000)

        prep_dict = extract_features_prep(test_window, sampling_rate=12000)
        predict_list = predict.extract_features(test_window, sampling_rate=12000)

        feature_names = [
            "rms", "mean", "std", "peak", "peak_to_peak", "skewness",
            "kurtosis", "crest_factor", "dominant_frequency_hz",
            "spectral_centroid_hz", "spectral_bandwidth_hz", "spectral_energy"
        ]

        # Check kurtosis specifically: standard Gaussian window should have excess kurtosis near 0, NOT 3
        self.assertAlmostEqual(prep_dict["kurtosis"], 0.0, delta=0.2)
        self.assertAlmostEqual(predict_list[6], 0.0, delta=0.2)

        # Check all 12 features match between preprocessing and predict
        for idx, name in enumerate(feature_names):
            prep_val = prep_dict[name]
            pred_val = predict_list[idx]
            self.assertAlmostEqual(
                prep_val,
                pred_val,
                places=6,
                msg=f"Feature mismatch on '{name}': {prep_val} vs {pred_val}"
            )


if __name__ == "__main__":
    unittest.main()
