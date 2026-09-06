from scipy.io import loadmat
import numpy as np

# Load the CWRU recording
data = loadmat("data/raw/CWRU/97.mat")

# Extract Drive-End vibration signal
signal = data["X097_DE_time"].flatten()

# Take the first 1-second window
window = signal[:12000]

# Calculate RMS
rms = np.sqrt(np.mean(window ** 2))

print("Number of samples:", len(window))
print("RMS:", rms)