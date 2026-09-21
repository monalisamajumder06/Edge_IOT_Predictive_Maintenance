"""InfluxDB Line Protocol Serializer for Gateway Telemetry.

Subsystem: IoT + Backend + Dashboard (Member 3)
Phase: Phase 3 Implementation
Classification: [IMPLEMENTATION DECISION]

Translates normalized Phase 2 Output 1 telemetry into InfluxDB Line Protocol:
Measurement: predictions
Tag: device_id
Fields: fault_type (string), health_index (float), rul_hours (float)
Timestamp: Unix epoch milliseconds
"""

from datetime import datetime, timezone
from typing import Any, Dict, Union


def escape_tag(value: str) -> str:
    """Escape special characters in InfluxDB tag keys and values.
    
    Commas, equal signs, and spaces must be escaped with a backslash.
    """
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace(",", "\\,")
        .replace(" ", "\\ ")
        .replace("=", "\\=")
    )


def escape_string_field(value: str) -> str:
    """Escape special characters in InfluxDB string field values.
    
    String fields must be enclosed in double quotes. Double quotes and backslashes
    inside string values must be escaped.
    """
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def parse_timestamp_to_ms(ts: Union[str, datetime, int, float, None]) -> int:
    """Convert an ISO-8601 string, datetime, or numeric timestamp to Unix epoch milliseconds.
    
    Preserves the exact normalized timestamp from Phase 2 Output 1.
    """
    if ts is None:
        return int(datetime.now(timezone.utc).timestamp() * 1000)
    
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return int(ts.timestamp() * 1000)
    
    if isinstance(ts, (int, float)):
        # If timestamp is already in seconds (10 digits), convert to ms
        if ts < 1e11:
            return int(ts * 1000)
        # If already in ms (13 digits), return as integer
        return int(ts)
    
    if isinstance(ts, str):
        # Handle ISO-8601 string (e.g. 2026-09-13T10:43:55.000Z or +00:00)
        clean_str = ts.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(clean_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except ValueError:
            raise ValueError(f"Cannot parse timestamp string into epoch milliseconds: '{ts}'")
            
    raise TypeError(f"Unsupported timestamp type: {type(ts).__name__}")


def format_line_protocol(
    normalized_telemetry: Dict[str, Any],
    measurement: str = "predictions",
) -> str:
    """Serialize normalized Phase 2 Output 1 telemetry into InfluxDB Line Protocol.
    
    Boundary Rule:
    This function consumes already-validated and normalized telemetry from Phase 2.
    It performs storage boundary translation only and does not revalidate raw MQTT payloads.
    
    Storage Schema [IMPLEMENTATION DECISION]:
        Measurement: predictions
        Tag: device_id=<escaped_id>
        Fields: fault_type="<escaped_fault>",health_index=<float>,rul_hours=<float>
        Timestamp: <epoch_ms>
        
    Args:
        normalized_telemetry: Dictionary conforming to Phase 2 Output 1 structure.
        measurement: InfluxDB measurement name (default: 'predictions').
        
    Returns:
        Formatted Line Protocol string.
        
    Raises:
        KeyError: If a required storage boundary key ('device_id', 'fault_type', 
                 'health_index', or 'rul_hours') is absent from the normalized input.
        ValueError: If numeric values cannot be coerced to float.
    """
    # Serializer Defense (Storage Boundary Only)
    required_keys = ["device_id", "fault_type", "health_index", "rul_hours"]
    for k in required_keys:
        if k not in normalized_telemetry or normalized_telemetry[k] is None:
            raise KeyError(f"Storage serializer requires '{k}' in normalized telemetry payload.")

    raw_device_id = str(normalized_telemetry["device_id"]).strip()
    if not raw_device_id:
        raise ValueError("Storage serializer requires non-empty 'device_id'.")

    # Coerce numeric values strictly to float for InfluxDB schema consistency [IMPLEMENTATION DECISION]
    try:
        health_index = float(normalized_telemetry["health_index"])
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Cannot serialize health_index as float: {normalized_telemetry['health_index']}") from exc

    try:
        rul_hours = float(normalized_telemetry["rul_hours"])
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Cannot serialize rul_hours as float: {normalized_telemetry['rul_hours']}") from exc

    # Parse normalized timestamp (fallback to arrival time if missing)
    ts_raw = normalized_telemetry.get("timestamp") or normalized_telemetry.get("gateway_received_at")
    timestamp_ms = parse_timestamp_to_ms(ts_raw)

    # Format components
    tag_part = f"device_id={escape_tag(raw_device_id)}"
    field_fault = f"fault_type={escape_string_field(normalized_telemetry['fault_type'])}"
    field_health = f"health_index={health_index}"
    field_rul = f"rul_hours={rul_hours}"
    field_part = f"{field_fault},{field_health},{field_rul}"

    # Line Protocol: <measurement>[,<tag_key>=<tag_value>] <field_key>=<field_value> [<timestamp>]
    return f"{measurement},{tag_part} {field_part} {timestamp_ms}"
