"""Automated Test Suite for Python MQTT Dummy Publisher.

Subsystem: IoT + Backend + Dashboard (Member 3)
Phase: Phase 2 Baseline Development
Classification: [IMPLEMENTATION DECISION]

Tests strictly focus on publisher responsibilities:
- Reading dummy datasets
- Validating outgoing telemetry against CoreTelemetryPayload in NORMAL mode
- Constructing correct topic hierarchy (motors/{device_id}/prediction)
- Handling multi-motor topics (motor_01, motor_02)
- Serializing telemetry JSON payloads cleanly
- Test injection mode generating invalid payloads bypassing schema validation
- Broker connection failure resilience and error logging
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from pydantic import ValidationError

from gateway.dummy_publisher import (
    build_prediction_topic,
    load_dummy_dataset,
    validate_and_format_payload,
    generate_test_injection_payload,
    MqttDummyPublisher,
    run_normal_mode,
    run_test_mode,
)
from schemas.telemetry import CoreTelemetryPayload


class TestMqttPublisherTopicAndPayloadFormatting:
    """Tests topic generation and payload serialization."""

    def test_build_prediction_topic(self):
        """Verify topic hierarchy follows motors/{device_id}/prediction."""
        assert build_prediction_topic("motor_01") == "motors/motor_01/prediction"
        assert build_prediction_topic("motor_02") == "motors/motor_02/prediction"
        assert build_prediction_topic("pump_subassembly_4") == "motors/pump_subassembly_4/prediction"

    def test_validate_and_format_canonical_sample(self):
        """Verify canonical Phase 1 sample generates correct topic and JSON payload."""
        canonical = {
            "device_id": "motor_01",
            "fault_type": "Inner_Race",
            "health_index": 0.88,
            "rul_hours": 420,
        }
        topic, payload_str = validate_and_format_payload(canonical)
        assert topic == "motors/motor_01/prediction"

        parsed = json.loads(payload_str)
        assert parsed["device_id"] == "motor_01"
        assert parsed["fault_type"] == "Inner_Race"
        assert parsed["health_index"] == 0.88
        assert parsed["rul_hours"] == 420

    def test_validate_and_format_multimotor_sample(self):
        """Verify multiple motor device IDs construct distinct appropriate topics."""
        record_m1 = {
            "device_id": "motor_01",
            "fault_type": "Bearing_Ball",
            "health_index": 0.65,
            "rul_hours": 210,
        }
        record_m2 = {
            "device_id": "motor_02",
            "fault_type": "Normal",
            "health_index": 0.99,
            "rul_hours": 1200,
        }
        topic1, _ = validate_and_format_payload(record_m1)
        topic2, _ = validate_and_format_payload(record_m2)
        assert topic1 == "motors/motor_01/prediction"
        assert topic2 == "motors/motor_02/prediction"

    def test_load_dummy_dataset_loads_existing_file(self):
        """Verify load_dummy_dataset successfully parses data/dummy_predictions.json."""
        records = load_dummy_dataset()
        assert isinstance(records, list)
        assert len(records) >= 3
        # Check first entry matches canonical project specification
        assert records[0]["device_id"] == "motor_01"
        assert records[0]["fault_type"] == "Inner_Race"


class TestNormalModeValidationRejection:
    """Tests verifying normal mode strictly rejects invalid payloads on publisher side."""

    def test_normal_mode_rejects_missing_required_fields(self):
        """Verify normal mode validation rejects records missing required fields."""
        invalid_missing = {
            "device_id": "motor_01",
            "fault_type": "Inner_Race",
            # missing health_index and rul_hours
        }
        with pytest.raises(ValidationError):
            validate_and_format_payload(invalid_missing)

    def test_normal_mode_rejects_invalid_numeric_types(self):
        """Verify normal mode validation rejects records with non-numeric fields."""
        invalid_types = {
            "device_id": "motor_01",
            "fault_type": "Inner_Race",
            "health_index": "not_a_float",
            "rul_hours": 420,
        }
        with pytest.raises(ValidationError):
            validate_and_format_payload(invalid_types)

    def test_normal_mode_rejects_empty_device_id(self):
        """Verify normal mode validation rejects empty string device_id."""
        invalid_id = {
            "device_id": "",
            "fault_type": "Inner_Race",
            "health_index": 0.88,
            "rul_hours": 420,
        }
        with pytest.raises(ValidationError):
            validate_and_format_payload(invalid_id)


class TestTestInjectionModePayloadGeneration:
    """Tests verifying test injection mode generates invalid payloads bypassing schema."""

    def test_inject_malformed_json_syntax(self):
        """Verify malformed-json produces raw unparseable JSON string."""
        topic, raw_payload = generate_test_injection_payload("malformed-json")
        assert topic == "motors/motor_01/prediction"
        assert "MALFORMED_JSON" in raw_payload
        with pytest.raises(json.JSONDecodeError):
            json.loads(raw_payload)

    def test_inject_missing_field(self):
        """Verify missing-field produces JSON missing health_index."""
        topic, raw_payload = generate_test_injection_payload("missing-field")
        assert topic == "motors/motor_01/prediction"
        parsed = json.loads(raw_payload)
        assert "health_index" not in parsed
        assert "device_id" in parsed

    def test_inject_invalid_type(self):
        """Verify invalid-type produces non-numeric health_index."""
        topic, raw_payload = generate_test_injection_payload("invalid-type")
        assert topic == "motors/motor_01/prediction"
        parsed = json.loads(raw_payload)
        assert isinstance(parsed["health_index"], str)

    def test_inject_topic_mismatch(self):
        """Verify topic-mismatch publishes payload with motor_01 to motor_99 topic."""
        topic, raw_payload = generate_test_injection_payload("topic-mismatch")
        assert topic == "motors/motor_99/prediction"
        parsed = json.loads(raw_payload)
        assert parsed["device_id"] == "motor_01"

    def test_inject_empty_id(self):
        """Verify empty-id produces payload with empty device_id string."""
        topic, raw_payload = generate_test_injection_payload("empty-id")
        parsed = json.loads(raw_payload)
        assert parsed["device_id"] == ""

    def test_unknown_injection_type_raises_error(self):
        """Verify unsupported injection type raises ValueError."""
        with pytest.raises(ValueError) as exc:
            generate_test_injection_payload("non-existent-type")
        assert "Unknown injection_type" in str(exc.value)


class TestMqttPublisherExecutionAndFailureHandling:
    """Tests verifying publisher client logic and connection handling."""

    @patch("paho.mqtt.client.Client.connect")
    @patch("paho.mqtt.client.Client.loop_start")
    def test_publisher_connect_handles_refusal(self, mock_loop, mock_connect):
        """Verify publisher handles ConnectionRefusedError cleanly without crashing."""
        mock_connect.side_effect = ConnectionRefusedError("Connection refused by broker")
        publisher = MqttDummyPublisher(host="127.0.0.1", port=9999)
        connected = publisher.connect()
        assert connected is False
        assert publisher.connected is False

    def test_publisher_publish_message_mock(self):
        """Verify publish_message calls underlying paho publish and checks status."""
        publisher = MqttDummyPublisher(host="localhost", port=1883)
        mock_info = MagicMock()
        mock_info.is_published.return_value = True
        publisher.client.publish = MagicMock(return_value=mock_info)

        success = publisher.publish_message("motors/motor_01/prediction", '{"test": 1}')
        assert success is True
        publisher.client.publish.assert_called_once_with(
            "motors/motor_01/prediction", payload='{"test": 1}', qos=1, retain=False
        )

    def test_run_normal_mode_publishes_all_records(self):
        """Verify run_normal_mode iterates through dataset and publishes all valid records."""
        publisher = MagicMock(spec=MqttDummyPublisher)
        publisher.publish_message.return_value = True

        count = run_normal_mode(publisher, once=True, delay_seconds=0)
        assert count >= 3
        assert publisher.publish_message.call_count >= 3

    def test_run_test_mode_publishes_injected_payload(self):
        """Verify run_test_mode publishes test payload."""
        publisher = MagicMock(spec=MqttDummyPublisher)
        publisher.publish_message.return_value = True

        success = run_test_mode(publisher, injection_type="missing-field")
        assert success is True
        publisher.publish_message.assert_called_once()
