"""Application configuration management for Edge-IoT Predictive Maintenance Platform.

Loads settings from environment variables and .env file.
Classification: [IMPLEMENTATION DECISION]
"""

from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized configuration for IoT messaging, database, and backend services."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # MQTT Broker Settings
    # -------------------------------------------------------------------------
    mqtt_broker_host: str = Field(
        default="localhost",
        description="Hostname or IP address of Mosquitto MQTT broker",
    )
    mqtt_broker_port: int = Field(
        default=1883,
        description="Port for MQTT broker communication",
    )
    mqtt_keepalive: int = Field(
        default=60,
        description="Keepalive interval in seconds",
    )
    mqtt_client_id: str = Field(
        default="edge_maint_backend_subscriber",
        description="MQTT client identifier for the backend service",
    )
    mqtt_topic_prediction_pattern: str = Field(
        default="motors/+/prediction",
        description="Wildcard subscription pattern for motor prediction telemetry",
    )
    mqtt_topic_status_pattern: str = Field(
        default="motors/+/status",
        description="Wildcard subscription pattern for motor status telemetry",
    )
    mqtt_qos: int = Field(
        default=1,
        description="MQTT Quality of Service level (0, 1, or 2)",
    )

    # -------------------------------------------------------------------------
    # InfluxDB Settings
    # -------------------------------------------------------------------------
    influxdb_url: str = Field(
        default="http://localhost:8086",
        description="URL for InfluxDB v2 instance",
    )
    influxdb_org: str = Field(
        default="industrial_iot",
        description="InfluxDB organization name",
    )
    influxdb_bucket: str = Field(
        default="motor_telemetry",
        description="InfluxDB bucket name for motor time-series data",
    )
    influxdb_token: str = Field(
        default="my-secure-placeholder-token",
        description="Authentication token for InfluxDB",
    )

    # -------------------------------------------------------------------------
    # FastAPI Backend Settings
    # -------------------------------------------------------------------------
    backend_host: str = Field(
        default="0.0.0.0",
        description="Bind host for FastAPI server",
    )
    backend_port: int = Field(
        default=8000,
        description="Bind port for FastAPI server",
    )
    backend_debug: bool = Field(
        default=True,
        description="Debug mode flag for development",
    )
    backend_log_level: str = Field(
        default="INFO",
        description="Logging level",
    )

    # -------------------------------------------------------------------------
    # Dashboard Settings
    # -------------------------------------------------------------------------
    dashboard_api_url: str = Field(
        default="http://localhost:8000",
        description="Base URL of FastAPI backend for dashboard consumption",
    )
    dashboard_port: int = Field(
        default=8501,
        description="Port for Streamlit dashboard",
    )
    dashboard_refresh_interval_seconds: int = Field(
        default=2,
        description="Auto-refresh interval for dashboard live views",
    )


@lru_cache()
def get_settings() -> Settings:
    """Return a cached singleton instance of application settings."""
    return Settings()
