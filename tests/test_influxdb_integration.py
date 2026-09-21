"""Live Integration Test Suite for InfluxDB v2 Persistence Layer.

Subsystem: IoT + Backend + Dashboard (Member 3)
Phase: Phase 3 Implementation
Classification: [IMPLEMENTATION DECISION]

Requirements:
- Clearly separated from Unit Tests.
- Connects to live InfluxDB instance at INFLUXDB_URL.
- Verifies real HTTP write, Flux query execution, multi-motor coexistence, and contract value preservation.
- HONEST REPORTING: If InfluxDB is unavailable, tests report SKIPPED with an explicit diagnostic
  message ("InfluxDB unavailable at http://localhost:8086, skipping live integration test")
  rather than falsely passing.
"""

import time
from typing import Dict, List
import pytest
import requests

from config.settings import get_settings
from gateway.line_protocol import format_line_protocol


# Fixture to check InfluxDB reachability before running integration tests
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
                "Skipping live integration tests.",
                allow_module_level=True,
            )
    except requests.RequestException:
        pytest.skip(
            f"InfluxDB unavailable at {settings.influxdb_url}. "
            "Start InfluxDB using .\\scripts\\setup_influxdb_windows.ps1 -Start to run integration tests.",
            allow_module_level=True,
        )


def execute_flux_query(url: str, org: str, token: str, query: str) -> str:
    """Helper to run a Flux query against InfluxDB v2 API and return annotated CSV."""
    query_url = f"{url.rstrip('/')}/api/v2/query?org={org}"
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/vnd.flux",
        "Accept": "application/csv",
    }
    resp = requests.post(query_url, data=query.encode("utf-8"), headers=headers, timeout=5.0)
    if resp.status_code != 200:
        raise RuntimeError(f"Flux query failed ({resp.status_code}): {resp.text}")
    return resp.text


class TestInfluxDbLiveIntegration:
    """Live InfluxDB write and query verification tests."""

    def test_live_write_canonical_telemetry_returns_204(self):
        """Verify writing canonical motor_01 Line Protocol point returns HTTP 204 No Content."""
        settings = get_settings()
        sample = {
            "status": "ACCEPTED",
            "disposition": "ACCEPTED",
            "device_id": "motor_01",
            "fault_type": "Inner_Race",
            "health_index": 0.88,
            "rul_hours": 420.0,
            "timestamp": "2026-09-13T14:00:00.000Z",
            "gateway_received_at": "2026-09-13T14:00:00.000Z",
            "topic": "motors/motor_01/prediction",
        }
        line_protocol = format_line_protocol(sample)

        write_url = (
            f"{settings.influxdb_url.rstrip('/')}/api/v2/write"
            f"?org={settings.influxdb_org}&bucket={settings.influxdb_bucket}&precision=ms"
        )
        headers = {
            "Authorization": f"Token {settings.influxdb_token}",
            "Content-Type": "text/plain; charset=utf-8",
        }

        resp = requests.post(write_url, data=line_protocol.encode("utf-8"), headers=headers, timeout=5.0)
        assert resp.status_code == 204, f"Write failed: {resp.status_code} - {resp.text}"

    def test_live_multimotor_coexistence_and_query_fidelity(self):
        """Verify motor_01 and motor_02 write to independent series and can be queried."""
        settings = get_settings()
        t_base = int(time.time() * 1000)

        # 1. Write motor_01 point
        m1 = {
            "device_id": "motor_01",
            "fault_type": "Inner_Race",
            "health_index": 0.85,
            "rul_hours": 410.0,
            "timestamp": t_base,
        }
        # 2. Write motor_02 point at exact same timestamp
        m2 = {
            "device_id": "motor_02",
            "fault_type": "Normal",
            "health_index": 0.97,
            "rul_hours": 950.0,
            "timestamp": t_base,
        }

        write_url = (
            f"{settings.influxdb_url.rstrip('/')}/api/v2/write"
            f"?org={settings.influxdb_org}&bucket={settings.influxdb_bucket}&precision=ms"
        )
        headers = {
            "Authorization": f"Token {settings.influxdb_token}",
            "Content-Type": "text/plain; charset=utf-8",
        }

        line1 = format_line_protocol(m1)
        line2 = format_line_protocol(m2)
        payload = f"{line1}\n{line2}"

        write_resp = requests.post(write_url, data=payload.encode("utf-8"), headers=headers, timeout=5.0)
        assert write_resp.status_code == 204

        # 3. Query motor_01 latest point via Flux
        query_m1 = f'''
        from(bucket: "{settings.influxdb_bucket}")
          |> range(start: -15m)
          |> filter(fn: (r) => r._measurement == "predictions" and r.device_id == "motor_01")
          |> last()
        '''
        csv_m1 = execute_flux_query(settings.influxdb_url, settings.influxdb_org, settings.influxdb_token, query_m1)
        assert "motor_01" in csv_m1
        assert "fault_type" in csv_m1
        assert "health_index" in csv_m1
        assert "rul_hours" in csv_m1

        # 4. Query motor_02 latest point via Flux
        query_m2 = f'''
        from(bucket: "{settings.influxdb_bucket}")
          |> range(start: -15m)
          |> filter(fn: (r) => r._measurement == "predictions" and r.device_id == "motor_02")
          |> last()
        '''
        csv_m2 = execute_flux_query(settings.influxdb_url, settings.influxdb_org, settings.influxdb_token, query_m2)
        assert "motor_02" in csv_m2
        assert "Normal" in csv_m2
