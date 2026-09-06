from scipy.io import loadmat

# Load the raw CWRU recording
data = loadmat("data/raw/CWRU/97.mat")

# Extract Drive-End vibration signal
signal = data["X097_DE_time"].flatten()

# CWRU sampling rate
sampling_rate = 12000

# 1-second window
window_size = sampling_rate

# 50% overlap
step_size = window_size // 2

# Create windows
windows = []

for start in range(0, len(signal) - window_size + 1, step_size):
    window = signal[start:start + window_size]
    windows.append(window)

print("Total raw samples:", len(signal))
print("Window size:", window_size)
print("Step size:", step_size)
print("Number of windows:", len(windows))
print("First window shape:", windows[0].shape)