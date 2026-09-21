"""FastAPI route dependencies.

Subsystem: IoT + Backend + Dashboard (Member 3)
Phase: Phase 4 Implementation
Classification: [IMPLEMENTATION DECISION]
"""

from fastapi import Request
from backend.services.influx_service import InfluxDBService


def get_influx_service(request: Request) -> InfluxDBService:
    """Dependency provider for InfluxDBService instance."""
    if hasattr(request.app.state, "influx_service") and request.app.state.influx_service is not None:
        return request.app.state.influx_service
    return InfluxDBService()
