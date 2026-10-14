"""Experiment-level, leakage-free data partitioning utilities.

Guarantees that run-to-failure experiments and distinct bearing life cycles
are never mixed across training and testing partitions.
"""

from typing import List, Optional, Set, Tuple
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit


def verify_no_experiment_leakage(
    train_df: pd.DataFrame, test_df: pd.DataFrame, group_col: str = "bearing_id"
) -> bool:
    """Verify that train and test sets have strictly zero overlapping experiment groups."""
    train_groups: Set = set(train_df[group_col].unique())
    test_groups: Set = set(test_df[group_col].unique())
    overlap = train_groups.intersection(test_groups)

    if len(overlap) > 0:
        raise ValueError(
            f"Data leakage detected! Experiments present in both train and test partitions: {overlap}"
        )
    return True


def split_experiments_by_bearing(
    df: pd.DataFrame,
    group_col: str = "bearing_id",
    test_groups: Optional[List[str]] = None,
    test_size: float = 0.33,
    random_state: int = 42,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Partition a run-to-failure feature dataset strictly at the experiment/bearing level.

    Args:
        df: Processed feature dataset containing multiple bearings.
        group_col: Column identifying individual run-to-failure bearings.
        test_groups: Optional explicit list of bearing IDs to assign to the test partition.
        test_size: Approximate fraction of bearing groups to allocate to test if test_groups is None.
        random_state: Seed for reproducible group splitting.

    Returns:
        Tuple of (train_df, test_df).
    """
    if group_col not in df.columns:
        raise KeyError(f"Group column '{group_col}' not found in dataset columns.")

    unique_groups = df[group_col].unique().tolist()
    if len(unique_groups) < 2:
        raise ValueError(
            f"Cannot split dataset with fewer than 2 distinct bearing experiments. "
            f"Found: {unique_groups}"
        )

    if test_groups is not None:
        test_set = set(test_groups)
        train_df = df[~df[group_col].isin(test_set)].copy()
        test_df = df[df[group_col].isin(test_set)].copy()
    else:
        gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=random_state)
        train_idx, test_idx = next(gss.split(df, groups=df[group_col]))
        train_df = df.iloc[train_idx].copy()
        test_df = df.iloc[test_idx].copy()

    # Safety assertion
    verify_no_experiment_leakage(train_df, test_df, group_col=group_col)

    train_df["split"] = "train"
    test_df["split"] = "test"

    return train_df, test_df
