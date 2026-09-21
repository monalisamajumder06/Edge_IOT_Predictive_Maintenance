"""Industrial Edge-IoT Predictive Maintenance Dashboard.

Subsystem: IoT + Backend + Dashboard (Member 3)
Phase: Phase 5 Implementation
Classification: [PROJECT REQUIREMENT / IMPLEMENTATION DECISION]

Primary user-facing dashboard for plant technicians and maintenance engineers.
Consumes the FastAPI REST API backend exclusively (no direct InfluxDB access).
Dynamically discovers motors, plots degradation trends, logs fault events,
and handles backend/database outages cleanly.
"""

import logging
import os
import sys
import time
from pathlib import Path

# Ensure project root is available on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from config.settings import get_settings
from dashboard.api_client import (
    ApiClientError,
    ApiConnectionError,
    ApiDegradedError,
    ApiNotFoundError,
    DashboardApiClient,
)
from dashboard.components import (
    render_fault_history,
    render_fleet_overview,
    render_health_chart,
    render_motor_status_metrics,
    render_rul_chart,
    render_system_health_banner,
)

logger = logging.getLogger("dashboard.app")

# -----------------------------------------------------------------------------
# Page Configuration
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Edge-IoT Motor Predictive Maintenance",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main() -> None:
    settings = get_settings()
    api_url = os.environ.get("DASHBOARD_API_URL", settings.dashboard_api_url)
    client = DashboardApiClient(base_url=api_url)

    # -------------------------------------------------------------------------
    # Header Section
    # -------------------------------------------------------------------------
    st.title("⚙️ Industrial Motor Predictive Maintenance")
    st.caption(
        "Edge-IoT Telemetry & Condition Monitoring Dashboard (Member 3 Pipeline: "
        "Prediction JSON → Mosquitto → Node-RED → InfluxDB → FastAPI → Dashboard)"
    )

    # -------------------------------------------------------------------------
    # Sidebar Controls
    # -------------------------------------------------------------------------
    st.sidebar.header("🕹️ Controls & Navigation")

    # Manual Refresh Button
    if st.sidebar.button("🔄 Refresh Data", use_container_width=True):
        st.rerun()

    # Time Range Selection
    st.sidebar.subheader("⏳ Time Range")
    time_range_options = {
        "Last 1 Hour": "-1h",
        "Last 24 Hours": "-24h",
        "Last 7 Days": "-7d",
        "Last 30 Days": "-30d",
    }
    selected_range_label = st.sidebar.selectbox(
        "Historical Time Window",
        options=list(time_range_options.keys()),
        index=1,  # Default to Last 24 Hours
        help="Select historical window for health, RUL, and fault trend charts.",
    )
    time_range_param = time_range_options[selected_range_label]

    # Backend Connection Info
    st.sidebar.markdown("---")
    st.sidebar.subheader("🔌 Backend Connection")
    st.sidebar.code(f"API URL: {api_url}", language="text")

    # Auto-refresh control (conservative, opt-in)
    st.sidebar.markdown("---")
    st.sidebar.subheader("⏱️ Auto-Refresh")
    auto_refresh_enabled = st.sidebar.checkbox(
        "Enable Live Polling",
        value=False,
        help="Periodically re-fetches telemetry without continuous hammering.",
    )
    refresh_interval = st.sidebar.slider(
        "Interval (seconds)",
        min_value=5,
        max_value=60,
        value=settings.dashboard_refresh_interval_seconds if settings.dashboard_refresh_interval_seconds >= 5 else 10,
        step=5,
    )

    # -------------------------------------------------------------------------
    # System & Database Vitality Check
    # -------------------------------------------------------------------------
    health_data = client.get_health()
    render_system_health_banner(health_data)

    if health_data.get("status") == "OFFLINE":
        st.error(
            f"❌ **FastAPI Service Unreachable**\n\n"
            f"The dashboard cannot establish a connection to `{api_url}`.\n\n"
            "**Troubleshooting Steps:**\n"
            "1. Verify FastAPI server is running: `python -m uvicorn backend.main:app --port 8000`\n"
            "2. Verify the host and port match the `DASHBOARD_API_URL` setting.\n"
            "3. Check local firewall or network bindings."
        )
        st.stop()

    st.markdown("---")

    # -------------------------------------------------------------------------
    # 1. Fleet Overview Section
    # -------------------------------------------------------------------------
    motors = []
    try:
        motors = client.get_motors()
        render_fleet_overview(motors)
    except ApiDegradedError as exc:
        st.warning(f"⚠️ {exc.message}")
    except ApiConnectionError as exc:
        st.error(f"❌ {exc.message}")
    except ApiClientError as exc:
        st.error(f"❌ Failed to fetch fleet telemetry: {exc.message}")

    st.markdown("---")

    # -------------------------------------------------------------------------
    # 2. Motor Detail Deep-Dive
    # -------------------------------------------------------------------------
    st.subheader("🔍 Motor Detail Deep-Dive")

    # Dynamically populate motor selector from discovered fleet
    motor_ids = [m.get("device_id") for m in motors if m.get("device_id")]

    if not motor_ids:
        st.info("No active motors available in the fleet to inspect.")
        st.stop()

    selected_motor_id = st.selectbox(
        "Select Motor Asset to Inspect",
        options=motor_ids,
        index=0,
        help="Dynamically populated from discovered motors. Select a motor to display its real-time telemetry and historical trends.",
    )

    if selected_motor_id:
        # Fetch latest telemetry
        try:
            latest_telemetry = client.get_motor_latest(selected_motor_id)
            render_motor_status_metrics(latest_telemetry)
        except ApiNotFoundError:
            st.warning(f"Motor '{selected_motor_id}' has no recent telemetry records.")
        except ApiDegradedError as exc:
            st.warning(f"⚠️ {exc.message}")
        except Exception as exc:
            st.error(f"Failed to fetch latest telemetry for '{selected_motor_id}': {exc}")

        st.markdown("---")

        # Visualizations (Side-by-side Trends)
        chart_col1, chart_col2 = st.columns(2)

        with chart_col1:
            try:
                health_history = client.get_motor_health(selected_motor_id, start=time_range_param)
                render_health_chart(health_history)
            except ApiNotFoundError:
                st.info(f"No health history records found for '{selected_motor_id}'.")
            except Exception as exc:
                st.error(f"Failed to load health trend: {exc}")

        with chart_col2:
            try:
                rul_history = client.get_motor_rul(selected_motor_id, start=time_range_param)
                render_rul_chart(rul_history)
            except ApiNotFoundError:
                st.info(f"No RUL history records found for '{selected_motor_id}'.")
            except Exception as exc:
                st.error(f"Failed to load RUL trend: {exc}")

        st.markdown("---")

        # Fault Classification History
        try:
            fault_history = client.get_motor_faults(selected_motor_id, start=time_range_param)
            render_fault_history(fault_history)
        except ApiNotFoundError:
            st.info(f"No fault records found for '{selected_motor_id}'.")
        except Exception as exc:
            st.error(f"Failed to load fault history: {exc}")

    # -------------------------------------------------------------------------
    # Auto-Refresh Polling Loop
    # -------------------------------------------------------------------------
    if auto_refresh_enabled:
        time.sleep(refresh_interval)
        st.rerun()


if __name__ == "__main__":
    main()
