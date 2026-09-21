"""API response schemas for Edge-IoT Predictive Maintenance Platform.

Subsystem: IoT + Backend + Dashboard (Member 3)
Phase: Phase 4 Implementation
Classification: [IMPLEMENTATION DECISION]

Defines Pydantic response models for FastAPI endpoints:
- Latest motor telemetry
- Historical telemetry records
- Health trend observations
- RUL trend observations
- Fault history observations
- Fleet overview
- Health check status
- Structured error responses
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    """Health check response schema.
    
    Classification: [IMPLEMENTATION DECISION]
    Clearly distinguishes between API service availability and InfluxDB database reachability.
    """
    model_config = ConfigDict(extra="ignore")

    status: str = Field(
        ...,
        description="Overall system status: 'HEALTHY' when all components operational, 'DEGRADED' if database unavailable",
        examples=["HEALTHY", "DEGRADED"],
    )
    service: str = Field(
        default="UP",
        description="FastAPI service lifecycle status",
        examples=["UP"],
    )
    database: str = Field(
        ...,
        description="InfluxDB connectivity status: 'CONNECTED' or 'UNAVAILABLE'",
        examples=["CONNECTED", "UNAVAILABLE"],
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the health evaluation",
    )
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional diagnostic details (sanitized, zero credentials leaked)",
    )


class MotorTelemetryResponse(BaseModel):
    """Telemetry representation matching core project contract.
    
    Classification: [PROJECT REQUIREMENT / IMPLEMENTATION DECISION]
    Directly reflects data persisted in InfluxDB measurement 'predictions'.
    """
    model_config = ConfigDict(extra="ignore")

    device_id: str = Field(
        ...,
        description="Unique motor asset identifier",
        examples=["motor_01"],
    )
    fault_type: str = Field(
        ...,
        description="Diagnostic fault classification label",
        examples=["Inner_Race", "Normal"],
    )
    health_index: float = Field(
        ...,
        description="Composite health indicator [0.0 - 1.0]",
        examples=[0.88],
    )
    rul_hours: Union[int, float] = Field(
        ...,
        description="Remaining Useful Life in operating hours",
        examples=[420.0],
    )
    timestamp: datetime = Field(
        ...,
        description="Observation timestamp in UTC (ISO-8601)",
    )


class HealthObservation(BaseModel):
    """Health index historical trend observation point."""
    model_config = ConfigDict(extra="ignore")

    timestamp: datetime = Field(..., description="Observation UTC timestamp")
    health_index: float = Field(..., description="Composite health index value")


class RulObservation(BaseModel):
    """Remaining Useful Life historical trend observation point."""
    model_config = ConfigDict(extra="ignore")

    timestamp: datetime = Field(..., description="Observation UTC timestamp")
    rul_hours: Union[int, float] = Field(..., description="Remaining Useful Life in hours")


class FaultObservation(BaseModel):
    """Historical fault classification event observation point."""
    model_config = ConfigDict(extra="ignore")

    timestamp: datetime = Field(..., description="Observation UTC timestamp")
    fault_type: str = Field(..., description="Diagnostic fault classification label")


class FleetOverviewResponse(BaseModel):
    """Fleet status overview presenting latest state for all detected motors."""
    model_config = ConfigDict(extra="ignore")

    motors: List[MotorTelemetryResponse] = Field(
        ...,
        description="Latest telemetry state for each monitored motor",
    )
    total_motors: int = Field(
        ...,
        description="Count of distinct active motors in the fleet",
        examples=[2],
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of fleet overview generation",
    )


class ErrorResponse(BaseModel):
    """Structured error response schema."""
    model_config = ConfigDict(extra="ignore")

    error: str = Field(..., description="High-level error classification")
    detail: str = Field(..., description="Descriptive, sanitized error message")
    status_code: int = Field(..., description="HTTP status code")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when error occurred",
    )
