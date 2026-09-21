# Technician Visualization Dashboard Specification
## Subsystem: IoT + Backend + Dashboard (Member 3)
### Phase: Phase 5 Implementation Baseline
### Classification: [PROJECT REQUIREMENT / IMPLEMENTATION DECISION]

---

## 1. Overview & Architecture

The **Technician Visualization Dashboard** provides a lightweight, intuitive, and robust user interface for plant maintenance technicians and reliability engineers. It enables real-time condition monitoring, degradation tracking, and Remaining Useful Life (RUL) visibility across monitored industrial electric motors.

### 1.1 Invariance Principle & Data Flow
```
[Phase 1 Dummy / Phase 2+ Edge TinyML MCU]
                      │
                      ▼ MQTT (motors/{device_id}/prediction)
               [Mosquitto Broker]
                      │
                      ▼
        [Node-RED Gateway Normalization]
                      │ Line Protocol Write
                      ▼
           [InfluxDB v2 Database]
           (Bucket: motor_telemetry)
                      │ Flux Query
                      ▼
           [FastAPI Backend Service]
                      │ HTTP REST JSON
                      ▼
        [Streamlit Dashboard Application] <── (THIS PHASE)
                      │
                      ▼
     [Plant Technician / Maintenance Decision]
```

### 1.2 Strict Scope Boundaries
- **No Direct Database Access**: The dashboard connects exclusively to the read-only FastAPI REST API (HTTP/JSON). It never connects directly to InfluxDB.
- **No Invented Maintenance Thresholds**: The dashboard does not fabricate arbitrary threshold classifications (e.g., `health < 0.5 = Critical`) or color-code health indexes based on ungrounded assumptions.
- **No Invented Fault Severities**: Fault labels (e.g., `Inner_Race`, `Normal`, `Synthetic_Test_Fault_A`) are displayed verbatim as reported by the backend without speculative severity categorizations.
- **No Data Fabrication**: If telemetry records or historical observations are missing, clear informative empty states are displayed rather than synthetic zeros or interpolated projections.

---

## 2. Technology Selection

- **Framework**: **Streamlit** (v1.63.0+, Python-native).
- **Rationale**:
  - Python-native: Seamless integration with existing project data contracts and Pydantic schemas.
  - Zero Node.js/frontend build chain: Easily runs on both local Windows/macOS workstations and the target Raspberry Pi 4 edge gateway.
  - Built-in reactive widgets: Metrics cards, dynamic dataframes, and interactive time-series line charts with minimal memory overhead.

---

## 3. Installation & Configuration

### 3.1 Dependencies
Ensure required dependencies are installed:
```powershell
pip install streamlit requests pandas altair
```

### 3.2 Configuration Parameters
The dashboard consumes configuration dynamically from `config/settings.py` and supports environment variable overrides:

| Setting / Variable | Default Value | Description |
| :--- | :--- | :--- |
| `DASHBOARD_API_URL` | `http://localhost:8000` | Base URL of the FastAPI REST backend service |
| `DASHBOARD_PORT` | `8501` | Streamlit web server binding port |
| `DASHBOARD_REFRESH_INTERVAL_SECONDS` | `2` | Suggested live polling refresh interval |

---

## 4. How to Start the Dashboard

### 4.1 Local Development (Windows):
```powershell
# In terminal with activated Python environment:
python -m streamlit run dashboard/app.py --server.port 8501
```

### 4.2 Raspberry Pi 4 Gateway (Linux / Debian):
```bash
# In headless mode on edge gateway:
python3 -m streamlit run dashboard/app.py --server.port 8501 --server.headless true --server.address 0.0.0.0
```

Access the dashboard via web browser at `http://localhost:8501` (or `http://<gateway-ip>:8501`).

---

## 5. Available Views & User Controls

### 5.1 System Vitality Banner
At the top of the interface, the dashboard displays the live health state retrieved from `GET /health`:
- 🟢 **Operational**: Backend is `UP` and InfluxDB is `CONNECTED`.
- 🟡 **Degraded**: Backend is `UP` but InfluxDB is `UNAVAILABLE` (e.g., database service down). Live queries show warnings.
- 🔴 **Offline**: FastAPI service is completely unreachable. The dashboard displays clear troubleshooting instructions and gracefully halts queries.

