"""FastAPI Client for Edge-IoT Predictive Maintenance Dashboard.

Subsystem: IoT + Backend + Dashboard (Member 3)
Phase: Phase 5 Implementation
Classification: [PROJECT REQUIREMENT / IMPLEMENTATION DECISION]

Encapsulates all HTTP communication between the Streamlit dashboard and the
FastAPI REST API backend. Ensures zero direct connections to InfluxDB,
strict timeout enforcement, credential sanitization, and structured error states.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
import requests

from config.settings import get_settings

logger = logging.getLogger("dashboard.api_client")


class ApiClientError(Exception):
    """Base exception for dashboard API client errors."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ApiConnectionError(ApiClientError):
    """Raised when the FastAPI backend is completely unreachable or times out."""


class ApiNotFoundError(ApiClientError):
    """Raised when a requested resource (e.g. motor device_id) is not found (404)."""


class ApiDegradedError(ApiClientError):
    """Raised when the backend reports degraded status (e.g. InfluxDB unreachable, 503)."""


class DashboardApiClient:
    """HTTP Client for communicating with the FastAPI Predictive Maintenance backend."""

    def __init__(self, base_url: Optional[str] = None, timeout: float = 4.0):
        settings = get_settings()
        self.base_url = (base_url or settings.dashboard_api_url).rstrip("/")
        self.timeout = timeout
        self._token_to_redact = settings.influxdb_token

    def _sanitize(self, text: str) -> str:
        """Sanitize error messages to prevent credential leakage."""
        if self._token_to_redact and self._token_to_redact in text:
            return text.replace(self._token_to_redact, "[REDACTED]")
        return text

    def _handle_request_exception(self, exc: Exception, endpoint: str) -> None:
        """Convert requests exceptions into structured, sanitized API client exceptions."""
        err_msg = self._sanitize(str(exc))
        if isinstance(exc, (requests.ConnectionError, requests.ConnectTimeout)):
            logger.warning("Connection failed to backend at %s: %s", self.base_url, err_msg)
            raise ApiConnectionError(
                f"FastAPI backend unavailable at {self.base_url}. Verify the backend service is running."
            ) from exc
        elif isinstance(exc, requests.Timeout):
            logger.warning("Request timed out to %s%s", self.base_url, endpoint)
            raise ApiConnectionError(
                f"Request to backend at {self.base_url}{endpoint} timed out after {self.timeout}s."
            ) from exc
        else:
            logger.error("Unexpected network error on %s%s: %s", self.base_url, endpoint, err_msg)
            raise ApiClientError(f"Network error while communicating with backend: {err_msg}") from exc

    def get_health(self) -> Dict[str, Any]:
        """Query system and database health from GET /health.

        Returns:
            Dict containing status ("HEALTHY", "DEGRADED", or "OFFLINE"),
            service status ("UP" or "DOWN"), database status ("CONNECTED", "UNAVAILABLE", or "UNKNOWN"),
            and optional details.
        """
        url = f"{self.base_url}/health"
        try:
            resp = requests.get(url, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "status": data.get("status", "HEALTHY"),
                    "service": data.get("service", "UP"),
                    "database": data.get("database", "CONNECTED"),
                    "timestamp": data.get("timestamp", datetime.now(timezone.utc).isoformat()),
                    "details": data.get("details", {}),
                }
            elif resp.status_code == 503:
                try:
                    data = resp.json()
                except Exception:
                    data = {}
                return {
                    "status": "DEGRADED",
                    "service": "UP",
                    "database": "UNAVAILABLE",
                    "timestamp": data.get("timestamp", datetime.now(timezone.utc).isoformat()),
                    "details": data.get("details", {"error": "InfluxDB unreachable"}),
                }
            else:
                return {
                    "status": "DEGRADED",
                    "service": "UP",
                    "database": "UNKNOWN",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "details": {"error": f"Unexpected health response (HTTP {resp.status_code})"},
                }
        except Exception as exc:
            logger.warning("GET /health failed: %s", self._sanitize(str(exc)))
            return {
                "status": "OFFLINE",
                "service": "DOWN",
                "database": "UNKNOWN",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "details": {"error": f"FastAPI backend unreachable at {self.base_url}"},
            }

    def get_motors(self) -> List[Dict[str, Any]]:
        """Retrieve fleet overview from GET /api/motors.

        Returns:
            List of motor telemetry dictionaries.
        """
        url = f"{self.base_url}/api/motors"
        try:
            resp = requests.get(url, timeout=self.timeout)
        except Exception as exc:
            self._handle_request_exception(exc, "/api/motors")

        if resp.status_code == 200:
            data = resp.json()
            return data.get("motors", [])
        elif resp.status_code == 503:
            raise ApiDegradedError("Backend reports InfluxDB is currently unavailable (HTTP 503).", status_code=503)
        elif resp.status_code == 502:
            raise ApiClientError("Backend failed to query InfluxDB (HTTP 502 Bad Gateway).", status_code=502)
        else:
            raise ApiClientError(f"Failed to fetch fleet overview (HTTP {resp.status_code}).", status_code=resp.status_code)

    # Alias for flexibility
    get_fleet = get_motors

    def get_motor_latest(self, device_id: str) -> Dict[str, Any]:
        """Retrieve latest telemetry for a specific motor from GET /api/motors/{device_id}/latest.

        Args:
            device_id: Motor identifier string (e.g. 'motor_01')

        Returns:
            Telemetry dict with device_id, fault_type, health_index, rul_hours, timestamp.
        """
        clean_id = device_id.strip()
        url = f"{self.base_url}/api/motors/{clean_id}/latest"
        try:
            resp = requests.get(url, timeout=self.timeout)
        except Exception as exc:
            self._handle_request_exception(exc, f"/api/motors/{clean_id}/latest")

        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 404:
            raise ApiNotFoundError(f"Motor '{clean_id}' not found or has no telemetry records.", status_code=404)
        elif resp.status_code == 400:
            raise ApiClientError(f"Invalid motor identifier '{clean_id}' (HTTP 400).", status_code=400)
        elif resp.status_code == 503:
            raise ApiDegradedError("Backend reports InfluxDB is currently unavailable (HTTP 503).", status_code=503)
        else:
            raise ApiClientError(
                f"Failed to fetch latest telemetry for '{clean_id}' (HTTP {resp.status_code}).",
                status_code=resp.status_code,
            )

    def get_motor_health(
        self,
        device_id: str,
        start: str = "-24h",
        stop: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve historical health index trend observations from GET /api/motors/{device_id}/health.

        Returns:
            List of dicts with 'timestamp' and 'health_index'.
        """
        clean_id = device_id.strip()
        url = f"{self.base_url}/api/motors/{clean_id}/health"
        params: Dict[str, str] = {"start": start}
        if stop:
            params["stop"] = stop

        try:
            resp = requests.get(url, params=params, timeout=self.timeout)
        except Exception as exc:
            self._handle_request_exception(exc, f"/api/motors/{clean_id}/health")

        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 404:
            raise ApiNotFoundError(f"Motor '{clean_id}' not found or has no telemetry records.", status_code=404)
        elif resp.status_code == 400:
            raise ApiClientError(f"Invalid parameters for health trend query (HTTP 400).", status_code=400)
        elif resp.status_code == 503:
            raise ApiDegradedError("Backend reports InfluxDB is currently unavailable (HTTP 503).", status_code=503)
        else:
            raise ApiClientError(
                f"Failed to fetch health trend for '{clean_id}' (HTTP {resp.status_code}).",
                status_code=resp.status_code,
            )

    def get_motor_rul(
        self,
        device_id: str,
        start: str = "-24h",
        stop: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve historical RUL trend observations from GET /api/motors/{device_id}/rul.

        Returns:
            List of dicts with 'timestamp' and 'rul_hours'.
        """
        clean_id = device_id.strip()
        url = f"{self.base_url}/api/motors/{clean_id}/rul"
        params: Dict[str, str] = {"start": start}
        if stop:
            params["stop"] = stop

        try:
            resp = requests.get(url, params=params, timeout=self.timeout)
        except Exception as exc:
            self._handle_request_exception(exc, f"/api/motors/{clean_id}/rul")

        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 404:
            raise ApiNotFoundError(f"Motor '{clean_id}' not found or has no telemetry records.", status_code=404)
        elif resp.status_code == 400:
            raise ApiClientError(f"Invalid parameters for RUL trend query (HTTP 400).", status_code=400)
        elif resp.status_code == 503:
            raise ApiDegradedError("Backend reports InfluxDB is currently unavailable (HTTP 503).", status_code=503)
        else:
            raise ApiClientError(
                f"Failed to fetch RUL trend for '{clean_id}' (HTTP {resp.status_code}).",
                status_code=resp.status_code,
            )

    def get_motor_faults(
        self,
        device_id: str,
        start: str = "-7d",
        stop: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve historical fault observations from GET /api/motors/{device_id}/faults.

        Returns:
            List of dicts with 'timestamp' and 'fault_type'.
        """
        clean_id = device_id.strip()
        url = f"{self.base_url}/api/motors/{clean_id}/faults"
        params: Dict[str, str] = {"start": start}
        if stop:
            params["stop"] = stop

        try:
            resp = requests.get(url, params=params, timeout=self.timeout)
        except Exception as exc:
            self._handle_request_exception(exc, f"/api/motors/{clean_id}/faults")

        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 404:
            raise ApiNotFoundError(f"Motor '{clean_id}' not found or has no telemetry records.", status_code=404)
        elif resp.status_code == 400:
            raise ApiClientError(f"Invalid parameters for fault history query (HTTP 400).", status_code=400)
        elif resp.status_code == 503:
            raise ApiDegradedError("Backend reports InfluxDB is currently unavailable (HTTP 503).", status_code=503)
        else:
            raise ApiClientError(
                f"Failed to fetch fault history for '{clean_id}' (HTTP {resp.status_code}).",
                status_code=resp.status_code,
            )
