# FastAPI REST API Specification
## Subsystem: IoT + Backend + Dashboard (Member 3)
### Phase: Phase 4 Implementation Baseline
### Classification: [PROJECT REQUIREMENT / IMPLEMENTATION DECISION]

---

## 1. Overview & Architecture

The FastAPI backend provides a lightweight, performant, read-only REST API exposing motor predictive maintenance telemetry stored in InfluxDB v2. It acts as the data provider for the future Phase 5 visualization dashboard (Streamlit / Grafana) and remote client tools.

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
                      │
                      ▼ Flux Query (HTTP POST /api/v2/query)
           [FastAPI Backend Service]  <── (THIS PHASE)
                      │
                      ▼ HTTP REST JSON
           [Phase 5 Dashboard Client]
```

All endpoints are strictly **read-only**. Data mutation or deletion is prohibited at the API layer to preserve audit integrity of industrial telemetry.

---

## 2. Configuration & Environment

The backend consumes configuration dynamically from `config/settings.py` with environment variable overrides:

| Environment Variable | Default Value | Description |
| :--- | :--- | :--- |
| `BACKEND_HOST` | `0.0.0.0` | Bind host address |
| `BACKEND_PORT` | `8000` | Bind port number |
| `BACKEND_DEBUG` | `True` | FastAPI debug mode flag |
| `BACKEND_LOG_LEVEL` | `INFO` | Application log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `INFLUXDB_URL` | `http://localhost:8086` | Base URL of InfluxDB v2 instance |
| `INFLUXDB_ORG` | `industrial_iot` | InfluxDB organization name |
| `INFLUXDB_BUCKET` | `motor_telemetry` | Target time-series bucket |
| `INFLUXDB_TOKEN` | `my-secure-placeholder-token` | InfluxDB API read/write token |

---

## 3. Endpoints Specification

### 3.1 Health Check: `GET /health`
* **Purpose**: Verify service vitality and database reachability.
* **Classification**:
  - `[PROJECT REQUIREMENT]`: Must clearly distinguish between API service running and InfluxDB database reachability. Must never falsely report full health when database is down.
  - `[IMPLEMENTATION DECISION]`: Returns HTTP 200 when all healthy; returns HTTP 503 when InfluxDB is unreachable.

#### Example Request:
```http
GET /health HTTP/1.1
Host: localhost:8000
```

#### Example Response (200 OK - Healthy):
```json
{
  "status": "HEALTHY",
  "service": "UP",
  "database": "CONNECTED",
  "timestamp": "2026-09-13T14:15:00.000000Z",
  "details": {
    "database_connected": true,
    "database_status": "CONNECTED",
    "url": "http://localhost:8086"
  }
}
```

#### Example Response (503 Service Unavailable - Database Down):
```json
{
  "status": "DEGRADED",
  "service": "UP",
  "database": "UNAVAILABLE",
  "timestamp": "2026-09-13T14:15:00.000000Z",
  "details": {
    "error": "InfluxDB service at http://localhost:8086 is unreachable."
  }
}
```

---

### 3.2 Fleet Overview: `GET /api/motors`
* **Purpose**: Discover all monitored motors and retrieve their latest recorded state.
* **Response Model**: `FleetOverviewResponse`

#### Example Request:
```http
GET /api/motors HTTP/1.1
Host: localhost:8000
```

#### Example Response (200 OK):
```json
{
  "motors": [
    {
      "device_id": "motor_01",
      "fault_type": "Inner_Race",
      "health_index": 0.88,
      "rul_hours": 420.0,
      "timestamp": "2026-09-13T14:00:00Z"
    },
    {
      "device_id": "motor_02",
      "fault_type": "Normal",
      "health_index": 0.97,
      "rul_hours": 950.0,
      "timestamp": "2026-09-13T11:12:17.068Z"
    }
  ],
  "total_motors": 2,
  "timestamp": "2026-09-13T14:15:02.123456Z"
}
```

---

### 3.3 Latest Telemetry for One Motor: `GET /api/motors/{device_id}/latest`
* **Purpose**: Retrieve the single most recent telemetry observation for a specific motor.
* **Path Parameters**:
  - `device_id` (string, required): Motor identifier (e.g. `motor_01`). Must match `^[a-zA-Z0-9_\-]+$`.
