from pathlib import Path
from scipy.io import loadmat

DATA_DIR = Path("data/raw/CWRU")

mat_files = sorted(DATA_DIR.glob("*.mat"), key=lambda x: int(x.stem))

print(f"Total .mat files found: {len(mat_files)}")
print()

for file in mat_files:
    data = loadmat(file)

    signal_keys = [
        key for key in data.keys()
        if "_DE_time" in key or "_FE_time" in key or "_BA_time" in key
    ]

    rpm_keys = [
        key for key in data.keys()
        if key.endswith("RPM")
    ]

    print(f"{file.name}")
    print(f"  Signal keys: {signal_keys}")
    print(f"  RPM keys: {rpm_keys}")

    for key in signal_keys:
        print(f"  {key} shape: {data[key].shape}")

    if rpm_keys:
        print(f"  RPM: {data[rpm_keys[0]].flatten()[0]}")

    print("-" * 60)