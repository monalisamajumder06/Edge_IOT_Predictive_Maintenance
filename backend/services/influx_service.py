"""InfluxDB Query Service and Abstraction Layer.

Subsystem: IoT + Backend + Dashboard (Member 3)
Phase: Phase 4 Implementation
Classification: [IMPLEMENTATION DECISION]

Encapsulates all Flux query execution, parameter validation, annotated CSV parsing,
and error handling against InfluxDB v2.
Prevents credential leakage and isolates database query mechanics from API routes.
"""

import csv
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
import httpx

from config.settings import Settings, get_settings
from backend.schemas.responses import (
    FaultObservation,
    HealthObservation,
    MotorTelemetryResponse,
    RulObservation,
)


class InfluxDBUnavailableError(Exception):
    """Raised when InfluxDB service cannot be reached or times out."""
    pass


class InfluxDBQueryError(Exception):
    """Raised when InfluxDB rejects a Flux query or returns a non-200 status."""
    pass


DEVICE_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-]+$")
RELATIVE_DURATION_REGEX = re.compile(r"^-[0-9]+(s|m|h|d|w|y)$")
ISO8601_REGEX = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})?$")


def validate_device_id(device_id: str) -> str:
    """Validate and sanitize device_id to prevent injection and malformed queries."""
    clean_id = device_id.strip()
    if not clean_id:
        raise ValueError("device_id cannot be empty.")
    if not DEVICE_ID_REGEX.match(clean_id):
        raise ValueError(
            f"Invalid device_id '{device_id}'. Only alphanumeric characters, underscores, and hyphens are allowed."
        )
    return clean_id


def validate_time_param(param: Optional[str], param_name: str = "time") -> Optional[str]:
    """Validate relative duration or ISO-8601 UTC timestamp to prevent Flux injection."""
    if param is None:
        return None
    clean_param = param.strip()
    if not clean_param:
        return None

    # Check relative duration (e.g. -1h, -24h, -7d, -30d)
    if RELATIVE_DURATION_REGEX.match(clean_param):
        return clean_param

    # Check 'now()' literal
    if clean_param.lower() == "now()":
        return "now()"

    # Check ISO-8601 format
    if ISO8601_REGEX.match(clean_param):
        # Verify valid datetime
        try:
            clean_ts = clean_param.replace("Z", "+00:00")
            datetime.fromisoformat(clean_ts)
            # Return time formatted for Flux
            return f'time(v: "{clean_param}")'
        except ValueError:
            pass

    raise ValueError(
        f"Invalid {param_name} format: '{param}'. "
        "Must be a relative duration (e.g., '-1h', '-24h', '-7d') or an ISO-8601 UTC timestamp."
    )


