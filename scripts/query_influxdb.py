"""Telemetry Query Utility for InfluxDB Verification.

Subsystem: IoT + Backend + Dashboard (Member 3)
Phase: Phase 3 Implementation
Classification: [IMPLEMENTATION DECISION]

Executes Flux queries against InfluxDB v2 to verify stored telemetry for motors.
"""

import sys
from pathlib import Path
from typing import Optional
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import get_settings


def run_query(flux_query: str) -> str:
    settings = get_settings()
    url = f"{settings.influxdb_url.rstrip('/')}/api/v2/query?org={settings.influxdb_org}"
    headers = {
        "Authorization": f"Token {settings.influxdb_token}",
        "Content-Type": "application/vnd.flux",
        "Accept": "application/csv",
    }
    resp = requests.post(url, data=flux_query.encode("utf-8"), headers=headers, timeout=5.0)
    if resp.status_code != 200:
        raise RuntimeError(f"Flux query failed ({resp.status_code}): {resp.text}")
    return resp.text


def main():
    settings = get_settings()
    print("==========================================================")
    print("Edge-IoT Predictive Maintenance - InfluxDB Telemetry Query")
    print(f"Bucket: {settings.influxdb_bucket} | Org: {settings.influxdb_org}")
    print("==========================================================")

    query = f'''
    from(bucket: "{settings.influxdb_bucket}")
      |> range(start: -1h)
      |> filter(fn: (r) => r._measurement == "predictions")
      |> keep(columns: ["_time", "device_id", "_field", "_value"])
    '''
    try:
        csv_output = run_query(query)
        print("\n--- Raw Stored Data (Annotated CSV) ---")
        lines = [line.strip() for line in csv_output.strip().split("\n") if line.strip() and not line.startswith("#")]
        for line in lines:
            print(line)

        print("\n--- Summary Verification ---")
        # Check presence of motors and fields
        has_motor1 = "motor_01" in csv_output
        has_motor2 = "motor_02" in csv_output
        has_health = "health_index" in csv_output
        has_rul = "rul_hours" in csv_output
        has_fault = "fault_type" in csv_output

        print(f"motor_01 present: {has_motor1}")
        print(f"motor_02 present: {has_motor2}")
        print(f"health_index field present: {has_health}")
        print(f"rul_hours field present: {has_rul}")
        print(f"fault_type field present: {has_fault}")

        if has_motor1 and has_motor2 and has_health and has_rul and has_fault:
            print("\n[VERIFICATION PASSED] All telemetry fields and multi-motor series confirmed in InfluxDB!")
        else:
            print("\n[VERIFICATION INCOMPLETE] Some telemetry fields or devices were missing.")
    except Exception as exc:
        print(f"[ERROR] Query failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
