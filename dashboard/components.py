"""UI Components and Visualizations for Streamlit Dashboard.

Subsystem: IoT + Backend + Dashboard (Member 3)
Phase: Phase 5 Implementation
Classification: [PROJECT REQUIREMENT / IMPLEMENTATION DECISION]

Reusable rendering components for:
- System and database health status banners
- Fleet overview table
- Motor latest status metric cards
- Health degradation time-series charts
- Remaining Useful Life (RUL) time-series charts
- Fault classification event log tables

Strict Domain Boundaries:
- Zero invented health thresholds (e.g. no arbitrary health < 0.5 = critical).
- Zero invented fault severity classifications (e.g. no arbitrary Inner_Race = critical).
- Clear empty state fallbacks without crashing or displaying fabricated values.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import pandas as pd
import streamlit as st


def format_iso_timestamp(ts: Any) -> str:
    """Format an ISO-8601 timestamp string into a readable UTC representation."""
    if not ts:
        return "N/A"
    try:
        if isinstance(ts, (int, float)):
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        elif isinstance(ts, str):
            clean_ts = ts.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_ts)
        elif isinstance(ts, datetime):
            dt = ts
        else:
            return str(ts)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return str(ts)


def render_system_health_banner(health_data: Dict[str, Any]) -> None:
    """Render a top-level system availability banner based on GET /health."""
    status = health_data.get("status", "UNKNOWN")
    service = health_data.get("service", "UNKNOWN")
    database = health_data.get("database", "UNKNOWN")

    if status == "HEALTHY" and service == "UP" and database == "CONNECTED":
        st.success(f"🟢 **System Operational** | Backend API: **{service}** | InfluxDB: **{database}**")
    elif status == "DEGRADED" or database == "UNAVAILABLE":
        st.warning(
            f"🟡 **System Degraded** | Backend API: **{service}** | InfluxDB: **{database}** — "
            "Database is unreachable. Live queries may fail."
        )
    else:
        st.error(
            f"🔴 **System Offline** | Backend API: **{service}** | InfluxDB: **{database}** — "
            "Cannot communicate with FastAPI service. Please verify the backend is running."
        )


def render_fleet_overview(motors: List[Dict[str, Any]]) -> None:
    """Render the fleet-level overview table of all detected motors."""
    st.subheader("Fleet Overview")

    if not motors:
        st.info("No active motor telemetry records discovered in the fleet.")
        return

    records = []
    for m in motors:
        records.append({
            "Device ID": m.get("device_id", "Unknown"),
            "Fault Classification": m.get("fault_type", "N/A"),
            "Health Index": f"{float(m.get('health_index', 0.0)):.2f}",
            "RUL (Hours)": f"{float(m.get('rul_hours', 0.0)):.1f}",
            "Last Telemetry (UTC)": format_iso_timestamp(m.get("timestamp")),
        })

    df = pd.DataFrame(records)
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_motor_status_metrics(motor_data: Dict[str, Any]) -> None:
    """Render current telemetry status metric cards for a selected motor."""
    st.markdown(f"### Current Telemetry: `{motor_data.get('device_id', 'Unknown')}`")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        fault_val = motor_data.get("fault_type", "N/A")
        st.metric(label="Fault Classification", value=fault_val)

    with col2:
        try:
            hi_val = f"{float(motor_data.get('health_index', 0.0)):.2f}"
        except (ValueError, TypeError):
            hi_val = "N/A"
        st.metric(label="Health Index", value=hi_val)

    with col3:
        try:
            rul_val = f"{float(motor_data.get('rul_hours', 0.0)):.1f} hrs"
        except (ValueError, TypeError):
            rul_val = "N/A"
        st.metric(label="Estimated RUL", value=rul_val)

    with col4:
        ts_val = format_iso_timestamp(motor_data.get("timestamp"))
        st.metric(label="Last Updated", value=ts_val)


def render_health_chart(observations: List[Dict[str, Any]]) -> None:
    """Render historical health index time-series degradation chart."""
    st.markdown("#### Health Index Trend")

    if not observations:
        st.info("No historical health data available for the selected time range.")
        return

    try:
        data = []
        for obs in observations:
            if "timestamp" in obs and "health_index" in obs:
                data.append({
                    "Timestamp": pd.to_datetime(obs["timestamp"]),
                    "Health Index": float(obs["health_index"]),
                })

        if not data:
            st.info("No valid health observation records found.")
            return

        df = pd.DataFrame(data).sort_values("Timestamp")
        df.set_index("Timestamp", inplace=True)
        st.line_chart(df["Health Index"], use_container_width=True)
    except Exception as exc:
        st.error(f"Unable to render health chart: {exc}")


def render_rul_chart(observations: List[Dict[str, Any]]) -> None:
    """Render historical Remaining Useful Life (RUL) time-series countdown chart."""
    st.markdown("#### Remaining Useful Life (RUL) Trend")

    if not observations:
        st.info("No historical RUL data available for the selected time range.")
        return

    try:
        data = []
        for obs in observations:
            if "timestamp" in obs and "rul_hours" in obs:
                data.append({
                    "Timestamp": pd.to_datetime(obs["timestamp"]),
                    "RUL (Hours)": float(obs["rul_hours"]),
                })

        if not data:
            st.info("No valid RUL observation records found.")
            return

        df = pd.DataFrame(data).sort_values("Timestamp")
        df.set_index("Timestamp", inplace=True)
        st.line_chart(df["RUL (Hours)"], use_container_width=True)
    except Exception as exc:
        st.error(f"Unable to render RUL chart: {exc}")


def render_fault_history(events: List[Dict[str, Any]]) -> None:
    """Render historical fault diagnostic classifications table."""
    st.markdown("#### Fault Classification History")

    if not events:
        st.info("No historical fault classification events recorded in this time range.")
        return

    try:
        records = []
        for ev in events:
            records.append({
                "Timestamp (UTC)": format_iso_timestamp(ev.get("timestamp")),
                "Fault Classification": ev.get("fault_type", "Unknown"),
            })

        df = pd.DataFrame(records)
        st.dataframe(df, use_container_width=True, hide_index=True)
    except Exception as exc:
        st.error(f"Unable to display fault history: {exc}")
