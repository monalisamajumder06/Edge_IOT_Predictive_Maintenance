"""Telemetry Contract and Schema Validation Test Suite.

Stratified into three explicit test categories:
- Group A: PROJECT-REQUIRED validation
- Group B: RECOMMENDED implementation validation
- Group C: OPEN/UNFINALIZED behavior and future compatibility
"""

import json
from pathlib import Path
from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from schemas.telemetry import (
    CoreTelemetryPayload,
    RecommendedTelemetryPayload,
    IngestionTelemetryPayload,
    attach_ingestion_timestamp,
)


# =============================================================================
# GROUP A: PROJECT-REQUIRED VALIDATION
#
# These tests verify constraints explicitly mandated by the project specification:
# - Required fields: device_id, fault_type, health_index, rul_hours
# - Verbatim project example parsing
# - Rejection of missing required fields and incompatible data types
# =============================================================================

class TestGroupAProjectRequiredValidation:
    """Tests enforcing strictly documented project requirements."""

    def test_verbatim_project_example_succeeds(self):
        """Verify the exact project document example validates cleanly against CoreTelemetryPayload."""
        canonical_sample = {
            "device_id": "motor_01",
            "fault_type": "Inner_Race",
            "health_index": 0.88,
            "rul_hours": 420,
        }
        payload = CoreTelemetryPayload(**canonical_sample)
        assert payload.device_id == "motor_01"
        assert payload.fault_type == "Inner_Race"
        assert payload.health_index == 0.88
        assert payload.rul_hours == 420

    @pytest.mark.parametrize("missing_field", ["device_id", "fault_type", "health_index", "rul_hours"])
    def test_missing_required_field_fails(self, missing_field):
        """Verify that omitting any project-mandated field raises a ValidationError."""
        base_data = {
            "device_id": "motor_01",
            "fault_type": "Inner_Race",
            "health_index": 0.88,
            "rul_hours": 420,
        }
        del base_data[missing_field]
        with pytest.raises(ValidationError) as exc_info:
            CoreTelemetryPayload(**base_data)
        errors = exc_info.value.errors()
        assert any(missing_field in err["loc"] for err in errors)

    def test_empty_string_device_id_fails(self):
        """Verify device_id cannot be an empty string."""
        invalid_data = {
            "device_id": "",
            "fault_type": "Inner_Race",
            "health_index": 0.88,
            "rul_hours": 420,
        }
        with pytest.raises(ValidationError):
            CoreTelemetryPayload(**invalid_data)

    def test_empty_string_fault_type_fails(self):
        """Verify fault_type cannot be an empty string."""
        invalid_data = {
            "device_id": "motor_01",
            "fault_type": "",
            "health_index": 0.88,
            "rul_hours": 420,
        }
        with pytest.raises(ValidationError):
            CoreTelemetryPayload(**invalid_data)

    def test_incompatible_health_index_type_fails(self):
        """Verify health_index rejects non-numeric string representations that cannot be coerced."""
        invalid_data = {
            "device_id": "motor_01",
            "fault_type": "Inner_Race",
            "health_index": "not_a_number",
            "rul_hours": 420,
        }
        with pytest.raises(ValidationError):
            CoreTelemetryPayload(**invalid_data)

    def test_incompatible_rul_hours_type_fails(self):
        """Verify rul_hours rejects non-numeric values."""
        invalid_data = {
            "device_id": "motor_01",
            "fault_type": "Inner_Race",
            "health_index": 0.88,
            "rul_hours": "invalid_hours",
        }
        with pytest.raises(ValidationError):
            CoreTelemetryPayload(**invalid_data)

    def test_rul_hours_supports_both_int_and_float(self):
        """Verify rul_hours accepts integer or float numbers (e.g. 420 or 420.5)."""
        data_int = {
            "device_id": "motor_01",
            "fault_type": "Inner_Race",
            "health_index": 0.88,
            "rul_hours": 420,
        }
        data_float = {
            "device_id": "motor_01",
            "fault_type": "Inner_Race",
            "health_index": 0.88,
            "rul_hours": 420.5,
        }
        p_int = CoreTelemetryPayload(**data_int)
        p_float = CoreTelemetryPayload(**data_float)
        assert p_int.rul_hours == 420
        assert p_float.rul_hours == 420.5


# =============================================================================
# GROUP B: RECOMMENDED IMPLEMENTATION VALIDATION
#
# These tests verify recommended engineering choices proposed by Member 3.
# These are NOT official project document requirements:
# - Range checks on health_index [0.0, 1.0]
# - Non-negative constraint on rul_hours (>= 0)
# - Timestamp fallback behavior at ingestion
# =============================================================================

