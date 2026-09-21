# FastAPI Application Backend
## Subsystem: IoT + Backend + Dashboard (Member 3)
### Classification: [PHASE 4 IMPLEMENTED]

---

## 1. Purpose
The FastAPI backend service exposes read-only REST endpoints querying motor predictive maintenance telemetry directly from InfluxDB v2. It provides a stable, decoupled data-access interface for the future Phase 5 visualization dashboard (Streamlit / Grafana) and plant technicians.

---

## 2. Directory Structure
```
backend/
├── __init__.py           # Package version and metadata
├── main.py               # Application factory, lifespan, exception handlers, route mounting
├── README.md             # Subsystem documentation & startup instructions
├── routes/
│   ├── __init__.py
│   ├── deps.py           # Dependency injection for InfluxDBService
│   ├── health.py         # GET /health endpoint
│   └── motors.py         # GET /api/motors/* endpoints
├── schemas/
│   ├── __init__.py
│   └── responses.py      # Pydantic response models
└── services/
    ├── __init__.py
    └── influx_service.py # InfluxDB async query client, CSV parser, and injection defense
```

---

## 3. Endpoints Overview

| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | System health check (API status and InfluxDB reachability) |
| `GET` | `/api/motors` | Fleet overview: latest telemetry across all detected motors |
| `GET` | `/api/motors/{device_id}/latest` | Most recent telemetry observation for one motor |
| `GET` | `/api/motors/{device_id}/history` | Historical telemetry records (`start`, `stop`) |
| `GET` | `/api/motors/{device_id}/health` | Historical health index trend observations for plotting |
| `GET` | `/api/motors/{device_id}/rul` | Historical RUL hours trend observations for plotting |
| `GET` | `/api/motors/{device_id}/faults` | Historical fault classification events |

Interactive OpenAPI documentation is available at `/docs` and ReDoc at `/redoc`.

---

## 4. Running the Backend Service

### Local Development / Windows
Ensure InfluxDB is running, then launch via uvicorn:
```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

### Raspberry Pi 4 Gateway (Debian Bookworm)
```bash
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 2
```

---

## 5. Configuration
Configuration parameters are inherited from `config/settings.py` via environment variables:
- `INFLUXDB_URL`: URL of InfluxDB v2 instance (default: `http://localhost:8086`)
- `INFLUXDB_ORG`: Organization name (default: `industrial_iot`)
- `INFLUXDB_BUCKET`: Time-series bucket (default: `motor_telemetry`)
- `INFLUXDB_TOKEN`: Authentication token
- `BACKEND_HOST`: Server bind address (default: `0.0.0.0`)
- `BACKEND_PORT`: Server bind port (default: `8000`)
- `BACKEND_DEBUG`: Debug flag (default: `True`)
- `BACKEND_LOG_LEVEL`: Logging verbosity (default: `INFO`)
