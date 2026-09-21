"""Telemetry contract validation models for Edge-IoT Predictive Maintenance Platform.

Defines schemas that enforce the edge-to-backend interface boundaries.
Classification tags are explicitly applied to distinguish project requirements from recommendations.
"""

from datetime import datetime, timezone
from typing import Optional, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator


class CoreTelemetryPayload(BaseModel):
    """Core telemetry payload strictly mandated by the project specification.

    Classification: [PROJECT REQUIREMENT]

    Ground truth example from project documentation:
    {
        "device_id": "motor_01",
        "fault_type": "Inner_Race",
        "health_index": 0.88,
        "rul_hours": 420
    }

    Note: The project specifies fault classification is conceptually multi-label,
    but the contract example defines a single string field (`fault_type`).
    The exact representation of multi-label output is an [OPEN DECISION]
    requiring coordination with Member 2. Speculative multi-label fields
    are intentionally NOT frozen into this core schema.
    """

    model_config = ConfigDict(
        extra="ignore",  # Downstream tolerance: ignore future metadata fields during baseline processing
        str_strip_whitespace=True,
    )

    device_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier of the monitored motor asset [PROJECT REQUIREMENT]",
        examples=["motor_01"],
    )
    fault_type: str = Field(
        ...,
        min_length=1,
        description="Diagnostic fault classification label [PROJECT REQUIREMENT]",
        examples=["Inner_Race"],
    )
    health_index: float = Field(
        ...,
        description="Composite health indicator from TinyML model [PROJECT REQUIREMENT]",
        examples=[0.88],
    )
    rul_hours: Union[int, float] = Field(
        ...,
        description="Remaining Useful Life in operating hours [PROJECT REQUIREMENT]",
        examples=[420],
    )


class RecommendedTelemetryPayload(CoreTelemetryPayload):
    """Telemetry payload applying recommended engineering validation constraints.

    Classification: [RECOMMENDATION]

    These range constraints are engineering assumptions proposed by Member 3.
    They are NOT official project document requirements and require confirmation with Member 2:
    - `health_index` bounded in [0.0, 1.0]
    - `rul_hours` non-negative (>= 0)
    """

    @field_validator("health_index")
    @classmethod
    def validate_health_index_range(cls, value: float) -> float:
        """Enforce recommended health_index range [0.0, 1.0].

        Classification: [RECOMMENDATION] - Requires team confirmation with Member 2.
        """
        if not (0.0 <= value <= 1.0):
            raise ValueError(
                f"Health index {value} is outside recommended range [0.0, 1.0]. "
                "(Note: Range [0.0, 1.0] is a recommended implementation assumption, "
                "pending confirmation with Member 2)."
            )
        return value

    @field_validator("rul_hours")
    @classmethod
    def validate_rul_non_negative(cls, value: Union[int, float]) -> Union[int, float]:
        """Enforce recommended non-negative RUL hours.

        Classification: [RECOMMENDATION] - Requires team confirmation with Member 2.
        """
        if value < 0:
            raise ValueError(
                f"RUL hours {value} cannot be negative. "
                "(Note: Non-negative constraint is a recommended implementation assumption, "
                "pending confirmation with Member 2)."
            )
        return value


class IngestionTelemetryPayload(CoreTelemetryPayload):
    """Telemetry payload representing data processed at the Gateway/Backend ingestion point.

    Classification: [IMPLEMENTATION DECISION]

    Incorporates an optional `timestamp` field for time-series persistence in InfluxDB.
    Timestamp ownership is an [OPEN DECISION]. Fallback injection of arrival UTC time
    is a [RECOMMENDATION] requiring team agreement.
    """

    timestamp: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp for time-series storage. Assigned by gateway if omitted [OPEN DECISION / RECOMMENDATION]",
    )


def attach_ingestion_timestamp(
    payload: Union[CoreTelemetryPayload, dict],
    received_at: Optional[datetime] = None,
) -> IngestionTelemetryPayload:
    """Attach an ingestion timestamp to a telemetry payload if missing.

    Classification: [RECOMMENDATION] - Implementation fallback for time-series database.

    Args:
        payload: CoreTelemetryPayload instance or dictionary.
        received_at: Explicit UTC timestamp, or defaults to current UTC time.

    Returns:
        IngestionTelemetryPayload with verified timestamp.
    """
    ts = received_at or datetime.now(timezone.utc)
    if isinstance(payload, dict):
        data = payload.copy()
        if "timestamp" not in data or data["timestamp"] is None:
            data["timestamp"] = ts
        return IngestionTelemetryPayload(**data)

    data_dict = payload.model_dump()
    data_dict["timestamp"] = ts
    return IngestionTelemetryPayload(**data_dict)
