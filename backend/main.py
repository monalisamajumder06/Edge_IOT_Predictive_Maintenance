"""FastAPI Backend Application Entrypoint.

Subsystem: IoT + Backend + Dashboard (Member 3)
Phase: Phase 4 Implementation
Classification: [PROJECT REQUIREMENT / IMPLEMENTATION DECISION]

Exposes REST endpoints for motor telemetry and health queries over InfluxDB.
Provides read-only access for downstream dashboards (Phase 5).
Excludes speculative CORS per Phase 4 requirements.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
from typing import AsyncGenerator
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from config.settings import get_settings
from backend.routes.health import router as health_router
from backend.routes.motors import router as motors_router
from backend.services.influx_service import InfluxDBService

logger = logging.getLogger("backend")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager managing async client lifecycle."""
    settings = get_settings()
    logging.basicConfig(level=settings.backend_log_level)
    logger.info("Initializing InfluxDB service client...")
    service = InfluxDBService(settings=settings)
    app.state.influx_service = service
    yield
    logger.info("Shutting down InfluxDB service client...")
    await service.close()
    app.state.influx_service = None


def create_app() -> FastAPI:
    """FastAPI Application Factory."""
    settings = get_settings()

    app = FastAPI(
        title="Edge-IoT Predictive Maintenance REST API",
        description=(
            "REST API exposing time-series telemetry and diagnostic predictions "
            "for industrial electric motors stored in InfluxDB. "
            "Built for Member 3 Phase 4 data delivery to future visualization dashboards."
        ),
        version="0.4.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
        debug=settings.backend_debug,
    )

    # -------------------------------------------------------------------------
    # Centralized Exception Handlers (Preventing Token / Stack Leakage)
    # -------------------------------------------------------------------------
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        # Sanitize exception message against InfluxDB token
        clean_detail = str(exc.detail).replace(settings.influxdb_token, "[REDACTED]")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": "HTTP_ERROR",
                "detail": clean_detail,
                "status_code": exc.status_code,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "VALIDATION_ERROR",
                "detail": str(exc.errors()),
                "status_code": status.HTTP_422_UNPROCESSABLE_ENTITY,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled server error: {exc}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "INTERNAL_SERVER_ERROR",
                "detail": "An unexpected server error occurred. Credentials and stack trace omitted.",
                "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    # -------------------------------------------------------------------------
    # Route Registration
    # -------------------------------------------------------------------------
    app.include_router(health_router)
    app.include_router(motors_router)

    return app


app = create_app()
