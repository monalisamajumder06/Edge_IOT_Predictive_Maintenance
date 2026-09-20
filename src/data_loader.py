import pandas as pd

def get_feature_columns():
    return [
        "rms",
        "mean",
        "std",
        "peak",
        "peak_to_peak",
        "skewness",
        "kurtosis",
        "crest_factor",
        "dominant_frequency_hz",
        "spectral_centroid_hz",
        "spectral_bandwidth_hz",
        "spectral_energy"
    ]

def load_and_split_data(data_path="data/processed/cwru_features.csv"):
    """
    Loads the CWRU feature dataset and performs a leakage-safe split.
    The split is done at the file/experiment level to ensure windows
    from the same recording do not appear in both train and test sets.
    """
    df = pd.read_csv(data_path)

    # Hardcoded, safe file-level split established for the project
    train_files = [
        97, 98, 100,
        105, 106, 108,
        118, 119, 121,
        130, 131, 133
    ]

    test_files = [
        99,
        107,
        120,
        132
    ]

    train_df = df[df["file_id"].isin(train_files)].copy()
    test_df = df[df["file_id"].isin(test_files)].copy()

    feature_columns = get_feature_columns()

    X_train = train_df[feature_columns]
    y_train = train_df["label"]

    X_test = test_df[feature_columns]
    y_test = test_df["label"]

    return X_train, X_test, y_train, y_test

if __name__ == "__main__":
    X_train, X_test, y_train, y_test = load_and_split_data()
    print("Leakage-safe split successful.")
    print("X_train shape:", X_train.shape)
    print("X_test shape:", X_test.shape)
    print("Classes in training:", y_train.unique())
