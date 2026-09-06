from scipy.io import loadmat
import numpy as np
import matplotlib.pyplot as plt

# Load the CWRU recording
data = loadmat("data/raw/CWRU/97.mat")

# Extract Drive-End vibration signal
signal = data["X097_DE_time"].flatten()

# Take the first 1-second window
window = signal[:12000]

# Sampling rate
sampling_rate = 12000

# Calculate FFT
fft_values = np.fft.rfft(window)
frequencies = np.fft.rfftfreq(len(window), 1 / sampling_rate)

# Magnitude of FFT
magnitude = np.abs(fft_values)

# Plot
plt.plot(frequencies, magnitude)

plt.xlabel("Frequency (Hz)")
plt.ylabel("Magnitude")
plt.title("FFT of CWRU Normal Bearing - First Window")
plt.show()