class InfluxDBService:
    """Async service managing InfluxDB connectivity, queries, and result parsing."""

    def __init__(self, settings: Optional[Settings] = None, client: Optional[httpx.AsyncClient] = None):
        self.settings = settings or get_settings()
        self._client = client
        self._owns_client = client is None

    async def get_client(self) -> httpx.AsyncClient:
        """Provide or initialize the async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=10.0)
            self._owns_client = True
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client if owned."""
        if self._owns_client and self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def check_health(self) -> Dict[str, Any]:
        """Check InfluxDB connectivity via /health endpoint.
        
        Returns:
            Dict containing reachability status and details.
            
        Raises:
            InfluxDBUnavailableError: If connection fails or returns unhealthy.
        """
        client = await self.get_client()
        url = f"{self.settings.influxdb_url.rstrip('/')}/health"
        try:
            resp = await client.get(url, timeout=3.0)
            if resp.status_code == 200:
                return {
                    "database_connected": True,
                    "database_status": "CONNECTED",
                    "url": self.settings.influxdb_url,
                }
            return {
                "database_connected": False,
                "database_status": "UNAVAILABLE",
                "status_code": resp.status_code,
            }
        except Exception as exc:
            raise InfluxDBUnavailableError(
                f"InfluxDB service at {self.settings.influxdb_url} is unreachable."
            ) from exc

    async def execute_flux(self, flux_query: str) -> str:
        """Execute a Flux query via HTTP POST /api/v2/query.
        
        Args:
            flux_query: Raw Flux query string.
            
        Returns:
            Annotated CSV string returned by InfluxDB.
            
        Raises:
            InfluxDBUnavailableError: If connection to InfluxDB fails.
            InfluxDBQueryError: If InfluxDB returns non-200 status.
        """
        client = await self.get_client()
        url = f"{self.settings.influxdb_url.rstrip('/')}/api/v2/query?org={self.settings.influxdb_org}"
        headers = {
            "Authorization": f"Token {self.settings.influxdb_token}",
            "Content-Type": "application/vnd.flux",
            "Accept": "application/csv",
        }
        try:
            resp = await client.post(url, content=flux_query.encode("utf-8"), headers=headers, timeout=10.0)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RequestError) as exc:
            raise InfluxDBUnavailableError(
                f"Failed to connect to InfluxDB at {self.settings.influxdb_url}."
            ) from exc

        if resp.status_code != 200:
            # Sanitize error to prevent token or sensitive detail leakage
            clean_error = resp.text.strip().replace(self.settings.influxdb_token, "[REDACTED]")
            raise InfluxDBQueryError(f"InfluxDB query failed ({resp.status_code}): {clean_error}")

        return resp.text

    def _parse_csv_records(self, csv_data: str) -> List[Dict[str, Any]]:
        """Parse InfluxDB annotated CSV into structured row dictionaries."""
        lines = [line.strip() for line in csv_data.splitlines() if line.strip() and not line.startswith("#")]
        if not lines:
            return []

        reader = csv.DictReader(lines)
        records = []
        for row in reader:
            if row.get("result") == "_result":
                records.append(row)
        return records

    async def get_motor_latest(self, device_id: str) -> Optional[MotorTelemetryResponse]:
        """Fetch latest telemetry for a specific motor."""
        dev = validate_device_id(device_id)
        query = f'''
        from(bucket: "{self.settings.influxdb_bucket}")
          |> range(start: -30d)
          |> filter(fn: (r) => r._measurement == "predictions" and r.device_id == "{dev}")
          |> group(columns: ["_field"])
          |> last()
          |> keep(columns: ["_time", "device_id", "_field", "_value"])
        '''
        csv_data = await self.execute_flux(query)
        rows = self._parse_csv_records(csv_data)
        if not rows:
            return None

        fields: Dict[str, Any] = {}
        timestamp_str = None
        for r in rows:
            fields[r["_field"]] = r["_value"]
            timestamp_str = r["_time"]

        required = ["fault_type", "health_index", "rul_hours"]
        if not all(k in fields for k in required) or timestamp_str is None:
            return None

        clean_ts = timestamp_str.replace("Z", "+00:00")
        return MotorTelemetryResponse(
            device_id=dev,
            fault_type=str(fields["fault_type"]),
            health_index=float(fields["health_index"]),
            rul_hours=float(fields["rul_hours"]),
            timestamp=datetime.fromisoformat(clean_ts),
        )

    async def get_fleet_latest(self) -> List[MotorTelemetryResponse]:
        """Fetch latest telemetry for all motors in the fleet."""
        query = f'''
        from(bucket: "{self.settings.influxdb_bucket}")
          |> range(start: -30d)
          |> filter(fn: (r) => r._measurement == "predictions")
          |> group(columns: ["device_id", "_field"])
          |> last()
          |> keep(columns: ["_time", "device_id", "_field", "_value"])
        '''
        csv_data = await self.execute_flux(query)
        rows = self._parse_csv_records(csv_data)

        motors: Dict[str, Dict[str, Any]] = defaultdict(dict)
        timestamps: Dict[str, str] = {}
        for r in rows:
            dev = r["device_id"]
            motors[dev][r["_field"]] = r["_value"]
            timestamps[dev] = r["_time"]

        results: List[MotorTelemetryResponse] = []
        for dev, fields in sorted(motors.items()):
            if "fault_type" in fields and "health_index" in fields and "rul_hours" in fields:
                clean_ts = timestamps[dev].replace("Z", "+00:00")
                results.append(
                    MotorTelemetryResponse(
                        device_id=dev,
                        fault_type=str(fields["fault_type"]),
                        health_index=float(fields["health_index"]),
                        rul_hours=float(fields["rul_hours"]),
                        timestamp=datetime.fromisoformat(clean_ts),
                    )
                )
        return results

    async def get_motor_history(
        self,
        device_id: str,
        start: str = "-24h",
        stop: Optional[str] = None,
    ) -> List[MotorTelemetryResponse]:
        """Fetch complete historical telemetry records for a motor within a time range."""
        dev = validate_device_id(device_id)
        start_flux = validate_time_param(start, "start") or "-24h"
        stop_flux = validate_time_param(stop, "stop")

        range_args = f"start: {start_flux}"
        if stop_flux:
            range_args += f", stop: {stop_flux}"

        query = f'''
        from(bucket: "{self.settings.influxdb_bucket}")
          |> range({range_args})
          |> filter(fn: (r) => r._measurement == "predictions" and r.device_id == "{dev}")
          |> keep(columns: ["_time", "device_id", "_field", "_value"])
        '''
        csv_data = await self.execute_flux(query)
        rows = self._parse_csv_records(csv_data)

        points: Dict[str, Dict[str, Any]] = defaultdict(dict)
        for r in rows:
            t = r["_time"]
            points[t][r["_field"]] = r["_value"]

        history: List[MotorTelemetryResponse] = []
        for t in sorted(points.keys()):
            f = points[t]
            if "fault_type" in f and "health_index" in f and "rul_hours" in f:
                clean_ts = t.replace("Z", "+00:00")
                history.append(
                    MotorTelemetryResponse(
                        device_id=dev,
                        fault_type=str(f["fault_type"]),
                        health_index=float(f["health_index"]),
                        rul_hours=float(f["rul_hours"]),
                        timestamp=datetime.fromisoformat(clean_ts),
                    )
                )
        return history

    async def get_motor_health_trend(
        self,
        device_id: str,
        start: str = "-24h",
        stop: Optional[str] = None,
    ) -> List[HealthObservation]:
        """Fetch historical health_index observations for plotting."""
        dev = validate_device_id(device_id)
        start_flux = validate_time_param(start, "start") or "-24h"
        stop_flux = validate_time_param(stop, "stop")

        range_args = f"start: {start_flux}"
        if stop_flux:
            range_args += f", stop: {stop_flux}"

        query = f'''
        from(bucket: "{self.settings.influxdb_bucket}")
          |> range({range_args})
          |> filter(fn: (r) => r._measurement == "predictions" and r.device_id == "{dev}" and r._field == "health_index")
          |> keep(columns: ["_time", "_value"])
        '''
        csv_data = await self.execute_flux(query)
        rows = self._parse_csv_records(csv_data)

        trend: List[HealthObservation] = []
        for r in rows:
            clean_ts = r["_time"].replace("Z", "+00:00")
            trend.append(
                HealthObservation(
                    timestamp=datetime.fromisoformat(clean_ts),
                    health_index=float(r["_value"]),
                )
            )
        trend.sort(key=lambda x: x.timestamp)
        return trend

    async def get_motor_rul_trend(
        self,
        device_id: str,
        start: str = "-24h",
        stop: Optional[str] = None,
    ) -> List[RulObservation]:
        """Fetch historical rul_hours observations for plotting."""
        dev = validate_device_id(device_id)
        start_flux = validate_time_param(start, "start") or "-24h"
        stop_flux = validate_time_param(stop, "stop")

        range_args = f"start: {start_flux}"
        if stop_flux:
            range_args += f", stop: {stop_flux}"

        query = f'''
        from(bucket: "{self.settings.influxdb_bucket}")
          |> range({range_args})
          |> filter(fn: (r) => r._measurement == "predictions" and r.device_id == "{dev}" and r._field == "rul_hours")
          |> keep(columns: ["_time", "_value"])
        '''
        csv_data = await self.execute_flux(query)
        rows = self._parse_csv_records(csv_data)

        trend: List[RulObservation] = []
        for r in rows:
            clean_ts = r["_time"].replace("Z", "+00:00")
            trend.append(
                RulObservation(
                    timestamp=datetime.fromisoformat(clean_ts),
                    rul_hours=float(r["_value"]),
                )
            )
        trend.sort(key=lambda x: x.timestamp)
        return trend

    async def get_motor_fault_history(
        self,
        device_id: str,
        start: str = "-7d",
        stop: Optional[str] = None,
    ) -> List[FaultObservation]:
        """Fetch historical fault classification events."""
        dev = validate_device_id(device_id)
        start_flux = validate_time_param(start, "start") or "-7d"
        stop_flux = validate_time_param(stop, "stop")

        range_args = f"start: {start_flux}"
        if stop_flux:
            range_args += f", stop: {stop_flux}"

        query = f'''
        from(bucket: "{self.settings.influxdb_bucket}")
          |> range({range_args})
          |> filter(fn: (r) => r._measurement == "predictions" and r.device_id == "{dev}" and r._field == "fault_type")
          |> keep(columns: ["_time", "_value"])
        '''
        csv_data = await self.execute_flux(query)
        rows = self._parse_csv_records(csv_data)

        history: List[FaultObservation] = []
        for r in rows:
            clean_ts = r["_time"].replace("Z", "+00:00")
            history.append(
                FaultObservation(
                    timestamp=datetime.fromisoformat(clean_ts),
                    fault_type=str(r["_value"]),
                )
            )
        history.sort(key=lambda x: x.timestamp)
        return history
