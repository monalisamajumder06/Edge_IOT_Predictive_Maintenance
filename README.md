# Edge-IoT Predictive Maintenance Platform for Industrial Motors
## Subsystem: IoT + Backend + Dashboard (Member 3)

This repository hosts the IoT messaging, gateway buffering, time-series storage, backend API, and visualization dashboard for the **Edge-IoT Predictive Maintenance Platform for Industrial Motors**.

---

## 1. High-Level Architecture

The end-to-end platform integrates edge sensing, TinyML edge inference, and an industrial IoT stack:

```
Motor Sensors (ADXL355, SCT-013, MLX90614, INMP441)
    ↓
ESP32-S3 / STM32H7 Edge MCU
    ↓
Signal Processing (FFT, RMS, Kurtosis, Skewness, Crest Factor, Log-Mel)
    ↓
TinyML Fault Classification & RUL Estimation
    ↓
MQTT Telemetry (JSON Payload)
    ↓
Raspberry Pi Gateway (Mosquitto / Node-RED)
    ↓
InfluxDB (Time-Series Storage) [PHASE 3 COMPLETE]
    ↓
FastAPI (Backend Application & Data Access) [PHASE 4 COMPLETE]
    ↓
Streamlit (Technician Dashboard) [PHASE 5 COMPLETE]
```

---

## 2. Team Boundaries

* **Member 1**: Sensor interfacing, data acquisition, and signal processing (FFT, RMS, time/frequency domain feature extraction).
* **Member 2**: Lightweight 1D Depthwise Separable CNN, multi-label fault classification, RUL regression, and INT8 TinyML deployment on MCU.
* **Member 3 (This Subsystem)**: MQTT topic/payload contracts, Raspberry Pi gateway routing/buffering, InfluxDB time-series storage, FastAPI backend, and Streamlit dashboard visualization.

---

## 3. Repository Structure

```
Industrial_Edge-AI/
├── README.md                      # Project documentation and Member 3 guide
├── docs/                          # Architectural specifications & contracts
│   ├── member3_system_boundary.md # Formal delineation of team responsibilities
│   ├── telemetry_contract.md      # Telemetry schema, field specs, contract versioning
│   ├── mqtt_topics.md             # MQTT topic conventions, QoS, and retention rules
│   ├── data_flow.md               # End-to-end data flow (Phase 1 dummy vs future real MCU)
│   ├── integration_open_decisions.md # Open decisions matrix & team coordination log
│   ├── influxdb_storage_schema.md # InfluxDB storage schema, Line Protocol & Flux recipes
│   ├── fastapi_api.md             # Phase 4 REST API specification and endpoint docs
│   └── dashboard.md               # Phase 5 Dashboard architecture & operator manual
├── config/                        # Configuration loader and settings
│   ├── __init__.py
│   └── settings.py                # Centralized settings with environment variable overrides
├── schemas/                       # Pydantic v2 data models and contract validators
│   ├── __init__.py
│   └── telemetry.py               # CoreTelemetryPayload definition
├── data/                          # Grounded dummy prediction datasets for testing
│   └── dummy_predictions.json
├── gateway/                       # Raspberry Pi gateway & Node-RED routing (Phases 2 & 3)
│   ├── README.md                  # Comprehensive gateway documentation & run guide
│   ├── dummy_publisher.py         # Python MQTT telemetry publisher (Normal & Test modes)
│   ├── line_protocol.py           # InfluxDB Line Protocol serializer for Phase 2 Output 1
│   ├── mosquitto/
│   │   └── mosquitto.conf         # Mosquitto broker configuration (MQTT 5.0/3.1.1, port 1883)
│   └── flows/
│       └── gateway_flow.json      # Node-RED gateway ingestion, validation & InfluxDB write flow
├── scripts/                       # Database setup, initialization & query utilities
│   ├── setup_influxdb_windows.ps1 # Setup and start local InfluxDB on Windows
│   ├── init_influxdb.py           # Idempotent InfluxDB onboarding & bucket creation
│   └── query_influxdb.py          # Direct Flux query utility for verifying stored data
├── backend/                       # FastAPI application & InfluxDB query service (Phase 4)
│   ├── README.md                  # Backend documentation & endpoint reference
│   ├── main.py                    # FastAPI application factory & lifecycle management
│   ├── routes/                    # Route handlers (/health, /api/motors)
│   ├── schemas/                   # Pydantic response models
│   └── services/                  # InfluxDB async query service
├── dashboard/                     # Streamlit visual interface (Phase 5)
│   ├── README.md                  # Dashboard execution guide
│   ├── app.py                     # Streamlit application entrypoint
│   ├── api_client.py              # Dedicated HTTP client for FastAPI REST endpoints
│   └── components.py              # Reusable UI widgets, metrics cards, and charts
└── tests/                         # Automated test suite (104 tests)
    ├── __init__.py
    ├── test_telemetry_contract.py # Telemetry contract schema validation tests
    ├── test_mqtt_publisher.py     # Publisher logic & topic construction tests
    ├── test_influxdb_storage.py   # Unit tests for Line Protocol serialization & storage
    ├── test_influxdb_integration.py # Live InfluxDB integration tests
    ├── test_fastapi_backend.py    # Unit tests for FastAPI endpoints and error handling
    ├── test_fastapi_integration.py# Live integration tests for FastAPI against InfluxDB
    ├── test_dashboard_api_client.py # Unit tests for DashboardApiClient
    └── test_dashboard_components.py # Unit tests for UI components and data transformation
```

---

## 4. Verification & Testing

### Automated Test Suite (104 Tests)
To run all unit and integration tests across the project:
```bash
python -m pytest tests/ -v
```

### End-to-End Software Stack Execution
1. **Start InfluxDB** (Port 8086):
   ```powershell
   .\scripts\setup_influxdb_windows.ps1 -Start -Init
   ```
2. **Start Mosquitto Broker** (Port 1883).
3. **Start Node-RED Gateway** (Port 1880):
   ```bash
   node-red gateway/flows/gateway_flow.json
   ```
4. **Start FastAPI Backend** (Port 8000):
   ```bash
   python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
   ```
5. **Start Streamlit Dashboard** (Port 8501):
   ```bash
   python -m streamlit run dashboard/app.py --server.port 8501
   ```
6. **Publish Telemetry** (Normal Mode):
   ```bash
   python gateway/dummy_publisher.py --mode normal --once
   ```
7. **View Dashboard**:
   Open browser at `http://localhost:8501`.