class TestGroupBRecommendedImplementationValidation:
    """Tests verifying recommended implementation choices (subject to team confirmation)."""

    def test_recommended_health_index_valid_range(self):
        """Verify RecommendedTelemetryPayload accepts valid boundary values 0.0 and 1.0."""
        low = RecommendedTelemetryPayload(
            device_id="motor_01", fault_type="Inner_Race", health_index=0.0, rul_hours=10
        )
        high = RecommendedTelemetryPayload(
            device_id="motor_01", fault_type="Inner_Race", health_index=1.0, rul_hours=10
        )
        assert low.health_index == 0.0
        assert high.health_index == 1.0

    def test_recommended_health_index_out_of_bounds_rejected(self):
        """Verify RecommendedTelemetryPayload rejects health_index outside [0.0, 1.0] as a recommendation."""
        invalid_high = {
            "device_id": "motor_01",
            "fault_type": "Inner_Race",
            "health_index": 1.05,
            "rul_hours": 100,
        }
        with pytest.raises(ValidationError) as exc_info:
            RecommendedTelemetryPayload(**invalid_high)
        assert "recommended range" in str(exc_info.value).lower()

        invalid_low = {
            "device_id": "motor_01",
            "fault_type": "Inner_Race",
            "health_index": -0.01,
            "rul_hours": 100,
        }
        with pytest.raises(ValidationError) as exc_info:
            RecommendedTelemetryPayload(**invalid_low)
        assert "recommended range" in str(exc_info.value).lower()

    def test_recommended_rul_hours_negative_rejected(self):
        """Verify RecommendedTelemetryPayload rejects negative rul_hours as a recommendation."""
        invalid_rul = {
            "device_id": "motor_01",
            "fault_type": "Inner_Race",
            "health_index": 0.88,
            "rul_hours": -5,
        }
        with pytest.raises(ValidationError) as exc_info:
            RecommendedTelemetryPayload(**invalid_rul)
        assert "recommended implementation assumption" in str(exc_info.value).lower()

    def test_ingestion_timestamp_fallback_when_missing(self):
        """Verify attach_ingestion_timestamp generates UTC timestamp when missing [RECOMMENDATION]."""
        raw = {
            "device_id": "motor_01",
            "fault_type": "Inner_Race",
            "health_index": 0.88,
            "rul_hours": 420,
        }
        ingested = attach_ingestion_timestamp(raw)
        assert isinstance(ingested, IngestionTelemetryPayload)
        assert isinstance(ingested.timestamp, datetime)
        assert ingested.device_id == "motor_01"

    def test_ingestion_timestamp_preserved_when_provided(self):
        """Verify explicit timestamp from edge is preserved if supplied [RECOMMENDATION]."""
        fixed_time = datetime(2026, 9, 13, 8, 30, 0, tzinfo=timezone.utc)
        raw = {
            "device_id": "motor_01",
            "fault_type": "Inner_Race",
            "health_index": 0.88,
            "rul_hours": 420,
            "timestamp": fixed_time,
        }
        ingested = IngestionTelemetryPayload(**raw)
        assert ingested.timestamp == fixed_time


# =============================================================================
# GROUP C: OPEN / UNFINALIZED BEHAVIOR AND TEST DATA
#
# These tests verify that:
# - Core schema does NOT prematurely enforce unfinalized multi-label structures
# - Downstream pipeline is tolerant to extra future metadata without crashing
# - The dummy predictions JSON dataset adheres to the schema
# =============================================================================

class TestGroupCOpenUnfinalizedBehavior:
    """Tests confirming contract tolerance and dummy dataset validity."""

    def test_extra_metadata_fields_tolerated_without_crashing(self):
        """Verify core contract ignores optional/future metadata fields without raising error.

        Ensures forward-compatibility when Member 2 or Member 1 adds metadata.
        """
        payload_with_metadata = {
            "device_id": "motor_01",
            "fault_type": "Inner_Race",
            "health_index": 0.88,
            "rul_hours": 420,
            "inference_time_ms": 14.2,  # Future optional metadata
            "model_version": "v1.0.0",  # Future optional metadata
        }
        # Must not raise ValidationError due to extra="ignore"
        parsed = CoreTelemetryPayload(**payload_with_metadata)
        assert parsed.device_id == "motor_01"
        assert parsed.fault_type == "Inner_Race"

    def test_dummy_predictions_file_conforms_to_schema(self):
        """Verify data/dummy_predictions.json file loads and each row satisfies CoreTelemetryPayload."""
        json_path = Path(__file__).parent.parent / "data" / "dummy_predictions.json"
        assert json_path.exists(), f"Dummy predictions file not found at {json_path}"

        with open(json_path, "r", encoding="utf-8") as f:
            records = json.load(f)

        assert isinstance(records, list)
        assert len(records) >= 1

        # The first entry MUST be the project specification example
        first_entry = records[0]
        assert first_entry["device_id"] == "motor_01"
        assert first_entry["fault_type"] == "Inner_Race"
        assert first_entry["health_index"] == 0.88
        assert first_entry["rul_hours"] == 420

        # All entries must parse into CoreTelemetryPayload
        for row in records:
            payload = CoreTelemetryPayload(**row)
            assert len(payload.device_id) > 0
            assert len(payload.fault_type) > 0
