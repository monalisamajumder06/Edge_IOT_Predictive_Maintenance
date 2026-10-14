"""Remaining Useful Life (RUL) and Health Index target generation module.

Provides mathematically grounded degradation targets constructed strictly
from each bearing's observed run-to-failure timeline. Never infers failure
times across unrelated bearings or experiments.
"""

from typing import List, Optional, Union
import numpy as np
import pandas as pd


def compute_linear_rul(
    timeline: Union[List[float], np.ndarray, pd.Series],
    failure_point: Optional[float] = None,
) -> np.ndarray:
    """Compute exact linear remaining useful life (RUL) until failure.

    Args:
        timeline: Monotonically non-decreasing timestamps, operating hours,
            or sequential snapshot indices for a single bearing experiment.
        failure_point: Explicit time/index of end-of-life. If None, uses the
            final observation in timeline (timeline[-1]).

    Returns:
        1D numpy array of remaining useful life values in the same units as timeline.
        Reaches exactly 0.0 at failure_point.
    """
    arr = np.asarray(timeline, dtype=float)
    if len(arr) == 0:
        raise ValueError("Timeline cannot be empty.")

    t_fail = float(failure_point) if failure_point is not None else float(arr[-1])

    if np.any(np.diff(arr) < 0):
        raise ValueError("Timeline must be monotonically non-decreasing.")

    if t_fail < arr[0]:
        raise ValueError(
            f"Failure point ({t_fail}) cannot be earlier than start time ({arr[0]})."
        )

    # Linear countdown: RUL(t) = max(0, t_fail - t)
    rul = np.maximum(0.0, t_fail - arr)
    return rul


def compute_piecewise_rul(
    timeline: Union[List[float], np.ndarray, pd.Series],
    max_rul: Optional[float] = None,
    healthy_fraction: float = 0.6,
    failure_point: Optional[float] = None,
) -> np.ndarray:
    """Compute piecewise-linear RUL (plateau during healthy phase, linear degradation to 0).

    Standard formulation in prognostic literature (e.g., Heimes 2008, NASA PHM).
    During the initial healthy phase, physical degradation is negligible, so RUL
    is capped at max_rul. Once degradation initiates, RUL decreases linearly to 0.

    Args:
        timeline: Monotonically non-decreasing time values or snapshot indices.
        max_rul: Upper limit for RUL target. If None, automatically derived as
            (1 - healthy_fraction) * total_duration.
        healthy_fraction: Proportion of lifetime considered baseline healthy
            (default 0.60, representing the first 60% of test life).
        failure_point: Explicit failure time, defaults to timeline[-1].

    Returns:
        1D numpy array of piecewise-linear RUL targets.
    """
    linear_rul = compute_linear_rul(timeline, failure_point=failure_point)
    total_life = float(linear_rul[0])

    if max_rul is None:
        if not (0.0 < healthy_fraction < 1.0):
            raise ValueError("healthy_fraction must be between 0.0 and 1.0.")
        cap = total_life * (1.0 - healthy_fraction)
    else:
        if max_rul <= 0:
            raise ValueError("max_rul must be strictly positive.")
        cap = float(max_rul)

    # Cap RUL during healthy plateau
    piecewise = np.minimum(linear_rul, cap)
    return piecewise


def compute_health_index(
    timeline: Union[List[float], np.ndarray, pd.Series],
    failure_point: Optional[float] = None,
) -> np.ndarray:
    """Compute normalized composite Health Index strictly bounded in [0.0, 1.0].

    1.0 represents pristine operating baseline health; 0.0 represents catastrophic failure.
    Directly satisfies Member 3's RecommendedTelemetryPayload specification.

    Args:
        timeline: Monotonically non-decreasing time values or snapshot indices.
        failure_point: Explicit failure time, defaults to timeline[-1].

    Returns:
        1D numpy array of continuous Health Index values from 1.0 to 0.0.
    """
    linear_rul = compute_linear_rul(timeline, failure_point=failure_point)
    total_duration = float(linear_rul[0])

    if total_duration < 1e-12:
        return np.zeros_like(linear_rul, dtype=float)

    # Health Index = remaining_life / total_life
    hi = np.clip(linear_rul / total_duration, 0.0, 1.0)
    return hi
