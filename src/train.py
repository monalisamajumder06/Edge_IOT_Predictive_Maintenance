import pandas as pd
from sklearn.model_selection import train_test_split


FEATURE_PATH = "data/processed/cwru_features.csv"

# Load feature dataset
df = pd.read_csv(FEATURE_PATH)

# Get one row per experiment
groups = df[["file_id", "label"]].drop_duplicates()

# Split experiments, not individual windows
train_groups, test_groups = train_test_split(
    groups,
    test_size=0.25,
    random_state=42,
    stratify=groups["label"]
)

# Get the actual file IDs
train_file_ids = train_groups["file_id"].tolist()
test_file_ids = test_groups["file_id"].tolist()

# Create train/test datasets
train_df = df[df["file_id"].isin(train_file_ids)].copy()
test_df = df[df["file_id"].isin(test_file_ids)].copy()

print("Training files:", sorted(train_file_ids))
print("Testing files:", sorted(test_file_ids))

print("\nTraining shape:", train_df.shape)
print("Testing shape:", test_df.shape)

print("\nTraining class distribution:")
print(train_df["label"].value_counts())

print("\nTesting class distribution:")
print(test_df["label"].value_counts())

# Safety check: no experiment can appear in both sets
overlap = set(train_file_ids) & set(test_file_ids)

print("\nFiles appearing in both train and test:", overlap)
# Select features and target
feature_columns = ["rms", "dominant_frequency_hz"]

X_train = train_df[feature_columns]
y_train = train_df["label"]

X_test = test_df[feature_columns]
y_test = test_df["label"]

print("\nX_train shape:", X_train.shape)
print("X_test shape:", X_test.shape)

print("\nFirst training samples:")
print(X_train.head())

print("\nFirst training labels:")
print(y_train.head())
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report


# Create baseline Random Forest model
model = RandomForestClassifier(
    n_estimators=100,
    random_state=42
)

# Train the model
model.fit(X_train, y_train)

# Make predictions on unseen experiments
y_pred = model.predict(X_test)

# Calculate accuracy
accuracy = accuracy_score(y_test, y_pred)

print("\nBaseline Model: Random Forest")
print("Accuracy:", accuracy)

print("\nClassification Report:")
print(classification_report(y_test, y_pred))