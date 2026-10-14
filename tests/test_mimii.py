"""Unit tests for MIMII industrial machine acoustic anomaly detection pipeline.

Verifies:
1. Native 16 kHz 16-bit PCM WAV audio ingestion & sampling rate enforcement.
2. Log-Mel filterbank matrix generation in pure NumPy (16 bands, 50 Hz to 8000 Hz).
3. Acoustic feature extraction (energy, dynamics, Wiener spectral flatness, spectral roll-off).
4. Metadata parsing from standard MIMII directory structures (machine_type, machine_id, condition).
5. Unsupervised recording-level split (train on normal only, test on normal + anomaly) without window leakage.
6. Machine-level domain generalization splitting with strict instance isolation.
"""

from pathlib import Path
import shutil
import sys
import unittest
import numpy as np
import scipy.io.wavfile as wavfile

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from data_pipeline.mimii import (
    load_mimii_wav,
    compute_mel_filterbank,
    extract_audio_features,
    parse_mimii_path_metadata,
    process_mimii_recording,
    process_mimii_subset,
    split_mimii_by_machine,
    split_mimii_by_recording,
    generate_synthetic_mimii_subset,
    SAMPLING_RATE_MIMII,
)
from data_pipeline.splits import verify_no_experiment_leakage


class TestMIMIIPipeline(unittest.TestCase):
    """Test suite for MIMII acoustic anomaly detection pipeline."""

    def setUp(self):
        self.temp_dir = Path("data/interim/test_mimii")
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_load_mimii_wav_and_sampling_rate_enforcement(self):
        """Verify 16 kHz audio loading, int16 normalization, and sample rate checks."""
        # 1. Valid 16 kHz file
        valid_path = self.temp_dir / "valid_16k.wav"
        t = np.arange(16000) / 16000.0
        tone = (0.5 * np.sin(2 * np.pi * 440.0 * t) * 32767).astype(np.int16)
        wavfile.write(valid_path, 16000, tone)

        loaded = load_mimii_wav(valid_path)
        self.assertEqual(len(loaded), 16000)
        self.assertTrue(np.all(loaded >= -1.0) and np.all(loaded <= 1.0))
        self.assertAlmostEqual(float(np.max(np.abs(loaded))), 0.5, places=2)

        # 2. Invalid 8 kHz file
        invalid_path = self.temp_dir / "invalid_8k.wav"
        wavfile.write(invalid_path, 8000, tone[:8000])
        with self.assertRaises(ValueError) as ctx:
            load_mimii_wav(invalid_path)
        self.assertIn("16000 Hz", str(ctx.exception))

    def test_mel_filterbank_matrix_properties(self):
        """Verify triangular Mel filterbank matrix shape and non-negativity."""
        n_mels = 16
        n_fft = 1024
        fbank = compute_mel_filterbank(sr=16000.0, n_fft=n_fft, n_mels=n_mels, f_min=50.0, f_max=8000.0)

        # Shape should be (n_mels, n_fft // 2 + 1) -> (16, 513)
        self.assertEqual(fbank.shape, (16, 513))
        self.assertTrue(np.all(fbank >= 0.0))
        # Every filter should have non-zero energy
        row_sums = np.sum(fbank, axis=1)
        self.assertTrue(np.all(row_sums > 0.0))

    def test_extract_audio_features(self):
        """Verify acoustic feature extraction on pure tone vs white noise."""
        fs = 16000.0
        n_samples = 16000  # 1 second
        t = np.arange(n_samples) / fs

        # Pure tone at 1000 Hz
        pure_tone = 0.5 * np.sin(2 * np.pi * 1000.0 * t)
        feats_tone = extract_audio_features(pure_tone, sampling_rate=fs, n_mels=16)

        self.assertAlmostEqual(feats_tone["spectral_centroid_hz"], 1000.0, delta=20.0)
        self.assertLess(feats_tone["spectral_flatness"], 0.05)  # Pure tone has low flatness
        self.assertIn("audio_rms", feats_tone)
        self.assertIn("spectral_rolloff_hz", feats_tone)

        # All 16 log-Mel energy bands present
        for m in range(16):
            self.assertIn(f"mel_band_{m:02d}", feats_tone)

        # White noise
        rng = np.random.default_rng(42)
        noise = rng.normal(0, 0.2, size=n_samples)
        feats_noise = extract_audio_features(noise, sampling_rate=fs, n_mels=16)

        # Noise has high spectral flatness (Wiener entropy)
        self.assertGreater(feats_noise["spectral_flatness"], feats_tone["spectral_flatness"])
        self.assertGreater(feats_noise["spectral_bandwidth_hz"], feats_tone["spectral_bandwidth_hz"])

    def test_end_to_end_synthetic_mimii_pipeline(self):
        """Verify processing synthetic MIMII directory and unsupervised recording split."""
        dataset_path = generate_synthetic_mimii_subset(
            output_dir=self.temp_dir,
            machine_type="pump",
            machine_ids=("id_00", "id_02"),
            snr="0_dB",
            n_normal_per_machine=4,
            n_anomaly_per_machine=2,
            duration_sec=2.0,
        )

        df = process_mimii_subset(dataset_path, split_strategy="recording")

        self.assertIn("split", df.columns)
        self.assertIn("anomaly_label", df.columns)
        self.assertIn("machine_id", df.columns)
        self.assertIn("mel_band_00", df.columns)

        train_df = df[df["split"] == "train"]
        test_df = df[df["split"] == "test"]

        # 1. Unsupervised formulation: Train partition must contain ONLY normal recordings
        self.assertEqual(train_df["anomaly_label"].max(), 0)
        self.assertTrue((train_df["condition"] == "normal").all())

        # 2. Test partition contains both normal and anomalous recordings
        self.assertIn(1, test_df["anomaly_label"].values)
        self.assertIn(0, test_df["anomaly_label"].values)

        # 3. Leakage verification: train and test share zero recording_ids
        self.assertTrue(verify_no_experiment_leakage(train_df, test_df, group_col="recording_id"))

    def test_machine_level_domain_generalization_split(self):
        """Verify machine-level split isolates machine instances for domain generalization."""
        dataset_path = generate_synthetic_mimii_subset(
            output_dir=self.temp_dir,
            machine_type="pump",
            machine_ids=("id_00", "id_02"),
            snr="0_dB",
            n_normal_per_machine=3,
            n_anomaly_per_machine=2,
            duration_sec=2.0,
        )

        df = process_mimii_subset(dataset_path, split_strategy="machine")
        train_df = df[df["split"] == "train"]
        test_df = df[df["split"] == "test"]

        self.assertTrue(verify_no_experiment_leakage(train_df, test_df, group_col="machine_id"))
        train_machines = set(train_df["machine_id"].unique())
        test_machines = set(test_df["machine_id"].unique())
        self.assertEqual(len(train_machines.intersection(test_machines)), 0)


if __name__ == "__main__":
    unittest.main()
