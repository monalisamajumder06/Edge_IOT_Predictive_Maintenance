"""Live Integration Test Suite for FastAPI Backend over Real InfluxDB.

Subsystem: IoT + Backend + Dashboard (Member 3)
Phase: Phase 4 Implementation
Classification: [IMPLEMENTATION DECISION]

Requirements:
- Clearly separated from mocked unit tests.
- Verifies real end-to-end data path: Live InfluxDB -> InfluxDBService -> FastAPI Routes -> TestClient.
- HONEST REPORTING: If InfluxDB is unavailable at INFLUXDB_URL, tests report SKIPPED
  with a descriptive diagnostic message rather than falsely passing.
"""

import pytest
import requests
from fastapi.testclient import TestClient

from backend.main import app
from config.settings import get_settings


@pytest.fixture(scope="module", autouse=True)
def require_live_influxdb():
    """Verify InfluxDB is reachable before executing integration tests."""
    settings = get_settings()
    url = f"{settings.influxdb_url.rstrip('/')}/health"
    try:
        resp = requests.get(url, timeout=2.0)
        if resp.status_code != 200:
            pytest.skip(
                f"InfluxDB service at {settings.influxdb_url} is not healthy (status={resp.status_code}). "
                "Skipping live FastAPI integration tests.",
                allow_module_level=True,
            )
    except requests.RequestException:
        pytest.skip(
            f"InfluxDB unavailable at {settings.influxdb_url}. "
            "Start InfluxDB using .\\scripts\\setup_influxdb_windows.ps1 -Start to run integration tests.",
            allow_module_level=True,
        )


@pytest.fixture
def live_client():
    """Create a TestClient against the real unmocked application."""
    with TestClient(app) as client:
        yield client


class TestFastApiLiveIntegration:
    """End-to-end integration tests querying real InfluxDB database records."""

    def test_live_health_endpoint_reports_connected(self, live_client):
        """Verify GET /health against live InfluxDB reports HEALTHY and CONNECTED."""
        resp = live_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "HEALTHY"
        assert data["service"] == "UP"
        assert data["database"] == "CONNECTED"

    def test_live_fleet_overview_discovers_stored_motors(self, live_client):
        """Verify GET /api/motors discovers stored motors (motor_01 and motor_02)."""
        resp = live_client.get("/api/motors")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_motors"] >= 2

        motor_ids = [m["device_id"] for m in data["motors"]]
        assert "motor_01" in motor_ids
        assert "motor_02" in motor_ids

    def test_live_motor_01_latest_matches_stored_contract(self, live_client):
        """Verify GET /api/motors/motor_01/latest returns actual Phase 3 stored data."""
        resp = live_client.get("/api/motors/motor_01/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["device_id"] == "motor_01"
        assert data["fault_type"] in ("Inner_Race", "Synthetic_Test_Fault_A")
        assert isinstance(data["health_index"], float)
        assert isinstance(data["rul_hours"], (int, float))
        assert "timestamp" in data

    def test_live_motor_02_latest_matches_stored_contract(self, live_client):
        """Verify GET /api/motors/motor_02/latest returns actual Phase 3 stored data."""
        resp = live_client.get("/api/motors/motor_02/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["device_id"] == "motor_02"
        assert data["fault_type"] in ("Normal", "Synthetic_Test_Fault_B")
        assert isinstance(data["health_index"], float)

    def test_live_motor_history_returns_chronological_records(self, live_client):
        """Verify GET /api/motors/motor_01/history returns time-series records."""
        resp = live_client.get("/api/motors/motor_01/history?start=-30d")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0
        for record in data:
            assert record["device_id"] == "motor_01"
            assert "fault_type" in record
            assert "health_index" in record
            assert "rul_hours" in record
            assert "timestamp" in record

    def test_live_motor_health_trend_returns_observations(self, live_client):
        """Verify GET /api/motors/motor_01/health returns health trend observations."""
        resp = live_client.get("/api/motors/motor_01/health?start=-30d")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0
        for obs in data:
            assert "timestamp" in obs
            assert isinstance(obs["health_index"], float)

    def test_live_motor_rul_trend_returns_observations(self, live_client):
        """Verify GET /api/motors/motor_01/rul returns RUL trend observations."""
        resp = live_client.get("/api/motors/motor_01/rul?start=-30d")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0
        for obs in data:
            assert "timestamp" in obs
            assert isinstance(obs["rul_hours"], (int, float))

    def test_live_motor_fault_history_returns_observations(self, live_client):
        """Verify GET /api/motors/motor_01/faults returns fault history observations."""
        resp = live_client.get("/api/motors/motor_01/faults?start=-30d")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0
        for obs in data:
            assert "timestamp" in obs
            assert isinstance(obs["fault_type"], str)

    def test_live_motor_not_found_returns_404(self, live_client):
        """Verify querying non-existent motor returns structured 404."""
        resp = live_client.get("/api/motors/motor_nonexistent_99/latest")
        assert resp.status_code == 404
        data = resp.json()
        assert "not found" in data["detail"].lower()
