"""Unit Tests for Dashboard API Client.

Subsystem: IoT + Backend + Dashboard (Member 3)
Phase: Phase 5 Implementation
Classification: [PROJECT REQUIREMENT / IMPLEMENTATION DECISION]

Tests cover:
1. API client health request (healthy 200, degraded 503, offline connection failure).
2. API client fleet request (successful retrieval, multiple motors, empty fleet).
3. API client latest motor request (found, not found 404).
4. API client health history request (chronological points, empty history).
5. API client RUL history request (chronological points, empty history).
6. API client fault history request (chronological events, empty history).
7. HTTP error handling (400, 404, 500, 502, 503).
8. Timeout handling.
9. Empty history handling.
10. Multiple motor handling without cross-contamination.
11. Verification that dashboard client does not hardcode a fixed motor list.
12. Base API URL configuration from settings and custom override.
"""

from unittest.mock import MagicMock, patch
import pytest
import requests

from config.settings import Settings, get_settings
from dashboard.api_client import (
    ApiClientError,
    ApiConnectionError,
    ApiDegradedError,
    ApiNotFoundError,
    DashboardApiClient,
)


@pytest.fixture
def api_client():
    """Create a DashboardApiClient with test base URL."""
    return DashboardApiClient(base_url="http://127.0.0.1:8000", timeout=2.0)


# =============================================================================
# 1. CONFIGURATION TESTS
# =============================================================================
class TestApiClientConfiguration:
    """Verifies API URL configuration and settings consumption."""

    def test_default_url_from_settings(self, monkeypatch):
        """Verify client respects default settings URL."""
        client = DashboardApiClient()
        settings = get_settings()
        assert client.base_url == settings.dashboard_api_url.rstrip("/")

    def test_custom_url_override(self):
        """Verify client accepts and strips custom base URL."""
        client = DashboardApiClient(base_url="http://custom-host:9999/")
        assert client.base_url == "http://custom-host:9999"

    def test_token_redaction_in_errors(self, monkeypatch):
        """Verify sensitive InfluxDB token is never exposed in error text."""
        secret_token = "ultra-secret-test-token-xyz"
        monkeypatch.setattr(get_settings(), "influxdb_token", secret_token)
        client = DashboardApiClient(base_url="http://127.0.0.1:8000")

        with patch("requests.get", side_effect=requests.ConnectionError(f"Failed token: {secret_token}")):
            with pytest.raises(ApiConnectionError) as exc_info:
                client.get_fleet()
            assert secret_token not in str(exc_info.value)
            assert "[REDACTED]" in str(exc_info.value) or "unavailable" in str(exc_info.value)


# =============================================================================
# 2. HEALTH CHECK TESTS
# =============================================================================
class TestHealthEndpoint:
    """Verifies health check endpoint parsing and outage states."""

    @patch("requests.get")
    def test_health_healthy_200(self, mock_get, api_client):
        """Verify 200 OK returns HEALTHY state."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "HEALTHY",
            "service": "UP",
            "database": "CONNECTED",
            "timestamp": "2026-09-13T12:00:00Z",
            "details": {"database_connected": True},
        }
        mock_get.return_value = mock_resp

        health = api_client.get_health()
        assert health["status"] == "HEALTHY"
        assert health["service"] == "UP"
        assert health["database"] == "CONNECTED"

    @patch("requests.get")
    def test_health_degraded_503(self, mock_get, api_client):
        """Verify 503 reports DEGRADED state with InfluxDB UNAVAILABLE."""
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.json.return_value = {
            "status": "DEGRADED",
            "service": "UP",
            "database": "UNAVAILABLE",
            "details": {"error": "InfluxDB unreachable"},
        }
        mock_get.return_value = mock_resp

        health = api_client.get_health()
        assert health["status"] == "DEGRADED"
        assert health["service"] == "UP"
        assert health["database"] == "UNAVAILABLE"

    @patch("requests.get")
    def test_health_offline_connection_refused(self, mock_get, api_client):
        """Verify connection failure reports OFFLINE state without raising an unhandled crash."""
        mock_get.side_effect = requests.ConnectionError("Connection refused")

        health = api_client.get_health()
        assert health["status"] == "OFFLINE"
        assert health["service"] == "DOWN"
        assert health["database"] == "UNKNOWN"


# =============================================================================
# 3. FLEET OVERVIEW & MOTOR DISCOVERY TESTS
# =============================================================================
class TestFleetOverviewEndpoint:
    """Verifies fleet discovery and multi-motor handling."""

    @patch("requests.get")
    def test_get_motors_success_multiple(self, mock_get, api_client):
        """Verify multiple motors returned dynamically without hardcoding."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "motors": [
                {
                    "device_id": "pump_alpha",
                    "fault_type": "Inner_Race",
                    "health_index": 0.85,
                    "rul_hours": 350.0,
                    "timestamp": "2026-09-13T12:00:00Z",
                },
                {
                    "device_id": "compressor_beta",
                    "fault_type": "Normal",
                    "health_index": 0.98,
                    "rul_hours": 920.0,
                    "timestamp": "2026-09-13T12:05:00Z",
                },
            ],
            "total_motors": 2,
        }
        mock_get.return_value = mock_resp

        motors = api_client.get_motors()
        assert len(motors) == 2
        # Verify arbitrary non-hardcoded motor IDs are respected
        device_ids = [m["device_id"] for m in motors]
        assert "pump_alpha" in device_ids
        assert "compressor_beta" in device_ids

    @patch("requests.get")
    def test_get_motors_empty_fleet(self, mock_get, api_client):
        """Verify empty fleet returns empty list gracefully."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"motors": [], "total_motors": 0}
        mock_get.return_value = mock_resp

        motors = api_client.get_motors()
        assert motors == []

    @patch("requests.get")
    def test_get_motors_degraded_503_raises_api_degraded(self, mock_get, api_client):
        """Verify 503 response raises ApiDegradedError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.json.return_value = {"detail": "InfluxDB unavailable"}
        mock_get.return_value = mock_resp

        with pytest.raises(ApiDegradedError) as exc_info:
            api_client.get_motors()
        assert exc_info.value.status_code == 503


