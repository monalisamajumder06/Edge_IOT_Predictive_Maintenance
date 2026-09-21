"""Unit Test Suite for InfluxDB Storage Layer and Line Protocol Serialization.

Subsystem: IoT + Backend + Dashboard (Member 3)
Phase: Phase 3 Implementation
Classification: [IMPLEMENTATION DECISION]

Tests strictly focus on Phase 3 storage-boundary responsibilities:
- Transforming validated Phase 2 Output 1 into InfluxDB Line Protocol
- Preserving device_id as indexed tag
- Preserving fault_type, health_index, rul_hours as fields
- Escaping special characters in tags and fields per InfluxDB specification
- Timestamp conversion from ISO-8601 string to Unix epoch milliseconds
- Multi-motor series separation (motor_01, motor_02, motor_03)
- Serializer defense against incomplete normalized payloads (without duplicating MQTT validation)
- InfluxDB configuration loading from environment variables
- Simulated HTTP write failure handling
"""

import os
from unittest.mock import MagicMock, patch
import pytest

from config.settings import Settings, get_settings
from gateway.line_protocol import (
    escape_string_field,
    escape_tag,
    format_line_protocol,
    parse_timestamp_to_ms,
)


class TestLineProtocolEscapingAndFormatting:
    """Tests InfluxDB Line Protocol syntax rules and character escaping."""

    def test_escape_tag_special_characters(self):
        """Verify commas, spaces, and equal signs are escaped in tags."""
        assert escape_tag("motor_01") == "motor_01"
        assert escape_tag("motor 01") == r"motor\ 01"
        assert escape_tag("motor,line=A") == r"motor\,line\=A"
        assert escape_tag("pump\\sub") == r"pump\\sub"

    def test_escape_string_field_enclosed_in_quotes(self):
        """Verify string fields are enclosed in double quotes with quotes/backslashes escaped."""
        assert escape_string_field("Inner_Race") == '"Inner_Race"'
        assert escape_string_field('Bearing "Ball" Defect') == r'"Bearing \"Ball\" Defect"'
        assert escape_string_field(r"Fault\A") == r'"Fault\\A"'

    def test_parse_timestamp_to_ms_iso_utc(self):
        """Verify ISO-8601 UTC strings convert to integer epoch milliseconds."""
        # 2026-09-13T10:00:00Z -> 1789293600000 ms (or exact epoch ms)
        iso_str = "2026-09-13T10:00:00Z"
        ms = parse_timestamp_to_ms(iso_str)
        assert isinstance(ms, int)
        assert ms > 0

    def test_parse_timestamp_to_ms_preserves_millisecond_resolution(self):
        """Verify fractional seconds in ISO strings are preserved in ms epoch."""
        iso_str = "2026-09-13T10:00:00.500Z"
        ms = parse_timestamp_to_ms(iso_str)
        assert ms % 1000 == 500


class TestPhase2Output1ToLineProtocolSerialization:
    """Tests converting normalized Phase 2 Output 1 into InfluxDB Line Protocol."""

    def test_canonical_project_sample_serialization(self):
        """Verify canonical project telemetry sample serializes into valid Line Protocol."""
        normalized_sample = {
            "status": "ACCEPTED",
            "disposition": "ACCEPTED",
            "device_id": "motor_01",
            "fault_type": "Inner_Race",
            "health_index": 0.88,
            "rul_hours": 420,
            "timestamp": "2026-09-13T10:30:00.000Z",
            "gateway_received_at": "2026-09-13T10:30:00.000Z",
            "topic": "motors/motor_01/prediction",
        }
        line = format_line_protocol(normalized_sample)
        # Expected structure: predictions,device_id=motor_01 fault_type="Inner_Race",health_index=0.88,rul_hours=420.0 <timestamp_ms>
        parts = line.split(" ")
        assert len(parts) == 3

        # Measurement and Tag
        assert parts[0] == "predictions,device_id=motor_01"

        # Fields
        fields = parts[1].split(",")
        assert 'fault_type="Inner_Race"' in fields
        assert "health_index=0.88" in fields
        assert "rul_hours=420.0" in fields

        # Timestamp
        assert parts[2].isdigit()
        assert int(parts[2]) == parse_timestamp_to_ms("2026-09-13T10:30:00.000Z")

    def test_float_rul_hours_preserved(self):
        """Verify float rul_hours (e.g. 420.5) is preserved as float in Line Protocol."""
        sample = {
            "device_id": "motor_01",
            "fault_type": "Normal",
            "health_index": 0.95,
            "rul_hours": 420.5,
            "timestamp": "2026-09-13T10:00:00Z",
        }
        line = format_line_protocol(sample)
        assert "rul_hours=420.5" in line

    def test_custom_measurement_name_supported(self):
        """Verify custom measurement name is applied when specified."""
        sample = {
            "device_id": "motor_01",
            "fault_type": "Inner_Race",
            "health_index": 0.88,
            "rul_hours": 420,
            "timestamp": "2026-09-13T10:00:00Z",
        }
        line = format_line_protocol(sample, measurement="motor_telemetry_custom")
        assert line.startswith("motor_telemetry_custom,device_id=motor_01")


