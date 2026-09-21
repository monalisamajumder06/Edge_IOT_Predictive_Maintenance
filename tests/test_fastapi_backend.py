"""Unit Test Suite for FastAPI Backend and REST API.

Subsystem: IoT + Backend + Dashboard (Member 3)
Phase: Phase 4 Implementation
Classification: [IMPLEMENTATION DECISION]

Tests cover:
- Route availability and OpenAPI schema validation
- Health check endpoint (healthy and degraded / 503 states)
- Motor latest telemetry retrieval
- Motor historical telemetry retrieval
- Health index trend observations
- RUL hours trend observations
- Fault history observations
- Fleet overview across multiple motors
- Motor not found error handling (404)
- Parameter validation (device_id, time-range syntax) (400)
- InfluxDB outage handling (503)
- InfluxDB query failure handling (502)
- Zero credential / token leakage in error responses
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.routes.deps import get_influx_service
from backend.schemas.responses import (
    FaultObservation,
    HealthObservation,
    MotorTelemetryResponse,
    RulObservation,
)
from backend.services.influx_service import (
    InfluxDBQueryError,
    InfluxDBService,
    InfluxDBUnavailableError,
)
from config.settings import get_settings


@pytest.fixture
def mock_service():
    """Create a mock InfluxDBService instance for dependency override."""
    service = AsyncMock(spec=InfluxDBService)
    return service


@pytest.fixture
def client(mock_service):
    """Create a TestClient with dependency overrides applied."""
    app.dependency_overrides[get_influx_service] = lambda: mock_service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# =============================================================================
# 1. ROUTE AVAILABILITY & OPENAPI SCHEMA
# =============================================================================
class TestRouteAvailability:
    """Verifies that all required endpoints are registered in FastAPI."""

    def test_openapi_schema_available(self, client):
        """Verify OpenAPI documentation JSON is served correctly."""
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert "paths" in schema
        paths = schema["paths"]

        # Ensure all required Phase 4 endpoints are registered
        assert "/health" in paths
        assert "/api/motors" in paths
        assert "/api/motors/{device_id}/latest" in paths
        assert "/api/motors/{device_id}/history" in paths
        assert "/api/motors/{device_id}/health" in paths
        assert "/api/motors/{device_id}/rul" in paths
        assert "/api/motors/{device_id}/faults" in paths

    def test_docs_page_available(self, client):
        """Verify Swagger UI docs page is accessible."""
        resp = client.get("/docs")
        assert resp.status_code == 200
        assert "SwaggerUIBundle" in resp.text


# =============================================================================
# 2. HEALTH CHECK ENDPOINT
# =============================================================================
class TestHealthEndpoint:
    """Tests /health behavior distinguishing API from DB reachability."""

    def test_health_healthy_returns_200(self, client, mock_service):
        """Verify 200 OK when both API and InfluxDB are operational."""
        mock_service.check_health.return_value = {
            "database_connected": True,
            "database_status": "CONNECTED",
            "url": "http://localhost:8086",
        }
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "HEALTHY"
        assert data["service"] == "UP"
        assert data["database"] == "CONNECTED"
        assert "timestamp" in data

    def test_health_db_unavailable_returns_503(self, client, mock_service):
        """Verify 503 Service Unavailable when InfluxDB is down."""
        mock_service.check_health.side_effect = InfluxDBUnavailableError(
            "InfluxDB service at http://localhost:8086 is unreachable."
        )
        resp = client.get("/health")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "DEGRADED"
        assert data["service"] == "UP"
        assert data["database"] == "UNAVAILABLE"

    def test_health_db_check_reports_unhealthy_returns_503(self, client, mock_service):
        """Verify 503 when InfluxDB responds but reports unhealthy."""
        mock_service.check_health.return_value = {
            "database_connected": False,
            "database_status": "UNAVAILABLE",
            "status_code": 500,
        }
        resp = client.get("/health")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "DEGRADED"
        assert data["database"] == "UNAVAILABLE"


# =============================================================================
# 3. LATEST MOTOR TELEMETRY ENDPOINT
# =============================================================================
class TestMotorLatestEndpoint:
    """Tests GET /api/motors/{device_id}/latest."""

    def test_get_motor_latest_success(self, client, mock_service):
        """Verify returning latest motor telemetry matching contract."""
        now = datetime(2026, 9, 13, 14, 0, 0, tzinfo=timezone.utc)
        mock_service.get_motor_latest.return_value = MotorTelemetryResponse(
            device_id="motor_01",
            fault_type="Inner_Race",
            health_index=0.88,
            rul_hours=420.0,
            timestamp=now,
        )

        resp = client.get("/api/motors/motor_01/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["device_id"] == "motor_01"
        assert data["fault_type"] == "Inner_Race"
        assert data["health_index"] == 0.88
        assert data["rul_hours"] == 420.0
        assert data["timestamp"] == "2026-09-13T14:00:00Z"

    def test_get_motor_latest_not_found_returns_404(self, client, mock_service):
        """Verify 404 when motor has no stored telemetry."""
        mock_service.get_motor_latest.return_value = None

        resp = client.get("/api/motors/motor_unknown/latest")
        assert resp.status_code == 404
        data = resp.json()
        assert "not found" in data["detail"].lower()
        assert data["status_code"] == 404

    def test_get_motor_latest_invalid_device_id_returns_400(self, client):
        """Verify 400 when device_id contains invalid characters."""
        resp = client.get("/api/motors/motor;drop_table/latest")
        assert resp.status_code == 400
        data = resp.json()
        assert "invalid device_id" in data["detail"].lower()


# =============================================================================
# 4. HISTORICAL TELEMETRY ENDPOINT
# =============================================================================
class TestMotorHistoryEndpoint:
    """Tests GET /api/motors/{device_id}/history."""

    def test_get_motor_history_success(self, client, mock_service):
        """Verify returning historical records for a motor."""
        t1 = datetime(2026, 9, 13, 11, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 13, 12, 0, 0, tzinfo=timezone.utc)
        mock_service.get_motor_history.return_value = [
            MotorTelemetryResponse(
                device_id="motor_01",
                fault_type="Inner_Race",
                health_index=0.85,
                rul_hours=410.0,
                timestamp=t1,
            ),
            MotorTelemetryResponse(
                device_id="motor_01",
                fault_type="Inner_Race",
                health_index=0.88,
                rul_hours=420.0,
                timestamp=t2,
            ),
        ]

        resp = client.get("/api/motors/motor_01/history?start=-24h")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["health_index"] == 0.85
        assert data[1]["health_index"] == 0.88

    def test_get_motor_history_invalid_time_range_returns_400(self, client):
        """Verify 400 when time range parameter is invalid syntax."""
        resp = client.get("/api/motors/motor_01/history?start=invalid_time_range")
        assert resp.status_code == 400
        data = resp.json()
        assert "invalid start format" in data["detail"].lower()

    def test_get_motor_history_motor_not_found_returns_404(self, client, mock_service):
        """Verify 404 when history is requested for non-existent motor."""
        mock_service.get_motor_history.return_value = []
        mock_service.get_motor_latest.return_value = None

        resp = client.get("/api/motors/motor_nonexistent/history")
        assert resp.status_code == 404


# =============================================================================
# 5. HEALTH AND RUL TREND ENDPOINTS
# =============================================================================
class TestTrendEndpoints:
    """Tests GET /api/motors/{device_id}/health and /rul."""

    def test_get_health_trend_success(self, client, mock_service):
        """Verify health trend observations return timestamp + health_index."""
        t1 = datetime(2026, 9, 13, 11, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 13, 12, 0, 0, tzinfo=timezone.utc)
        mock_service.get_motor_health_trend.return_value = [
            HealthObservation(timestamp=t1, health_index=0.85),
            HealthObservation(timestamp=t2, health_index=0.88),
        ]

        resp = client.get("/api/motors/motor_01/health?start=-24h")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["health_index"] == 0.85
        assert data[1]["health_index"] == 0.88
        assert "timestamp" in data[0]

    def test_get_rul_trend_success(self, client, mock_service):
        """Verify RUL trend observations return timestamp + rul_hours."""
        t1 = datetime(2026, 9, 13, 11, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 13, 12, 0, 0, tzinfo=timezone.utc)
        mock_service.get_motor_rul_trend.return_value = [
            RulObservation(timestamp=t1, rul_hours=410.0),
            RulObservation(timestamp=t2, rul_hours=420.0),
        ]

        resp = client.get("/api/motors/motor_01/rul?start=-24h")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["rul_hours"] == 410.0
        assert data[1]["rul_hours"] == 420.0

    def test_get_fault_history_success(self, client, mock_service):
        """Verify fault history observations return timestamp + fault_type."""
        t1 = datetime(2026, 9, 13, 11, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 13, 12, 0, 0, tzinfo=timezone.utc)
        mock_service.get_motor_fault_history.return_value = [
            FaultObservation(timestamp=t1, fault_type="Normal"),
            FaultObservation(timestamp=t2, fault_type="Inner_Race"),
        ]

        resp = client.get("/api/motors/motor_01/faults?start=-7d")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["fault_type"] == "Normal"
        assert data[1]["fault_type"] == "Inner_Race"


# =============================================================================
# 6. FLEET OVERVIEW ENDPOINT
# =============================================================================
class TestFleetEndpoint:
    """Tests GET /api/motors."""

    def test_get_fleet_success(self, client, mock_service):
        """Verify fleet overview returns latest state for all detected motors."""
        t_base = datetime(2026, 9, 13, 14, 0, 0, tzinfo=timezone.utc)
        mock_service.get_fleet_latest.return_value = [
            MotorTelemetryResponse(
                device_id="motor_01",
                fault_type="Inner_Race",
                health_index=0.88,
                rul_hours=420.0,
                timestamp=t_base,
            ),
            MotorTelemetryResponse(
                device_id="motor_02",
                fault_type="Normal",
                health_index=0.97,
                rul_hours=950.0,
                timestamp=t_base,
            ),
        ]

        resp = client.get("/api/motors")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_motors"] == 2
        assert len(data["motors"]) == 2
        assert data["motors"][0]["device_id"] == "motor_01"
        assert data["motors"][1]["device_id"] == "motor_02"


# =============================================================================
# 7. INFLUXDB OUTAGE & ERROR HANDLING
# =============================================================================
class TestDatabaseOutageAndFailureHandling:
    """Tests graceful handling when InfluxDB fails or is unavailable."""

    def test_influxdb_unavailable_returns_503(self, client, mock_service):
        """Verify routes return 503 when InfluxDB cannot be reached."""
        mock_service.get_motor_latest.side_effect = InfluxDBUnavailableError(
            "Failed to connect to InfluxDB."
        )

        resp = client.get("/api/motors/motor_01/latest")
        assert resp.status_code == 503
        data = resp.json()
        assert "failed to connect" in data["detail"].lower()

    def test_influxdb_query_failure_returns_502(self, client, mock_service):
        """Verify routes return 502 when InfluxDB rejects a query."""
        mock_service.get_fleet_latest.side_effect = InfluxDBQueryError(
            "InfluxDB query failed (400): syntax error"
        )

        resp = client.get("/api/motors")
        assert resp.status_code == 502
        data = resp.json()
        assert "syntax error" in data["detail"].lower()


# =============================================================================
# 8. SECURITY & CREDENTIAL LEAKAGE DEFENSE
# =============================================================================
class TestSecurityAndLeakageDefense:
    """Verify security controls and credential protection."""

    def test_token_is_never_leaked_in_error_responses(self, client, mock_service):
        """Verify sensitive InfluxDB authentication tokens are never exposed in error responses."""
        settings = get_settings()
        secret_token = settings.influxdb_token

        # Simulate exception containing the secret token
        mock_service.get_motor_latest.side_effect = InfluxDBQueryError(
            f"Query failed with token={secret_token} unauthorized"
        )

        resp = client.get("/api/motors/motor_01/latest")
        # Token must be redacted and never present in response text
        assert secret_token not in resp.text
        assert "[REDACTED]" in resp.text or secret_token not in resp.text
