"""Motor telemetry and fleet REST endpoints.

Subsystem: IoT + Backend + Dashboard (Member 3)
Phase: Phase 4 Implementation
Classification: [PROJECT REQUIREMENT / IMPLEMENTATION DECISION]

Provides read-only REST access to motor telemetry stored in InfluxDB:
- Fleet overview
- Latest motor state
- Historical telemetry
- Health trend
- RUL trend
- Fault history
"""

from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.routes.deps import get_influx_service
from backend.schemas.responses import (
    ErrorResponse,
    FaultObservation,
    FleetOverviewResponse,
    HealthObservation,
    MotorTelemetryResponse,
    RulObservation,
)
from backend.services.influx_service import (
    InfluxDBQueryError,
    InfluxDBService,
    InfluxDBUnavailableError,
    validate_device_id,
    validate_time_param,
)

router = APIRouter(prefix="/api/motors", tags=["Motors"])


@router.get(
    "",
    response_model=FleetOverviewResponse,
    summary="Fleet Overview",
    description="Retrieves the latest available telemetry state for all detected motors in the fleet.",
    responses={
        200: {"description": "Successfully retrieved fleet overview."},
        502: {"model": ErrorResponse, "description": "InfluxDB query error."},
        503: {"model": ErrorResponse, "description": "InfluxDB service unavailable."},
    },
)
async def get_fleet(
    service: InfluxDBService = Depends(get_influx_service),
) -> FleetOverviewResponse:
    """Return latest state for all monitored motors."""
    try:
        motors = await service.get_fleet_latest()
        return FleetOverviewResponse(
            motors=motors,
            total_motors=len(motors),
            timestamp=datetime.now(timezone.utc),
        )
    except InfluxDBUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except InfluxDBQueryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.get(
    "/{device_id}/latest",
    response_model=MotorTelemetryResponse,
    summary="Latest Telemetry for One Motor",
    description="Retrieves the most recent telemetry observation for a specific motor.",
    responses={
        200: {"description": "Latest telemetry observation found."},
        400: {"model": ErrorResponse, "description": "Invalid device_id format."},
        404: {"model": ErrorResponse, "description": "Motor not found or has no telemetry."},
        502: {"model": ErrorResponse, "description": "InfluxDB query error."},
        503: {"model": ErrorResponse, "description": "InfluxDB service unavailable."},
    },
)
async def get_motor_latest(
    device_id: str,
    service: InfluxDBService = Depends(get_influx_service),
) -> MotorTelemetryResponse:
    """Return the latest telemetry state for one motor."""
    try:
        clean_id = validate_device_id(device_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        latest = await service.get_motor_latest(clean_id)
        if latest is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Motor '{clean_id}' not found or has no telemetry records.",
            )
        return latest
    except InfluxDBUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except InfluxDBQueryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.get(
    "/{device_id}/history",
    response_model=List[MotorTelemetryResponse],
    summary="Historical Telemetry for One Motor",
    description="Retrieves chronological historical telemetry records within the specified time window.",
    responses={
        200: {"description": "Historical telemetry records retrieved."},
        400: {"model": ErrorResponse, "description": "Invalid parameters or time range."},
        404: {"model": ErrorResponse, "description": "Motor not found."},
        502: {"model": ErrorResponse, "description": "InfluxDB query error."},
        503: {"model": ErrorResponse, "description": "InfluxDB service unavailable."},
    },
)
async def get_motor_history(
    device_id: str,
    start: str = Query(
        "-24h",
        description="Start of time window as relative duration (e.g. '-1h', '-24h', '-7d') or ISO-8601 UTC string",
    ),
    stop: Optional[str] = Query(
        None,
        description="Optional end of time window (e.g. 'now()' or ISO-8601 UTC string)",
    ),
    service: InfluxDBService = Depends(get_influx_service),
) -> List[MotorTelemetryResponse]:
    """Return historical telemetry records for one motor."""
    try:
        clean_id = validate_device_id(device_id)
        validate_time_param(start, "start")
        validate_time_param(stop, "stop")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        records = await service.get_motor_history(clean_id, start=start, stop=stop)
        if not records:
            # Check if motor exists at all
            existing = await service.get_motor_latest(clean_id)
            if existing is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Motor '{clean_id}' not found or has no telemetry records.",
                )
        return records
    except InfluxDBUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except InfluxDBQueryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.get(
    "/{device_id}/health",
    response_model=List[HealthObservation],
    summary="Motor Health Trend",
    description="Retrieves historical health_index observations for plotting trend curves.",
    responses={
        200: {"description": "Health trend observations retrieved."},
        400: {"model": ErrorResponse, "description": "Invalid parameters or time range."},
        404: {"model": ErrorResponse, "description": "Motor not found."},
        502: {"model": ErrorResponse, "description": "InfluxDB query error."},
        503: {"model": ErrorResponse, "description": "InfluxDB service unavailable."},
    },
)
async def get_motor_health_trend(
    device_id: str,
    start: str = Query("-24h", description="Start of time window (relative or ISO-8601)"),
    stop: Optional[str] = Query(None, description="Optional end of time window"),
    service: InfluxDBService = Depends(get_influx_service),
) -> List[HealthObservation]:
    """Return historical health_index observations for plotting."""
    try:
        clean_id = validate_device_id(device_id)
        validate_time_param(start, "start")
        validate_time_param(stop, "stop")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        observations = await service.get_motor_health_trend(clean_id, start=start, stop=stop)
        if not observations:
            existing = await service.get_motor_latest(clean_id)
            if existing is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Motor '{clean_id}' not found or has no telemetry records.",
                )
        return observations
    except InfluxDBUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except InfluxDBQueryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.get(
    "/{device_id}/rul",
    response_model=List[RulObservation],
    summary="Motor RUL Trend",
    description="Retrieves historical rul_hours observations for plotting trend curves.",
    responses={
        200: {"description": "RUL trend observations retrieved."},
        400: {"model": ErrorResponse, "description": "Invalid parameters or time range."},
        404: {"model": ErrorResponse, "description": "Motor not found."},
        502: {"model": ErrorResponse, "description": "InfluxDB query error."},
        503: {"model": ErrorResponse, "description": "InfluxDB service unavailable."},
    },
)
async def get_motor_rul_trend(
    device_id: str,
    start: str = Query("-24h", description="Start of time window (relative or ISO-8601)"),
    stop: Optional[str] = Query(None, description="Optional end of time window"),
    service: InfluxDBService = Depends(get_influx_service),
) -> List[RulObservation]:
    """Return historical rul_hours observations for plotting."""
    try:
        clean_id = validate_device_id(device_id)
        validate_time_param(start, "start")
        validate_time_param(stop, "stop")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        observations = await service.get_motor_rul_trend(clean_id, start=start, stop=stop)
        if not observations:
            existing = await service.get_motor_latest(clean_id)
            if existing is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Motor '{clean_id}' not found or has no telemetry records.",
                )
        return observations
    except InfluxDBUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except InfluxDBQueryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.get(
    "/{device_id}/faults",
    response_model=List[FaultObservation],
    summary="Motor Fault Classification History",
    description="Retrieves historical diagnostic fault classification events.",
    responses={
        200: {"description": "Fault classification events retrieved."},
        400: {"model": ErrorResponse, "description": "Invalid parameters or time range."},
        404: {"model": ErrorResponse, "description": "Motor not found."},
        502: {"model": ErrorResponse, "description": "InfluxDB query error."},
        503: {"model": ErrorResponse, "description": "InfluxDB service unavailable."},
    },
)
async def get_motor_fault_history(
    device_id: str,
    start: str = Query("-7d", description="Start of time window (relative or ISO-8601)"),
    stop: Optional[str] = Query(None, description="Optional end of time window"),
    service: InfluxDBService = Depends(get_influx_service),
) -> List[FaultObservation]:
    """Return historical fault classification events."""
    try:
        clean_id = validate_device_id(device_id)
        validate_time_param(start, "start")
        validate_time_param(stop, "stop")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        events = await service.get_motor_fault_history(clean_id, start=start, stop=stop)
        if not events:
            existing = await service.get_motor_latest(clean_id)
            if existing is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Motor '{clean_id}' not found or has no telemetry records.",
                )
        return events
    except InfluxDBUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except InfluxDBQueryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
