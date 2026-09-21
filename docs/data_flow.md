# End-to-End Data Flow Architecture
## Subsystem: IoT + Backend + Dashboard

---

## 1. Architectural Philosophy: The Invariance Principle

The core architectural invariant of Member 3's subsystem is:

> **The downstream pipeline (Mosquitto → Raspberry Pi Gateway → Node-RED → InfluxDB → FastAPI → Dashboard) operates strictly on the standardized Telemetry Contract and is completely agnostic to whether the producer is a Python dummy generator or a physical edge MCU running TinyML.**

---

## 2. Phase 1 Data Flow (Decoupled Baseline Development)

In Phase 1, development proceeds independently using synthetic prediction generation:

```
┌─────────────────────────────────────────────────────────────┐
│ [TEST COMPONENT]                                            │
│ Dummy Telemetry Generator (Python / data/dummy_predictions) │
│ - Generates contract-compliant JSON                         │
│ - Publishes to `motors/motor_01/prediction`                 │
└──────────────────────────────┬──────────────────────────────┘
                               │ MQTT (QoS 1)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ [MEMBER 3 BACKBONE]                                         │
│ Mosquitto MQTT Broker (Port 1883)                           │
│ - Accepts message over TCP                                  │
│ - Dispatches to subscribers of `motors/+/prediction`        │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ [MEMBER 3 GATEWAY LAYER] (Phase 2 Implemented)              │
│ Raspberry Pi Gateway / Node-RED                             │
│ - Subscribes to `motors/+/prediction` (QoS 1)               │
│ - Parses JSON safely & validates required telemetry schema  │
│ - Rejects malformed / invalid messages to dead-letter log   │
│ - Attaches arrival UTC timestamp if missing                 │
│ - Normalizes valid telemetry for downstream pipeline        │
│ - Buffering: In-flight in Phase 2; persistent queue deferred│
└──────────────────────────────┬──────────────────────────────┘
                               │ Line Protocol Write
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ [MEMBER 3 PERSISTENCE]                                      │
│ InfluxDB Time-Series Database                               │
│ - Bucket: `motor_telemetry`                                 │
│ - Measurement: `predictions`                                │
│ - Tag: `device_id`                                          │
│ - Fields: `health_index`, `rul_hours`, `fault_type`         │
└──────────────────────────────┬──────────────────────────────┘
                               │ Flux / InfluxQL Query
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ [MEMBER 3 APPLICATION API] (Phase 4 Implemented)            │
│ FastAPI Backend Service (Port 8000)                         │
│ - Validates parameters & queries InfluxDB via Flux          │
│ - Distinguishes between service UP and database CONNECTED   │
│ - Exposes REST read-only endpoints:                         │
│   - `GET /health`                                           │
│   - `GET /api/motors` (Fleet overview)                      │
│   - `GET /api/motors/{device_id}/latest`                    │
│   - `GET /api/motors/{device_id}/health`                    │
│   - `GET /api/motors/{device_id}/rul`                       │
│   - `GET /api/motors/{device_id}/faults`                    │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP REST JSON
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ [MEMBER 3 PRESENTATION LAYER] (Phase 5 Implemented)         │
│ Streamlit Dashboard (Port 8501)                             │
│ - Real-time System Status Banner (Operational/Degraded)     │
│ - Dynamic Fleet Overview Table                              │
│ - Selected Motor Current Status Metric Cards                │
│ - Historical Health Degradation Trend Line Chart            │
│ - Historical Remaining Useful Life (RUL) Countdown Chart    │
│ - Historical Fault Diagnostic Log Table                     │
│ - Technician Decision-Support Interface                     │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Implementation Status vs. Future Integration

To ensure full transparency across team boundaries, the status of the platform is formally categorized as follows:

### 3.1 CURRENTLY IMPLEMENTED (Member 3 Complete Software Pipeline):
- **Dummy Prediction Source**: Python-based telemetry publisher (`gateway/dummy_publisher.py`) simulating canonical single and multi-motor predictions conforming strictly to `schemas/telemetry.py`.
- **MQTT Messaging**: Mosquitto MQTT broker on port 1883 enforcing QoS 1 topic hierarchy `motors/{device_id}/prediction`.
- **Edge Gateway Ingestion**: Raspberry Pi Node-RED flow (`gateway/flows/gateway_flow.json`) with JSON parsing, schema validation, timestamp fallback, and line-protocol formatting.
- **Time-Series Storage**: InfluxDB v2 instance on port 8086 persisting measurements in bucket `motor_telemetry`.
- **Analytical REST API**: FastAPI backend service on port 8000 providing read-only REST access with Flux query injection defenses and credential sanitization.
- **Visualization Dashboard**: Streamlit dashboard on port 8501 providing fleet overview, motor inspection, trend charts, and outage handling.

### 3.2 FUTURE INTEGRATION (Members 1 & 2 Dependent):
- **Physical Sensor Data**: Live acquisition from ADXL355 (Vibration), SCT-013 (Current), MLX90614 (Temperature), and INMP441 (Acoustic) hardware sensors (Member 1).
- **Edge DSP & Windowing**: On-device 1-second 50% overlap framing and feature extraction (FFT, Log-Mel, RMS) on ESP32-S3/STM32H7 (Member 1).
- **Edge TinyML Inference**: Live on-device execution of quantized 1D CNN for fault classification and RUL regression (Member 2).
- **Hardware Gateway Deployment**: Physical flashing and bench mounting of Raspberry Pi 4 Model B hardware (Member 3 physical stage).
- **Multi-Label Fault Representation**: When Member 2 finalizes whether multiple concurrent faults will be formatted as an array or probability distribution dictionary, backend responses and dashboard charts will be extended.

> [!NOTE]
> Under the **Invariance Principle**, when physical sensors and TinyML models are connected in future phases, the downstream Member 3 software stack (Mosquitto → Node-RED → InfluxDB → FastAPI → Dashboard) requires **zero architectural redesign**.

---

## 4. Failure Modes & Buffering Strategy

1. **Network Disconnection (Edge MCU to Gateway)**:
   - Edge MCU buffers unsent predictions locally in a circular RAM buffer (if supported by firmware) or discards oldest during prolonged drops.
2. **Phase 2 Gateway Processing & Buffering Boundary**:
   - In Phase 2, Node-RED processes telemetry in-flight.
   - Duplicate messages are accepted and passed through; deduplication is handled via InfluxDB series timestamp idempotency in Phase 3.
3. **Gateway to Database Disconnection (Phase 3 Implemented)**:
   - In Phase 3, Node-RED intercepts network write failures via a scoped Catch node and error disposition switch, logging `[INFLUXDB UNAVAILABLE]` without crashing Node-RED.
   - Durable disk-backed queueing (e.g. SQLite buffer) is documented as `[RECOMMENDATION / FUTURE WORK]`.
4. **Database Write Failure (Phase 3 Implemented)**:
   - InfluxDB non-204 responses (e.g., 401 Unauthorized, 404 Bucket Not Found) are caught and logged to `[INFLUXDB WRITE FAILED]` with full diagnostic context.
5. **Backend Outage or Degradation (Phase 4 & 5 Implemented)**:
   - FastAPI `/health` endpoint detects and reports InfluxDB disconnection with HTTP 503 DEGRADED.
   - Streamlit dashboard intercepts 503 degraded states and connection drops, notifying the technician visually without crashing or displaying fabricated values.