### 5.2 Global Controls (Sidebar)
- **🔄 Refresh Data**: Instantly re-queries FastAPI for fresh fleet and motor telemetry.
- **⏳ Time Range Selector**: Allows selecting the historical trend window:
  - `Last 1 Hour` (`-1h`)
  - `Last 24 Hours` (`-24h`) [Default]
  - `Last 7 Days` (`-7d`)
  - `Last 30 Days` (`-30d`)
- **⏱️ Auto-Refresh**: Optional toggle with configurable polling intervals (5 to 60 seconds) without aggressive API hammering.
- **🔌 Backend Connection**: Displays active `DASHBOARD_API_URL`.

### 5.3 Fleet Overview View
Discovers all active motors dynamically from `GET /api/motors`:
- Displays a summary table of all detected motors:
  - `Device ID`
  - `Fault Classification`
  - `Health Index`
  - `RUL (Hours)`
  - `Last Telemetry (UTC)`
- Automatically adapts to any number of motors (e.g. `motor_01`, `motor_02`, etc.) without hardcoding.

### 5.4 Motor Detail Deep-Dive
When a technician selects a motor asset from the dynamic selector:
1. **Current Telemetry Metrics**:
   - `Fault Classification`: Verbatim diagnostic label.
   - `Health Index`: Numerical value formatted to 2 decimal places.
   - `Estimated RUL`: Operating hours countdown.
   - `Last Updated`: UTC timestamp formatted for readability.
2. **Health Index Trend Chart**:
   - Time-series plot of historical `health_index` observations.
   - Gracefully shows *"No historical health data available"* if no observations exist.
3. **Remaining Useful Life (RUL) Trend Chart**:
   - Time-series plot of historical `rul_hours` countdown observations.
   - Gracefully shows *"No historical RUL data available"* if no observations exist.
4. **Fault Classification History Table**:
   - Chronological log of diagnostic events (`Timestamp (UTC)` and `Fault Classification`).

---

## 6. Error Handling & Resilience

1. **Backend Service Offline**:
   - Catches connection errors without crashing.
   - Displays clear troubleshooting banner directing the operator to verify `uvicorn` and port configuration.
2. **Database Outage (HTTP 503)**:
   - Identifies degraded mode via `GET /health`.
   - Informs operator that InfluxDB is unreachable while keeping the UI accessible.
3. **Nonexistent / Empty Motor (HTTP 404)**:
   - Displays clear informational notification: *"Motor has no telemetry records"*.
4. **Empty Historical Window**:
   - Informs technician cleanly instead of drawing empty or misleading charts.
5. **Credential Security**:
   - All client-side exception handlers sanitize responses to ensure InfluxDB tokens or sensitive paths are never shown in technician alerts.

---

## 7. End-to-End Demonstration Procedure

To run and verify the full pipeline end-to-end:

1. **Start InfluxDB**:
   ```powershell
   .\scripts\setup_influxdb_windows.ps1 -Start
   ```
2. **Start Mosquitto MQTT Broker**:
   Ensure broker is running on port 1883.
3. **Start Node-RED**:
   Ensure Node-RED is running with `gateway/flows/gateway_flow.json` deployed.
4. **Start FastAPI Backend**:
   ```powershell
   python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
   ```
5. **Start Streamlit Dashboard**:
   ```powershell
   python -m streamlit run dashboard/app.py --server.port 8501
   ```
6. **Publish Test Telemetry**:
   ```powershell
   python gateway/dummy_publisher.py --mode normal --once
   ```
7. **Observe Dashboard**:
   - Verify `motor_01` and `motor_02` appear in the Fleet Overview.
   - Select `motor_01` to view latest telemetry and degradation trends.
   - Select `motor_02` to verify distinct telemetry and independent historical curves.

---

## 8. Raspberry Pi 4 Considerations & Future Work

1. **Resource Footprint**:
   - Streamlit + FastAPI + InfluxDB v2 easily operate within the 4GB/8GB RAM envelope of a Raspberry Pi 4 Model B.
   - Keep auto-refresh intervals at $\ge 5\text{s}$ to minimize CPU spikes on ARM Cortex-A72 cores.
2. **Future Enhancements**:
   - **Multi-Label Fault Probabilities**: When Member 2 finalizes multi-label predictions, add bar charts displaying fault likelihood distributions.
   - **Maintenance Threshold Rules**: If formalized in subsequent project phases, add configurable amber/red threshold indicators.
   - **Alternative Grafana Export**: For industrial control rooms preferring Grafana, datasource configuration connecting to InfluxDB can be provisioned.
