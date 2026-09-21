"""Health check route handler.

Subsystem: IoT + Backend + Dashboard (Member 3)
Phase: Phase 4 Implementation
Classification: [PROJECT REQUIREMENT / IMPLEMENTATION DECISION]

Requirement: Clearly distinguish between API service running and InfluxDB reachability.
Implementation Decision: Return HTTP 200 when all healthy; HTTP 503 when InfluxDB is unavailable.
"""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Response, status

from backend.routes.deps import get_influx_service
from backend.schemas.responses import HealthResponse
from backend.services.influx_service import InfluxDBService, InfluxDBUnavailableError

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="System and Database Health Check",
    description="Reports API service availability and live InfluxDB connectivity status. "
                "Distinguishes between API service running and database availability.",
    responses={
        200: {"description": "API service running and InfluxDB connected."},
        503: {"description": "API service running but InfluxDB is unreachable (degraded state)."},
    },
)
async def get_health(
    response: Response,
    service: InfluxDBService = Depends(get_influx_service),
) -> HealthResponse:
    """Evaluate API and InfluxDB health."""
    try:
        db_check = await service.check_health()
        if db_check.get("database_connected", False):
            response.status_code = status.HTTP_200_OK
            return HealthResponse(
                status="HEALTHY",
                service="UP",
                database="CONNECTED",
                timestamp=datetime.now(timezone.utc),
                details=db_check,
            )
        else:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return HealthResponse(
                status="DEGRADED",
                service="UP",
                database="UNAVAILABLE",
                timestamp=datetime.now(timezone.utc),
                details=db_check,
            )
    except InfluxDBUnavailableError as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(
            status="DEGRADED",
            service="UP",
            database="UNAVAILABLE",
            timestamp=datetime.now(timezone.utc),
            details={"error": str(exc)},
        )
