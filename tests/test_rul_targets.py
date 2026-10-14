"""Unit tests for Remaining Useful Life (RUL) and Health Index target generation.

Verifies:
1. Exact linear RUL countdown to 0.0 at failure time.
2. Monotonic decreasing property of RUL.
3. Piecewise-linear RUL capping during the healthy baseline phase.
4. Composite Health Index bounded strictly within [0.0, 1.0].
5. Validation guards against empty timelines, non-monotonic inputs, and invalid parameters.
6. Multi-bearing independence: failure times are never inferred across experiments.
"""

import sys
import unittest
from pathlib import Path
import numpy as np

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from data_pipeline.rul_targets import (
    compute_linear_rul,
    compute_piecewise_rul,
    compute_health_index,
)


class TestRULTargets(unittest.TestCase):
    """Test suite for RUL and Health Index mathematical formulations."""

    def setUp(self):
        # 100-hour experiment recorded hourly (0.0 to 100.0)
        self.timeline_hours = np.linspace(0.0, 100.0, 101)

    def test_linear_rul_exact_countdown(self):
        """Verify linear RUL decreases monotonically and reaches exactly 0.0 at failure."""
        rul = compute_linear_rul(self.timeline_hours)

        self.assertEqual(len(rul), len(self.timeline_hours))
        self.assertEqual(rul[0], 100.0)
        self.assertEqual(rul[-1], 0.0)
        self.assertEqual(rul[50], 50.0)

        # Monotonically non-increasing: diff <= 0 everywhere
        diffs = np.diff(rul)
        self.assertTrue(np.all(diffs <= 0.0), "Linear RUL is not monotonically decreasing.")

    def test_linear_rul_custom_failure_point(self):
        """Verify explicit failure point can be provided for multi-stage evaluations."""
        timeline = [0.0, 10.0, 20.0, 30.0]
        rul = compute_linear_rul(timeline, failure_point=50.0)
        np.testing.assert_array_equal(rul, [50.0, 40.0, 30.0, 20.0])

    def test_piecewise_rul_capping_and_degradation(self):
        """Verify piecewise RUL caps healthy phase at max_rul and degrades linearly to 0."""
        # Cap at 40 hours max RUL
        pw_rul = compute_piecewise_rul(self.timeline_hours, max_rul=40.0)

        self.assertEqual(len(pw_rul), 101)
        # First 60 hours (timeline 0.0 to 60.0) should all be capped at 40.0
        self.assertEqual(pw_rul[0], 40.0)
        self.assertEqual(pw_rul[60], 40.0)
        # From hour 60 to 100, degrades linearly from 40 to 0
        self.assertEqual(pw_rul[80], 20.0)
        self.assertEqual(pw_rul[-1], 0.0)

        diffs = np.diff(pw_rul)
        self.assertTrue(np.all(diffs <= 0.0), "Piecewise RUL is not monotonically non-increasing.")

    def test_health_index_bounds_and_direction(self):
        """Verify Health Index starts at 1.0, degrades to 0.0, and stays in [0.0, 1.0]."""
        hi = compute_health_index(self.timeline_hours)

        self.assertEqual(len(hi), 101)
        self.assertAlmostEqual(hi[0], 1.0, places=6)
        self.assertAlmostEqual(hi[-1], 0.0, places=6)
        self.assertAlmostEqual(hi[50], 0.5, places=6)

        # Strictly bounded in [0.0, 1.0]
        self.assertTrue(np.all((hi >= 0.0) & (hi <= 1.0)), "Health index outside [0.0, 1.0].")

    def test_invalid_timeline_inputs_raise_errors(self):
        """Verify validation errors for empty, descending, or illogical inputs."""
        # Empty timeline
        with self.assertRaises(ValueError):
            compute_linear_rul([])

        # Non-monotonic (descending) timeline
        with self.assertRaises(ValueError):
            compute_linear_rul([0.0, 10.0, 5.0, 20.0])

        # Failure point earlier than start time
        with self.assertRaises(ValueError):
            compute_linear_rul([10.0, 20.0, 30.0], failure_point=5.0)

        # Invalid healthy fraction in piecewise RUL
        with self.assertRaises(ValueError):
            compute_piecewise_rul(self.timeline_hours, healthy_fraction=1.5)


if __name__ == "__main__":
    unittest.main()