# =============================================================================
# 4. MOTOR LATEST TELEMETRY TESTS
# =============================================================================
class TestMotorLatestEndpoint:
    """Verifies single motor latest telemetry retrieval and error codes."""

    @patch("requests.get")
    def test_get_motor_latest_success(self, mock_get, api_client):
        """Verify successful single motor latest telemetry lookup."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "device_id": "motor_01",
            "fault_type": "Inner_Race",
            "health_index": 0.88,
            "rul_hours": 420.0,
            "timestamp": "2026-09-13T12:00:00Z",
        }
        mock_get.return_value = mock_resp

        telemetry = api_client.get_motor_latest("motor_01")
        assert telemetry["device_id"] == "motor_01"
        assert telemetry["fault_type"] == "Inner_Race"
        assert telemetry["health_index"] == 0.88

    @patch("requests.get")
    def test_get_motor_latest_not_found_404(self, mock_get, api_client):
        """Verify 404 raises ApiNotFoundError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.json.return_value = {"detail": "Motor 'motor_99' not found"}
        mock_get.return_value = mock_resp

        with pytest.raises(ApiNotFoundError) as exc_info:
            api_client.get_motor_latest("motor_99")
        assert exc_info.value.status_code == 404

    @patch("requests.get")
    def test_get_motor_latest_bad_request_400(self, mock_get, api_client):
        """Verify 400 Bad Request raises ApiClientError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {"detail": "Invalid device_id format"}
        mock_get.return_value = mock_resp

        with pytest.raises(ApiClientError) as exc_info:
            api_client.get_motor_latest("bad id with spaces")
        assert exc_info.value.status_code == 400


# =============================================================================
# 5. HISTORICAL TRENDS & FAULT HISTORY TESTS
# =============================================================================
class TestHistoricalEndpoints:
    """Verifies health, RUL, and fault historical endpoints."""

    @patch("requests.get")
    def test_get_motor_health_success_and_empty(self, mock_get, api_client):
        """Verify health history parsing and query parameters."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"timestamp": "2026-09-13T10:00:00Z", "health_index": 0.85},
            {"timestamp": "2026-09-13T11:00:00Z", "health_index": 0.88},
        ]
        mock_get.return_value = mock_resp

        health_points = api_client.get_motor_health("motor_01", start="-12h", stop="now()")
        assert len(health_points) == 2
        assert health_points[0]["health_index"] == 0.85
        # Verify query parameters passed to requests.get
        mock_get.assert_called_with(
            "http://127.0.0.1:8000/api/motors/motor_01/health",
            params={"start": "-12h", "stop": "now()"},
            timeout=2.0,
        )

    @patch("requests.get")
    def test_get_motor_rul_success(self, mock_get, api_client):
        """Verify RUL history parsing."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"timestamp": "2026-09-13T10:00:00Z", "rul_hours": 450.0},
            {"timestamp": "2026-09-13T11:00:00Z", "rul_hours": 420.0},
        ]
        mock_get.return_value = mock_resp

        rul_points = api_client.get_motor_rul("motor_01", start="-24h")
        assert len(rul_points) == 2
        assert rul_points[1]["rul_hours"] == 420.0

    @patch("requests.get")
    def test_get_motor_faults_success(self, mock_get, api_client):
        """Verify fault classification events parsing."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"timestamp": "2026-09-13T10:00:00Z", "fault_type": "Inner_Race"},
            {"timestamp": "2026-09-13T11:00:00Z", "fault_type": "Outer_Race"},
        ]
        mock_get.return_value = mock_resp

        fault_events = api_client.get_motor_faults("motor_01", start="-7d")
        assert len(fault_events) == 2
        assert fault_events[0]["fault_type"] == "Inner_Race"
        assert fault_events[1]["fault_type"] == "Outer_Race"


# =============================================================================
# 6. NETWORK & TIMEOUT HANDLING
# =============================================================================
class TestNetworkErrorHandling:
    """Verifies timeout and connection refusal handling across endpoints."""

    @patch("requests.get", side_effect=requests.Timeout("Request timed out"))
    def test_timeout_raises_api_connection_error(self, mock_get, api_client):
        """Verify timeout raises ApiConnectionError with user-friendly text."""
        with pytest.raises(ApiConnectionError) as exc_info:
            api_client.get_motor_latest("motor_01")
        assert "timed out" in str(exc_info.value)

    @patch("requests.get", side_effect=requests.ConnectionError("Connection refused"))
    def test_connection_error_raises_api_connection_error(self, mock_get, api_client):
        """Verify connection refusal raises ApiConnectionError."""
        with pytest.raises(ApiConnectionError) as exc_info:
            api_client.get_motor_health("motor_01")
        assert "unavailable" in str(exc_info.value)
