# Member 3 System Boundary Specification
## Subsystem: IoT + Backend + Dashboard

---

## 1. Subsystem Scope & Purpose

As **Member 3**, the primary mission is to build, operate, and maintain the **data ingestion, buffering, storage, backend API, and visualization pipeline** of the *Edge-IoT Predictive Maintenance Platform for Industrial Motors*.

Member 3 operates downstream of the edge hardware and inference pipeline. The subsystem ingests structured prediction and health telemetry emitted over MQTT, routes and buffers it on the Raspberry Pi gateway, persists it into a time-series database (InfluxDB), exposes performant data access APIs (FastAPI), and renders real-time visual insights for technicians and maintenance decision-makers (Grafana / Streamlit).

---

## 2. Team Responsibility Matrix

| Subsystem Component | Responsible Member | Status / Scope |
| :--- | :--- | :--- |
| **Vibration Sensing (ADXL355 SPI)** | Member 1 | Sensor acquisition, hardware wiring, SPI driver |
| **Current Sensing (SCT-013 + ADS1115 ADC)** | Member 1 | Current calibration, ADC driver, I2C bus |
| **Temperature Sensing (MLX90614 I2C)** | Member 1 | Non-contact thermal acquisition, I2C driver |
| **Acoustic Sensing (INMP441 I2S Microphone)**| Member 1 | Acoustic sampling, DMA buffer management |
| **Windowing & Overlap** | Member 1 | 1-second windows, 50% overlap framing |
| **DSP & Feature Extraction** | Member 1 | FFT, RMS, kurtosis, skewness, crest factor, Log-Mel |
| **1D Depthwise Separable CNN** | Member 2 | Multi-label fault classification architecture |
| **RUL Estimation Model** | Member 2 | RUL regression architecture, training, validation |
| **Edge Quantization & TinyML Deployment** | Member 2 | INT8 quantization, TFLite Micro / CMSIS-NN on ESP32-S3/STM32H7 |
| **Edge MQTT Client Emission** | Member 2 / 3 Interface | Formatting inference results to agreed JSON contract |
| **MQTT Topic & Payload Contract Design** | **Member 3** | Standardized JSON contract & topic hierarchy `[PROJECT REQUIREMENT]` |
| **Raspberry Pi Gateway Environment** | **Member 3** | Gateway OS setup, host configuration, bridge management `[PROJECT REQUIREMENT]` |
| **Mosquitto MQTT Broker** | **Member 3** | Broker setup, authentication, QoS configuration `[PROJECT REQUIREMENT]` |
| **Node-RED Ingestion & Buffering** | **Member 3** | Ingestion flows, backpressure buffering, dead-letter routing `[PROJECT REQUIREMENT]` |
| **InfluxDB Time-Series Storage** | **Member 3** | Bucket design, retention policy, measurement schemas `[PROJECT REQUIREMENT]` |
| **FastAPI Backend Application** | **Member 3** | REST endpoints, query services, alert logic `[PROJECT REQUIREMENT]` |
| **Technician Visualization Dashboard** | **Member 3** | Grafana / Streamlit real-time & historical dashboards `[PROJECT REQUIREMENT]` |
| **Edge-to-Dashboard Integration Testing** | **Member 3** | Contract validation, synthetic load test, pipeline tests `[PROJECT REQUIREMENT]` |

---

## 3. Explicit Boundaries: What Member 3 Does NOT Do

To maintain architectural focus and avoid duplicated effort, Member 3 is **strictly not responsible for**:

1. ❌ **Sensor Acquisition & Hardware Drivers**:
   - No physical pin manipulation, SPI/I2C/I2S timing, or ADC calibration for ADXL355, SCT-013, MLX90614, or INMP441.
2. ❌ **Digital Signal Processing (DSP)**:
   - No implementation of FFT transforms, windowing algorithms, RMS filters, kurtosis/skewness/crest factor calculations, or Log-Mel filterbank extraction.
3. ❌ **Machine Learning Model Development**:
   - No model training, loss function optimization, hyperparameter tuning, or dataset curation for fault classification or RUL regression.
4. ❌ **TinyML Model Compilation & MCU Deployment**:
   - No TensorFlow Lite Micro conversion, INT8 weight quantization, CMSIS-NN kernel optimization, or MCU firmware flashing.

---

## 4. Member 3 System Boundary Architecture

```
══════════════════════════════════════════════════════════════════════════
UPSTREAM (Members 1 & 2)
  Motor Sensors → ESP32-S3 / STM32H7 → DSP → TinyML Inference
══════════════════════════════════════════════════════════════════════════
                                    │
                                    │ Publishes agreed Telemetry JSON
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ MEMBER 3 SYSTEM BOUNDARY                                               │
│                                                                        │
│  1. MQTT Ingestion Layer (Mosquitto Broker)                            │
│     - Listens on `motors/{device_id}/prediction`                       │
│     - Enforces QoS 1 delivery                                          │
│                                                                        │
│  2. Gateway Routing & Buffering (Raspberry Pi / Node-RED)             │
│     - Ingests incoming MQTT packets                                    │
│     - Attaches ingestion timestamp fallback if missing                 │
│     - Local ring-buffering in case of network/database downtime        │
│                                                                        │
│  3. Time-Series Storage (InfluxDB)                                     │
│     - Persists measurements (`health_index`, `rul_hours`, etc.)        │
│     - Indexed by `device_id` tag                                       │
│                                                                        │
│  4. Application API (FastAPI)                                          │
│     - Exposes analytical endpoints (`/telemetry`, `/health`, etc.)     │
│     - Validates payloads via Pydantic contract                         │
│                                                                        │
│  5. Visualization (Grafana / Streamlit)                                │
│     - Renders real-time motor health trends                            │
│     - Displays RUL countdown and fault status                          │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
══════════════════════════════════════════════════════════════════════════
DOWNSTREAM: Plant Technician & Maintenance Decision-Makers
══════════════════════════════════════════════════════════════════════════
```

---

## 5. Invariance Principle

A foundational architectural requirement of Member 3's system is the **Invariance Principle**:

> **The downstream system (Gateway, InfluxDB, FastAPI, Dashboard) MUST NOT need to know whether incoming telemetry was generated by a synthetic Python dummy generator (Phase 1) or by the real ESP32-S3/STM32H7 TinyML edge inference engine (Phase 2+).**

As long as the payload satisfies the formal Telemetry Contract, all downstream processing remains 100% identical.