* **Response Model**: `MotorTelemetryResponse`

#### Example Request:
```http
GET /api/motors/motor_01/latest HTTP/1.1
Host: localhost:8000
```

#### Example Response (200 OK):
```json
{
  "device_id": "motor_01",
  "fault_type": "Inner_Race",
  "health_index": 0.88,
  "rul_hours": 420.0,
  "timestamp": "2026-09-13T14:00:00Z"
}
```

#### Error Behavior:
* `400 Bad Request`: If `device_id` contains invalid characters or is empty.
* `404 Not Found`: If no telemetry records exist for `device_id`.
  ```json
  {
    "error": "HTTP_ERROR",
    "detail": "Motor 'motor_99' not found or has no telemetry records.",
    "status_code": 404,
    "timestamp": "2026-09-13T14:15:05.000000Z"
  }
  ```

---

### 3.4 Historical Telemetry: `GET /api/motors/{device_id}/history`
* **Purpose**: Retrieve chronological telemetry observations for multi-metric dashboard charts.
* **Path Parameters**:
  - `device_id` (string, required): Motor identifier.
* **Query Parameters**:
  - `start` (string, optional, default: `"-24h"`): Start of time range. Accepts relative duration (e.g. `"-1h"`, `"-24h"`, `"-7d"`, `"-30d"`) or ISO-8601 UTC timestamp (e.g. `"2026-09-13T00:00:00Z"`).
  - `stop` (string, optional): End of time range. Accepts `"now()"` or ISO-8601 UTC timestamp.
* **Response Model**: `List[MotorTelemetryResponse]`

#### Example Request:
```http
GET /api/motors/motor_01/history?start=-1h HTTP/1.1
Host: localhost:8000
```

#### Example Response (200 OK):
```json
[
  {
    "device_id": "motor_01",
    "fault_type": "Inner_Race",
    "health_index": 0.85,
    "rul_hours": 410.0,
    "timestamp": "2026-09-13T11:00:54.430Z"
  },
  {
    "device_id": "motor_01",
    "fault_type": "Inner_Race",
    "health_index": 0.88,
    "rul_hours": 420.0,
    "timestamp": "2026-09-13T14:00:00Z"
  }
]
```

---

### 3.5 Health Index Trend: `GET /api/motors/{device_id}/health`
* **Purpose**: Retrieve historical health index values for dedicated degradation plotting.
* **Response Model**: `List[HealthObservation]`

#### Example Request:
```http
GET /api/motors/motor_01/health?start=-24h HTTP/1.1
Host: localhost:8000
```

#### Example Response (200 OK):
```json
[
  {
    "timestamp": "2026-09-13T11:00:54.430Z",
    "health_index": 0.85
  },
  {
    "timestamp": "2026-09-13T14:00:00Z",
    "health_index": 0.88
  }
]
```

---

### 3.6 RUL Hours Trend: `GET /api/motors/{device_id}/rul`
* **Purpose**: Retrieve historical Remaining Useful Life estimations for countdown / trend plotting.
* **Response Model**: `List[RulObservation]`

#### Example Request:
```http
GET /api/motors/motor_01/rul?start=-24h HTTP/1.1
Host: localhost:8000
```

#### Example Response (200 OK):
```json
[
  {
    "timestamp": "2026-09-13T11:00:54.430Z",
    "rul_hours": 410.0
  },
  {
    "timestamp": "2026-09-13T14:00:00Z",
    "rul_hours": 420.0
  }
]
```

---

### 3.7 Fault Classification History: `GET /api/motors/{device_id}/faults`
* **Purpose**: Retrieve historical diagnostic classifications to track fault progression.
* **Query Parameters**:
  - `start` (string, optional, default: `"-7d"`): Start of time range.
  - `stop` (string, optional): End of time range.
* **Response Model**: `List[FaultObservation]`

#### Example Request:
```http
GET /api/motors/motor_01/faults?start=-7d HTTP/1.1
Host: localhost:8000
```

