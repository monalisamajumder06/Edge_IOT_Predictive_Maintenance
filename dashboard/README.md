# Technician Visualization Dashboard
## Subsystem: IoT + Backend + Dashboard (Member 3)
### Phase: Phase 5 Implementation Complete
### Classification: [PROJECT REQUIREMENT / IMPLEMENTATION DECISION]

---

## 1. Purpose & Overview

This directory contains the user-facing visualization dashboard for plant maintenance technicians and reliability engineers. The application consumes the FastAPI REST API backend (Phase 4) and provides real-time condition monitoring, fleet overviews, historical health and RUL degradation curves, and fault event logs.

## 2. Directory Structure

```
dashboard/
├── __init__.py         # Dashboard package marker
├── app.py              # Primary Streamlit application entrypoint
├── api_client.py       # Encapsulated HTTP client querying FastAPI endpoints
├── components.py       # Reusable UI widgets, metrics cards, and charts
└── README.md           # This execution guide
```

## 3. How to Launch the Dashboard

### Prerequisites
1. InfluxDB running on port 8086 (`.\scripts\setup_influxdb_windows.ps1 -Start`).
2. FastAPI backend running on port 8000 (`python -m uvicorn backend.main:app --port 8000`).

### Launch Command
```powershell
python -m streamlit run dashboard/app.py --server.port 8501
```

Once running, navigate to `http://localhost:8501`.

## 4. Configuration

The dashboard uses `config/settings.py` with environment variable overrides:
- `DASHBOARD_API_URL`: Base URL of the FastAPI REST API (default: `http://localhost:8000`).
- `DASHBOARD_PORT`: Streamlit server port (default: `8501`).
- `DASHBOARD_REFRESH_INTERVAL_SECONDS`: Auto-refresh interval (default: `2`).

## 5. Architectural Guardrails
- Connects **exclusively** to the FastAPI REST API via HTTP/JSON.
- Never connects directly to InfluxDB.
- Never invents unauthorized maintenance thresholds or fault severities.
- Displays empty states cleanly when telemetry records are not present.