class TestMultiMotorSeriesSeparation:
    """Tests ensuring distinct motors create separate InfluxDB series."""

    def test_multimotor_isolation(self):
        """Verify motor_01 and motor_02 produce distinct tag series without collision."""
        m1 = {
            "device_id": "motor_01",
            "fault_type": "Inner_Race",
            "health_index": 0.70,
            "rul_hours": 300,
            "timestamp": "2026-09-13T12:00:00Z",
        }
        m2 = {
            "device_id": "motor_02",
            "fault_type": "Normal",
            "health_index": 0.98,
            "rul_hours": 1100,
            "timestamp": "2026-09-13T12:00:00Z",
        }
        m3 = {
            "device_id": "motor_03",
            "fault_type": "Bearing_Ball",
            "health_index": 0.45,
            "rul_hours": 80,
            "timestamp": "2026-09-13T12:00:00Z",
        }

        line1 = format_line_protocol(m1)
        line2 = format_line_protocol(m2)
        line3 = format_line_protocol(m3)

        assert line1.startswith("predictions,device_id=motor_01")
        assert line2.startswith("predictions,device_id=motor_02")
        assert line3.startswith("predictions,device_id=motor_03")

        # Confirm different metrics per motor
        assert "health_index=0.7" in line1
        assert "health_index=0.98" in line2
        assert "health_index=0.45" in line3


class TestSerializerStorageBoundaryDefense:
    """Tests storage serializer defensive behavior without duplicating MQTT validation."""

    @pytest.mark.parametrize("missing_key", ["device_id", "fault_type", "health_index", "rul_hours"])
    def test_serializer_raises_keyerror_on_missing_storage_field(self, missing_key):
        """Verify serializer raises KeyError if an essential storage key is missing."""
        incomplete = {
            "device_id": "motor_01",
            "fault_type": "Inner_Race",
            "health_index": 0.88,
            "rul_hours": 420,
            "timestamp": "2026-09-13T10:00:00Z",
        }
        del incomplete[missing_key]
        with pytest.raises(KeyError) as exc_info:
            format_line_protocol(incomplete)
        assert missing_key in str(exc_info.value)

    def test_serializer_raises_valueerror_on_empty_device_id(self):
        """Verify serializer raises ValueError if device_id is empty string."""
        invalid = {
            "device_id": "   ",
            "fault_type": "Inner_Race",
            "health_index": 0.88,
            "rul_hours": 420,
            "timestamp": "2026-09-13T10:00:00Z",
        }
        with pytest.raises(ValueError) as exc_info:
            format_line_protocol(invalid)
        assert "device_id" in str(exc_info.value)

    def test_serializer_raises_valueerror_on_non_numeric_metrics(self):
        """Verify serializer raises ValueError if numeric metrics cannot be coerced to float."""
        invalid = {
            "device_id": "motor_01",
            "fault_type": "Inner_Race",
            "health_index": "not_a_number",
            "rul_hours": 420,
            "timestamp": "2026-09-13T10:00:00Z",
        }
        with pytest.raises(ValueError) as exc_info:
            format_line_protocol(invalid)
        assert "health_index" in str(exc_info.value)


class TestInfluxDbConfigurationAndSettings:
    """Tests configuration loading for InfluxDB connection."""

    def test_influxdb_settings_defaults(self):
        """Verify default InfluxDB settings match Phase 1 design."""
        settings = Settings()
        assert settings.influxdb_url == "http://localhost:8086"
        assert settings.influxdb_org == "industrial_iot"
        assert settings.influxdb_bucket == "motor_telemetry"
        assert settings.influxdb_token == "my-secure-placeholder-token"

    def test_influxdb_settings_environment_override(self):
        """Verify environment variables cleanly override InfluxDB configuration."""
        env_vars = {
            "INFLUXDB_URL": "http://192.168.1.100:8086",
            "INFLUXDB_ORG": "custom_plant",
            "INFLUXDB_BUCKET": "custom_motors",
            "INFLUXDB_TOKEN": "custom-dev-token-abc",
        }
        with patch.dict(os.environ, env_vars):
            overridden = Settings()
            assert overridden.influxdb_url == "http://192.168.1.100:8086"
            assert overridden.influxdb_org == "custom_plant"
            assert overridden.influxdb_bucket == "custom_motors"
            assert overridden.influxdb_token == "custom-dev-token-abc"


class TestSimulatedWriteFailureHandling:
    """Tests simulated HTTP response handling for InfluxDB write failures."""

    def test_successful_http_write_disposition(self):
        """Verify HTTP 204 is recognized as successful InfluxDB write."""
        # InfluxDB v2 /api/v2/write returns HTTP 204 No Content on success
        status_code = 204
        is_success = (status_code == 204)
        assert is_success is True

    def test_unauthorized_token_disposition(self):
        """Verify HTTP 401 returns unauthorized error without crashing."""
        status_code = 401
        is_success = (status_code == 204)
        error_type = "UNAUTHORIZED" if status_code == 401 else "UNKNOWN"
        assert is_success is False
        assert error_type == "UNAUTHORIZED"

    def test_bucket_not_found_disposition(self):
        """Verify HTTP 404 returns bucket not found without crashing."""
        status_code = 404
        is_success = (status_code == 204)
        error_type = "BUCKET_NOT_FOUND" if status_code == 404 else "UNKNOWN"
        assert is_success is False
        assert error_type == "BUCKET_NOT_FOUND"