#### Example Response (200 OK):
```json
[
  {
    "timestamp": "2026-09-13T11:00:54.430Z",
    "fault_type": "Inner_Race"
  },
  {
    "timestamp": "2026-09-13T11:01:43.880Z",
    "fault_type": "Synthetic_Test_Fault_A"
  },
  {
    "timestamp": "2026-09-13T14:00:00Z",
    "fault_type": "Inner_Race"
  }
]
```

---

## 4. Error Handling & Security

1. **Structured Error Schema**:
   All non-200 responses return a consistent JSON schema:
   ```json
   {
     "error": "HTTP_ERROR",
     "detail": "Description of the error",
     "status_code": 400,
     "timestamp": "2026-09-13T14:15:00.000000Z"
   }
   ```
2. **HTTP Status Codes**:
   - `400 Bad Request`: Invalid parameter format (`device_id` invalid, `start`/`stop` malformed).
   - `404 Not Found`: Motor does not exist or has no stored telemetry.
   - `422 Unprocessable Entity`: Schema/type validation failures.
   - `502 Bad Gateway`: InfluxDB returned an unexpected error on query execution.
   - `503 Service Unavailable`: InfluxDB is down or unreachable.
3. **Flux Query Injection Protection**:
   All dynamic inputs are strictly validated against strict regexes before interpolation into Flux queries. Invalid characters or SQL/Flux syntax triggers an immediate `400 Bad Request`.
4. **Credential Redaction**:
   All exception handlers actively sanitize error strings to ensure the `INFLUXDB_TOKEN` is never leaked in HTTP response bodies or public logs.

---

## 5. Dashboard Consumption Guide (Phase 5 Preparation)

When building the Phase 5 dashboard (Streamlit / Grafana):

1. **Fleet Status Card**:
   - Call `GET /api/motors` periodically (e.g. every 2 seconds).
   - Display a grid of motor cards showing current health index, RUL countdown, and fault indicator.
2. **Individual Motor Deep-Dive**:
   - When a technician clicks a motor card (e.g. `motor_01`), fetch `GET /api/motors/motor_01/latest` for real-time telemetry gauges.
   - Fetch `GET /api/motors/motor_01/health?start=-24h` for the 24-hour health degradation line chart.
   - Fetch `GET /api/motors/motor_01/rul?start=-24h` for the RUL projection curve.
   - Fetch `GET /api/motors/motor_01/faults?start=-7d` for a historical fault event log table.
3. **Database Outage Graceful Handling**:
   - Call `GET /health` on startup. If status is `503`, show a clear visual banner: "Database Unavailable - Check InfluxDB Connection".

---

## 6. How to Start the Backend

### Local Development / Windows:
```powershell
# In terminal with activated environment:
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

### Raspberry Pi 4 Gateway (Linux / Debian):
```bash
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 2
```

---

## 7. Future Extensions (Out of Scope for Phase 4)

The following items are intentional future extensions to be handled in subsequent phases:
1. **TinyML Real Inferences**:
   When Member 2 deploys real MCU inference (replacing synthetic dummy predictions), the FastAPI layer requires **zero modifications** due to the Invariance Principle.
2. **Multi-Label Fault Representation**:
   When Member 2 finalizes whether multiple concurrent faults will be formatted as an array (`fault_types`) or probability dictionary (`fault_probabilities`), new auxiliary fields can be incorporated into `MotorTelemetryResponse` without breaking backwards compatibility.
3. **Browser Cross-Origin Access (CORS)**:
   Speculative CORS has been excluded. If the Phase 5 dashboard architecture requires browser direct cross-origin calls, minimal CORS middleware can be configured in `backend/main.py`.
4. **Authentication & Role-Based Access (RBAC)**:
   For local bench and gateway environments, authentication is omitted. Production plant deployments may incorporate JWT tokens or reverse-proxy authentication (NGINX).
5. **Additional Sensor Metrics**:
   If raw features (RMS, FFT spectrum, temperature) are persisted in InfluxDB, dedicated sub-endpoints (e.g. `/api/motors/{id}/vibration`) can be added following the same service abstraction pattern.
